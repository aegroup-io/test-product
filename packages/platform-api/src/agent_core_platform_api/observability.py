from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.models import (
    AgentSessionEvent,
    OperationalSignal,
    OrchestrationLane,
    Product,
    StandardsUpgradeRun,
    WebhookDelivery,
)
from agent_core_platform_api.scheduler import ACTIVE_LANE_OWNERSHIP_STATES, SchedulerService
from agent_core_platform_api.schemas import (
    FleetObservabilityResponse,
    LaneActivityResponse,
    LaneObservabilityResponse,
    LaneStatusSummaryResponse,
    ObservabilityArtifactReferencesResponse,
    ObservabilityCorrelationResponse,
    ObservabilityNotificationResponse,
)


WAITING_LANE_STATES = frozenset({"AwaitingApproval", "AwaitingGitHub"})
RUNNER_HEALTH_LANE_STATES = frozenset({"Running", "AwaitingApproval", "AwaitingGitHub"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def lane_signal_correlation(lane: OrchestrationLane) -> dict[str, str]:
    correlation: dict[str, str] = {
        "product_id": str(lane.product_id),
        "repo_id": str(lane.repo_id),
        "work_item_id": str(lane.work_item_id),
        "lane_id": str(lane.lane_id),
    }
    if lane.product is not None:
        correlation["org_id"] = str(lane.product.org_id)
    if lane.agent_session_id is not None:
        correlation["agent_session_id"] = str(lane.agent_session_id)
    return correlation


def product_signal_correlation(product: Product) -> dict[str, str]:
    return {
        "org_id": str(product.org_id),
        "product_id": str(product.product_id),
    }


def delivery_signal_correlation(delivery: WebhookDelivery) -> dict[str, str]:
    correlation: dict[str, str] = {
        "delivery_id": str(delivery.delivery_id),
        "github_delivery_guid": delivery.github_delivery_guid,
    }
    if delivery.installation_id:
        correlation["installation_id"] = delivery.installation_id
    return correlation


def signal_value_with_correlation(
    value: dict[str, Any] | list | str | int | float | bool | None,
    correlation: dict[str, str] | None,
) -> dict[str, Any] | list | str | int | float | bool | None:
    if not correlation:
        return value
    if not isinstance(value, dict):
        return {"value": value, "correlation": correlation}
    payload = dict(value)
    payload["correlation"] = {**correlation, **dict(payload.get("correlation") or {})}
    return payload


def lane_summary(lane: OrchestrationLane, *, recent_events: list[AgentSessionEvent] | None = None) -> str:
    session = lane.agent_session
    if session is not None and isinstance(session.continuation_summary, dict):
        summary = session.continuation_summary.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    for event in recent_events or []:
        if isinstance(event.summary, str) and event.summary.strip():
            return event.summary.strip()
    if session is not None and isinstance(session.wait_reason, str) and session.wait_reason.strip():
        return session.wait_reason.strip()
    if lane.state == "RetryPending" and lane.retry_due_at is not None:
        return f"Retry scheduled for {lane.retry_due_at.isoformat()}."
    if lane.state == "HandedOff" and lane.handoff_reason:
        return lane.handoff_reason
    if lane.last_error:
        return lane.last_error
    return f"Lane is {lane.state}."


def lane_heartbeat_status(lane: OrchestrationLane, *, now: datetime | None = None) -> str:
    observed_at = _ensure_utc(now) or _now()
    if lane.finished_at is not None or lane.state not in ACTIVE_LANE_OWNERSHIP_STATES:
        return "terminal"
    if lane.state in WAITING_LANE_STATES:
        return "waiting"
    if lane.state not in RUNNER_HEALTH_LANE_STATES:
        return "active"

    timeout = get_settings().runner_heartbeat_timeout_seconds
    session = lane.agent_session
    environment = lane.execution_environment
    freshest = max(
        (
            value
            for value in (
                _ensure_utc(session.heartbeat_at) if session is not None else None,
                _ensure_utc(session.last_event_at) if session is not None else None,
                _ensure_utc(environment.heartbeat_at) if environment is not None else None,
                _ensure_utc(lane.started_at),
                _ensure_utc(lane.claimed_at),
            )
            if value is not None
        ),
        default=None,
    )
    if freshest is None:
        return "unknown"
    return "stale" if (observed_at - freshest).total_seconds() > timeout else "healthy"


class ObservabilityService:
    def __init__(self, session: Session):
        self.session = session

    def get_fleet_observability(self) -> FleetObservabilityResponse:
        generated_at = _now()
        lanes = self._lane_query().order_by(OrchestrationLane.updated_at.desc()).all()
        notifications = self._fleet_notifications(lanes=lanes, observed_at=generated_at)
        lane_summaries = [
            self._lane_status_summary(lane)
            for lane in sorted(lanes, key=lambda item: item.updated_at or item.created_at, reverse=True)[:20]
        ]
        delivery_lag = self._delivery_lag_seconds(generated_at)

        return FleetObservabilityResponse(
            generated_at=generated_at,
            queue_depth=SchedulerService(self.session).eligible_queue_depth(),
            active_lane_count=sum(1 for lane in lanes if lane.state in ACTIVE_LANE_OWNERSHIP_STATES),
            retry_backlog_count=sum(1 for lane in lanes if lane.state == "RetryPending"),
            dead_letter_backlog_count=self.session.query(WebhookDelivery).filter(WebhookDelivery.status == "dead-letter").count(),
            mirror_lag_seconds=delivery_lag,
            stale_heartbeat_count=sum(1 for lane in lanes if lane_heartbeat_status(lane, now=generated_at) == "stale"),
            lane_state_counts=dict(sorted(Counter(lane.state for lane in lanes).items())),
            notification_count=len(notifications),
            notifications=notifications,
            lanes=lane_summaries,
        )

    def get_lane_observability(self, lane_id) -> LaneObservabilityResponse:
        lane = self._lane_query().filter(OrchestrationLane.lane_id == lane_id).one_or_none()
        if lane is None:
            raise ValueError(f"Lane not found: {lane_id}")
        from agent_core_platform_api.operator_api import OperatorAPIService

        session_events = (
            self.session.query(AgentSessionEvent)
            .filter(AgentSessionEvent.lane_id == lane.lane_id)
            .order_by(AgentSessionEvent.observed_at.desc(), AgentSessionEvent.sequence.desc())
            .limit(20)
            .all()
        )
        signals = (
            self.session.query(OperationalSignal)
            .filter(
                OperationalSignal.target_kind.in_(["lane", "product", "webhook_delivery"]),
                func.json_extract(OperationalSignal.value, "$.correlation.lane_id") == str(lane.lane_id),
            )
            .order_by(OperationalSignal.observed_at.desc())
            .limit(20)
            .all()
        )
        lane_notifications = [item for item in self._fleet_notifications(lanes=[lane], observed_at=_now()) if item.target_id == str(lane.lane_id)]
        recent_activity = self._build_recent_activity(lane=lane, session_events=session_events, signals=signals)

        return LaneObservabilityResponse(
            lane=OperatorAPIService(self.session).get_lane(lane.lane_id),
            correlation=ObservabilityCorrelationResponse.model_validate(lane_signal_correlation(lane)),
            heartbeat_status=lane_heartbeat_status(lane),
            summary=lane_summary(lane, recent_events=session_events),
            last_activity_at=max(
                (
                    value
                    for value in (
                        _ensure_utc(lane.updated_at),
                        _ensure_utc(lane.agent_session.last_event_at) if lane.agent_session is not None else None,
                        _ensure_utc(lane.execution_environment.heartbeat_at) if lane.execution_environment is not None else None,
                    )
                    if value is not None
                ),
                default=None,
            ),
            recent_activity=recent_activity,
            notifications=lane_notifications,
            artifact_references=ObservabilityArtifactReferencesResponse(
                workspace_uri=lane.execution_environment.workspace_uri if lane.execution_environment is not None else None,
                artifact_uri=lane.execution_environment.artifact_uri if lane.execution_environment is not None else None,
                log_uri=lane.execution_environment.log_uri if lane.execution_environment is not None else None,
                cache_uri=lane.execution_environment.cache_uri if lane.execution_environment is not None else None,
            ),
        )

    def _lane_query(self):
        return self.session.query(OrchestrationLane).options(
            joinedload(OrchestrationLane.product),
            joinedload(OrchestrationLane.repo),
            joinedload(OrchestrationLane.work_item),
            joinedload(OrchestrationLane.execution_environment),
            joinedload(OrchestrationLane.agent_session),
        )

    def _delivery_lag_seconds(self, observed_at: datetime) -> int | None:
        oldest = (
            self.session.query(WebhookDelivery)
            .filter(
                WebhookDelivery.processed_at.is_(None),
                WebhookDelivery.status.notin_(["processed", "dead-letter"]),
            )
            .order_by(WebhookDelivery.received_at.asc())
            .first()
        )
        if oldest is None or oldest.received_at is None:
            return None
        return max(0, int((observed_at - _ensure_utc(oldest.received_at)).total_seconds()))

    def _lane_status_summary(self, lane: OrchestrationLane) -> LaneStatusSummaryResponse:
        return LaneStatusSummaryResponse(
            lane_id=lane.lane_id,
            product_id=lane.product_id,
            work_item_id=lane.work_item_id,
            issue_number=lane.work_item.issue_number if lane.work_item is not None else 0,
            title=lane.work_item.title if lane.work_item is not None else "",
            state=lane.state,
            attempt=lane.attempt,
            retry_due_at=lane.retry_due_at,
            heartbeat_status=lane_heartbeat_status(lane),
            summary=lane_summary(lane),
            updated_at=lane.updated_at,
        )

    def _fleet_notifications(
        self,
        *,
        lanes: list[OrchestrationLane],
        observed_at: datetime,
    ) -> list[ObservabilityNotificationResponse]:
        notifications: list[ObservabilityNotificationResponse] = []
        for lane in lanes:
            correlation = ObservabilityCorrelationResponse.model_validate(lane_signal_correlation(lane))
            if lane.state in WAITING_LANE_STATES:
                notifications.append(
                    ObservabilityNotificationResponse(
                        notification_type="blocked-lane",
                        severity="warning",
                        title="Lane is blocked awaiting operator action",
                        summary=lane_summary(lane),
                        observed_at=lane.updated_at,
                        target_kind="lane",
                        target_id=str(lane.lane_id),
                        source_kind="derived",
                        correlation=correlation,
                    )
                )
            if lane.state == "RetryPending" and lane.attempt >= 2:
                notifications.append(
                    ObservabilityNotificationResponse(
                        notification_type="repeated-retry",
                        severity="warning",
                        title="Lane has entered repeated retry handling",
                        summary=lane_summary(lane),
                        observed_at=lane.retry_due_at or lane.updated_at,
                        target_kind="lane",
                        target_id=str(lane.lane_id),
                        source_kind="derived",
                        correlation=correlation,
                    )
                )
            if lane.state == "HandedOff" or (lane.work_item is not None and lane.work_item.handoff_status == "in_review"):
                notifications.append(
                    ObservabilityNotificationResponse(
                        notification_type="ready-for-review",
                        severity="info",
                        title="Lane is ready for review handoff",
                        summary=lane_summary(lane),
                        observed_at=lane.finished_at or lane.updated_at,
                        target_kind="lane",
                        target_id=str(lane.lane_id),
                        source_kind="derived",
                        correlation=correlation,
                    )
                )

        if any(lane_heartbeat_status(lane, now=observed_at) == "stale" for lane in lanes):
            stale_lanes = [lane for lane in lanes if lane_heartbeat_status(lane, now=observed_at) == "stale"]
            lane = stale_lanes[0]
            notifications.append(
                ObservabilityNotificationResponse(
                    notification_type="heartbeat-degraded",
                    severity="error",
                    title="Runner heartbeat health is degraded",
                    summary=f"{len(stale_lanes)} lane(s) have stale runner heartbeats.",
                    observed_at=observed_at,
                    target_kind="lane",
                    target_id=str(lane.lane_id),
                    source_kind="derived",
                    correlation=ObservabilityCorrelationResponse.model_validate(lane_signal_correlation(lane)),
                )
            )

        dead_letters = (
            self.session.query(WebhookDelivery)
            .filter(WebhookDelivery.status == "dead-letter")
            .order_by(WebhookDelivery.received_at.desc())
            .all()
        )
        if dead_letters:
            latest_dead_letter = dead_letters[0]
            notifications.append(
                ObservabilityNotificationResponse(
                    notification_type="degraded-sync-health",
                    severity="error",
                    title="GitHub sync health is degraded",
                    summary=f"{len(dead_letters)} webhook deliveries are in the dead-letter backlog.",
                    observed_at=latest_dead_letter.received_at,
                    target_kind="webhook_delivery",
                    target_id=str(latest_dead_letter.delivery_id),
                    source_kind="derived",
                    correlation=ObservabilityCorrelationResponse.model_validate(delivery_signal_correlation(latest_dead_letter)),
                )
            )

        failed_baselines = self._failed_baseline_runs()
        for run in failed_baselines[:5]:
            notifications.append(
                ObservabilityNotificationResponse(
                    notification_type="baseline-upgrade-failed",
                    severity="warning",
                    title="Baseline upgrade requires operator attention",
                    summary=f"Latest standards upgrade for product {run.product.key} is {run.outcome_status or run.outcome_kind}.",
                    observed_at=run.updated_at or run.created_at,
                    target_kind="product",
                    target_id=str(run.product_id),
                    source_kind="derived",
                    correlation=ObservabilityCorrelationResponse.model_validate(product_signal_correlation(run.product)),
                )
            )

        notifications.sort(key=lambda item: _ensure_utc(item.observed_at) or observed_at, reverse=True)
        return notifications[:20]

    def _failed_baseline_runs(self) -> list[StandardsUpgradeRun]:
        runs = (
            self.session.query(StandardsUpgradeRun)
            .options(joinedload(StandardsUpgradeRun.product))
            .order_by(StandardsUpgradeRun.updated_at.desc(), StandardsUpgradeRun.created_at.desc())
            .all()
        )
        latest_by_product: dict[str, StandardsUpgradeRun] = {}
        for run in runs:
            key = str(run.product_id)
            latest_by_product.setdefault(key, run)
        return [
            run
            for run in latest_by_product.values()
            if (run.outcome_status or "").lower() in {"conflict", "failed"}
        ]

    def _build_recent_activity(
        self,
        *,
        lane: OrchestrationLane,
        session_events: list[AgentSessionEvent],
        signals: list[OperationalSignal],
    ) -> list[LaneActivityResponse]:
        activity: list[LaneActivityResponse] = []
        lane_correlation = ObservabilityCorrelationResponse.model_validate(lane_signal_correlation(lane))
        for event in session_events:
            activity.append(
                LaneActivityResponse(
                    kind="session_event",
                    event_type=event.event_type,
                    summary=event.summary,
                    severity="error" if event.event_type == "session_failed" else "info",
                    observed_at=event.observed_at,
                    source_kind="runner",
                    correlation=lane_correlation,
                    payload=event.payload,
                )
            )
        for signal in signals:
            signal_correlation = self._signal_correlation(signal, fallback=lane_signal_correlation(lane))
            activity.append(
                LaneActivityResponse(
                    kind="signal",
                    event_type=signal.signal_type,
                    summary=self._signal_summary(signal),
                    severity=signal.severity,
                    observed_at=signal.observed_at,
                    source_kind=signal.source_kind,
                    correlation=signal_correlation,
                    payload=signal.value,
                )
            )
        activity.sort(key=lambda item: _ensure_utc(item.observed_at) or _now(), reverse=True)
        return activity[:30]

    def _signal_summary(self, signal: OperationalSignal) -> str | None:
        if isinstance(signal.value, dict):
            for key in ("reason", "summary", "error", "message"):
                value = signal.value.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return signal.signal_type

    def _signal_correlation(
        self,
        signal: OperationalSignal,
        *,
        fallback: dict[str, str] | None = None,
    ) -> ObservabilityCorrelationResponse:
        correlation: dict[str, Any] = {}
        if isinstance(signal.value, dict) and isinstance(signal.value.get("correlation"), dict):
            correlation.update(signal.value["correlation"])
        if fallback:
            for key, value in fallback.items():
                correlation.setdefault(key, value)
        return ObservabilityCorrelationResponse.model_validate(correlation)
