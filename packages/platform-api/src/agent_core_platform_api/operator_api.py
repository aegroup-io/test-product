from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import quote
from zipfile import ZipFile

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from agent_core_platform_api.execution_runtime import ExecutionEnvironmentService, LaneProvisioningError
from agent_core_platform_api.github_integration import (
    DEFAULT_GITHUB_API_BASE_URL,
    GITHUB_ACCEPT_HEADER,
    GitHubAppConfigError,
    GitHubPATAuthService,
)
from agent_core_platform_api.github_mirror import GitHubMirrorService
from agent_core_platform_api.governance import build_write_audit
from agent_core_platform_api.models import (
    AgentSession,
    AgentSessionEvent,
    GitHubProjectMirror,
    GitHubProjectItemMirror,
    ManagedAsset,
    OperationalSignal,
    OrchestrationLane,
    Product,
    PullRequestMirror,
    RepositoryBinding,
    WorkItem,
)
from agent_core_platform_api.observability import lane_signal_correlation, product_signal_correlation, signal_value_with_correlation
from agent_core_platform_api.product_adoption import ProductAdoptionConflictError, ProductAdoptionService
from agent_core_platform_api.product_contract import ProductContractService
from agent_core_platform_api.scheduler import ACTIVE_LANE_OWNERSHIP_STATES, SchedulerService
from agent_core_platform_api.schemas import (
    BaselineResponse,
    BaselineUpgradeRunSummaryResponse,
    ExecutionEnvironmentSummaryResponse,
    ProductDeliveryCockpitResponse,
    ProductDeliveryProjectSummaryResponse,
    ProductDeliveryPullRequestSummaryResponse,
    ProductDeliveryWorkItemSummaryResponse,
    ProductDeliveryWorkPressureResponse,
    GitHubProjectMirrorSummaryResponse,
    LaneAgentSessionSummaryResponse,
    LaneResponse,
    LaneWorkItemSummaryResponse,
    ProductAdoptionRequest,
    ProductResponse,
    ProductSeedJobSummaryResponse,
    ProductSummaryResponse,
    RepositoryBindingSummaryResponse,
)
from agent_core_platform_api.work_item_normalization import WorkItemNormalizationService


