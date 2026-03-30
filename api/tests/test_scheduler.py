from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.models import OperationalSignal, Organization, OrchestrationLane, Setting
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.scheduler import (
    PLATFORM_SETTINGS_SCOPE_ID,
    SCHEDULER_LIMITS_SETTING_KEY,
    SCHEDULER_TICK_LOCK_SETTING_KEY,
    SchedulerService,
)
from orcha_api.main import app


def _configure_env(database_url: str) -> None:
    os.environ["AGENT_CORE_AUTH_DISABLED"] = "1"
    os.environ["AGENT_CORE_DATABASE_URL"] = database_url
    os.environ["AGENT_CORE_CRYPTO_SEED"] = "agent-core-test-seed"
    os.environ["AGENT_CORE_INITIAL_ORG_NAME"] = "Primary"
    os.environ["AGENT_CORE_INITIAL_ORG_SLUG"] = "primary"
    get_settings.cache_clear()
    reset_database_state()


def _reset_env() -> None:
    get_settings.cache_clear()
    reset_database_state()


def _seed_product(session, *, key: str, max_concurrent_lanes: int = 4):
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    product = store.create_product(
        org_id=org.org_id,
        key=key,
        name=key.title(),
        status="Active",
        setup_state="ready",
        baseline_channel="stable",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
        effective_config={
            "github": {
                "status_field": "Status",
                "ready_status": "Ready",
                "done_status": "Done",
            },
            "execution": {
                "profile": "standard-python",
                "max_concurrent_lanes": max_concurrent_lanes,
            },
        },
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id=f"R_{key}",
        owner="aegroup-io",
        name=key,
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="seeded",
    )
    project = store.create_project_mirror(
        product_id=product.product_id,
        github_project_node_id=f"PVT_{key}",
        number=1,
        title=key.title(),
        status_field_name="Status",
        status_options=["Ready", "In Progress", "Done"],
        mirror_version=1,
    )
    product.primary_repo_id = repo.repo_id
    product.primary_project_id = project.project_id
    session.flush()
    return product, repo, project


def _seed_work_item(
    session,
    *,
    repo,
    project,
    issue_number: int,
    ready_at: datetime,
    labels: list[str] | None = None,
):
    store = OrchaStateStore(session)
    work_item = store.create_work_item(
        repo_id=repo.repo_id,
        project_id=project.project_id,
        github_issue_node_id=f"I_{repo.name}_{issue_number}",
        issue_number=issue_number,
        title=f"Work item {issue_number}",
        body="Tracks scheduler behavior",
        status="Ready",
        labels=labels or [],
        assignees=[],
        dependencies=[],
        dependency_state="clear",
        priority_hint=None,
        linked_prs=[],
        eligibility_flags=["eligible"],
        handoff_status="none",
        requires_repair=False,
        created_at=ready_at - timedelta(days=1),
        updated_at=ready_at,
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id=f"PVTI_{repo.name}_{issue_number}",
        github_content_node_id=work_item.github_issue_node_id,
        content_type="Issue",
        work_item_id=work_item.work_item_id,
        status_name="Ready",
        field_values_payload=[
            {
                "field_name": "Status",
                "value": "Ready",
                "updated_at": ready_at.isoformat(),
            }
        ],
        raw_payload={},
        last_reconciled_at=ready_at,
    )
    session.flush()
    return work_item


def _set_limits(session, *, scope_type: str, scope_id: str, payload: dict) -> None:
    setting = (
        session.query(Setting)
        .filter(
            Setting.scope_type == scope_type,
            Setting.scope_id == scope_id,
            Setting.key == SCHEDULER_LIMITS_SETTING_KEY,
        )
        .one_or_none()
    )
    if setting is None:
        session.add(
            Setting(
                scope_type=scope_type,
                scope_id=scope_id,
                key=SCHEDULER_LIMITS_SETTING_KEY,
                value_json=payload,
            )
        )
    else:
        setting.value_json = payload
    session.flush()


