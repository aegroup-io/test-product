from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified

from agent_core_platform_api.models import (
    ACTIVE_LANE_OWNERSHIP_STATES,
    OperationalSignal,
    OrchestrationLane,
    Product,
    RepositoryBinding,
    Setting,
    WorkItem,
)


SCHEDULER_LIMITS_SETTING_KEY = "orcha.scheduler_limits"
SCHEDULER_TICK_LOCK_SETTING_KEY = "orcha.scheduler_tick_lock"
PLATFORM_SETTINGS_SCOPE_ID = "global"
CAPACITY_CONSUMING_LANE_STATES = (
    "Queued",
    "Claimed",
    "Provisioning",
    "Running",
    "AwaitingApproval",
    "AwaitingGitHub",
    "RetryPending",
)
TERMINAL_LANE_STATES = {"HandedOff", "Cancelled", "FailedTerminal"}
DISQUALIFYING_LABELS = {"blocked", "needs-decision", "needs decision"}
_PRIORITY_RANKS = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _casefold(value: str | None) -> str:
    return value.strip().casefold() if isinstance(value, str) and value.strip() else ""


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, str):
        try:
            return _ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _coerce_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value)
        return parsed if parsed >= 1 else None
    return None


@dataclass(slots=True)
class SchedulerCandidate:
    work_item: WorkItem
    repo: RepositoryBinding
    product: Product
    ready_at: datetime
    work_item_priority: int
    product_priority: int | None
    execution_profile: str


@dataclass(slots=True)
class CapacityUsage:
    global_active: int
    org_active: Counter[str]
    product_active: Counter[str]
    repo_active: Counter[str]
    profile_active: Counter[str]


