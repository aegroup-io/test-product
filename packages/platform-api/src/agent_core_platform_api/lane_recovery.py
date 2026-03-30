from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from agent_core_platform_api.execution_runtime import (
    ACTIVE_ENVIRONMENT_STATUSES,
    ExecutionEnvironmentService,
    RuntimeCleanupRequest,
)
from agent_core_platform_api.models import ExecutionEnvironment, OperationalSignal, OrchestrationLane, Product, Setting
from agent_core_platform_api.observability import lane_signal_correlation, product_signal_correlation, signal_value_with_correlation
from agent_core_platform_api.scheduler import ACTIVE_LANE_OWNERSHIP_STATES, SchedulerService


PRODUCT_CONTRACT_VIOLATION_SETTING_KEY = "orcha.runtime_contract_violations"
RETRYABLE_FAILURE_KINDS = frozenset(
    {
        "runtime.transient",
        "runtime.unavailable",
        "runtime.heartbeat_missing",
        "runtime.environment_missing",
        "runtime.github_unavailable",
    }
)
HEARTBEAT_MONITORED_LANE_STATES = frozenset({"Running", "AwaitingApproval", "AwaitingGitHub"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: int = 300
    max_delay_seconds: int = 3600
    jitter_ratio: float = 0.2
    stale_heartbeat_after_seconds: int = 1800
    contract_violation_quarantine_threshold: int = 3


@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    failure_kind: str
    reason: str
    retry_due_at: datetime | None
    delay_seconds: int | None


@dataclass(frozen=True)
class RecoverySummary:
    retried: int = 0
    resumed: int = 0
    cancelled: int = 0
    failed: int = 0
    reattached: int = 0
    orphaned_environments_cleaned: int = 0
    quarantined_products: int = 0

    def merge(self, **kwargs: int) -> "RecoverySummary":
        payload = {
            "retried": self.retried,
            "resumed": self.resumed,
            "cancelled": self.cancelled,
            "failed": self.failed,
            "reattached": self.reattached,
            "orphaned_environments_cleaned": self.orphaned_environments_cleaned,
            "quarantined_products": self.quarantined_products,
        }
        for key, value in kwargs.items():
            payload[key] += value
        return RecoverySummary(**payload)


class LaneRecoveryService:
    def __init__(
        self,
        session: Session,
        *,
        policy: RetryPolicy | None = None,
        runtime: ExecutionEnvironmentService | None = None,
        scheduler: SchedulerService | None = None,
    ):
        self.session = session
        self.policy = policy or RetryPolicy()
        self.runtime = runtime or ExecutionEnvironmentService(session)
        self.scheduler = scheduler or SchedulerService(session)

    def recover_startup_state(self, *, now: datetime | None = None) -> RecoverySummary:
        observed_at = _ensure_utc(now) or _now()
        summary = self.reconcile_active_lanes(now=observed_at)
        summary = summary.merge(**self.resume_due_retries(now=observed_at).__dict__)
        summary = summary.merge(**self.cleanup_orphaned_environments().__dict__)
        return summary

    def cancel_active_lanes_for_shutdown(
        self,
        *,
        now: datetime | None = None,
        reason: str = "runtime.api_shutdown",
    ) -> RecoverySummary:
        observed_at = _ensure_utc(now) or _now()
        summary = RecoverySummary()
        lanes = (
            self.session.query(OrchestrationLane)
            .options(
                joinedload(OrchestrationLane.product),
                joinedload(OrchestrationLane.repo),
                joinedload(OrchestrationLane.work_item),
                joinedload(OrchestrationLane.execution_environment),
                joinedload(OrchestrationLane.agent_session),
            )
            .filter(OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES))
            .order_by(OrchestrationLane.created_at.asc(), OrchestrationLane.attempt.asc())
            .all()
        )

        for lane in lanes:
            environment = lane.execution_environment
            if environment is None or environment.status not in ACTIVE_ENVIRONMENT_STATUSES:
                continue
            savepoint = self.session.begin_nested()
            try:
                self._cancel_lane(lane, reason=reason, observed_at=observed_at)
                if lane.agent_session is not None and lane.agent_session.status not in {"completed", "failed"}:
                    lane.agent_session.status = "failed"
                    lane.agent_session.wait_reason = None
                    lane.agent_session.requires_human_input = False
                    lane.agent_session.last_error_category = "integration"
                savepoint.commit()
                summary = summary.merge(cancelled=1)
            except Exception:
                savepoint.rollback()
                self.session.expire_all()

        return summary

    def reconcile_active_lanes(self, *, now: datetime | None = None) -> RecoverySummary:
        observed_at = _ensure_utc(now) or _now()
        summary = RecoverySummary()
        lanes = (
            self.session.query(OrchestrationLane)
            .options(
                joinedload(OrchestrationLane.product),
                joinedload(OrchestrationLane.repo),
                joinedload(OrchestrationLane.work_item),
                joinedload(OrchestrationLane.execution_environment),
                joinedload(OrchestrationLane.agent_session),
            )
            .filter(OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES))
            .order_by(OrchestrationLane.created_at.asc(), OrchestrationLane.attempt.asc())
            .all()
        )

        for lane in lanes:
            if lane.state == "RetryPending":
                continue
            if not self.scheduler.is_dispatch_eligible(lane.work_item, lane.repo, lane.product):
                self._cancel_lane(lane, reason="recovery.eligibility_lost", observed_at=observed_at)
                summary = summary.merge(cancelled=1)
                continue

            environment = lane.execution_environment
            if environment is None or not self.runtime.provider.can_reuse(environment):
                self.handle_lane_failure(
                    lane.lane_id,
                    failure_kind="runtime.environment_missing",
                    reason="Active lane lost its execution environment.",
                    observed_at=observed_at,
                )
                summary = summary.merge(retried=1)
                continue

            if not self.runtime.continuation_is_safe(lane.lane_id):
                quarantined = self._quarantine_contract_violator(
                    lane,
                    reason="Active lane no longer matches the accepted execution boundary.",
                    observed_at=observed_at,
                )
                summary = summary.merge(
                    failed=1,
                    quarantined_products=1 if quarantined else 0,
                )
                continue

            if self._heartbeat_is_stale(lane, environment, observed_at):
                self.handle_lane_failure(
                    lane.lane_id,
                    failure_kind="runtime.heartbeat_missing",
                    reason="Runner heartbeat timed out while the lane was active.",
                    observed_at=observed_at,
                )
                summary = summary.merge(retried=1)
                continue

            if (
                lane.state in {"Claimed", "Provisioning"}
                and environment.status in ACTIVE_ENVIRONMENT_STATUSES
                and lane.agent_session is not None
                and lane.agent_session.runner_session_id
                and lane.agent_session.status in {"running", "awaiting_approval", "awaiting_human_input"}
            ):
                self.scheduler.transition_lane_state(
                    lane.lane_id,
                    "Provisioning",
                    reason="recovery.reattached",
                    observed_at=observed_at,
                    source_kind="recovery",
                )
                summary = summary.merge(reattached=1)

        return summary

    def resume_due_retries(self, *, now: datetime | None = None) -> RecoverySummary:
        observed_at = _ensure_utc(now) or _now()
        summary = RecoverySummary()
        lanes = (
            self.session.query(OrchestrationLane)
            .options(
                joinedload(OrchestrationLane.product),
                joinedload(OrchestrationLane.repo),
                joinedload(OrchestrationLane.work_item),
                joinedload(OrchestrationLane.execution_environment),
            )
            .filter(
                OrchestrationLane.state == "RetryPending",
                OrchestrationLane.retry_due_at.is_not(None),
                OrchestrationLane.retry_due_at <= observed_at,
            )
            .order_by(OrchestrationLane.retry_due_at.asc(), OrchestrationLane.attempt.asc())
            .all()
        )
        for lane in lanes:
            if not self.scheduler.is_dispatch_eligible(lane.work_item, lane.repo, lane.product):
                self._cancel_lane(lane, reason="recovery.retry_ineligible", observed_at=observed_at)
                summary = summary.merge(cancelled=1)
                continue

            self._close_retry_attempt(lane, observed_at=observed_at)
            claimed = self.scheduler.claim_work_item(lane.work_item_id)
            if claimed is not None:
                summary = summary.merge(resumed=1)
        return summary

    def cleanup_orphaned_environments(self) -> RecoverySummary:
        summary = RecoverySummary()
        environments = (
            self.session.query(ExecutionEnvironment)
            .options(joinedload(ExecutionEnvironment.lane))
            .filter(ExecutionEnvironment.status.in_(ACTIVE_ENVIRONMENT_STATUSES))
            .all()
        )
        for environment in environments:
            lane = environment.lane
            if lane is not None and lane.state in ACTIVE_LANE_OWNERSHIP_STATES:
                continue
            self._cleanup_environment(environment, reason="recovery.orphan_cleanup")
            summary = summary.merge(orphaned_environments_cleaned=1)
        return summary

    def handle_lane_failure(
        self,
        lane_id: UUID,
        *,
        failure_kind: str,
        reason: str,
        observed_at: datetime | None = None,
    ) -> RetryDecision:
        lane = self._load_lane(lane_id)
        timestamp = _ensure_utc(observed_at) or _now()
        retryable = failure_kind in RETRYABLE_FAILURE_KINDS and lane.attempt < self.policy.max_attempts
        if retryable:
            delay_seconds = self._retry_delay_seconds(lane.lane_id, lane.attempt, failure_kind)
            retry_due_at = timestamp + timedelta(seconds=delay_seconds)
            self.scheduler.transition_lane_state(
                lane.lane_id,
                "RetryPending",
                reason=failure_kind,
                error_detail=reason,
                retry_due_at=retry_due_at,
                observed_at=timestamp,
                source_kind="recovery",
            )
            self._record_signal(
                target_kind="lane",
                target_id=str(lane.lane_id),
                signal_type="lane.retry_scheduled",
                severity="warning",
                value={
                    "failure_kind": failure_kind,
                    "retry_due_at": retry_due_at.isoformat(),
                    "delay_seconds": delay_seconds,
                },
                observed_at=timestamp,
            )
            return RetryDecision(
                retryable=True,
                failure_kind=failure_kind,
                reason=reason,
                retry_due_at=retry_due_at,
                delay_seconds=delay_seconds,
            )

        self.scheduler.transition_lane_state(
            lane.lane_id,
            "FailedTerminal",
            reason=failure_kind,
            error_detail=reason,
            observed_at=timestamp,
            source_kind="recovery",
        )
        return RetryDecision(
            retryable=False,
            failure_kind=failure_kind,
            reason=reason,
            retry_due_at=None,
            delay_seconds=None,
        )

    def _close_retry_attempt(self, lane: OrchestrationLane, *, observed_at: datetime) -> None:
        environment = lane.execution_environment
        if environment is not None and environment.status in ACTIVE_ENVIRONMENT_STATUSES:
            self.runtime.finalize_lane_environment(
                lane.lane_id,
                final_state="Cancelled",
                disposition="terminate",
                reason="recovery.retry_superseded",
            )
            return
        self.scheduler.transition_lane_state(
            lane.lane_id,
            "Cancelled",
            reason="recovery.retry_superseded",
            error_detail=lane.last_error,
            observed_at=observed_at,
            source_kind="recovery",
        )

    def _cancel_lane(self, lane: OrchestrationLane, *, reason: str, observed_at: datetime) -> None:
        environment = lane.execution_environment
        if environment is not None and environment.status in ACTIVE_ENVIRONMENT_STATUSES:
            self.runtime.finalize_lane_environment(
                lane.lane_id,
                final_state="Cancelled",
                disposition="terminate",
                reason=reason,
            )
            return
        self.scheduler.transition_lane_state(
            lane.lane_id,
            "Cancelled",
            reason=reason,
            error_detail=lane.last_error,
            observed_at=observed_at,
            source_kind="recovery",
        )

    def _quarantine_contract_violator(
        self,
        lane: OrchestrationLane,
        *,
        reason: str,
        observed_at: datetime,
    ) -> bool:
        environment = lane.execution_environment
        if environment is not None and environment.status in ACTIVE_ENVIRONMENT_STATUSES:
            self.runtime.finalize_lane_environment(
                lane.lane_id,
                final_state="FailedTerminal",
                disposition="quarantine",
                reason="recovery.contract_violation",
            )
        else:
            self.scheduler.transition_lane_state(
                lane.lane_id,
                "FailedTerminal",
                reason="recovery.contract_violation",
                error_detail=reason,
                observed_at=observed_at,
                source_kind="recovery",
            )
        return self._record_contract_violation(product=lane.product, reason=reason, observed_at=observed_at)

    def _record_contract_violation(self, *, product: Product, reason: str, observed_at: datetime) -> bool:
        setting = (
            self.session.query(Setting)
            .filter(
                Setting.scope_type == "product",
                Setting.scope_id == str(product.product_id),
                Setting.key == PRODUCT_CONTRACT_VIOLATION_SETTING_KEY,
            )
            .one_or_none()
        )
        payload: dict[str, Any] = setting.value_json if setting is not None and isinstance(setting.value_json, dict) else {}
        count = int(payload.get("count", 0)) + 1
        updated_payload = {
            "count": count,
            "last_reason": reason,
            "last_violation_at": observed_at.isoformat(),
        }
        if setting is None:
            self.session.add(
                Setting(
                    scope_type="product",
                    scope_id=str(product.product_id),
                    key=PRODUCT_CONTRACT_VIOLATION_SETTING_KEY,
                    value_json=updated_payload,
                )
            )
        else:
            setting.value_json = updated_payload

        if count < self.policy.contract_violation_quarantine_threshold:
            return False

        product.status = "Quarantined"
        product.setup_state = "setup-needed"
        diagnostics = list(product.setup_diagnostics or [])
        diagnostics.append(
            {
                "classification": "blocking setup error",
                "code": "runtime.contract_violation_quarantine",
                "message": reason,
            }
        )
        product.setup_diagnostics = diagnostics
        self._record_signal(
            target_kind="product",
            target_id=str(product.product_id),
            signal_type="product.quarantined",
            severity="error",
            value={"reason": reason, "violation_count": count},
            observed_at=observed_at,
        )
        return True

    def _heartbeat_is_stale(
        self,
        lane: OrchestrationLane,
        environment: ExecutionEnvironment,
        observed_at: datetime,
    ) -> bool:
        if lane.state not in HEARTBEAT_MONITORED_LANE_STATES:
            return False
        reference_points = [
            _ensure_utc(environment.heartbeat_at),
            _ensure_utc(lane.agent_session.last_event_at) if lane.agent_session is not None else None,
            _ensure_utc(lane.started_at),
            _ensure_utc(environment.created_at),
        ]
        freshest = max((value for value in reference_points if value is not None), default=None)
        if freshest is None:
            return False
        return observed_at - freshest > timedelta(seconds=self.policy.stale_heartbeat_after_seconds)

    def _retry_delay_seconds(self, lane_id: UUID, attempt: int, failure_kind: str) -> int:
        base_delay = min(self.policy.max_delay_seconds, self.policy.base_delay_seconds * (2 ** max(attempt - 1, 0)))
        jitter_span = int(round(base_delay * self.policy.jitter_ratio))
        if jitter_span <= 0:
            return max(1, base_delay)
        digest = hashlib.sha256(f"{lane_id}:{attempt}:{failure_kind}".encode("utf-8")).digest()
        jitter_offset = int.from_bytes(digest[:2], "big") % (jitter_span * 2 + 1)
        return min(max(1, base_delay - jitter_span + jitter_offset), self.policy.max_delay_seconds)

    def _cleanup_environment(self, environment: ExecutionEnvironment, *, reason: str) -> None:
        cleanup = self.runtime.provider.cleanup(
            RuntimeCleanupRequest(
                environment_id=str(environment.execution_environment_id),
                container_handle=environment.container_handle,
                workspace_uri=environment.workspace_uri,
                artifact_uri=environment.artifact_uri,
                log_uri=environment.log_uri,
                cache_uri=environment.cache_uri,
                disposition="terminate",
                reason=reason,
            )
        )
        metadata = dict(environment.provider_metadata or {})
        metadata["cleanup"] = cleanup.provider_metadata
        environment.provider_metadata = metadata
        environment.status = cleanup.status
        environment.terminated_at = cleanup.terminated_at
        environment.quarantine_reason = None

    def _record_signal(
        self,
        *,
        target_kind: str,
        target_id: str,
        signal_type: str,
        severity: str,
        value: dict[str, Any],
        observed_at: datetime,
    ) -> None:
        self.session.add(
            OperationalSignal(
                target_kind=target_kind,
                target_id=target_id,
                signal_type=signal_type,
                severity=severity,
                value=signal_value_with_correlation(value, self._correlation_for_signal(target_kind=target_kind, target_id=target_id)),
                observed_at=observed_at,
                source_kind="recovery",
            )
        )

    def _load_lane(self, lane_id: UUID) -> OrchestrationLane:
        return (
            self.session.query(OrchestrationLane)
            .options(
                joinedload(OrchestrationLane.product),
                joinedload(OrchestrationLane.repo),
                joinedload(OrchestrationLane.work_item),
                joinedload(OrchestrationLane.execution_environment),
                joinedload(OrchestrationLane.agent_session),
            )
            .filter(OrchestrationLane.lane_id == lane_id)
            .one()
        )

    def _correlation_for_signal(self, *, target_kind: str, target_id: str) -> dict[str, str] | None:
        target_uuid = UUID(target_id)
        if target_kind == "lane":
            lane = self.session.query(OrchestrationLane).options(joinedload(OrchestrationLane.product)).filter(
                OrchestrationLane.lane_id == target_uuid
            ).one_or_none()
            return lane_signal_correlation(lane) if lane is not None else None
        if target_kind == "product":
            product = self.session.query(Product).filter(Product.product_id == target_uuid).one_or_none()
            return product_signal_correlation(product) if product is not None else None
        return None
