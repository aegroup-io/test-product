from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.governance import action_policy, build_lane_policy, load_secret_plaintexts, normalize_action_type, redact_value
from agent_core_platform_api.graph_context import GraphContextService
from agent_core_platform_api.models import AgentSession, AgentSessionEvent, ExecutionEnvironment, OrchestrationLane
from agent_core_platform_api.work_item_normalization import (
    RUNNER_CAPABILITY_REPAIR_REASON,
    RUNNER_HANDSHAKE_TIMEOUT_REPAIR_REASON,
    RUNNER_HEARTBEAT_TIMEOUT_REPAIR_REASON,
    WorkItemNormalizationService,
)


ACTIVE_SESSION_STATUSES = frozenset({"launching", "running", "awaiting_approval", "awaiting_human_input"})
WAITING_SESSION_STATUSES = frozenset({"awaiting_approval", "awaiting_human_input"})
TERMINAL_SESSION_STATUSES = frozenset({"completed", "failed"})
ERROR_CATEGORIES = frozenset({"infrastructure", "integration", "policy", "repo_contract", "agent_runtime"})
PROGRESS_EVENT_TYPES = frozenset(
    {
        "session_started",
        "turn_started",
        "tool_call_started",
        "tool_call_finished",
        "artifact_created",
        "turn_completed",
        "token_usage_reported",
        "status_summary",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AgentRunnerLaunchRequest:
    lane_id: str
    agent_session_id: str
    lane_metadata: dict[str, Any]
    issue_context: dict[str, Any]
    instruction_bundle: dict[str, Any]
    policy: dict[str, Any]
    artifact_destinations: dict[str, str]
    secret_references: list[str]
    tool_permissions: list[str]
    required_capabilities: list[str]


@dataclass(frozen=True)
class RunnerHandshake:
    runner_session_id: str
    runner_version: str
    capabilities: list[str]
    environment_identity: str
    heartbeat_at: datetime | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=_now)
    summary: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    token_usage: dict[str, int] | None = None
    tool_name: str | None = None
    tool_status: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class TimeoutEvaluation:
    timeout_type: str
    error_category: str
    observed_at: datetime


@dataclass(frozen=True)
class SessionProjection:
    status: str
    last_event: str | None
    turn_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_call_count: int
    requires_human_input: bool
    wait_reason: str | None
    continuation_summary: dict[str, Any]
    last_error_category: str | None
    heartbeat_at: datetime | None


class RunnerProtocolError(RuntimeError):
    """Raised when the runner protocol contract cannot be satisfied."""


class RunnerProtocolService:
    def __init__(self, session: Session):
        self.session = session
        settings = get_settings()
        self.startup_timeout = timedelta(seconds=settings.runner_startup_timeout_seconds)
        self.heartbeat_timeout = timedelta(seconds=settings.runner_heartbeat_timeout_seconds)
        self.approval_wait_timeout = timedelta(seconds=settings.runner_approval_wait_timeout_seconds)

    def prepare_lane_session(
        self,
        lane_id,
        *,
        instruction_bundle: dict[str, Any],
        policy: dict[str, Any] | None = None,
        secret_references: list[str] | None = None,
        tool_permissions: list[str] | None = None,
        required_capabilities: list[str] | None = None,
    ) -> AgentRunnerLaunchRequest:
        lane = self._load_lane(lane_id)
        environment = self._require_environment(lane)

        session = lane.agent_session or self._ensure_agent_session(lane)
        instruction_bundle_payload = dict(instruction_bundle)
        if "graph_context" not in instruction_bundle_payload:
            instruction_bundle_payload["graph_context"] = GraphContextService(self.session).build_lane_prompt_context(lane_id)
        policy_payload = build_lane_policy(
            lane,
            policy_overrides=policy or {},
            secret_references=secret_references,
            tool_permissions=tool_permissions,
        )
        launch_payload = {
            "lane_metadata": self._lane_metadata(lane),
            "issue_context": self._issue_context(lane),
            "instruction_bundle": instruction_bundle_payload,
            "policy": policy_payload,
            "artifact_destinations": self._artifact_destinations(environment),
            "secret_references": sorted(secret_references or []),
            "tool_permissions": sorted(tool_permissions or []),
            "required_capabilities": sorted(required_capabilities or []),
        }

        session.status = "launching"
        session.wait_reason = None
        session.requires_human_input = False
        session.last_error_category = None
        session.launch_payload = launch_payload
        session.policy_snapshot = policy_payload
        lane.agent_session_id = session.agent_session_id
        self.session.flush()

        return AgentRunnerLaunchRequest(
            lane_id=str(lane.lane_id),
            agent_session_id=str(session.agent_session_id),
            lane_metadata=launch_payload["lane_metadata"],
            issue_context=launch_payload["issue_context"],
            instruction_bundle=launch_payload["instruction_bundle"],
            policy=launch_payload["policy"],
            artifact_destinations=launch_payload["artifact_destinations"],
            secret_references=launch_payload["secret_references"],
            tool_permissions=launch_payload["tool_permissions"],
            required_capabilities=launch_payload["required_capabilities"],
        )

    def record_handshake(self, lane_id, handshake: RunnerHandshake) -> AgentSession:
        lane = self._load_lane(lane_id)
        environment = self._require_environment(lane)
        session = lane.agent_session or self._ensure_agent_session(lane)
        expected_environment_identity = environment.container_handle

        if session.runner_session_id:
            if (
                session.status == "running"
                and session.runner_session_id == handshake.runner_session_id
                and session.environment_identity == handshake.environment_identity
            ):
                return session
            raise RunnerProtocolError("Runner handshake already completed for this lane.")

        if session.status != "launching":
            raise RunnerProtocolError(f"Runner handshake is only valid while session is launching, not {session.status}.")

        if expected_environment_identity and handshake.environment_identity != expected_environment_identity:
            raise RunnerProtocolError(
                "Runner handshake environment identity does not match the provisioned execution environment."
            )

        required_capabilities = {
            capability
            for capability in session.launch_payload.get("required_capabilities", [])
            if isinstance(capability, str) and capability.strip()
        }
        advertised_capabilities = sorted({capability.strip() for capability in handshake.capabilities if capability.strip()})
        missing_capabilities = sorted(required_capabilities.difference(advertised_capabilities))
        if missing_capabilities:
            observed_at = _ensure_utc(handshake.heartbeat_at) or _now()
            WorkItemNormalizationService(self.session).flag_runtime_repair(
                lane.work_item,
                repair_reason=RUNNER_CAPABILITY_REPAIR_REASON,
                observed_at=observed_at,
            )
            self._mark_failed(
                lane=lane,
                session=session,
                observed_at=observed_at,
                reason=f"Runner handshake missing required capabilities: {', '.join(missing_capabilities)}",
                error_category="integration",
                payload={"missing_capabilities": missing_capabilities},
            )
            raise RunnerProtocolError(f"Runner handshake missing required capabilities: {', '.join(missing_capabilities)}")

        heartbeat_at = _ensure_utc(handshake.heartbeat_at) or _now()
        session.runner_session_id = handshake.runner_session_id
        session.runner_version = handshake.runner_version
        session.capabilities = advertised_capabilities
        session.environment_identity = expected_environment_identity or handshake.environment_identity
        session.thread_id = handshake.thread_id or session.thread_id
        session.status = "running"
        session.heartbeat_at = heartbeat_at
        session.wait_reason = None
        session.requires_human_input = False
        environment.heartbeat_at = heartbeat_at
        lane.state = "Running"

        self._append_event(
            lane=lane,
            session=session,
            event=RuntimeEvent(
                event_type="session_started",
                observed_at=heartbeat_at,
                summary="Runner handshake completed.",
                payload={
                    "runner_session_id": handshake.runner_session_id,
                    "runner_version": handshake.runner_version,
                    "capabilities": advertised_capabilities,
                    "environment_identity": session.environment_identity,
                },
                thread_id=handshake.thread_id,
            ),
        )
        self.session.flush()
        return session

    def record_event(self, lane_id, event: RuntimeEvent) -> AgentSessionEvent:
        lane = self._load_lane(lane_id)
        session = lane.agent_session or self._ensure_agent_session(lane)
        if session.status == "launching":
            raise RunnerProtocolError("Runner event received before handshake completed.")
        if session.status in TERMINAL_SESSION_STATUSES and event.event_type not in {"session_completed", "session_failed"}:
            raise RunnerProtocolError("Runner event received after session already reached terminal state.")
        persisted = self._append_event(lane=lane, session=session, event=event)
        self.session.flush()
        return persisted

    def record_heartbeat(
        self,
        lane_id,
        *,
        heartbeat_at: datetime | None = None,
        thread_id: str | None = None,
        turn_id: str | None = None,
    ) -> AgentSession:
        lane = self._load_lane(lane_id)
        environment = self._require_environment(lane)
        session = lane.agent_session or self._ensure_agent_session(lane)
        if session.status == "launching":
            raise RunnerProtocolError("Runner heartbeat received before handshake completed.")

        observed_at = _ensure_utc(heartbeat_at) or _now()
        session.heartbeat_at = observed_at
        session.thread_id = thread_id or session.thread_id
        session.turn_id = turn_id or session.turn_id
        environment.heartbeat_at = observed_at
        self.session.flush()
        return session

    def evaluate_timeouts(self, lane_id, *, as_of: datetime | None = None) -> TimeoutEvaluation | None:
        lane = self._load_lane(lane_id)
        session = lane.agent_session
        if session is None or session.status not in ACTIVE_SESSION_STATUSES:
            return None

        observed_at = _ensure_utc(as_of) or _now()
        if session.status == "launching":
            started_at = _ensure_utc(session.created_at) or observed_at
            if observed_at - started_at > self.startup_timeout:
                WorkItemNormalizationService(self.session).flag_runtime_repair(
                    lane.work_item,
                    repair_reason=RUNNER_HANDSHAKE_TIMEOUT_REPAIR_REASON,
                    observed_at=observed_at,
                )
                self._mark_failed(
                    lane=lane,
                    session=session,
                    observed_at=observed_at,
                    reason="Runner handshake timed out before startup completed.",
                    error_category="integration",
                    payload={"timeout_type": "handshake_timeout"},
                )
                return TimeoutEvaluation("handshake_timeout", "integration", observed_at)

        heartbeat_at = _ensure_utc(session.heartbeat_at) or _ensure_utc(session.last_event_at) or _ensure_utc(session.created_at)
        if session.status == "running" and heartbeat_at is not None and observed_at - heartbeat_at > self.heartbeat_timeout:
            WorkItemNormalizationService(self.session).flag_runtime_repair(
                lane.work_item,
                repair_reason=RUNNER_HEARTBEAT_TIMEOUT_REPAIR_REASON,
                observed_at=observed_at,
            )
            self._mark_failed(
                lane=lane,
                session=session,
                observed_at=observed_at,
                reason="Runner heartbeat timed out while the lane was active.",
                error_category="agent_runtime",
                payload={"timeout_type": "no_heartbeat_timeout"},
            )
            return TimeoutEvaluation("no_heartbeat_timeout", "agent_runtime", observed_at)

        if session.status in WAITING_SESSION_STATUSES:
            waiting_since = _ensure_utc(session.last_event_at) or heartbeat_at
            if waiting_since is not None and observed_at - waiting_since > self.approval_wait_timeout:
                self._mark_failed(
                    lane=lane,
                    session=session,
                    observed_at=observed_at,
                    reason="Runner approval or human-input wait timed out.",
                    error_category="policy",
                    payload={"timeout_type": "approval_wait_timeout"},
                )
                return TimeoutEvaluation("approval_wait_timeout", "policy", observed_at)

        return None

    def rebuild_session_projection(self, lane_id) -> SessionProjection:
        lane = self._load_lane(lane_id)
        session = lane.agent_session or self._ensure_agent_session(lane)
        projection = {
            "status": "launching",
            "last_event": None,
            "turn_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "tool_call_count": 0,
            "requires_human_input": False,
            "wait_reason": None,
            "continuation_summary": {},
            "last_error_category": None,
            "heartbeat_at": None,
        }
        for event in session.events:
            projection["last_event"] = event.event_type
            projection["input_tokens"] += event.input_tokens_delta
            projection["output_tokens"] += event.output_tokens_delta
            projection["total_tokens"] += event.total_tokens_delta
            projection["heartbeat_at"] = _ensure_utc(event.observed_at)
            if event.event_type == "turn_started":
                projection["turn_count"] += 1
            if event.event_type == "tool_call_finished":
                projection["tool_call_count"] += 1
            if event.event_type == "status_summary":
                updated_at = _ensure_utc(event.observed_at) or _now()
                projection["continuation_summary"] = {
                    **event.payload,
                    "summary": event.summary,
                    "updated_at": updated_at.isoformat(),
                }
            if event.event_type == "approval_requested":
                requested_action = normalize_action_type(event.payload.get("action_type") if isinstance(event.payload, dict) else None)
                requested_policy = action_policy(session.policy_snapshot, requested_action)
                if requested_policy == "blocked":
                    projection["status"] = "failed"
                    projection["wait_reason"] = None
                    projection["last_error_category"] = "policy"
                    projection["requires_human_input"] = False
                elif requested_policy != "high-trust":
                    projection["status"] = "awaiting_approval"
                    projection["wait_reason"] = event.summary
                    projection["requires_human_input"] = False
            elif event.event_type == "human_input_requested":
                projection["status"] = "awaiting_human_input"
                projection["wait_reason"] = event.summary
                projection["requires_human_input"] = True
            elif event.event_type == "session_failed":
                projection["status"] = "failed"
                projection["wait_reason"] = None
                projection["last_error_category"] = event.error_category
                projection["requires_human_input"] = False
            elif event.event_type == "session_completed":
                projection["status"] = "completed"
                projection["wait_reason"] = None
                projection["requires_human_input"] = False
            elif event.event_type in PROGRESS_EVENT_TYPES:
                projection["status"] = "running"
                projection["requires_human_input"] = False
                projection["wait_reason"] = None

        return SessionProjection(**projection)

    def _append_event(self, *, lane: OrchestrationLane, session: AgentSession, event: RuntimeEvent) -> AgentSessionEvent:
        observed_at = _ensure_utc(event.observed_at) or _now()
        secret_values = load_secret_plaintexts(self.session)
        payload = redact_value(dict(event.payload), secret_values)
        summary = redact_value(event.summary, secret_values)
        token_usage = dict(event.token_usage or {})
        input_delta = int(token_usage.get("input_tokens") or 0)
        output_delta = int(token_usage.get("output_tokens") or 0)
        total_delta = int(token_usage.get("total_tokens") or (input_delta + output_delta))
        error_category = self._normalize_error_category(event.error_category or payload.get("error_category"))
        persisted = AgentSessionEvent(
            agent_session_id=session.agent_session_id,
            lane_id=lane.lane_id,
            sequence=self._next_sequence(session.agent_session_id),
            event_type=event.event_type,
            summary=summary,
            payload=payload,
            input_tokens_delta=input_delta,
            output_tokens_delta=output_delta,
            total_tokens_delta=total_delta,
            tool_name=event.tool_name,
            tool_status=event.tool_status,
            error_category=error_category,
            observed_at=observed_at,
        )
        self.session.add(persisted)

        session.last_event = event.event_type
        session.last_event_at = observed_at
        session.thread_id = event.thread_id or session.thread_id
        session.turn_id = event.turn_id or session.turn_id
        session.input_tokens += input_delta
        session.output_tokens += output_delta
        session.total_tokens += total_delta
        session.heartbeat_at = observed_at
        if lane.execution_environment is not None:
            lane.execution_environment.heartbeat_at = observed_at
        if event.event_type == "turn_started":
            session.turn_count += 1
        if event.event_type == "tool_call_finished":
            session.tool_call_count += 1
        if event.event_type == "status_summary":
            session.continuation_summary = {
                **payload,
                "summary": summary,
                "updated_at": observed_at.isoformat(),
            }
        if event.event_type in PROGRESS_EVENT_TYPES:
            session.status = "running"
            session.wait_reason = None
            session.requires_human_input = False
            lane.state = "Running"
        if event.event_type == "approval_requested":
            requested_action = normalize_action_type(payload.get("action_type"))
            posture = action_policy(session.policy_snapshot, requested_action)
            if posture == "blocked":
                self.session.flush()
                self._mark_failed(
                    lane=lane,
                    session=session,
                    observed_at=observed_at,
                    reason=f"Governance policy blocked requested action: {requested_action or 'unspecified'}.",
                    error_category="policy",
                    payload={"action_type": requested_action or "unspecified", "policy_mode": "blocked"},
                )
            elif posture != "high-trust":
                session.status = "awaiting_approval"
                session.wait_reason = summary or str(payload.get("reason") or "Awaiting operator approval.")
                session.requires_human_input = False
                lane.state = "AwaitingApproval"
        elif event.event_type == "human_input_requested":
            session.status = "awaiting_human_input"
            session.wait_reason = event.summary or str(payload.get("reason") or "Awaiting human input.")
            session.requires_human_input = True
            lane.state = "AwaitingGitHub"
        elif event.event_type == "session_completed":
            session.status = "completed"
            session.wait_reason = None
            session.requires_human_input = False
            lane.state = "HandedOff"
            lane.handoff_reason = summary or str(payload.get("reason") or "Runner session completed.")
            lane.last_error = None
            lane.retry_due_at = None
            lane.finished_at = observed_at
        elif event.event_type == "session_failed":
            session.status = "failed"
            session.wait_reason = None
            session.requires_human_input = False
            session.last_error_category = error_category
            lane.state = "FailedTerminal"
            lane.handoff_reason = None
            lane.last_error = summary or str(payload.get("error") or "Runner session failed.")
            lane.retry_due_at = None
            lane.finished_at = observed_at
        elif event.event_type == "turn_completed" and session.status == "running":
            session.wait_reason = None
        return persisted

    def _mark_failed(
        self,
        *,
        lane: OrchestrationLane,
        session: AgentSession,
        observed_at: datetime,
        reason: str,
        error_category: str,
        payload: dict[str, Any],
    ) -> None:
        self._append_event(
            lane=lane,
            session=session,
            event=RuntimeEvent(
                event_type="session_failed",
                observed_at=observed_at,
                summary=reason,
                payload=payload,
                error_category=error_category,
            ),
        )

    def _ensure_agent_session(self, lane: OrchestrationLane) -> AgentSession:
        session = lane.agent_session
        if session is not None:
            return session
        session = AgentSession(lane_id=lane.lane_id, status="launching")
        self.session.add(session)
        self.session.flush()
        lane.agent_session = session
        lane.agent_session_id = session.agent_session_id
        return session

    def _load_lane(self, lane_id) -> OrchestrationLane:
        lane = self.session.get(OrchestrationLane, lane_id)
        if lane is None:
            raise RunnerProtocolError(f"Lane not found: {lane_id}")
        if lane.product is None or lane.repo is None or lane.work_item is None:
            raise RunnerProtocolError("Lane is missing product, repository, or work-item context.")
        return lane

    def _require_environment(self, lane: OrchestrationLane) -> ExecutionEnvironment:
        environment = lane.execution_environment
        if environment is None:
            raise RunnerProtocolError("Lane does not have a provisioned execution environment.")
        if environment.status not in {"Ready", "Running"}:
            raise RunnerProtocolError(f"Execution environment is not ready for the runner: {environment.status}")
        return environment

    def _next_sequence(self, agent_session_id) -> int:
        current = (
            self.session.query(func.max(AgentSessionEvent.sequence))
            .filter(AgentSessionEvent.agent_session_id == agent_session_id)
            .scalar()
        )
        return int(current or 0) + 1

    def _lane_metadata(self, lane: OrchestrationLane) -> dict[str, Any]:
        return {
            "lane_id": str(lane.lane_id),
            "attempt": lane.attempt,
            "branch_name": lane.branch_name,
            "product_id": str(lane.product_id),
            "product_key": lane.product.key,
            "repo_id": str(lane.repo_id),
            "repository": {"owner": lane.repo.owner, "name": lane.repo.name, "default_branch": lane.repo.default_branch},
            "execution_environment_id": str(lane.execution_environment_id) if lane.execution_environment_id else None,
            "environment_identity": lane.execution_environment.container_handle if lane.execution_environment is not None else None,
        }

    def _issue_context(self, lane: OrchestrationLane) -> dict[str, Any]:
        return {
            "work_item_id": str(lane.work_item_id),
            "issue_number": lane.work_item.issue_number,
            "title": lane.work_item.title,
            "status": lane.work_item.status,
            "linked_prs": list(lane.work_item.linked_prs or []),
            "handoff_status": lane.work_item.handoff_status,
        }

    def _artifact_destinations(self, environment: ExecutionEnvironment) -> dict[str, str]:
        return {
            "workspace_uri": environment.workspace_uri or "",
            "artifact_uri": environment.artifact_uri or "",
            "log_uri": environment.log_uri or "",
            "cache_uri": environment.cache_uri or "",
        }

    def _approval_posture(self, policy: dict[str, Any]) -> str:
        if not isinstance(policy, dict):
            return "high-trust"
        for key in ("approval_posture", "posture", "mode"):
            value = policy.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "high-trust"

    def _normalize_error_category(self, value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip().lower().replace("-", "_").replace("/", "_")
        if normalized == "repo contract":
            normalized = "repo_contract"
        if normalized in ERROR_CATEGORIES:
            return normalized
        aliases = {
            "repo": "repo_contract",
            "repo_failure": "repo_contract",
            "runtime": "agent_runtime",
            "agent": "agent_runtime",
            "agentruntime": "agent_runtime",
            "infra": "infrastructure",
        }
        return aliases.get(normalized)