TERMINAL_RETRYABLE_LANE_STATES = frozenset({"Cancelled", "FailedTerminal", "HandedOff"})
NON_CANCELABLE_LANE_STATES = frozenset({"Cancelled", "FailedTerminal", "HandedOff"})
DRIFTING_MANAGED_ASSET_STATES = frozenset({"conflict", "missing-advisory", "missing-local", "missing-managed", "missing-required", "update-available"})
ADVISORY_MANAGED_ASSET_STATES = frozenset({"advisory-drift", "advisory-reviewed", "deferred"})
DELIVERY_WORK_ITEM_LIMIT = 6
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _GitHubRepositorySnapshot:
    def __init__(self, session: Session, repository: RepositoryBinding):
        self.session = session
        self.repository = repository
        self._temp_dir: TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        self._temp_dir = TemporaryDirectory()
        destination = Path(self._temp_dir.name).resolve()
        self._download_archive(destination)
        return destination

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def _download_archive(self, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        token, api_base_url = self._load_repository_auth()
        response = httpx.get(
            f"{api_base_url.rstrip('/')}/repos/{self.repository.owner}/{self.repository.name}/zipball/{quote(self.repository.default_branch, safe='')}",
            headers=self._headers(token),
            timeout=60,
            follow_redirects=True,
        )
        if response.status_code >= 400:
            detail = response.text.strip() or f"GitHub request failed with status {response.status_code}."
            raise OperatorAPIValidationError(
                f"Unable to download repository snapshot for {self.repository.owner}/{self.repository.name}: {detail}"
            )
        self._extract_zip_archive(response.content, destination)

    def _load_repository_auth(self) -> tuple[str | None, str]:
        try:
            token, api_base_url, _ = GitHubPATAuthService(self.session).load_repository_token(
                owner=self.repository.owner,
                repo=self.repository.name,
            )
            return token, api_base_url
        except GitHubAppConfigError:
            if self.repository.visibility.lower() == "public":
                return None, DEFAULT_GITHUB_API_BASE_URL
            raise

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {
            "Accept": GITHUB_ACCEPT_HEADER,
        }
        if isinstance(token, str) and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    def _extract_zip_archive(self, archive_bytes: bytes, destination: Path) -> None:
        with ZipFile(io.BytesIO(archive_bytes)) as archive:
            infos = [info for info in archive.infolist() if info.filename]
            if not infos:
                raise OperatorAPIValidationError(
                    f"GitHub repository snapshot for {self.repository.owner}/{self.repository.name} was empty."
                )
            root_prefix = infos[0].filename.split("/", 1)[0]
            for info in infos:
                parts = [part for part in Path(info.filename).parts if part not in {"", "."}]
                if parts and parts[0] == root_prefix:
                    parts = parts[1:]
                if not parts:
                    continue
                target = destination.joinpath(*parts)
                resolved_target = target.resolve()
                if not resolved_target.is_relative_to(destination):
                    raise OperatorAPIValidationError("GitHub repository snapshot contained an invalid archive path.")
                if info.is_dir():
                    resolved_target.mkdir(parents=True, exist_ok=True)
                    continue
                resolved_target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, resolved_target.open("wb") as handle:
                    handle.write(source.read())


class OperatorAPIConflictError(ValueError):
    """Raised when an operator action conflicts with current durable state."""


class OperatorAPIValidationError(ValueError):
    """Raised when an operator action is invalid but the target exists."""


class OperatorAPIService:
    def __init__(self, session: Session):
        self.session = session

    def list_products(self, *, org_id=None, status: str | None = None) -> list[ProductSummaryResponse]:
        query = self._product_query()
        if org_id is not None:
            query = query.filter(Product.org_id == org_id)
        if status:
            query = query.filter(Product.status == status)
        products = query.order_by(Product.key.asc()).all()
        return [self._serialize_product(product) for product in products]

    def get_product(self, product_id) -> ProductSummaryResponse:
        product = self._product_query().filter(Product.product_id == product_id).one_or_none()
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        return self._serialize_product(product)

    def create_product(self, payload: ProductAdoptionRequest) -> ProductSummaryResponse:
        result = ProductAdoptionService(self.session).adopt_product(payload, dry_run=False)
        return ProductSummaryResponse.model_validate(result.product.model_dump(mode="python"))

    def pause_product(self, product_id, *, actor_id: str, reason: str) -> ProductSummaryResponse:
        product = self._require_product(product_id)
        if product.status == "Paused":
            raise OperatorAPIConflictError("Product is already paused.")
        if product.status == "Archived":
            raise OperatorAPIConflictError("Archived products cannot be paused.")
        product.status = "Paused"
        self._record_action(
            target_kind="product",
            target_id=str(product.product_id),
            signal_type="operator.product.pause",
            actor_id=actor_id,
            reason=reason,
            payload={"status": product.status},
            correlation=product_signal_correlation(product),
        )
        self.session.flush()
        return self._serialize_product(product)

    def resume_product(self, product_id, *, actor_id: str, reason: str) -> ProductSummaryResponse:
        product = self._require_product(product_id)
        if product.status != "Paused":
            raise OperatorAPIConflictError("Only paused products can be resumed.")
        if product.setup_state == "setup-needed":
            raise OperatorAPIValidationError("Product cannot be resumed while setup blockers remain.")
        product.status = "Active"
        self._record_action(
            target_kind="product",
            target_id=str(product.product_id),
            signal_type="operator.product.resume",
            actor_id=actor_id,
            reason=reason,
            payload={"status": product.status},
            correlation=product_signal_correlation(product),
        )
        self.session.flush()
        return self._serialize_product(product)

    def refresh_product(
        self,
        product_id,
        *,
        actor_id: str,
        reason: str,
        repo_root: str | None,
        operator_overrides: dict[str, Any] | None = None,
    ) -> ProductSummaryResponse:
        product = self._require_product(product_id)
        repository = self._resolve_primary_repo(product)
        normalized_repo_root = (repo_root or "").strip()
        if normalized_repo_root:
            repo_path = Path(normalized_repo_root).expanduser().resolve()
            if not repo_path.exists() or not repo_path.is_dir():
                raise OperatorAPIValidationError(f"Repository root does not exist or is not a directory: {repo_path}")
            ProductContractService(self.session).refresh_product_contract(
                product_id=product.product_id,
                repo_root=repo_path,
                operator_overrides=operator_overrides or {},
            )
            payload: dict[str, Any] = {"repo_root": str(repo_path), "setup_state": product.setup_state}
        else:
            with self._materialize_product_repo_snapshot(product) as repo_path:
                ProductContractService(self.session).refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_path,
                    operator_overrides=operator_overrides or {},
                )
            payload = {
                "repo_source": "github_snapshot",
                "owner": repository.owner if repository is not None else None,
                "repo": repository.name if repository is not None else None,
                "setup_state": product.setup_state,
            }
        WorkItemNormalizationService(self.session).clear_runtime_repairs_for_product(product.product_id)
        self._record_action(
            target_kind="product",
            target_id=str(product.product_id),
            signal_type="operator.product.refresh",
            actor_id=actor_id,
            reason=reason,
            payload=payload,
            correlation=product_signal_correlation(product),
        )
        self.session.flush()
        return self._serialize_product(product)

    def _materialize_product_repo_snapshot(self, product: Product):
        repository = self._resolve_primary_repo(product)
        if repository is None:
            raise OperatorAPIValidationError(
                "Refresh contract requires either a local repository root or a bound GitHub repository."
            )
        return _GitHubRepositorySnapshot(self.session, repository)

    def refresh_product_mirror(
        self,
        product_id,
        *,
        actor_id: str,
        reason: str,
    ) -> ProductSummaryResponse:
        product = self._require_product(product_id)
        result = GitHubMirrorService(self.session).refresh_product_mirror(
            product_id=product.product_id,
            ensure_webhook=True,
        )
        WorkItemNormalizationService(self.session).clear_runtime_repairs_for_product(product.product_id)
        self._record_action(
            target_kind="product",
            target_id=str(product.product_id),
            signal_type="operator.product.refresh_mirror",
            actor_id=actor_id,
            reason=reason,
            payload={
                "issue_count": result.issue_count,
                "project_item_count": result.project_item_count,
                "webhook_status": result.webhook_status,
                "webhook_delivery_url": result.webhook_delivery_url,
                "diagnostics": [item.model_dump() for item in result.diagnostics],
            },
            correlation=product_signal_correlation(product),
        )
        self.session.flush()
        return self._serialize_product(product)

    def list_lanes(self, *, product_id=None, status: str | None = None) -> list[LaneResponse]:
        query = self._lane_query()
        if product_id is not None:
            query = query.filter(OrchestrationLane.product_id == product_id)
        if status:
            query = query.filter(OrchestrationLane.state == status)
        lanes = query.order_by(OrchestrationLane.updated_at.desc(), OrchestrationLane.created_at.desc()).all()
        return [self._serialize_lane(lane) for lane in lanes]

    def get_lane(self, lane_id) -> LaneResponse:
        lane = self._lane_query().filter(OrchestrationLane.lane_id == lane_id).one_or_none()
        if lane is None:
            raise ValueError(f"Lane not found: {lane_id}")
        return self._serialize_lane(lane)

    def retry_lane(self, lane_id, *, actor_id: str, reason: str) -> LaneResponse:
        lane = self._require_lane(lane_id)
        if lane.state not in TERMINAL_RETRYABLE_LANE_STATES:
            raise OperatorAPIConflictError(f"Lane is not retryable from state: {lane.state}")
        if self._has_other_active_lane(lane):
            raise OperatorAPIConflictError("Another active lane already exists for this work item.")

        created_at = _now()
        retried_lane = OrchestrationLane(
            product_id=lane.product_id,
            repo_id=lane.repo_id,
            work_item_id=lane.work_item_id,
            attempt=self._next_attempt(lane.work_item_id),
            state="Queued",
            branch_name=f"orcha/issue-{lane.work_item.issue_number}",
        )
        self.session.add(retried_lane)
        self.session.flush()
        SchedulerService(self.session).transition_lane_state(
            retried_lane.lane_id,
            "Claimed",
            reason="operator.retry.claimed",
            observed_at=created_at,
            source_kind="operator_api",
        )
        self._record_action(
            target_kind="lane",
            target_id=str(lane.lane_id),
            signal_type="operator.lane.retry",
            actor_id=actor_id,
            reason=reason,
            payload={"new_lane_id": str(retried_lane.lane_id), "attempt": retried_lane.attempt},
            correlation=lane_signal_correlation(lane),
        )
        self.session.flush()
        return self._serialize_lane(self._require_lane(retried_lane.lane_id))

    def cancel_lane(self, lane_id, *, actor_id: str, reason: str, disposition: str) -> LaneResponse:
        lane = self._require_lane(lane_id)
        if lane.state in NON_CANCELABLE_LANE_STATES:
            raise OperatorAPIConflictError(f"Lane cannot be cancelled from state: {lane.state}")

        environment = lane.execution_environment
        if environment is not None and environment.status not in {"Quarantined", "Terminated"}:
            try:
                ExecutionEnvironmentService(self.session).finalize_lane_environment(
                    lane.lane_id,
                    final_state="Cancelled",
                    disposition=disposition,
                    reason=reason,
                )
            except LaneProvisioningError as exc:
                raise OperatorAPIValidationError(str(exc)) from exc
        else:
            SchedulerService(self.session).transition_lane_state(
                lane.lane_id,
                "Cancelled",
                reason=reason,
                observed_at=_now(),
                source_kind="operator_api",
            )
        if lane.agent_session is not None:
            self._append_session_action(
                lane=lane,
                session=lane.agent_session,
                event_type="operator_cancelled",
                summary=reason,
                payload={"actor_id": actor_id, "reason": reason, "disposition": disposition},
            )
            lane.agent_session.status = "failed"
            lane.agent_session.wait_reason = None
            lane.agent_session.requires_human_input = False
            lane.agent_session.last_error_category = "policy"
        self._record_action(
            target_kind="lane",
            target_id=str(lane.lane_id),
            signal_type="operator.lane.cancel",
            actor_id=actor_id,
            reason=reason,
            payload={"disposition": disposition, "state": lane.state},
            correlation=lane_signal_correlation(lane),
        )
        self.session.flush()
        return self._serialize_lane(lane)

    def approve_lane(self, lane_id, *, actor_id: str, reason: str, approval_payload: dict[str, Any]) -> LaneResponse:
        lane = self._require_lane(lane_id)
        session = lane.agent_session
        if session is None or lane.state != "AwaitingApproval" or session.status != "awaiting_approval":
            raise OperatorAPIConflictError("Lane is not awaiting operator approval.")
        self._append_session_action(
            lane=lane,
            session=session,
            event_type="operator_approved",
            summary=reason,
            payload={"actor_id": actor_id, "reason": reason, "approval_payload": approval_payload},
        )
        session.status = "running"
        session.wait_reason = None
        session.requires_human_input = False
        lane.state = "Running"
        self._record_action(
            target_kind="lane",
            target_id=str(lane.lane_id),
            signal_type="operator.lane.approve",
            actor_id=actor_id,
            reason=reason,
            payload={"approval_payload": approval_payload},
            correlation=lane_signal_correlation(lane),
        )
        self.session.flush()
        return self._serialize_lane(lane)

    def submit_human_input(self, lane_id, *, actor_id: str, reason: str, input_payload: dict[str, Any]) -> LaneResponse:
        lane = self._require_lane(lane_id)
        session = lane.agent_session
        if session is None or lane.state != "AwaitingGitHub" or session.status != "awaiting_human_input":
            raise OperatorAPIConflictError("Lane is not awaiting human input.")
        self._append_session_action(
            lane=lane,
            session=session,
            event_type="operator_human_input",
            summary=reason,
            payload={"actor_id": actor_id, "reason": reason, "input_payload": input_payload},
        )
        session.status = "running"
        session.wait_reason = None
        session.requires_human_input = False
        lane.state = "Running"
        self._record_action(
            target_kind="lane",
            target_id=str(lane.lane_id),
            signal_type="operator.lane.human_input",
            actor_id=actor_id,
            reason=reason,
            payload={"input_payload": input_payload},
            correlation=lane_signal_correlation(lane),
        )
        self.session.flush()
        return self._serialize_lane(lane)

    def list_baselines(self, *, org_id=None, drift_status: str | None = None) -> list[BaselineResponse]:
        query = self._product_query()
        if org_id is not None:
            query = query.filter(Product.org_id == org_id)
        products = query.order_by(Product.key.asc()).all()
        baselines = [self._serialize_baseline(product) for product in products]
        if drift_status:
            baselines = [item for item in baselines if item.drift_status == drift_status]
        return baselines

    def get_baseline(self, product_id) -> BaselineResponse:
        product = self._product_query().filter(Product.product_id == product_id).one_or_none()
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        return self._serialize_baseline(product)

    def _product_query(self):
        return self.session.query(Product).options(
            selectinload(Product.repositories).selectinload(RepositoryBinding.work_items).selectinload(WorkItem.project_items),
            selectinload(Product.repositories).selectinload(RepositoryBinding.pull_requests),
            selectinload(Product.seed_jobs),
            joinedload(Product.project_mirror).selectinload(GitHubProjectMirror.items),
            selectinload(Product.managed_assets),
            selectinload(Product.standards_upgrade_runs),
        )

    def _lane_query(self):
        return self.session.query(OrchestrationLane).options(
            joinedload(OrchestrationLane.product),
            joinedload(OrchestrationLane.repo),
            joinedload(OrchestrationLane.work_item),
            joinedload(OrchestrationLane.execution_environment),
            joinedload(OrchestrationLane.agent_session),
        )

    def _serialize_product(self, product: Product) -> ProductSummaryResponse:
        primary_repo = self._resolve_primary_repo(product)
        payload = {
            "product_id": product.product_id,
            "org_id": product.org_id,
            "key": product.key,
            "name": product.name,
            "description": product.description,
            "status": product.status,
            "baseline_channel": product.baseline_channel,
            "standards_pack_key": product.standards_pack_key,
            "standards_pack_version": product.standards_pack_version,
            "agent_core_version": product.agent_core_version,
            "execution_profile": product.execution_profile,
            "component_root_node_id": product.component_root_node_id,
            "manifest_schema_version": product.manifest_schema_version,
            "setup_state": product.setup_state,
            "setup_diagnostics": product.setup_diagnostics,
            "effective_config": product.effective_config,
            "operator_overrides": product.operator_overrides,
            "last_config_refresh_at": product.last_config_refresh_at,
            "last_accepted_config_at": product.last_accepted_config_at,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
            "latest_seed_job": self._resolve_latest_seed_job(product),
            "primary_repo": primary_repo,
            "primary_project": product.project_mirror,
            "managed_assets": sorted(product.managed_assets, key=lambda item: item.path),
            "delivery_cockpit": self._serialize_delivery_cockpit(product),
        }
        return ProductSummaryResponse.model_validate(payload)

    def _resolve_latest_seed_job(self, product: Product) -> ProductSeedJobSummaryResponse | None:
        if not product.seed_jobs:
            return None
        latest_job = max(
            product.seed_jobs,
            key=lambda job: (job.updated_at or datetime.min.replace(tzinfo=timezone.utc), job.created_at),
        )
        return ProductSeedJobSummaryResponse.model_validate(latest_job)

    def _serialize_delivery_cockpit(self, product: Product) -> ProductDeliveryCockpitResponse | None:
        repositories = sorted(product.repositories, key=lambda item: (item.created_at, item.owner, item.name))
        primary_repo = self._resolve_primary_repo(product)
        repo_by_id = {repo.repo_id: repo for repo in repositories}
        work_items = sorted(
            [work_item for repo in repositories for work_item in repo.work_items],
            key=self._delivery_work_item_sort_key,
        )
        if not repositories and product.project_mirror is None and not work_items:
            return None

        open_work_items = [item for item in work_items if self._is_open_delivery_work_item(item)]
        visible_work_items = open_work_items[:DELIVERY_WORK_ITEM_LIMIT]
        repair_count = sum(1 for item in work_items if item.requires_repair)
        stale_count = sum(1 for item in work_items if self._delivery_work_item_mirror_state(item) == "stale")
        mirror_state = self._delivery_product_mirror_state(
            project=product.project_mirror,
            repair_count=repair_count,
            stale_count=stale_count,
        )
        return ProductDeliveryCockpitResponse.model_validate(
            {
                "mirror_state": mirror_state,
                "work_pressure": self._serialize_delivery_work_pressure(work_items),
                "project": self._serialize_delivery_project_summary(
                    project=product.project_mirror,
                    primary_repo=primary_repo,
                    mirror_state=mirror_state,
                ),
                "work_items": [
                    self._serialize_delivery_work_item(
                        work_item=item,
                        repo=repo_by_id[item.repo_id],
                    )
                    for item in visible_work_items
                    if item.repo_id in repo_by_id
                ],
                "remaining_work_item_count": max(len(open_work_items) - len(visible_work_items), 0),
            }
        )

    def _serialize_delivery_work_pressure(
        self,
        work_items: list[WorkItem],
    ) -> ProductDeliveryWorkPressureResponse:
        counts = Counter(item.status for item in work_items)
        return ProductDeliveryWorkPressureResponse.model_validate(
            {
                "total_open_count": sum(1 for item in work_items if self._is_open_delivery_work_item(item)),
                "triage_count": counts.get("Triage", 0),
                "ready_count": counts.get("Ready", 0),
                "blocked_count": counts.get("Blocked", 0),
                "in_progress_count": counts.get("In Progress", 0),
                "in_review_count": counts.get("In Review", 0),
                "done_count": counts.get("Done", 0),
                "ambiguous_count": sum(
                    1 for item in work_items if item.requires_repair or item.dependency_state == "ambiguous"
                ),
                "stale_count": sum(1 for item in work_items if self._delivery_work_item_mirror_state(item) == "stale"),
            }
        )

    def _serialize_delivery_project_summary(
        self,
        *,
        project: GitHubProjectMirror | None,
        primary_repo: RepositoryBinding | None,
        mirror_state: str,
    ) -> ProductDeliveryProjectSummaryResponse | None:
        if project is None:
            return None
        items = list(project.items or [])
        return ProductDeliveryProjectSummaryResponse.model_validate(
            {
                "project_id": project.project_id,
                "number": project.number,
                "title": project.title,
                "status_field_name": project.status_field_name,
                "item_count": len(items),
                "issue_count": sum(1 for item in items if item.content_type == "Issue"),
                "pull_request_count": sum(1 for item in items if item.content_type == "PullRequest"),
                "mirror_state": mirror_state,
                "last_reconciled_at": project.last_reconciled_at,
                "url": self._github_project_url(project=project, primary_repo=primary_repo),
            }
        )

    def _serialize_delivery_work_item(
        self,
        *,
        work_item: WorkItem,
        repo: RepositoryBinding,
    ) -> ProductDeliveryWorkItemSummaryResponse:
        project_item = self._select_delivery_project_item(work_item, preferred_project_id=work_item.project_id)
        linked_pull_requests = self._serialize_delivery_pull_requests(work_item=work_item, repo=repo)
        return ProductDeliveryWorkItemSummaryResponse.model_validate(
            {
                "work_item_id": work_item.work_item_id,
                "repo_id": repo.repo_id,
                "repo_owner": repo.owner,
                "repo_name": repo.name,
                "issue_number": work_item.issue_number,
                "title": work_item.title,
                "status": work_item.status,
                "status_source": work_item.status_source,
                "dependency_state": work_item.dependency_state,
                "priority_hint": work_item.priority_hint,
                "handoff_status": work_item.handoff_status,
                "eligibility_flags": list(work_item.eligibility_flags or []),
                "mirror_state": self._delivery_work_item_mirror_state(work_item),
                "requires_repair": bool(work_item.requires_repair),
                "repair_reasons": list(work_item.repair_reasons or []),
                "last_normalized_at": work_item.last_normalized_at,
                "updated_at": work_item.updated_at,
                "project_status_name": project_item.status_name if project_item is not None else None,
                "url": self._github_issue_url(repo=repo, issue_number=work_item.issue_number),
                "linked_pull_requests": linked_pull_requests,
            }
        )

    def _serialize_delivery_pull_requests(
        self,
        *,
        work_item: WorkItem,
        repo: RepositoryBinding,
    ) -> list[ProductDeliveryPullRequestSummaryResponse]:
        details_by_node_id: dict[str, dict[str, Any]] = {}
        pull_requests_by_node_id = {
            pull_request.github_pr_node_id: pull_request
            for pull_request in repo.pull_requests
            if pull_request.github_pr_node_id
        }

        for node_id in work_item.linked_prs or []:
            pull_request = pull_requests_by_node_id.get(node_id)
            if pull_request is None:
                details_by_node_id[str(node_id)] = {"github_pr_node_id": str(node_id)}
                continue
            details_by_node_id[pull_request.github_pr_node_id] = {
                "github_pr_node_id": pull_request.github_pr_node_id,
                "number": pull_request.number,
                "title": pull_request.title,
                "state": pull_request.state,
                "is_draft": bool(pull_request.is_draft),
                "review_state": pull_request.review_state,
                "merge_state": pull_request.merge_state,
                "merged_at": pull_request.merged_at,
            }

        raw_payload = work_item.raw_payload if isinstance(work_item.raw_payload, dict) else {}
        for payload in self._issue_pull_request_payloads(raw_payload):
            github_pr_node_id = payload.get("id") or payload.get("node_id")
            if not isinstance(github_pr_node_id, str) or not github_pr_node_id:
                continue
            existing = details_by_node_id.get(github_pr_node_id, {})
            number = payload.get("number")
            title = payload.get("title")
            details_by_node_id[github_pr_node_id] = {
                "github_pr_node_id": github_pr_node_id,
                "number": number if isinstance(number, int) else existing.get("number"),
                "title": title.strip() if isinstance(title, str) and title.strip() else existing.get("title"),
                "state": str(payload.get("state") or existing.get("state") or "").lower() or None,
                "is_draft": bool(payload.get("isDraft") or payload.get("draft") or existing.get("is_draft") or False),
                "review_state": payload.get("reviewDecision") or payload.get("review_state") or existing.get("review_state"),
                "merge_state": payload.get("mergeStateStatus") or payload.get("merge_state") or existing.get("merge_state"),
                "merged_at": payload.get("mergedAt") or payload.get("merged_at") or existing.get("merged_at"),
            }

        def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
            number = item.get("number")
            if isinstance(number, int):
                return (0, number, item.get("github_pr_node_id") or "")
            return (1, 0, item.get("github_pr_node_id") or "")

        sorted_details = sorted(details_by_node_id.values(), key=sort_key)
        return [
            ProductDeliveryPullRequestSummaryResponse.model_validate(
                {
                    **detail,
                    "url": self._github_pull_request_url(repo=repo, number=detail.get("number")),
                }
            )
            for detail in sorted_details
        ]

    def _delivery_work_item_sort_key(self, work_item: WorkItem) -> tuple[int, int, int, int, float]:
        mirror_state = self._delivery_work_item_mirror_state(work_item)
        mirror_rank = 0 if mirror_state == "ambiguous" else 1 if mirror_state == "stale" else 2
        handoff_rank = 0 if work_item.handoff_status == "in_review" else 1 if work_item.handoff_status == "merged" else 2
        status_rank = {
            "Blocked": 0,
            "In Review": 1,
            "In Progress": 2,
            "Ready": 3,
            "Triage": 4,
            "Done": 5,
        }.get(work_item.status, 6)
        priority_rank = {
            "high": 0,
            "medium": 1,
            "low": 2,
        }.get(str(work_item.priority_hint or "").casefold(), 3)
        updated_at = work_item.updated_at or work_item.created_at or _EPOCH
        return (mirror_rank, handoff_rank, status_rank, priority_rank, -updated_at.timestamp())

    def _is_open_delivery_work_item(self, work_item: WorkItem) -> bool:
        return work_item.status != "Done"

    def _delivery_work_item_mirror_state(self, work_item: WorkItem) -> str:
        if work_item.requires_repair:
            return "ambiguous"
        if work_item.last_normalized_at is None:
            return "stale"
        updated_at = work_item.updated_at or work_item.created_at or _EPOCH
        if work_item.last_normalized_at < updated_at:
            return "stale"
        return "current"

    def _delivery_product_mirror_state(
        self,
        *,
        project: GitHubProjectMirror | None,
        repair_count: int,
        stale_count: int,
    ) -> str:
        if repair_count:
            return "ambiguous"
        if project is not None and project.last_reconciled_at is None:
            return "stale"
        if stale_count:
            return "stale"
        return "current"

    def _select_delivery_project_item(
        self,
        work_item: WorkItem,
        *,
        preferred_project_id,
    ) -> GitHubProjectItemMirror | None:
        items = list(work_item.project_items or [])
        if preferred_project_id is not None:
            matching_items = [item for item in items if item.project_id == preferred_project_id]
            if matching_items:
                items = matching_items
        if not items:
            return None
        return max(
            items,
            key=lambda item: (
                item.last_reconciled_at or _EPOCH,
                item.updated_at or item.created_at or _EPOCH,
            ),
        )

    def _issue_pull_request_payloads(self, raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
        pull_request_payloads: list[dict[str, Any]] = []
        closed_references = raw_payload.get("closedByPullRequestsReferences")
        if isinstance(closed_references, dict):
            nodes = closed_references.get("nodes")
            if isinstance(nodes, list):
                pull_request_payloads.extend(item for item in nodes if isinstance(item, dict))

        timeline_items = raw_payload.get("timelineItems")
        if isinstance(timeline_items, dict):
            nodes = timeline_items.get("nodes")
            if isinstance(nodes, list):
                for timeline_item in nodes:
                    if not isinstance(timeline_item, dict):
                        continue
                    source = timeline_item.get("source")
                    if isinstance(source, dict) and str(source.get("__typename") or "") == "PullRequest":
                        pull_request_payloads.append(source)
        return pull_request_payloads

    def _github_repo_url(self, repo: RepositoryBinding) -> str:
        return f"https://github.com/{repo.owner}/{repo.name}"

    def _github_issue_url(self, *, repo: RepositoryBinding, issue_number: int) -> str:
        return f"{self._github_repo_url(repo)}/issues/{issue_number}"

    def _github_pull_request_url(self, *, repo: RepositoryBinding, number: int | None) -> str | None:
        if not isinstance(number, int):
            return None
        return f"{self._github_repo_url(repo)}/pull/{number}"

    def _github_project_url(
        self,
        *,
        project: GitHubProjectMirror,
        primary_repo: RepositoryBinding | None,
    ) -> str | None:
        raw_payload = project.raw_payload if isinstance(project.raw_payload, dict) else {}
        for key in ("url", "html_url"):
            value = raw_payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        resource_path = raw_payload.get("resourcePath")
        if isinstance(resource_path, str) and resource_path.strip():
            return f"https://github.com{resource_path.strip()}"
        if primary_repo is None:
            return None
        return f"https://github.com/orgs/{primary_repo.owner}/projects/{project.number}"

    def _serialize_lane(self, lane: OrchestrationLane) -> LaneResponse:
        work_item = lane.work_item
        if work_item is None or lane.product is None or lane.repo is None:
            raise ValueError("Lane is missing required product, repository, or work-item context.")
        session = lane.agent_session
        environment = lane.execution_environment
        return LaneResponse.model_validate(
            {
                "lane_id": lane.lane_id,
                "product_id": lane.product_id,
                "repo_id": lane.repo_id,
                "work_item_id": lane.work_item_id,
                "attempt": lane.attempt,
                "state": lane.state,
                "claimed_at": lane.claimed_at,
                "started_at": lane.started_at,
                "finished_at": lane.finished_at,
                "branch_name": lane.branch_name,
                "retry_due_at": lane.retry_due_at,
                "handoff_reason": lane.handoff_reason,
                "last_error": lane.last_error,
                "created_at": lane.created_at,
                "updated_at": lane.updated_at,
                "product": {
                    "product_id": lane.product.product_id,
                    "key": lane.product.key,
                    "name": lane.product.name,
                    "status": lane.product.status,
                },
                "repository": RepositoryBindingSummaryResponse.model_validate(lane.repo),
                "work_item": {
                    "work_item_id": work_item.work_item_id,
                    "issue_number": work_item.issue_number,
                    "title": work_item.title,
                    "status": work_item.status,
                    "dependency_state": work_item.dependency_state,
                    "handoff_status": work_item.handoff_status,
                    "linked_prs": list(work_item.linked_prs or []),
                    "updated_at": work_item.updated_at,
                },
                "execution_environment": self._serialize_environment(environment),
                "agent_session": self._serialize_agent_session(session),
            }
        )

    def _serialize_environment(self, environment) -> ExecutionEnvironmentSummaryResponse | None:
        if environment is None:
            return None
        return ExecutionEnvironmentSummaryResponse.model_validate(environment)

    def _serialize_agent_session(self, session: AgentSession | None) -> LaneAgentSessionSummaryResponse | None:
        if session is None:
            return None
        return LaneAgentSessionSummaryResponse.model_validate(session)

    def _serialize_baseline(self, product: Product) -> BaselineResponse:
        asset_counts = Counter((asset.drift_status or "current") for asset in product.managed_assets)
        latest_run = None
        if product.standards_upgrade_runs:
            latest = max(product.standards_upgrade_runs, key=lambda item: item.updated_at or item.created_at)
            latest_run = BaselineUpgradeRunSummaryResponse.model_validate(latest)
        drift_status = "unknown"
        if product.managed_assets:
            if any((asset.drift_status or "current") in DRIFTING_MANAGED_ASSET_STATES for asset in product.managed_assets):
                drift_status = "drift"
            elif any((asset.drift_status or "current") in ADVISORY_MANAGED_ASSET_STATES for asset in product.managed_assets):
                drift_status = "advisory"
            else:
                drift_status = "current"
        return BaselineResponse.model_validate(
            {
                "product_id": product.product_id,
                "org_id": product.org_id,
                "product_key": product.key,
                "product_name": product.name,
                "product_status": product.status,
                "baseline_channel": product.baseline_channel,
                "standards_pack_key": product.standards_pack_key,
                "standards_pack_version": product.standards_pack_version,
                "agent_core_version": product.agent_core_version,
                "setup_state": product.setup_state,
                "setup_diagnostics": product.setup_diagnostics,
                "drift_status": drift_status,
                "managed_asset_counts": dict(sorted(asset_counts.items())),
                "managed_assets": sorted(product.managed_assets, key=lambda item: item.path),
                "latest_run": latest_run,
                "last_config_refresh_at": product.last_config_refresh_at,
                "last_accepted_config_at": product.last_accepted_config_at,
            }
        )

    def _require_product(self, product_id) -> Product:
        product = self._product_query().filter(Product.product_id == product_id).one_or_none()
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        return product

    def _resolve_primary_repo(self, product: Product) -> RepositoryBinding | None:
        if product.primary_repo_id is not None:
            repository = self.session.get(RepositoryBinding, product.primary_repo_id)
            if repository is not None:
                return repository
        return (
            self.session.query(RepositoryBinding)
            .filter(RepositoryBinding.product_id == product.product_id)
            .order_by(RepositoryBinding.created_at.asc())
            .first()
        )

    def _require_lane(self, lane_id) -> OrchestrationLane:
        lane = self._lane_query().filter(OrchestrationLane.lane_id == lane_id).one_or_none()
        if lane is None:
            raise ValueError(f"Lane not found: {lane_id}")
        return lane

    def _resolve_primary_repo(self, product: Product) -> RepositoryBinding | None:
        if product.primary_repo_id is not None:
            for repo in product.repositories:
                if repo.repo_id == product.primary_repo_id:
                    return repo
        return min(product.repositories, key=lambda item: item.created_at) if product.repositories else None

    def _has_other_active_lane(self, lane: OrchestrationLane) -> bool:
        return (
            self.session.query(OrchestrationLane.lane_id)
            .filter(
                OrchestrationLane.work_item_id == lane.work_item_id,
                OrchestrationLane.lane_id != lane.lane_id,
                OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES),
            )
            .first()
            is not None
        )

    def _next_attempt(self, work_item_id) -> int:
        current = (
            self.session.query(func.max(OrchestrationLane.attempt))
            .filter(OrchestrationLane.work_item_id == work_item_id)
            .scalar()
        )
        return int(current or 0) + 1

    def _append_session_action(
        self,
        *,
        lane: OrchestrationLane,
        session: AgentSession,
        event_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> None:
        observed_at = _now()
        current = (
            self.session.query(func.max(AgentSessionEvent.sequence))
            .filter(AgentSessionEvent.agent_session_id == session.agent_session_id)
            .scalar()
        )
        self.session.add(
            AgentSessionEvent(
                agent_session_id=session.agent_session_id,
                lane_id=lane.lane_id,
                sequence=int(current or 0) + 1,
                event_type=event_type,
                summary=summary,
                payload=payload,
                observed_at=observed_at,
            )
        )
        session.last_event = event_type
        session.last_event_at = observed_at

    def _record_action(
        self,
        *,
        target_kind: str,
        target_id: str,
        signal_type: str,
        actor_id: str,
        reason: str,
        payload: dict[str, Any],
        correlation: dict[str, str] | None = None,
    ) -> None:
        outcome = "recorded"
        for key in ("state", "status"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                outcome = value.strip()
                break
        self.session.add(
            OperationalSignal(
                target_kind=target_kind,
                target_id=target_id,
                signal_type=signal_type,
                severity="info",
                value=signal_value_with_correlation(
                    {
                        "actor_id": actor_id,
                        "reason": reason,
                        "audit": build_write_audit(
                            actor_type="human",
                            actor_id=actor_id,
                            target_kind=target_kind,
                            target_id=target_id,
                            action=signal_type,
                            approval_context={"mode": "human-operated", "reason": reason},
                            outcome=outcome,
                        ),
                        **payload,
                    },
                    correlation,
                ),
                observed_at=_now(),
                source_kind="operator_api",
            )
        )
