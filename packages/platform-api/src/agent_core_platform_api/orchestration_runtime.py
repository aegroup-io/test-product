from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import threading
from time import monotonic
from typing import Any

from sqlalchemy.orm import Session, joinedload

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.execution_runtime import ACTIVE_ENVIRONMENT_STATUSES, ExecutionEnvironmentService, LaneProvisioningError
from agent_core_platform_api.governance import ACTION_POLICY_FIELDS, normalize_approval_posture
from agent_core_platform_api.lane_recovery import LaneRecoveryService
from agent_core_platform_api.models import ACTIVE_LANE_OWNERSHIP_STATES, AgentSession, OperationalSignal, OrchestrationLane
from agent_core_platform_api.observability import lane_signal_correlation, signal_value_with_correlation
from agent_core_platform_api.runner_protocol import AgentRunnerLaunchRequest, RunnerProtocolError, RunnerProtocolService
from agent_core_platform_api.scheduler import SchedulerService


logger = logging.getLogger(__name__)
# Keep "Running" as a legacy compatibility lane state for rows created before
# handshake alignment; newly provisioned lanes remain "Provisioning" until handshake.
LAUNCHABLE_LANE_STATES = frozenset({"Claimed", "Provisioning", "Running"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class OrchestrationCycleSummary:
    claimed: int = 0
    provisioned: int = 0
    launches_prepared: int = 0
    retries_resumed: int = 0
    retried: int = 0
    cancelled: int = 0
    reattached: int = 0
    orphaned_environments_cleaned: int = 0
    timeouts_failed: int = 0

    def has_activity(self) -> bool:
        return any(getattr(self, field) for field in self.__dataclass_fields__)


class OrchestrationRuntimeService:
    def __init__(
        self,
        session: Session,
        *,
        scheduler: SchedulerService | None = None,
        runtime: ExecutionEnvironmentService | None = None,
        runner: RunnerProtocolService | None = None,
        recovery: LaneRecoveryService | None = None,
    ):
        self.session = session
        self.scheduler = scheduler or SchedulerService(session)
        self.runtime = runtime or ExecutionEnvironmentService(session)
        self.runner = runner or RunnerProtocolService(session)
        self.recovery = recovery or LaneRecoveryService(session, runtime=self.runtime, scheduler=self.scheduler)

    def run_cycle(
        self,
        *,
        observed_at: datetime | None = None,
        max_claims: int | None = None,
    ) -> OrchestrationCycleSummary:
        timestamp = _ensure_utc(observed_at) or _now()
        recovery_summary = self.recovery.reconcile_active_lanes(now=timestamp)
        resumed_summary = self.recovery.resume_due_retries(now=timestamp)
        claimed = self.scheduler.run_eligibility_tick(max_claims=max_claims)
        launch_summary = self._prepare_pending_launches(observed_at=timestamp)
        timeout_failures = self._evaluate_active_timeouts(observed_at=timestamp)
        cleanup_summary = self.recovery.cleanup_orphaned_environments()
        return OrchestrationCycleSummary(
            claimed=len(claimed),
            provisioned=launch_summary.provisioned,
            launches_prepared=launch_summary.launches_prepared,
            retries_resumed=resumed_summary.resumed,
            retried=recovery_summary.retried + resumed_summary.retried,
            cancelled=recovery_summary.cancelled + resumed_summary.cancelled,
            reattached=recovery_summary.reattached,
            orphaned_environments_cleaned=cleanup_summary.orphaned_environments_cleaned,
            timeouts_failed=timeout_failures,
        )

    def peek_next_launch(self) -> AgentRunnerLaunchRequest | None:
        lane = (
            self.session.query(OrchestrationLane)
            .options(
                joinedload(OrchestrationLane.product),
                joinedload(OrchestrationLane.repo),
                joinedload(OrchestrationLane.work_item),
                joinedload(OrchestrationLane.execution_environment),
                joinedload(OrchestrationLane.agent_session),
            )
            .filter(OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES))
            .order_by(OrchestrationLane.claimed_at.asc(), OrchestrationLane.created_at.asc())
            .all()
        )
        for candidate in lane:
            session = candidate.agent_session
            environment = candidate.execution_environment
            if session is None or environment is None:
                continue
            if session.status != "launching" or session.runner_session_id:
                continue
            if environment.status not in ACTIVE_ENVIRONMENT_STATUSES:
                continue
            launch_payload = dict(session.launch_payload or {})
            if not launch_payload:
                continue
            return AgentRunnerLaunchRequest(
                lane_id=str(candidate.lane_id),
                agent_session_id=str(session.agent_session_id),
                lane_metadata=dict(launch_payload.get("lane_metadata") or {}),
                issue_context=dict(launch_payload.get("issue_context") or {}),
                instruction_bundle=dict(launch_payload.get("instruction_bundle") or {}),
                policy=dict(launch_payload.get("policy") or {}),
                artifact_destinations=dict(launch_payload.get("artifact_destinations") or {}),
                secret_references=list(launch_payload.get("secret_references") or []),
                tool_permissions=list(launch_payload.get("tool_permissions") or []),
                required_capabilities=list(launch_payload.get("required_capabilities") or []),
            )
        return None

    def _prepare_pending_launches(self, *, observed_at: datetime) -> OrchestrationCycleSummary:
        provisioned = 0
        launches_prepared = 0
        lanes = (
            self.session.query(OrchestrationLane)
            .options(
                joinedload(OrchestrationLane.product),
                joinedload(OrchestrationLane.repo),
                joinedload(OrchestrationLane.work_item),
                joinedload(OrchestrationLane.execution_environment),
                joinedload(OrchestrationLane.agent_session),
            )
            .filter(OrchestrationLane.state.in_(LAUNCHABLE_LANE_STATES))
            .order_by(OrchestrationLane.claimed_at.asc(), OrchestrationLane.created_at.asc())
            .all()
        )

        for lane in lanes:
            savepoint = self.session.begin_nested()
            try:
                if lane.state == "Claimed":
                    self.runtime.provision_claimed_lane(lane.lane_id)
                    provisioned += 1
                    self.session.flush()
                    self.session.refresh(lane)
                if self._needs_launch_preparation(lane):
                    self.runner.prepare_lane_session(
                        lane.lane_id,
                        instruction_bundle=self._instruction_bundle(lane),
                        secret_references=self._secret_references(lane),
                        tool_permissions=self._tool_permissions(lane),
                        required_capabilities=self._required_capabilities(lane),
                    )
                    self._record_launch_prepared(lane, observed_at=observed_at)
                    launches_prepared += 1
                savepoint.commit()
            except (LaneProvisioningError, RunnerProtocolError, ValueError) as exc:
                savepoint.rollback()
                self.session.expire_all()
                self._fail_lane_terminal(lane_id=lane.lane_id, reason=str(exc), observed_at=observed_at)
            except Exception as exc:  # pragma: no cover - defensive guard for runtime/provider failures
                savepoint.rollback()
                self.session.expire_all()
                self.recovery.handle_lane_failure(
                    lane.lane_id,
                    failure_kind="runtime.unavailable",
                    reason=str(exc),
                    observed_at=observed_at,
                )
        return OrchestrationCycleSummary(provisioned=provisioned, launches_prepared=launches_prepared)

    def _evaluate_active_timeouts(self, *, observed_at: datetime) -> int:
        lane_ids = [
            lane_id
            for (lane_id,) in self.session.query(OrchestrationLane.lane_id)
            .join(AgentSession, AgentSession.lane_id == OrchestrationLane.lane_id)
            .filter(OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES))
            .all()
        ]
        timed_out = 0
        for lane_id in lane_ids:
            if self.runner.evaluate_timeouts(lane_id, as_of=observed_at) is not None:
                timed_out += 1
        return timed_out

    def _needs_launch_preparation(self, lane: OrchestrationLane) -> bool:
        environment = lane.execution_environment
        if environment is None or environment.status not in ACTIVE_ENVIRONMENT_STATUSES:
            return False
        session = lane.agent_session
        if session is None:
            return True
        if session.runner_session_id:
            return False
        return not bool(session.launch_payload)

    def _instruction_bundle(self, lane: OrchestrationLane) -> dict[str, Any]:
        body = lane.work_item.body if lane.work_item is not None else None
        return {
            "system_prompt": "Work within the accepted product policy, repo instructions, and current issue scope.",
            "task": f"Work GitHub issue #{lane.work_item.issue_number}: {lane.work_item.title}",
            "issue_body": body or "",
            "lane_context": {
                "attempt": lane.attempt,
                "branch_name": lane.branch_name,
                "product_key": lane.product.key if lane.product is not None else None,
                "repository": f"{lane.repo.owner}/{lane.repo.name}" if lane.repo is not None else None,
            },
        }

    def _secret_references(self, lane: OrchestrationLane) -> list[str]:
        effective_config = lane.product.effective_config if lane.product is not None else {}
        activation = effective_config.get("activation", {}) if isinstance(effective_config, dict) else {}
        configured = activation.get("required_secret_keys") if isinstance(activation, dict) else []
        return sorted({value.strip() for value in configured or [] if isinstance(value, str) and value.strip()})

    def _tool_permissions(self, lane: OrchestrationLane) -> list[str]:
        effective_config = lane.product.effective_config if lane.product is not None else {}
        runner = effective_config.get("runner", {}) if isinstance(effective_config, dict) else {}
        configured = runner.get("tool_permissions") if isinstance(runner, dict) else []
        return sorted({value.strip() for value in configured or [] if isinstance(value, str) and value.strip()})

    def _required_capabilities(self, lane: OrchestrationLane) -> list[str]:
        effective_config = lane.product.effective_config if lane.product is not None else {}
        runner = effective_config.get("runner", {}) if isinstance(effective_config, dict) else {}
        configured = {
            value.strip()
            for value in (runner.get("required_capabilities") if isinstance(runner, dict) else []) or []
            if isinstance(value, str) and value.strip()
        }
        configured.add("stream-events")

        governance = effective_config.get("governance", {}) if isinstance(effective_config, dict) else {}
        if isinstance(governance, dict):
            default_posture = normalize_approval_posture(governance.get("approval_posture"))
            action_postures = [normalize_approval_posture(governance.get(field), default=default_posture) for field in ACTION_POLICY_FIELDS.values()]
            if default_posture != "high-trust" or any(posture != "high-trust" for posture in action_postures):
                configured.add("approval-gates")
        return sorted(configured)

    def _record_launch_prepared(self, lane: OrchestrationLane, *, observed_at: datetime) -> None:
        session = lane.agent_session
        launch_payload = dict(session.launch_payload if session is not None else {})
        self.session.add(
            OperationalSignal(
                target_kind="lane",
                target_id=str(lane.lane_id),
                signal_type="lane.runner_launch_prepared",
                severity="info",
                value=signal_value_with_correlation(
                    {
                        "lane_id": str(lane.lane_id),
                        "agent_session_id": str(session.agent_session_id) if session is not None else None,
                        "required_capabilities": list(launch_payload.get("required_capabilities") or []),
                    },
                    lane_signal_correlation(lane),
                ),
                observed_at=observed_at,
                source_kind="runtime",
            )
        )

    def _fail_lane_terminal(self, *, lane_id, reason: str, observed_at: datetime) -> None:
        lane = self.session.get(OrchestrationLane, lane_id)
        if lane is None:
            return
        if lane.execution_environment is not None and lane.execution_environment.status in ACTIVE_ENVIRONMENT_STATUSES:
            try:
                self.runtime.finalize_lane_environment(
                    lane.lane_id,
                    final_state="FailedTerminal",
                    disposition="quarantine",
                    reason=reason,
                )
            except LaneProvisioningError:
                self.scheduler.transition_lane_state(
                    lane.lane_id,
                    "FailedTerminal",
                    reason="runtime.launch_failed",
                    error_detail=reason,
                    observed_at=observed_at,
                    source_kind="runtime",
                )
        else:
            self.scheduler.transition_lane_state(
                lane.lane_id,
                "FailedTerminal",
                reason="runtime.launch_failed",
                error_detail=reason,
                observed_at=observed_at,
                source_kind="runtime",
            )

        session = lane.agent_session
        if session is not None:
            session.status = "failed"
            session.wait_reason = None
            session.requires_human_input = False
            session.last_error_category = "integration"
        lane.last_error = reason
        self.session.flush()


class BackgroundOrchestrationLoop:
    def __init__(self, session_factory):
        settings = get_settings()
        self.session_factory = session_factory
        self.interval_seconds = max(settings.orchestration_tick_interval_seconds, 0.25)
        self.max_claims = settings.orchestration_max_claims_per_tick
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="orcha-orchestration-loop", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=max(self.interval_seconds * 2, 5))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            started_at = monotonic()
            with self.session_factory() as session:
                try:
                    summary = OrchestrationRuntimeService(session).run_cycle(max_claims=self.max_claims)
                    session.commit()
                    if summary.has_activity():
                        logger.info("orchestration cycle summary: %s", summary)
                except Exception:
                    session.rollback()
                    logger.exception("orchestration cycle failed")
            elapsed = monotonic() - started_at
            self._stop_event.wait(max(self.interval_seconds - elapsed, 0.0))
