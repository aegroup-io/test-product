from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from agent_core_platform_api.models import ComponentEdge, ComponentNode, Organization, Product, RepositoryBinding

if TYPE_CHECKING:
    from agent_core_platform_api.product_contract import ComponentsManifest


GRAPH_FRESHNESS_CURRENT = "current"
GRAPH_FRESHNESS_STALE = "stale"
GRAPH_FRESHNESS_UNKNOWN = "unknown"
GRAPH_PRECEDENCE_EFFECTIVE = "effective"
GRAPH_PRECEDENCE_SHADOWED = "shadowed"
GRAPH_CONFIDENCE_CONFIRMED = "confirmed"
GRAPH_CONFIDENCE_UNCERTAIN = "uncertain"
GRAPH_CONFIDENCE_UNKNOWN = "unknown"
GRAPH_STALE_AFTER = timedelta(days=14)
GRAPH_CONFIDENCE_THRESHOLD = 0.75
GRAPH_SOURCE_PRIORITY = {
    "manual": 400,
    "declared": 300,
    "repo-metadata": 200,
    "seed": 150,
    "inferred": 100,
}


class ComponentGraphService:
    def __init__(self, session: Session):
        self.session = session

    def refresh_product_graph(
        self,
        *,
        product: Product,
        repo_binding: RepositoryBinding | None,
        components_manifest: ComponentsManifest | None,
        declared_source_ref: str | None,
        observed_at: datetime,
    ) -> None:
        nodes_by_key = {
            node.key: node
            for node in self.session.query(ComponentNode)
            .filter(ComponentNode.product_id == product.product_id)
            .all()
        }
        organization = self.session.get(Organization, product.org_id)
        owner_slug = organization.slug if organization is not None else None
        repo_source_ref = None
        if repo_binding is not None:
            repo_source_ref = f"{repo_binding.owner}/{repo_binding.name}"

        root_node = self._upsert_node(
            nodes_by_key,
            product_id=product.product_id,
            key=product.key,
            type="product",
            name=product.name,
            owner=owner_slug,
            version=product.agent_core_version,
            status=product.status,
            source_kind="repo-metadata",
            source_ref=repo_source_ref,
            confidence=0.9,
            last_verified_at=observed_at,
            freshness_status=GRAPH_FRESHNESS_CURRENT,
        )
        product.component_root_node_id = root_node.component_node_id

        repo_node: ComponentNode | None = None
        if repo_binding is not None:
            repo_node = self._upsert_node(
                nodes_by_key,
                product_id=product.product_id,
                key=self._repo_node_key(product),
                type="repository",
                name=repo_binding.name,
                owner=repo_binding.owner,
                version=repo_binding.default_branch,
                status=repo_binding.adoption_state,
                source_kind="repo-metadata",
                source_ref=repo_source_ref,
                confidence=0.6,
                last_verified_at=observed_at,
                freshness_status=GRAPH_FRESHNESS_CURRENT,
            )
            self._upsert_edge(
                from_node_id=root_node.component_node_id,
                to_node_id=repo_node.component_node_id,
                relationship_type="owns",
                source_kind="repo-metadata",
                source_ref=repo_source_ref,
                confidence=0.6,
                last_verified_at=observed_at,
                freshness_status=GRAPH_FRESHNESS_CURRENT,
            )

        declared_node_keys: set[str] = set()
        declared_edges: set[tuple[UUID, UUID, str]] = set()
        if components_manifest is not None:
            for component in components_manifest.components:
                node = self._upsert_node(
                    nodes_by_key,
                    product_id=product.product_id,
                    key=component.key,
                    type=component.type,
                    name=component.name,
                    owner=component.owner,
                    version=component.version,
                    status=component.status,
                    source_kind="declared",
                    source_ref=declared_source_ref,
                    confidence=1.0,
                    last_verified_at=observed_at,
                    freshness_status=GRAPH_FRESHNESS_CURRENT,
                )
                declared_node_keys.add(component.key)
                if component.key == product.key and component.type == "product":
                    product.component_root_node_id = node.component_node_id

            for edge in components_manifest.edges:
                from_node = nodes_by_key.get(edge.from_key)
                to_node = nodes_by_key.get(edge.to_key)
                if from_node is None or to_node is None:
                    continue
                self._upsert_edge(
                    from_node_id=from_node.component_node_id,
                    to_node_id=to_node.component_node_id,
                    relationship_type=edge.relationship,
                    source_kind="declared",
                    source_ref=declared_source_ref,
                    confidence=1.0,
                    last_verified_at=observed_at,
                    freshness_status=GRAPH_FRESHNESS_CURRENT,
                )
                declared_edges.add((from_node.component_node_id, to_node.component_node_id, edge.relationship))

        if declared_source_ref is not None:
            self._mark_missing_declared_nodes_stale(
                product_id=product.product_id,
                declared_node_keys=declared_node_keys,
            )
            self._mark_missing_declared_edges_stale(
                product_id=product.product_id,
                declared_edges=declared_edges,
            )

    def build_product_graph(self, *, product_id: UUID) -> dict[str, object]:
        product = self.session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")

        nodes = (
            self.session.query(ComponentNode)
            .filter(ComponentNode.product_id == product_id)
            .order_by(ComponentNode.key.asc())
            .all()
        )
        edges = (
            self.session.query(ComponentEdge)
            .join(ComponentEdge.from_node)
            .filter(ComponentNode.product_id == product_id)
            .options(joinedload(ComponentEdge.from_node), joinedload(ComponentEdge.to_node))
            .all()
        )
        edge_states = self._edge_precedence_states(edges)
        return {
            "product_id": product.product_id,
            "component_root_node_id": product.component_root_node_id,
            "nodes": [self._serialize_node(node) for node in nodes],
            "edges": [
                self._serialize_edge(edge, precedence_state=edge_states[edge.component_edge_id])
                for edge in sorted(
                    edges,
                    key=lambda edge: (
                        edge.from_node.key,
                        edge.to_node.key,
                        edge.relationship_type,
                        -self._source_priority(edge.source_kind),
                        edge.source_kind,
                    ),
                )
            ],
        }

    def _repo_node_key(self, product: Product) -> str:
        return f"{product.key}-repo"

    def _upsert_node(
        self,
        nodes_by_key: dict[str, ComponentNode],
        *,
        product_id: UUID,
        key: str,
        type: str,
        name: str,
        owner: str | None,
        version: str | None,
        status: str | None,
        source_kind: str,
        source_ref: str | None,
        confidence: float | None,
        last_verified_at: datetime | None,
        freshness_status: str,
    ) -> ComponentNode:
        node = nodes_by_key.get(key)
        if node is None:
            node = ComponentNode(
                product_id=product_id,
                key=key,
                type=type,
                name=name,
                owner=owner,
                version=version,
                status=status,
                source_kind=source_kind,
                source_ref=source_ref,
                confidence=confidence,
                last_verified_at=last_verified_at,
                freshness_status=freshness_status,
            )
            self.session.add(node)
            self.session.flush()
            nodes_by_key[key] = node
            return node

        if node.source_kind == "manual" and source_kind != "manual":
            return node

        node.type = type
        node.name = name
        if owner is not None or node.owner is None:
            node.owner = owner
        if version is not None or node.version is None:
            node.version = version
        if status is not None or node.status is None:
            node.status = status
        node.source_kind = source_kind
        node.source_ref = source_ref
        node.confidence = confidence
        node.last_verified_at = last_verified_at
        node.freshness_status = freshness_status
        self.session.flush()
        return node

    def _upsert_edge(
        self,
        *,
        from_node_id: UUID,
        to_node_id: UUID,
        relationship_type: str,
        source_kind: str,
        source_ref: str | None,
        confidence: float | None,
        last_verified_at: datetime | None,
        freshness_status: str,
    ) -> ComponentEdge:
        edge = (
            self.session.query(ComponentEdge)
            .filter(
                ComponentEdge.from_node_id == from_node_id,
                ComponentEdge.to_node_id == to_node_id,
                ComponentEdge.relationship_type == relationship_type,
                ComponentEdge.source_kind == source_kind,
            )
            .one_or_none()
        )
        if edge is None:
            edge = ComponentEdge(
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                relationship_type=relationship_type,
                source_kind=source_kind,
                source_ref=source_ref,
                confidence=confidence,
                last_verified_at=last_verified_at,
                freshness_status=freshness_status,
            )
            self.session.add(edge)
        else:
            edge.source_ref = source_ref
            edge.confidence = confidence
            edge.last_verified_at = last_verified_at
            edge.freshness_status = freshness_status
        self.session.flush()
        return edge

    def _mark_missing_declared_nodes_stale(
        self,
        *,
        product_id: UUID,
        declared_node_keys: set[str],
    ) -> None:
        existing_nodes = (
            self.session.query(ComponentNode)
            .filter(
                ComponentNode.product_id == product_id,
                ComponentNode.source_kind == "declared",
            )
            .all()
        )
        for node in existing_nodes:
            if node.key in declared_node_keys:
                continue
            node.freshness_status = GRAPH_FRESHNESS_STALE

    def _mark_missing_declared_edges_stale(
        self,
        *,
        product_id: UUID,
        declared_edges: set[tuple[UUID, UUID, str]],
    ) -> None:
        existing_edges = (
            self.session.query(ComponentEdge)
            .join(ComponentEdge.from_node)
            .filter(
                ComponentNode.product_id == product_id,
                ComponentEdge.source_kind == "declared",
            )
            .all()
        )
        for edge in existing_edges:
            edge_key = (edge.from_node_id, edge.to_node_id, edge.relationship_type)
            if edge_key in declared_edges:
                continue
            edge.freshness_status = GRAPH_FRESHNESS_STALE

    def _edge_precedence_states(self, edges: list[ComponentEdge]) -> dict[UUID, str]:
        grouped_edges: dict[tuple[UUID, UUID], list[ComponentEdge]] = defaultdict(list)
        for edge in edges:
            grouped_edges[(edge.from_node_id, edge.to_node_id)].append(edge)

        edge_states: dict[UUID, str] = {}
        for group in grouped_edges.values():
            current_edges = [edge for edge in group if self._freshness_status(edge) != GRAPH_FRESHNESS_STALE]
            candidates = current_edges or group
            winning_priority = max(self._source_priority(edge.source_kind) for edge in candidates)
            for edge in group:
                edge_states[edge.component_edge_id] = (
                    GRAPH_PRECEDENCE_EFFECTIVE
                    if edge in candidates and self._source_priority(edge.source_kind) == winning_priority
                    else GRAPH_PRECEDENCE_SHADOWED
                )
        return edge_states

    def _serialize_node(self, node: ComponentNode) -> dict[str, object]:
        freshness_status = self._freshness_status(node)
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
            "confidence": node.confidence,
            "confidence_status": self._confidence_status(node.confidence),
            "last_verified_at": node.last_verified_at,
            "freshness_status": freshness_status,
        }

    def _serialize_edge(self, edge: ComponentEdge, *, precedence_state: str) -> dict[str, object]:
        freshness_status = self._freshness_status(edge)
        return {
            "component_edge_id": edge.component_edge_id,
            "from_node_id": edge.from_node_id,
            "to_node_id": edge.to_node_id,
            "relationship": edge.relationship_type,
            "source_kind": edge.source_kind,
            "source_ref": edge.source_ref,
            "confidence": edge.confidence,
            "confidence_status": self._confidence_status(edge.confidence),
            "last_verified_at": edge.last_verified_at,
            "freshness_status": freshness_status,
            "precedence_state": precedence_state,
        }

    def _freshness_status(self, record: ComponentNode | ComponentEdge) -> str:
        freshness_status = (record.freshness_status or GRAPH_FRESHNESS_UNKNOWN).strip().lower()
        if freshness_status == GRAPH_FRESHNESS_STALE:
            return GRAPH_FRESHNESS_STALE
        if record.last_verified_at is None:
            return GRAPH_FRESHNESS_UNKNOWN
        verified_at = record.last_verified_at
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - verified_at > GRAPH_STALE_AFTER:
            return GRAPH_FRESHNESS_STALE
        return GRAPH_FRESHNESS_CURRENT

    def _confidence_status(self, confidence: float | None) -> str:
        if confidence is None:
            return GRAPH_CONFIDENCE_UNKNOWN
        if confidence < GRAPH_CONFIDENCE_THRESHOLD:
            return GRAPH_CONFIDENCE_UNCERTAIN
        return GRAPH_CONFIDENCE_CONFIRMED

    def _source_priority(self, source_kind: str) -> int:
        return GRAPH_SOURCE_PRIORITY.get(source_kind, 0)