def test_scheduler_tick_balances_products_and_prefers_older_ready_items() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _, repo_a, project_a = _seed_product(session, key="alpha")
                _, repo_b, project_b = _seed_product(session, key="beta")
                base = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
                _seed_work_item(session, repo=repo_a, project=project_a, issue_number=11, ready_at=base)
                _seed_work_item(session, repo=repo_a, project=project_a, issue_number=12, ready_at=base + timedelta(days=2))
                _seed_work_item(session, repo=repo_b, project=project_b, issue_number=21, ready_at=base + timedelta(days=1))
                session.commit()

                claimed = SchedulerService(session).run_eligibility_tick(max_claims=3)
                session.commit()

                assert [(lane.repo.name, lane.work_item.issue_number) for lane in claimed] == [
                    ("alpha", 11),
                    ("beta", 21),
                    ("alpha", 12),
                ]
            finally:
                session.close()
        _reset_env()


def test_scheduler_tick_respects_scope_caps_and_lowered_limits() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, key="alpha", max_concurrent_lanes=2)
                base = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
                for issue_number in (31, 32, 33):
                    _seed_work_item(
                        session,
                        repo=repo,
                        project=project,
                        issue_number=issue_number,
                        ready_at=base + timedelta(hours=issue_number - 31),
                    )

                _set_limits(
                    session,
                    scope_type="platform",
                    scope_id=PLATFORM_SETTINGS_SCOPE_ID,
                    payload={
                        "max_active_lanes": 3,
                        "execution_profiles": {"standard-python": {"max_active_lanes": 2}},
                    },
                )
                _set_limits(
                    session,
                    scope_type="org",
                    scope_id=str(product.org_id),
                    payload={"max_active_lanes": 3},
                )
                _set_limits(
                    session,
                    scope_type="repo",
                    scope_id=str(repo.repo_id),
                    payload={"max_active_lanes": 2},
                )
                session.commit()

                service = SchedulerService(session)
                first_tick = service.run_eligibility_tick(max_claims=3)
                session.commit()

                assert [lane.work_item.issue_number for lane in first_tick] == [31, 32]

                _set_limits(
                    session,
                    scope_type="platform",
                    scope_id=PLATFORM_SETTINGS_SCOPE_ID,
                    payload={
                        "max_active_lanes": 2,
                        "execution_profiles": {"standard-python": {"max_active_lanes": 2}},
                    },
                )
                session.commit()

                second_tick = service.run_eligibility_tick(max_claims=3)
                session.commit()

                assert second_tick == []
            finally:
                session.close()
        _reset_env()


def test_active_lane_guard_blocks_duplicate_active_claims() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, key="alpha")
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=41,
                    ready_at=datetime(2026, 3, 14, 15, 0, tzinfo=timezone.utc),
                )
                store = OrchaStateStore(session)
                store.create_lane(
                    product_id=product.product_id,
                    repo_id=repo.repo_id,
                    work_item_id=work_item.work_item_id,
                    attempt=1,
                    state="Claimed",
                )
                session.commit()

                session.add(
                    OrchestrationLane(
                        product_id=product.product_id,
                        repo_id=repo.repo_id,
                        work_item_id=work_item.work_item_id,
                        attempt=2,
                        state="Queued",
                    )
                )
                with pytest.raises(IntegrityError):
                    session.commit()
                session.rollback()
            finally:
                session.close()
        _reset_env()


def test_retry_pending_lanes_consume_scheduler_capacity() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, key="alpha", max_concurrent_lanes=1)
                active_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=61,
                    ready_at=datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc),
                )
                pending_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=62,
                    ready_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
                )
                store = OrchaStateStore(session)
                store.create_lane(
                    product_id=product.product_id,
                    repo_id=repo.repo_id,
                    work_item_id=active_item.work_item_id,
                    attempt=1,
                    state="RetryPending",
                )
                _set_limits(
                    session,
                    scope_type="platform",
                    scope_id=PLATFORM_SETTINGS_SCOPE_ID,
                    payload={
                        "max_active_lanes": 1,
                        "execution_profiles": {"standard-python": {"max_active_lanes": 1}},
                    },
                )
                session.commit()

                claimed = SchedulerService(session).run_eligibility_tick(max_claims=1)
                session.commit()

                assert claimed == []
                assert (
                    session.query(OrchestrationLane)
                    .filter(OrchestrationLane.work_item_id == pending_item.work_item_id)
                    .count()
                    == 0
                )
            finally:
                session.close()
        _reset_env()