class SchedulerService:
    def __init__(self, session: Session):
        self.session = session

    def run_eligibility_tick(self, *, max_claims: int | None = None) -> list[OrchestrationLane]:
        self._acquire_tick_lock()
        usage = self._load_capacity_usage()
        ordered_candidates = self._ordered_candidates()

        claimed: list[OrchestrationLane] = []
        for candidate in ordered_candidates:
            if max_claims is not None and len(claimed) >= max_claims:
                break
            if not self._has_capacity(candidate, usage):
                continue
            lane = self.claim_work_item(candidate.work_item.work_item_id)
            if lane is None:
                continue
            claimed.append(lane)
            self._consume_capacity(candidate, usage)
        return claimed

    def claim_work_item(self, work_item_id: UUID) -> OrchestrationLane | None:
        work_item = (
            self.session.query(WorkItem)
            .options(
                joinedload(WorkItem.repo).joinedload(RepositoryBinding.product),
                selectinload(WorkItem.project_items),
                selectinload(WorkItem.lanes),
            )
            .filter(WorkItem.work_item_id == work_item_id)
            .one_or_none()
        )
        if work_item is None or work_item.repo is None or work_item.repo.product is None:
            return None
        if not self._is_dispatch_eligible(work_item, work_item.repo, work_item.repo.product):
            return None
        if self._has_active_lane(work_item):
            return None

        claim_time = _now()
        lane = OrchestrationLane(
            product_id=work_item.repo.product.product_id,
            repo_id=work_item.repo.repo_id,
            work_item_id=work_item.work_item_id,
            attempt=self._next_attempt(work_item.work_item_id),
            state="Queued",
            branch_name=f"orcha/issue-{work_item.issue_number}",
        )

        savepoint = self.session.begin_nested()
        try:
            self.session.add(lane)
            self.session.flush()
            self._record_transition(
                lane,
                from_state=None,
                to_state="Queued",
                reason="scheduler.claim.queued",
                observed_at=claim_time,
            )
            self.transition_lane_state(
                lane.lane_id,
                "Claimed",
                reason="scheduler.claimed",
                observed_at=claim_time,
            )
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
            self.session.expire_all()
            return None

        self.session.refresh(lane)
        return lane

    def transition_lane_state(
        self,
        lane_id: UUID,
        new_state: str,
        *,
        reason: str | None = None,
        error_detail: str | None = None,
        retry_due_at: datetime | None = None,
        observed_at: datetime | None = None,
        source_kind: str = "scheduler",
    ) -> OrchestrationLane:
        lane = self.session.get(OrchestrationLane, lane_id)
        if lane is None:
            raise ValueError(f"Lane not found: {lane_id}")

        timestamp = observed_at or _now()
        previous_state = lane.state
        lane.state = new_state

        if new_state == "Claimed":
            lane.claimed_at = lane.claimed_at or timestamp
        if new_state in {"Provisioning", "Running", "AwaitingApproval", "AwaitingGitHub"}:
            lane.started_at = lane.started_at or timestamp
        if new_state == "RetryPending":
            lane.retry_due_at = retry_due_at
        elif retry_due_at is not None:
            lane.retry_due_at = retry_due_at
        if new_state in TERMINAL_LANE_STATES:
            lane.finished_at = timestamp
            lane.retry_due_at = None
        if new_state == "HandedOff" and reason:
            lane.handoff_reason = reason
        if error_detail is not None:
            lane.last_error = error_detail

        self._record_transition(
            lane,
            from_state=previous_state,
            to_state=new_state,
            reason=reason,
            observed_at=timestamp,
            source_kind=source_kind,
        )
        self.session.flush()
        return lane

    def is_dispatch_eligible(self, work_item: WorkItem, repo: RepositoryBinding, product: Product) -> bool:
        return self._is_dispatch_eligible(work_item, repo, product)

    def eligible_queue_depth(self) -> int:
        return len(self._ordered_candidates())

    def _ordered_candidates(self) -> list[SchedulerCandidate]:
        active_lane_exists = (
            self.session.query(OrchestrationLane.lane_id)
            .filter(
                OrchestrationLane.work_item_id == WorkItem.work_item_id,
                OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES),
            )
            .exists()
        )
        work_items = (
            self.session.query(WorkItem)
            .join(RepositoryBinding, RepositoryBinding.repo_id == WorkItem.repo_id)
            .join(Product, Product.product_id == RepositoryBinding.product_id)
            .options(
                joinedload(WorkItem.repo).joinedload(RepositoryBinding.product),
                selectinload(WorkItem.project_items),
            )
            .filter(
                Product.status == "Active",
                RepositoryBinding.is_archived.is_(False),
                WorkItem.closed_at.is_(None),
                WorkItem.status == "Ready",
                WorkItem.dependency_state == "clear",
                WorkItem.requires_repair.is_(False),
                ~active_lane_exists,
            )
            .all()
        )

        candidates = [
            self._to_candidate(work_item)
            for work_item in work_items
            if work_item.repo is not None
            and work_item.repo.product is not None
            and self._is_dispatch_eligible(work_item, work_item.repo, work_item.repo.product)
        ]
        return self._apply_product_fairness(candidates)

    def _to_candidate(self, work_item: WorkItem) -> SchedulerCandidate:
        repo = work_item.repo
        assert repo is not None
        product = repo.product
        assert product is not None
        return SchedulerCandidate(
            work_item=work_item,
            repo=repo,
            product=product,
            ready_at=self._ready_timestamp(work_item, repo),
            work_item_priority=self._priority_rank(work_item.priority_hint),
            product_priority=self._product_priority(product),
            execution_profile=self._execution_profile(product),
        )

    def _apply_product_fairness(self, candidates: list[SchedulerCandidate]) -> list[SchedulerCandidate]:
        grouped: dict[str, deque[SchedulerCandidate]] = defaultdict(deque)
        for candidate in sorted(
            candidates,
            key=lambda item: (item.product.product_id.hex, item.work_item_priority, item.ready_at, item.work_item.issue_number),
        ):
            grouped[str(candidate.product.product_id)].append(candidate)

        ordered: list[SchedulerCandidate] = []
        while grouped:
            product_ids = sorted(grouped, key=lambda product_id: self._product_sort_key(grouped[product_id][0]))
            for product_id in product_ids:
                ordered.append(grouped[product_id].popleft())
                if not grouped[product_id]:
                    del grouped[product_id]
        return ordered

    def _product_sort_key(self, candidate: SchedulerCandidate) -> tuple[int, int | datetime, datetime, str]:
        if candidate.product_priority is not None:
            return (0, candidate.product_priority, candidate.ready_at, candidate.product.key)
        return (1, candidate.ready_at, candidate.ready_at, candidate.product.key)

    def _is_dispatch_eligible(self, work_item: WorkItem, repo: RepositoryBinding, product: Product) -> bool:
        if product.status != "Active" or product.setup_state == "setup-needed":
            return False
        if repo.is_archived or work_item.closed_at is not None:
            return False
        if work_item.status != "Ready" or work_item.dependency_state != "clear" or work_item.requires_repair:
            return False
        if work_item.handoff_status not in {"none", "closed"}:
            return False
        if not self._execution_profile(product):
            return False
        normalized_labels = {_casefold(label) for label in work_item.labels or []}
        return not normalized_labels.intersection(DISQUALIFYING_LABELS)

    def _ready_timestamp(self, work_item: WorkItem, repo: RepositoryBinding) -> datetime:
        status_field_name = self._status_field_name(repo)
        for project_item in sorted(
            work_item.project_items,
            key=lambda item: _ensure_utc(item.last_reconciled_at) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        ):
            for field_value in project_item.field_values_payload or []:
                if _casefold(str(field_value.get("field_name") or "")) != _casefold(status_field_name):
                    continue
                ready_at = _coerce_datetime(field_value.get("updated_at"))
                if ready_at is not None:
                    return ready_at
        return _ensure_utc(work_item.updated_at) or _ensure_utc(work_item.created_at) or _now()

    def _status_field_name(self, repo: RepositoryBinding) -> str:
        product = repo.product
        if product is not None and isinstance(product.effective_config, dict):
            github = product.effective_config.get("github", {})
            if isinstance(github, dict):
                configured = github.get("status_field")
                if isinstance(configured, str) and configured.strip():
                    return configured.strip()
        return "Status"

    def _execution_profile(self, product: Product) -> str:
        if isinstance(product.effective_config, dict):
            execution = product.effective_config.get("execution", {})
            if isinstance(execution, dict):
                profile = execution.get("profile")
                if isinstance(profile, str) and profile.strip():
                    return profile.strip()
        return product.execution_profile or ""

    def _product_priority(self, product: Product) -> int | None:
        if not isinstance(product.effective_config, dict):
            return None
        for section_name in ("scheduling", "orchestration", "product"):
            section = product.effective_config.get(section_name, {})
            if not isinstance(section, dict):
                continue
            priority = _coerce_positive_int(section.get("priority"))
            if priority is not None:
                return priority
        return None

    def _priority_rank(self, priority_hint: str | None) -> int:
        return _PRIORITY_RANKS.get(_casefold(priority_hint), 99)

    def _load_capacity_usage(self) -> CapacityUsage:
        lanes = (
            self.session.query(OrchestrationLane)
            .options(joinedload(OrchestrationLane.product))
            .filter(OrchestrationLane.state.in_(CAPACITY_CONSUMING_LANE_STATES))
            .all()
        )

        org_active: Counter[str] = Counter()
        product_active: Counter[str] = Counter()
        repo_active: Counter[str] = Counter()
        profile_active: Counter[str] = Counter()
        for lane in lanes:
            repo_active[str(lane.repo_id)] += 1
            product_active[str(lane.product_id)] += 1
            if lane.product is not None:
                org_active[str(lane.product.org_id)] += 1
                profile = self._execution_profile(lane.product)
                if profile:
                    profile_active[profile] += 1

        return CapacityUsage(
            global_active=len(lanes),
            org_active=org_active,
            product_active=product_active,
            repo_active=repo_active,
            profile_active=profile_active,
        )

    def _has_capacity(self, candidate: SchedulerCandidate, usage: CapacityUsage) -> bool:
        platform_limits = self._load_limits("platform", PLATFORM_SETTINGS_SCOPE_ID)
        org_limits = self._load_limits("org", str(candidate.product.org_id))
        product_limits = self._load_limits("product", str(candidate.product.product_id))
        repo_limits = self._load_limits("repo", str(candidate.repo.repo_id))

        global_cap = _coerce_positive_int(platform_limits.get("max_active_lanes"))
        org_cap = _coerce_positive_int(org_limits.get("max_active_lanes"))
        repo_cap = _coerce_positive_int(repo_limits.get("max_active_lanes"))
        product_caps = [
            limit
            for limit in (
                _coerce_positive_int(product_limits.get("max_active_lanes")),
                self._product_config_cap(candidate.product),
            )
            if limit is not None
        ]
        product_cap = min(product_caps) if product_caps else None
        profile_cap = self._profile_cap(platform_limits, candidate.execution_profile)

        if global_cap is not None and usage.global_active >= global_cap:
            return False
        if org_cap is not None and usage.org_active[str(candidate.product.org_id)] >= org_cap:
            return False
        if product_cap is not None and usage.product_active[str(candidate.product.product_id)] >= product_cap:
            return False
        if repo_cap is not None and usage.repo_active[str(candidate.repo.repo_id)] >= repo_cap:
            return False
        if profile_cap is not None and usage.profile_active[candidate.execution_profile] >= profile_cap:
            return False
        return True

    def _product_config_cap(self, product: Product) -> int | None:
        if not isinstance(product.effective_config, dict):
            return None
        execution = product.effective_config.get("execution", {})
        if not isinstance(execution, dict):
            return None
        return _coerce_positive_int(execution.get("max_concurrent_lanes"))

    def _profile_cap(self, platform_limits: dict[str, Any], execution_profile: str) -> int | None:
        profiles = platform_limits.get("execution_profiles", {})
        if not isinstance(profiles, dict):
            return None
        profile_limits = profiles.get(execution_profile, {})
        if not isinstance(profile_limits, dict):
            return None
        return _coerce_positive_int(profile_limits.get("max_active_lanes"))

    def _load_limits(self, scope_type: str, scope_id: str) -> dict[str, Any]:
        setting = (
            self.session.query(Setting)
            .filter(
                Setting.scope_type == scope_type,
                Setting.scope_id == scope_id,
                Setting.key == SCHEDULER_LIMITS_SETTING_KEY,
            )
            .one_or_none()
        )
        if setting is None or not isinstance(setting.value_json, dict):
            return {}
        return dict(setting.value_json)

    def _acquire_tick_lock(self) -> None:
        timestamp = _now().isoformat()
        query = self.session.query(Setting).filter(
            Setting.scope_type == "platform",
            Setting.scope_id == PLATFORM_SETTINGS_SCOPE_ID,
            Setting.key == SCHEDULER_TICK_LOCK_SETTING_KEY,
        )
        setting = query.with_for_update().one_or_none()
        if setting is None:
            savepoint = self.session.begin_nested()
            try:
                setting = Setting(
                    scope_type="platform",
                    scope_id=PLATFORM_SETTINGS_SCOPE_ID,
                    key=SCHEDULER_TICK_LOCK_SETTING_KEY,
                    value_json={"last_tick_at": timestamp},
                )
                self.session.add(setting)
                self.session.flush()
                savepoint.commit()
                return
            except IntegrityError:
                savepoint.rollback()
                setting = query.with_for_update().one()

        payload = setting.value_json if isinstance(setting.value_json, dict) else {}
        setting.value_json = {**payload, "last_tick_at": timestamp}
        flag_modified(setting, "value_json")
        self.session.flush()

    def _consume_capacity(self, candidate: SchedulerCandidate, usage: CapacityUsage) -> None:
        usage.global_active += 1
        usage.org_active[str(candidate.product.org_id)] += 1
        usage.product_active[str(candidate.product.product_id)] += 1
        usage.repo_active[str(candidate.repo.repo_id)] += 1
        if candidate.execution_profile:
            usage.profile_active[candidate.execution_profile] += 1

    def _has_active_lane(self, work_item: WorkItem) -> bool:
        return (
            self.session.query(OrchestrationLane.lane_id)
            .filter(
                OrchestrationLane.work_item_id == work_item.work_item_id,
                OrchestrationLane.state.in_(ACTIVE_LANE_OWNERSHIP_STATES),
            )
            .first()
            is not None
        )

    def _next_attempt(self, work_item_id: UUID) -> int:
        max_attempt = (
            self.session.query(OrchestrationLane.attempt)
            .filter(OrchestrationLane.work_item_id == work_item_id)
            .order_by(OrchestrationLane.attempt.desc())
            .limit(1)
            .scalar()
        )
        return (max_attempt or 0) + 1

    def _record_transition(
        self,
        lane: OrchestrationLane,
        *,
        from_state: str | None,
        to_state: str,
        reason: str | None,
        observed_at: datetime,
        source_kind: str = "scheduler",
    ) -> None:
        signal_value = {
            "lane_id": str(lane.lane_id),
            "attempt": lane.attempt,
            "from_state": from_state,
            "to_state": to_state,
            "reason": reason,
            "work_item_id": str(lane.work_item_id),
            "correlation": {
                "lane_id": str(lane.lane_id),
                "work_item_id": str(lane.work_item_id),
                "repo_id": str(lane.repo_id),
                "product_id": str(lane.product_id),
                **({"org_id": str(lane.product.org_id)} if lane.product is not None else {}),
                **({"agent_session_id": str(lane.agent_session_id)} if lane.agent_session_id is not None else {}),
            },
        }
        self.session.add(
            OperationalSignal(
                target_kind="lane",
                target_id=str(lane.lane_id),
                signal_type="lane.state_transition",
                severity=self._transition_severity(to_state),
                value=signal_value,
                observed_at=observed_at,
                source_kind=source_kind,
            )
        )

    def _transition_severity(self, state: str) -> str:
        if state == "Cancelled":
            return "warning"
        if state == "FailedTerminal":
            return "error"
        return "info"
