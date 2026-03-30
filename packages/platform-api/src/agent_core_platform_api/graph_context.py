from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from agent_core_platform_api.models import (
    ComponentEdge,
    ComponentNode,
    OperationalSignal,
    OrchestrationLane,
    Product,
    PullRequestMirror,
    RepositoryBinding,
    WorkItem,
)


DEFAULT_SLICE_DEPTH = 3
FRESHNESS_WINDOW = timedelta(hours=24)
HOTSPOT_THRESHOLD = 2
ACTIVE_LANE_STATES = frozenset({"Queued", "Claimed", "Provisioning", "Running", "AwaitingApproval", "AwaitingGitHub", "RetryPending"})
TERMINAL_WORK_ITEM_STATUSES = frozenset({"done", "closed", "completed", "cancelled"})
OPEN_PULL_REQUEST_STATES = frozenset({"open"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _freshness(observed_at: datetime | None, *, as_of: datetime) -> dict[str, Any]:
    normalized = _ensure_utc(observed_at)
    if normalized is None:
        return {
            "observed_at": None,
            "status": "unknown",
            "stale_after_seconds": int(FRESHNESS_WINDOW.total_seconds()),
        }
    status = "fresh" if as_of - normalized <= FRESHNESS_WINDOW else "stale"
    return {
        "observed_at": normalized,
        "status": status,
        "stale_after_seconds": int(FRESHNESS_WINDOW.total_seconds()),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        normalized = _ensure_utc(value)
        return normalized.isoformat() if normalized is not None else None
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _json_string_match(column, key: str, value: str):
    serialized = cast(column, String)
    return or_(
        serialized.like(f'%"{key}": "{value}"%'),
        serialized.like(f'%"{key}":"{value}"%'),
    )


def _normalize_status(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_active_work_item(status: str | None) -> bool:
    normalized = _normalize_status(status)
    return bool(normalized) and normalized not in TERMINAL_WORK_ITEM_STATUSES


def _is_blocking_work_item(status: str | None) -> bool:
    normalized = _normalize_status(status)
    return normalized in {"blocked", "waiting", "dependencyblocked"}


def _signal_kind_bucket(signal: OperationalSignal) -> str:
    signal_type = signal.signal_type.lower()
    if "incident" in signal_type:
        return "incident"
    if "deployment" in signal_type or "environment" in signal_type or "runtime" in signal_type:
        return "runtime"
    if "lane.assignment" in signal_type or "lane_assignment" in signal_type:
        return "lane_assignment"
    return "signal"


def _extract_lane_ids(value: Any) -> set[str]:
    lane_ids: set[str] = set()
    if isinstance(value, dict):
        for key in ("lane_id", "laneId"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                lane_ids.add(candidate.strip())
        nested = value.get("lane_ids")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, str) and item.strip():
                    lane_ids.add(item.strip())
    return lane_ids


def _extract_work_item_ids(value: Any) -> set[str]:
    work_item_ids: set[str] = set()
    if isinstance(value, dict):
        for key in ("work_item_id", "workItemId"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                work_item_ids.add(candidate.strip())
        nested = value.get("work_item_ids")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, str) and item.strip():
                    work_item_ids.add(item.strip())
    return work_item_ids


class GraphContextService:
    def __init__(self, session: Session):
        self.session = session

    def build_product_slice(
        self,
        product_id,
        *,
        depth: int = DEFAULT_SLICE_DEPTH,
        component_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        product = self.session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")

        anchors = self._product_anchor_ids(product=product, component_keys=component_keys)
        if component_keys and not anchors:
            raise ValueError("Requested component keys were not found for the product.")
        return self._build_slice(
            scope="product",
            product=product,
            lane=None,
            anchor_ids=anchors,
            depth=depth,
        )

    def build_lane_slice(self, lane_id, *, depth: int = DEFAULT_SLICE_DEPTH) -> dict[str, Any]:
        lane = self.session.get(OrchestrationLane, lane_id)
        if lane is None:
            raise ValueError(f"Lane not found: {lane_id}")
        if lane.product is None or lane.repo is None or lane.work_item is None:
            raise ValueError("Lane is missing product, repository, or work-item context.")

        anchors = self._lane_anchor_ids(lane)
        return self._build_slice(
            scope="lane",
            product=lane.product,
            lane=lane,
            anchor_ids=anchors,
            depth=depth,
        )

    def build_lane_prompt_context(self, lane_id, *, depth: int = DEFAULT_SLICE_DEPTH) -> dict[str, Any]:
        graph_slice = self.build_lane_slice(lane_id, depth=depth)
        compact_nodes = [
            {
                "component_node_id": node["component_node_id"],
                "product_id": node["product_id"],
                "type": node["type"],
                "key": node["key"],
                "name": node["name"],
                "version": node["version"],
                "status": node["status"],
                "distance": node["distance"],
                "freshness": node["freshness"],
                "incident_count": len(node["overlay"]["incidents"]),
                "active_lane_count": len(node["overlay"]["active_lanes"]),
                "active_work_item_count": len(node["overlay"]["active_work_items"]),
                "open_pull_request_count": len(node["overlay"]["open_pull_requests"]),
                "hotspot_score": node["overlay"]["hotspot_score"],
            }
            for node in graph_slice["nodes"][:8]
        ]
        return _json_safe(
            {
                "scope": graph_slice["scope"],
                "product_id": graph_slice["product_id"],
                "lane_id": graph_slice["lane_id"],
                "generated_at": graph_slice["generated_at"],
                "freshness": graph_slice["freshness"],
                "anchor_node_ids": graph_slice["anchor_node_ids"],
                "nodes": compact_nodes,
                "blocked_dependencies": graph_slice["blocked_dependencies"][:6],
                "hotspots": graph_slice["hotspots"][:6],
            }
        )

    def _product_anchor_ids(self, *, product: Product, component_keys: list[str] | None) -> list[UUID]:
        if component_keys:
            nodes = (
                self.session.query(ComponentNode)
                .filter(
                    ComponentNode.product_id == product.product_id,
                    ComponentNode.key.in_(sorted(set(component_keys))),
                )
                .all()
            )
            return [node.component_node_id for node in nodes]

        anchors: list[UUID] = []
        if product.component_root_node_id is not None:
            anchors.append(product.component_root_node_id)

        repository_nodes = (
            self.session.query(ComponentNode)
            .filter(
                ComponentNode.product_id == product.product_id,
                ComponentNode.type == "repository",
            )
            .order_by(ComponentNode.key.asc())
            .all()
        )
        for node in repository_nodes:
            if node.component_node_id not in anchors:
                anchors.append(node.component_node_id)
        return anchors

    def _lane_anchor_ids(self, lane: OrchestrationLane) -> list[UUID]:
        anchors = self._product_anchor_ids(product=lane.product, component_keys=None)
        lane_id = str(lane.lane_id)
        work_item_id = str(lane.work_item_id)
        lane_signal_nodes = (
            self.session.query(OperationalSignal)
            .filter(
                OperationalSignal.target_kind == "component_node",
                OperationalSignal.value.is_not(None),
                or_(
                    _json_string_match(OperationalSignal.value, "lane_id", lane_id),
                    _json_string_match(OperationalSignal.value, "laneId", lane_id),
                    _json_string_match(OperationalSignal.value, "work_item_id", work_item_id),
                    _json_string_match(OperationalSignal.value, "workItemId", work_item_id),
                ),
            )
            .order_by(OperationalSignal.observed_at.desc())
            .all()
        )
        for signal in lane_signal_nodes:
            if not isinstance(signal.value, dict):
                continue
            signal_lane_ids = _extract_lane_ids(signal.value)
            signal_work_item_ids = _extract_work_item_ids(signal.value)
            if lane_id in signal_lane_ids or work_item_id in signal_work_item_ids:
                try:
                    node_id = UUID(signal.target_id)
                except ValueError:
                    continue
                if node_id not in anchors:
                    anchors.append(node_id)
        return anchors

    def _build_slice(
        self,
        *,
        scope: str,
        product: Product,
        lane: OrchestrationLane | None,
        anchor_ids: list[UUID],
        depth: int,
    ) -> dict[str, Any]:
        generated_at = _now()
        nodes, edges, distance_by_node = self._walk_graph(anchor_ids=anchor_ids, depth=max(depth, 0))
        node_ids = [node.component_node_id for node in nodes]
        edge_ids = [edge.component_edge_id for edge in edges]

        signals = self._load_signals(node_ids=node_ids, edge_ids=edge_ids, product=product)
        repositories = self._load_repositories(nodes=nodes, product=product)
        work_items = self._load_work_items(repositories)
        pull_requests = self._load_pull_requests(repositories)
        lanes = self._load_lanes(product=product, repositories=repositories)

        node_payloads: dict[UUID, dict[str, Any]] = {}
        blocked_counts: defaultdict[UUID, int] = defaultdict(int)
        for node in sorted(nodes, key=lambda item: (distance_by_node.get(item.component_node_id, 0), item.key)):
            payload = self._build_node_payload(
                node=node,
                product=product,
                distance=distance_by_node.get(node.component_node_id, 0),
                signals=signals,
                repositories=repositories,
                work_items=work_items,
                pull_requests=pull_requests,
                lanes=lanes,
                generated_at=generated_at,
            )
            node_payloads[node.component_node_id] = payload

        blocked_dependencies: list[dict[str, Any]] = []
        edge_payloads: list[dict[str, Any]] = []
        for edge in sorted(edges, key=lambda item: (distance_by_node.get(item.from_node_id, 0), str(item.relationship_type))):
            edge_payload, blocked_dependency = self._build_edge_payload(
                edge=edge,
                node_payloads=node_payloads,
                signals=signals,
                generated_at=generated_at,
            )
            edge_payloads.append(edge_payload)
            if blocked_dependency is not None:
                blocked_dependencies.append(blocked_dependency)
                blocked_counts[edge.from_node_id] += 1

        for node_id, count in blocked_counts.items():
            node_payloads[node_id]["overlay"]["blocked_dependency_count"] = count

        hotspots = [
            {
                "component_node_id": payload["component_node_id"],
                "product_id": payload["product_id"],
                "key": payload["key"],
                "name": payload["name"],
                "type": payload["type"],
                "hotspot_score": payload["overlay"]["hotspot_score"],
                "active_lane_count": len(payload["overlay"]["active_lanes"]),
                "active_work_item_count": len(payload["overlay"]["active_work_items"]),
                "observed_at": payload["freshness"]["observed_at"],
            }
            for payload in node_payloads.values()
            if payload["overlay"]["hotspot_score"] >= HOTSPOT_THRESHOLD
        ]
        hotspots.sort(key=lambda item: (-item["hotspot_score"], item["key"]))

        node_values = list(node_payloads.values())
        slice_freshness = self._slice_freshness(node_values=node_values, blocked_dependencies=blocked_dependencies, as_of=generated_at)
        return {
            "scope": scope,
            "product_id": product.product_id,
            "lane_id": lane.lane_id if lane is not None else None,
            "generated_at": generated_at,
            "freshness": slice_freshness,
            "anchor_node_ids": anchor_ids,
            "depth": depth,
            "nodes": node_values,
            "edges": edge_payloads,
            "blocked_dependencies": blocked_dependencies,
            "hotspots": hotspots,
        }

    def _walk_graph(self, *, anchor_ids: list[UUID], depth: int) -> tuple[list[ComponentNode], list[ComponentEdge], dict[UUID, int]]:
        if not anchor_ids:
            return [], [], {}

        visited = set(anchor_ids)
        frontier = set(anchor_ids)
        distance_by_node = {node_id: 0 for node_id in anchor_ids}
        edge_map: dict[UUID, ComponentEdge] = {}

        for level in range(depth):
            if not frontier:
                break
            frontier_ids = list(frontier)
            level_edges = (
                self.session.query(ComponentEdge)
                .filter(
                    or_(
                        ComponentEdge.from_node_id.in_(frontier_ids),
                        ComponentEdge.to_node_id.in_(frontier_ids),
                    )
                )
                .all()
            )
            next_frontier: set[UUID] = set()
            for edge in level_edges:
                edge_map[edge.component_edge_id] = edge
                for neighbor in (edge.from_node_id, edge.to_node_id):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
                        distance_by_node[neighbor] = level + 1
            frontier = next_frontier

        nodes = (
            self.session.query(ComponentNode)
            .filter(ComponentNode.component_node_id.in_(sorted(visited, key=str)))
            .all()
        )
        return nodes, list(edge_map.values()), distance_by_node

    def _load_signals(self, *, node_ids: list[UUID], edge_ids: list[UUID], product: Product) -> dict[str, dict[str, list[OperationalSignal]]]:
        node_signal_rows = (
            self.session.query(OperationalSignal)
            .filter(
                OperationalSignal.target_kind == "component_node",
                OperationalSignal.target_id.in_([str(node_id) for node_id in node_ids] or [""]),
            )
            .order_by(OperationalSignal.observed_at.desc())
            .all()
        )
        edge_signal_rows = (
            self.session.query(OperationalSignal)
            .filter(
                OperationalSignal.target_kind == "component_edge",
                OperationalSignal.target_id.in_([str(edge_id) for edge_id in edge_ids] or [""]),
            )
            .order_by(OperationalSignal.observed_at.desc())
            .all()
        )
        product_signal_rows = (
            self.session.query(OperationalSignal)
            .filter(
                OperationalSignal.target_kind == "product",
                OperationalSignal.target_id == str(product.product_id),
            )
            .order_by(OperationalSignal.observed_at.desc())
            .all()
        )
        return {
            "component_node": self._bucket_signals(node_signal_rows),
            "component_edge": self._bucket_signals(edge_signal_rows),
            "product": self._bucket_signals(product_signal_rows),
        }

    def _bucket_signals(self, rows: list[OperationalSignal]) -> dict[str, list[OperationalSignal]]:
        grouped: dict[str, list[OperationalSignal]] = defaultdict(list)
        for row in rows:
            grouped[row.target_id].append(row)
        return grouped

    def _load_repositories(self, nodes: list[ComponentNode], product: Product) -> dict[UUID, RepositoryBinding]:
        repository_nodes = [node for node in nodes if node.type == "repository"]
        if not repository_nodes:
            return {}
        repository_rows = (
            self.session.query(RepositoryBinding)
            .filter(RepositoryBinding.product_id == product.product_id)
            .all()
        )
        repository_by_identity = {
            (row.owner.lower(), row.name.lower()): row
            for row in repository_rows
        }
        mapping: dict[UUID, RepositoryBinding] = {}
        for node in repository_nodes:
            owner = (node.owner or "").lower()
            name = node.name.lower()
            repository = repository_by_identity.get((owner, name))
            if repository is not None:
                mapping[node.component_node_id] = repository
        return mapping

    def _load_work_items(self, repositories: dict[UUID, RepositoryBinding]) -> dict[UUID, list[WorkItem]]:
        repo_ids = [repository.repo_id for repository in repositories.values()]
        if not repo_ids:
            return {}
        rows = (
            self.session.query(WorkItem)
            .filter(WorkItem.repo_id.in_(repo_ids))
            .order_by(WorkItem.updated_at.desc(), WorkItem.issue_number.desc())
            .all()
        )
        grouped: dict[UUID, list[WorkItem]] = defaultdict(list)
        for row in rows:
            if _is_active_work_item(row.status):
                grouped[row.repo_id].append(row)
        return grouped

    def _load_pull_requests(self, repositories: dict[UUID, RepositoryBinding]) -> dict[UUID, list[PullRequestMirror]]:
        repo_ids = [repository.repo_id for repository in repositories.values()]
        if not repo_ids:
            return {}
        rows = (
            self.session.query(PullRequestMirror)
            .filter(PullRequestMirror.repo_id.in_(repo_ids))
            .order_by(PullRequestMirror.updated_at.desc(), PullRequestMirror.number.desc())
            .all()
        )
        grouped: dict[UUID, list[PullRequestMirror]] = defaultdict(list)
        for row in rows:
            if _normalize_status(row.state) in OPEN_PULL_REQUEST_STATES:
                grouped[row.repo_id].append(row)
        return grouped

    def _load_lanes(self, *, product: Product, repositories: dict[UUID, RepositoryBinding]) -> dict[str, Any]:
        repo_ids = [repository.repo_id for repository in repositories.values()]
        filters = [OrchestrationLane.product_id == product.product_id]
        if repo_ids:
            filters.append(OrchestrationLane.repo_id.in_(repo_ids))
        rows = (
            self.session.query(OrchestrationLane)
            .filter(*filters)
            .order_by(OrchestrationLane.updated_at.desc())
            .all()
        )
        product_lanes: list[OrchestrationLane] = []
        repo_lanes: dict[UUID, list[OrchestrationLane]] = defaultdict(list)
        for row in rows:
            if row.state not in ACTIVE_LANE_STATES:
                continue
            product_lanes.append(row)
            repo_lanes[row.repo_id].append(row)
        return {
            "product": product_lanes,
            "by_repo_id": repo_lanes,
            "by_lane_id": {str(row.lane_id): row for row in product_lanes},
        }

    def _build_node_payload(
        self,
        *,
        node: ComponentNode,
        product: Product,
        distance: int,
        signals: dict[str, dict[str, list[OperationalSignal]]],
        repositories: dict[UUID, RepositoryBinding],
        work_items: dict[UUID, list[WorkItem]],
        pull_requests: dict[UUID, list[PullRequestMirror]],
        lanes: dict[str, list[OrchestrationLane]],
        generated_at: datetime,
    ) -> dict[str, Any]:
        direct_signals = list(signals["component_node"].get(str(node.component_node_id), []))
        if node.component_node_id == product.component_root_node_id:
            direct_signals.extend(signals["product"].get(str(product.product_id), []))

        lane_ids_from_signals: set[str] = set()
        for signal in direct_signals:
            lane_ids_from_signals.update(_extract_lane_ids(signal.value))

        active_work_items: list[dict[str, Any]] = []
        open_pull_requests: list[dict[str, Any]] = []
        active_lane_rows: list[OrchestrationLane] = []
        active_lane_ids: set[str] = set()

        def add_lane_rows(rows: list[OrchestrationLane]) -> None:
            for row in rows:
                lane_id = str(row.lane_id)
                if lane_id in active_lane_ids:
                    continue
                active_lane_ids.add(lane_id)
                active_lane_rows.append(row)

        if node.type == "product":
            product_repo_ids = {repository.repo_id for repository in repositories.values()}
            for repo_id in sorted(product_repo_ids, key=str):
                active_work_items.extend(self._work_item_refs(work_items.get(repo_id, [])))
                open_pull_requests.extend(self._pull_request_refs(pull_requests.get(repo_id, [])))
            add_lane_rows(lanes.get("product", []))
        elif node.component_node_id in repositories:
            repository = repositories[node.component_node_id]
            active_work_items.extend(self._work_item_refs(work_items.get(repository.repo_id, [])))
            open_pull_requests.extend(self._pull_request_refs(pull_requests.get(repository.repo_id, [])))
            add_lane_rows(lanes.get("by_repo_id", {}).get(repository.repo_id, []))

        incidents = [self._signal_ref(signal) for signal in direct_signals if _signal_kind_bucket(signal) == "incident"]
        direct_signal_refs = [
            self._signal_ref(signal)
            for signal in direct_signals
            if _signal_kind_bucket(signal) not in {"incident", "lane_assignment"}
        ]
        lane_by_id = lanes.get("by_lane_id", {})
        for lane_id in sorted(lane_ids_from_signals):
            lane_row = lane_by_id.get(lane_id)
            if lane_row is not None:
                add_lane_rows([lane_row])

        active_lanes = self._lane_refs(active_lane_rows)

        hotspot_score = max(len(active_lanes), len(lane_ids_from_signals), len(active_work_items))
        freshness_observed_at = max(
            [timestamp for timestamp in [
                _ensure_utc(node.updated_at),
                *(item["updated_at"] for item in active_work_items),
                *(item["updated_at"] for item in open_pull_requests),
                *(item["updated_at"] for item in active_lanes),
                *(signal["observed_at"] for signal in incidents),
                *(signal["observed_at"] for signal in direct_signal_refs),
            ] if timestamp is not None],
            default=None,
        )

        return {
            "component_node_id": node.component_node_id,
            "product_id": node.product_id,
            "type": node.type,
            "key": node.key,
            "name": node.name,
            "owner": node.owner,
            "version": node.version,
            "status": node.status,
            "source_kind": node.source_kind,
            "source_ref": node.source_ref,
            "distance": distance,
            "freshness": _freshness(freshness_observed_at, as_of=generated_at),
            "overlay": {
                "active_work_items": active_work_items[:5],
                "open_pull_requests": open_pull_requests[:5],
                "active_lanes": active_lanes[:5],
                "incidents": incidents[:5],
                "signals": direct_signal_refs[:5],
                "hotspot_score": hotspot_score,
                "blocked_dependency_count": 0,
            },
        }

    def _build_edge_payload(
        self,
        *,
        edge: ComponentEdge,
        node_payloads: dict[UUID, dict[str, Any]],
        signals: dict[str, dict[str, list[OperationalSignal]]],
        generated_at: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        edge_signals = signals["component_edge"].get(str(edge.component_edge_id), [])
        from_node = node_payloads[edge.from_node_id]
        to_node = node_payloads[edge.to_node_id]

        block_reason = None
        block_observed_at = None
        if to_node["overlay"]["incidents"]:
            block_reason = "incident"
            block_observed_at = to_node["overlay"]["incidents"][0]["observed_at"]
        elif any(_is_blocking_work_item(item["status"]) for item in to_node["overlay"]["active_work_items"]):
            block_reason = "blocked_work_items"
            block_observed_at = max(
                (item["updated_at"] for item in to_node["overlay"]["active_work_items"]),
                default=None,
            )

        edge_freshness_at = max(
            [timestamp for timestamp in [
                _ensure_utc(edge.updated_at),
                _ensure_utc(edge.last_verified_at),
                *(_ensure_utc(signal.observed_at) for signal in edge_signals),
                block_observed_at,
            ] if timestamp is not None],
            default=None,
        )
        edge_payload = {
            "component_edge_id": edge.component_edge_id,
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "relationship_type": edge.relationship_type,
            "source_kind": edge.source_kind,
            "confidence": edge.confidence,
            "last_verified_at": _ensure_utc(edge.last_verified_at),
            "freshness": _freshness(edge_freshness_at, as_of=generated_at),
            "blocked": block_reason is not None,
        }

        blocked_dependency = None
        if block_reason is not None:
            blocked_dependency = {
                "component_edge_id": edge.component_edge_id,
                "from_node_id": edge.from_node_id,
                "from_key": from_node["key"],
                "to_node_id": edge.to_node_id,
                "to_key": to_node["key"],
                "relationship_type": edge.relationship_type,
                "reason": block_reason,
                "cross_product": from_node["product_id"] != to_node["product_id"],
                "observed_at": block_observed_at,
            }
        return edge_payload, blocked_dependency

    def _slice_freshness(
        self,
        *,
        node_values: list[dict[str, Any]],
        blocked_dependencies: list[dict[str, Any]],
        as_of: datetime,
    ) -> dict[str, Any]:
        observed_values = [
            value["freshness"]["observed_at"]
            for value in node_values
            if value["freshness"]["observed_at"] is not None
        ]
        observed_values.extend(
            item["observed_at"]
            for item in blocked_dependencies
            if item["observed_at"] is not None
        )
        observed_at = max(observed_values, default=None)
        if any(value["freshness"]["status"] == "stale" for value in node_values):
            status = "stale"
        elif observed_at is not None:
            status = "fresh"
        else:
            status = "unknown"
        return {
            "observed_at": observed_at,
            "status": status,
            "stale_after_seconds": int(FRESHNESS_WINDOW.total_seconds()),
        }

    def _signal_ref(self, signal: OperationalSignal) -> dict[str, Any]:
        return {
            "signal_id": signal.signal_id,
            "signal_type": signal.signal_type,
            "severity": signal.severity,
            "value": signal.value,
            "observed_at": _ensure_utc(signal.observed_at),
            "source_kind": signal.source_kind,
        }

    def _work_item_refs(self, rows: list[WorkItem]) -> list[dict[str, Any]]:
        return [
            {
                "work_item_id": row.work_item_id,
                "issue_number": row.issue_number,
                "title": row.title,
                "status": row.status,
                "dependency_state": row.dependency_state,
                "updated_at": _ensure_utc(row.updated_at),
            }
            for row in rows
        ]

    def _pull_request_refs(self, rows: list[PullRequestMirror]) -> list[dict[str, Any]]:
        return [
            {
                "pull_request_id": row.pull_request_id,
                "number": row.number,
                "title": row.title,
                "state": row.state,
                "review_state": row.review_state,
                "updated_at": _ensure_utc(row.updated_at),
            }
            for row in rows
        ]

    def _lane_refs(self, rows: list[OrchestrationLane]) -> list[dict[str, Any]]:
        return [
            {
                "lane_id": row.lane_id,
                "work_item_id": row.work_item_id,
                "state": row.state,
                "attempt": row.attempt,
                "updated_at": _ensure_utc(row.updated_at),
            }
            for row in rows
        ]
