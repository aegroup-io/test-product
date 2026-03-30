from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.models import AgentSessionEvent, OperationalSignal, Organization, WebhookDelivery
from agent_core_platform_api.observability import lane_signal_correlation
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.scheduler import SchedulerService
from orcha_api.main import app


def _configure_env(database_url: str) -> None:
    os.environ["AGENT_CORE_AUTH_DISABLED"] = "1"
    os.environ["AGENT_CORE_DATABASE_URL"] = database_url
    os.environ["AGENT_CORE_CRYPTO_SEED"] = "agent-core-test-seed"
    os.environ["AGENT_CORE_INITIAL_ORG_NAME"] = "Primary"
    os.environ["AGENT_CORE_INITIAL_ORG_SLUG"] = "primary"
    os.environ["AGENT_CORE_RUNNER_HEARTBEAT_TIMEOUT_SECONDS"] = "300"
    get_settings.cache_clear()
    reset_database_state()


def _reset_env() -> None:
    get_settings.cache_clear()
    reset_database_state()


def _seed_observability_fixture(session):
    now = datetime.now(timezone.utc)
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    product = store.create_product(
        org_id=org.org_id,
        key="atlas",
        name="Atlas",
        status="Active",
        setup_state="ready",
        baseline_channel="stable",
        standards_pack_key="default",
        standards_pack_version="1.0.0",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
        effective_config={
            "execution": {"profile": "standard-python", "max_concurrent_lanes": 4},
            "github": {"status_field": "Status", "ready_status": "Ready", "done_status": "Done"},
        },
        operator_overrides={},
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id="R_kgDOAtlas",
        owner="aegroup-io",
        name="atlas",
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="adopted",
        raw_payload={"clone_url": "https://example.invalid/atlas.git"},
    )
    pack = store.create_standards_pack(
        key="default",
        channel="stable",
        version="1.0.0",
        source_bundle="bundle://default",
        description="Default bundle",
        manifest={},
    )
    product.primary_repo_id = repo.repo_id
    session.flush()

    def create_work(issue_number: int, title: str, status: str = "Ready"):
        return store.create_work_item(
            repo_id=repo.repo_id,
            github_issue_node_id=f"I_{issue_number}",
            issue_number=issue_number,
            title=title,
            body=title,
            status=status,
            labels=[],
            assignees=[],
            dependencies=[],
            dependency_state="clear",
            priority_hint=None,
            linked_prs=[],
            eligibility_flags=["eligible"] if status == "Ready" else [],
            handoff_status="none",
            requires_repair=False,
            created_at=now - timedelta(days=1),
            updated_at=now,
        )

    running_item = create_work(302, "Runner summary", status="In Progress")
    retry_item = create_work(303, "Retry work", status="In Progress")
    approval_item = create_work(304, "Approval work", status="In Progress")
    handoff_item = create_work(305, "Review ready", status="In Progress")

    running_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=running_item.work_item_id,
        attempt=1,
        state="Running",
        claimed_at=now - timedelta(hours=2),
        started_at=now - timedelta(hours=2),
    )
    running_env = store.create_execution_environment(
        lane_id=running_lane.lane_id,
        runtime_provider="aks",
        container_image="runner:stable",
        status="Ready",
        workspace_uri="file:///tmp/running/workspace",
        artifact_uri="file:///tmp/running/artifacts",
        log_uri="file:///tmp/running/logs",
        cache_uri="file:///tmp/running/cache",
        heartbeat_at=now - timedelta(minutes=2),
        provider_metadata={},
    )
    running_lane.execution_environment_id = running_env.execution_environment_id
    running_session = store.create_agent_session(
        lane_id=running_lane.lane_id,
        thread_id="thread-1",
        turn_id="turn-3",
        status="running",
        capabilities=["stream-events"],
        last_event="status_summary",
        last_event_at=now - timedelta(minutes=2),
        heartbeat_at=now - timedelta(minutes=2),
        continuation_summary={"summary": "Ready to continue from the synthesized plan.", "updated_at": (now - timedelta(minutes=2)).isoformat()},
        requires_human_input=False,
    )
    running_lane.agent_session_id = running_session.agent_session_id
    session.add(
        AgentSessionEvent(
            agent_session_id=running_session.agent_session_id,
            lane_id=running_lane.lane_id,
            sequence=1,
            event_type="status_summary",
            summary="Ready to continue from the synthesized plan.",
            payload={"phase": "planning"},
            observed_at=now - timedelta(minutes=2),
        )
    )

    retry_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=retry_item.work_item_id,
        attempt=3,
        state="RetryPending",
        claimed_at=now - timedelta(hours=3),
        started_at=now - timedelta(hours=3),
        retry_due_at=now + timedelta(minutes=10),
        last_error="Runner heartbeat timed out while the lane was active.",
    )

    approval_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=approval_item.work_item_id,
        attempt=1,
        state="AwaitingApproval",
        claimed_at=now - timedelta(hours=1),
        started_at=now - timedelta(hours=1),
    )
    approval_session = store.create_agent_session(
        lane_id=approval_lane.lane_id,
        status="awaiting_approval",
        wait_reason="Need operator approval.",
        requires_human_input=False,
        capabilities=["approval-gates"],
        last_event="approval_requested",
        last_event_at=now - timedelta(minutes=30),
        heartbeat_at=now - timedelta(minutes=30),
        continuation_summary={},
    )
    approval_lane.agent_session_id = approval_session.agent_session_id

    handoff_item.handoff_status = "in_review"
    handoff_item.linked_prs = ["#99"]
    handoff_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=handoff_item.work_item_id,
        attempt=1,
        state="HandedOff",
        claimed_at=now - timedelta(hours=4),
        started_at=now - timedelta(hours=4),
        finished_at=now - timedelta(minutes=15),
        handoff_reason="PR #99 is ready for review.",
    )

    store.create_standards_upgrade_run(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        standards_pack_id=pack.standards_pack_id,
        source_bundle="bundle://default",
        source_version="1.0.0",
        outcome_kind="upgrade-pr",
        outcome_status="conflict",
        generated_pr_number=None,
        summary_payload={"summary": "Upgrade conflicted."},
    )

    queued_item = create_work(306, "Queued item", status="Ready")
    queued_item.updated_at = now - timedelta(minutes=5)

    delivery = WebhookDelivery(
        github_delivery_guid="delivery-1",
        event_name="issues",
        installation_id="12345",
        status="dead-letter",
        payload_hash="hash-1",
        received_at=now - timedelta(minutes=20),
        error_detail="projection failed",
    )
    lagging = WebhookDelivery(
        github_delivery_guid="delivery-2",
        event_name="issues",
        installation_id="12345",
        status="received",
        payload_hash="hash-2",
        received_at=now - timedelta(minutes=10),
    )
    session.add_all([delivery, lagging])
    session.flush()

    SchedulerService(session).transition_lane_state(
        running_lane.lane_id,
        "Running",
        reason="execution.workspace_ready",
        observed_at=now - timedelta(minutes=2),
    )
    session.commit()
    return {
        "running_lane_id": running_lane.lane_id,
        "running_lane": running_lane,
        "retry_lane_id": retry_lane.lane_id,
    }