def test_scheduler_normalizes_naive_ready_timestamps() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _, repo, project = _seed_product(session, key="alpha")
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=63,
                    ready_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
                )
                project_item = work_item.project_items[0]
                project_item.field_values_payload = [
                    {
                        "field_name": "Status",
                        "value": "Ready",
                        "updated_at": "2026-03-15T12:00:00",
                    }
                ]
                project_item.last_reconciled_at = datetime(2026, 3, 15, 12, 0)
                work_item.updated_at = datetime(2026, 3, 15, 12, 0)
                session.commit()

                claimed = SchedulerService(session).run_eligibility_tick(max_claims=1)
                session.commit()

                assert [lane.work_item.issue_number for lane in claimed] == [63]
            finally:
                session.close()
        _reset_env()


def test_concurrent_scheduler_ticks_do_not_exceed_capacity_caps() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, key="alpha", max_concurrent_lanes=1)
                _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=71,
                    ready_at=datetime(2026, 3, 15, 13, 0, tzinfo=timezone.utc),
                )
                _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=72,
                    ready_at=datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
                )
                _set_limits(
                    session,
                    scope_type="platform",
                    scope_id=PLATFORM_SETTINGS_SCOPE_ID,
                    payload={
                        "max_active_lanes": 1,
                        "execution_profiles": {"standard-python": {"max_active_lanes": 1}},
                    },
                )
                session.add(
                    Setting(
                        scope_type="platform",
                        scope_id=PLATFORM_SETTINGS_SCOPE_ID,
                        key=SCHEDULER_TICK_LOCK_SETTING_KEY,
                        value_json={"last_tick_at": None},
                    )
                )
                session.commit()
            finally:
                session.close()

            barrier = threading.Barrier(2)
            claimed_issue_numbers: list[list[int]] = []
            errors: list[str] = []

            def _run_tick() -> None:
                worker_session = get_session_factory()()
                try:
                    barrier.wait(timeout=10)
                    claims = SchedulerService(worker_session).run_eligibility_tick(max_claims=1)
                    worker_session.commit()
                    claimed_issue_numbers.append([lane.work_item.issue_number for lane in claims])
                except Exception as exc:  # noqa: BLE001 - test captures unexpected concurrency failures
                    worker_session.rollback()
                    errors.append(str(exc))
                finally:
                    worker_session.close()

            first = threading.Thread(target=_run_tick)
            second = threading.Thread(target=_run_tick)
            first.start()
            second.start()
            first.join(timeout=10)
            second.join(timeout=10)

            assert not first.is_alive()
            assert not second.is_alive()
            assert errors == []
            assert sum(len(result) for result in claimed_issue_numbers) == 1

            verify = get_session_factory()()
            try:
                active_lanes = (
                    verify.query(OrchestrationLane)
                    .filter(OrchestrationLane.state.in_(("Queued", "Claimed")))
                    .count()
                )
                assert active_lanes == 1
            finally:
                verify.close()
        _reset_env()


def test_lane_transitions_persist_handoff_and_cancellation_reasons() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _, repo, project = _seed_product(session, key="alpha")
                first_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=51,
                    ready_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
                )
                second_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=52,
                    ready_at=datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
                )
                session.commit()

                service = SchedulerService(session)
                handoff_lane = service.claim_work_item(first_item.work_item_id)
                cancelled_lane = service.claim_work_item(second_item.work_item_id)
                assert handoff_lane is not None
                assert cancelled_lane is not None

                service.transition_lane_state(
                    handoff_lane.lane_id,
                    "HandedOff",
                    reason="pull-request-opened",
                )
                service.transition_lane_state(
                    cancelled_lane.lane_id,
                    "Cancelled",
                    reason="operator-cancelled",
                )
                session.commit()

                persisted_handoff = session.get(OrchestrationLane, handoff_lane.lane_id)
                persisted_cancelled = session.get(OrchestrationLane, cancelled_lane.lane_id)
                assert persisted_handoff is not None
                assert persisted_cancelled is not None
                assert persisted_handoff.handoff_reason == "pull-request-opened"
                assert persisted_handoff.finished_at is not None
                assert persisted_cancelled.finished_at is not None

                signals = (
                    session.query(OperationalSignal)
                    .filter(OperationalSignal.signal_type == "lane.state_transition")
                    .order_by(OperationalSignal.observed_at.asc())
                    .all()
                )
                reasons = [signal.value.get("reason") for signal in signals if isinstance(signal.value, dict)]
                assert "pull-request-opened" in reasons
                assert "operator-cancelled" in reasons
            finally:
                session.close()
        _reset_env()