def test_v1_observability_summary_and_lane_detail() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                fixture = _seed_observability_fixture(session)
                running_lane_id = fixture["running_lane_id"]
            finally:
                session.close()

            summary = client.get("/v1/observability/summary")
            assert summary.status_code == 200
            payload = summary.json()
            assert payload["queue_depth"] == 1
            assert payload["retry_backlog_count"] == 1
            assert payload["dead_letter_backlog_count"] == 1
            notification_types = {item["notification_type"] for item in payload["notifications"]}
            assert "blocked-lane" in notification_types
            assert "repeated-retry" in notification_types
            assert "degraded-sync-health" in notification_types
            assert "baseline-upgrade-failed" in notification_types
            assert any(item["summary"] == "Ready to continue from the synthesized plan." for item in payload["lanes"])

            lane = client.get(f"/v1/observability/lanes/{running_lane_id}")
            assert lane.status_code == 200
            lane_payload = lane.json()
            assert lane_payload["summary"] == "Ready to continue from the synthesized plan."
            assert lane_payload["heartbeat_status"] == "healthy"
            assert lane_payload["artifact_references"]["workspace_uri"] == "file:///tmp/running/workspace"
            assert lane_payload["correlation"]["lane_id"] == str(running_lane_id)
            assert any(item["kind"] == "session_event" and item["event_type"] == "status_summary" for item in lane_payload["recent_activity"])
            assert any(item["kind"] == "signal" and item["event_type"] == "lane.state_transition" for item in lane_payload["recent_activity"])
        _reset_env()


def test_structured_lane_signals_include_correlation_metadata() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                fixture = _seed_observability_fixture(session)
                lane = session.get(type(fixture["running_lane"]), fixture["running_lane_id"])
                signal = (
                    session.query(OperationalSignal)
                    .filter(OperationalSignal.signal_type == "lane.state_transition")
                    .order_by(OperationalSignal.observed_at.desc())
                    .first()
                )
                assert signal is not None
                assert signal.value["correlation"] == lane_signal_correlation(lane)
            finally:
                session.close()
        _reset_env()
