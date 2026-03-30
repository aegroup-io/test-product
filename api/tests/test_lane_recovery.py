from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import tempfile

from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.execution_runtime import ExecutionEnvironmentService
from agent_core_platform_api.lane_recovery import LaneRecoveryService, RetryPolicy
from agent_core_platform_api.models import ExecutionEnvironment, OperationalSignal, Organization, OrchestrationLane
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.scheduler import SchedulerService
from orcha_api.main import app


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _configure_env(database_url: str, *, remote_execution_root: Path) -> None:
    os.environ["AGENT_CORE_AUTH_DISABLED"] = "1"
    os.environ["AGENT_CORE_DATABASE_URL"] = database_url
    os.environ["AGENT_CORE_CRYPTO_SEED"] = "agent-core-test-seed"
    os.environ["AGENT_CORE_INITIAL_ORG_NAME"] = "Primary"
    os.environ["AGENT_CORE_INITIAL_ORG_SLUG"] = "primary"
    os.environ["AGENT_CORE_REMOTE_EXECUTION_ROOT"] = str(remote_execution_root)
    os.environ["AGENT_CORE_RUNTIME_PROVIDER_NAMESPACE"] = "test-namespace"
    get_settings.cache_clear()
    reset_database_state()


def _reset_env() -> None:
    get_settings.cache_clear()
    reset_database_state()


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run(*args: str) -> str:
    result = subprocess.run(list(args), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _build_remote_repo(root: Path) -> tuple[Path, str]:
    bare_repo = root / "remote.git"
    source_repo = root / "source"
    _run("git", "init", "--bare", str(bare_repo))
    _run("git", "init", "--initial-branch=dev", str(source_repo))
    _git(source_repo, "config", "user.email", "test@example.com")
    _git(source_repo, "config", "user.name", "Test User")
    (source_repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(source_repo, "add", "README.md")
    _git(source_repo, "commit", "-m", "Initial commit")
    _git(source_repo, "remote", "add", "origin", bare_repo.as_uri())
    _git(source_repo, "push", "-u", "origin", "dev")
    return source_repo, bare_repo.as_uri()


def _seed_product(session, *, clone_url: str, key: str = "orcha", max_concurrent_lanes: int = 4):
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
                "container_image": "ghcr.io/aegroup/agent-core-runner:stable",
                "workspace_strategy": "branch-per-lane",
                "max_concurrent_lanes": max_concurrent_lanes,
            },
            "activation": {"required_secret_keys": []},
        },
        operator_overrides={},
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id=f"R_{key}",
        owner="aegroup-io",
        name=key,
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="adopted",
        raw_payload={"clone_url": clone_url},
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
    status: str = "Ready",
):
    store = OrchaStateStore(session)
    work_item = store.create_work_item(
        repo_id=repo.repo_id,
        project_id=project.project_id,
        github_issue_node_id=f"I_{repo.name}_{issue_number}",
        issue_number=issue_number,
        title=f"Work item {issue_number}",
        body="Tracks recovery behavior",
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
        created_at=ready_at - timedelta(days=1),
        updated_at=ready_at,
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id=f"PVTI_{repo.name}_{issue_number}",
        github_content_node_id=work_item.github_issue_node_id,
        content_type="Issue",
        work_item_id=work_item.work_item_id,
        status_name=status,
        field_values_payload=[
            {
                "field_name": "Status",
                "value": status,
                "updated_at": ready_at.isoformat(),
            }
        ],
        raw_payload={},
        last_reconciled_at=ready_at,
    )
    session.flush()
    return work_item


def _seed_lane(session, *, product, repo, work_item, attempt: int = 1, state: str = "Claimed", claimed_at: datetime):
    store = OrchaStateStore(session)
    lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=work_item.work_item_id,
        attempt=attempt,
        state=state,
        claimed_at=claimed_at,
        started_at=claimed_at if state in {"Provisioning", "Running", "AwaitingApproval", "AwaitingGitHub"} else None,
    )
    session.flush()
    return lane


def _provision_lane(session, lane_id) -> ExecutionEnvironment:
    environment = ExecutionEnvironmentService(session).provision_claimed_lane(lane_id)
    session.flush()
    return environment


def test_transient_failures_move_lanes_to_retry_pending_with_visible_retry_time() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=temp_path / "remote-execution")
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=22,
                    ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                lane = _seed_lane(
                    session,
                    product=product,
                    repo=repo,
                    work_item=work_item,
                    claimed_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                SchedulerService(session).transition_lane_state(
                    lane.lane_id,
                    "Running",
                    reason="test.setup",
                    observed_at=datetime(2026, 3, 16, 12, 1, tzinfo=timezone.utc),
                )
                observed_at = datetime(2026, 3, 16, 12, 5, tzinfo=timezone.utc)

                decision = LaneRecoveryService(
                    session,
                    policy=RetryPolicy(base_delay_seconds=120, max_delay_seconds=600, jitter_ratio=0.0, max_attempts=3),
                ).handle_lane_failure(
                    lane.lane_id,
                    failure_kind="runtime.transient",
                    reason="pod eviction",
                    observed_at=observed_at,
                )
                session.commit()
                session.refresh(lane)

                assert decision.retryable is True
                assert decision.retry_due_at == observed_at + timedelta(seconds=120)
                assert lane.state == "RetryPending"
                assert _as_utc(lane.retry_due_at) == observed_at + timedelta(seconds=120)
                assert lane.last_error == "pod eviction"
            finally:
                session.close()
        _reset_env()


def test_retryable_failures_cap_out_at_terminal_attempt_limit() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=temp_path / "remote-execution")
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=23,
                    ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                lane = _seed_lane(
                    session,
                    product=product,
                    repo=repo,
                    work_item=work_item,
                    attempt=3,
                    claimed_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                SchedulerService(session).transition_lane_state(
                    lane.lane_id,
                    "Running",
                    reason="test.setup",
                    observed_at=datetime(2026, 3, 16, 12, 1, tzinfo=timezone.utc),
                )

                decision = LaneRecoveryService(
                    session,
                    policy=RetryPolicy(base_delay_seconds=120, max_delay_seconds=600, jitter_ratio=0.0, max_attempts=3),
                ).handle_lane_failure(
                    lane.lane_id,
                    failure_kind="runtime.transient",
                    reason="repeated pod eviction",
                    observed_at=datetime(2026, 3, 16, 12, 5, tzinfo=timezone.utc),
                )
                session.commit()
                session.refresh(lane)

                assert decision.retryable is False
                assert lane.state == "FailedTerminal"
                assert lane.retry_due_at is None
                assert lane.last_error == "repeated pod eviction"
            finally:
                session.close()
        _reset_env()


def test_reconcile_retries_running_lanes_with_stale_heartbeats() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=24,
                    ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                lane = _seed_lane(
                    session,
                    product=product,
                    repo=repo,
                    work_item=work_item,
                    claimed_at=datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc),
                )
                environment = _provision_lane(session, lane.lane_id)
                SchedulerService(session).transition_lane_state(
                    lane.lane_id,
                    "Running",
                    reason="test.handshake_completed",
                    observed_at=datetime(2026, 3, 16, 9, 1, tzinfo=timezone.utc),
                )
                lane.started_at = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
                environment.created_at = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
                environment.heartbeat_at = datetime(2026, 3, 16, 9, 15, tzinfo=timezone.utc)

                summary = LaneRecoveryService(
                    session,
                    policy=RetryPolicy(base_delay_seconds=60, max_delay_seconds=300, jitter_ratio=0.0, stale_heartbeat_after_seconds=300),
                ).reconcile_active_lanes(now=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc))
                session.commit()
                session.refresh(lane)

                assert summary.retried == 1
                assert lane.state == "RetryPending"
                assert lane.last_error == "Runner heartbeat timed out while the lane was active."
                assert _as_utc(lane.retry_due_at) == datetime(2026, 3, 16, 12, 1, tzinfo=timezone.utc)
            finally:
                session.close()
        _reset_env()


def test_reconcile_cancels_lanes_that_lose_dispatch_eligibility() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=25,
                    ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                lane = _seed_lane(
                    session,
                    product=product,
                    repo=repo,
                    work_item=work_item,
                    claimed_at=datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc),
                )
                environment = _provision_lane(session, lane.lane_id)
                workspace_path = Path(environment.workspace_uri.removeprefix("file://"))
                work_item.status = "Blocked"
                work_item.eligibility_flags = ["blocked:dependencies"]

                summary = LaneRecoveryService(session).reconcile_active_lanes(
                    now=datetime(2026, 3, 16, 12, 5, tzinfo=timezone.utc)
                )
                session.commit()
                session.refresh(lane)
                session.refresh(environment)

                assert summary.cancelled == 1
                assert lane.state == "Cancelled"
                assert environment.status == "Terminated"
                assert not workspace_path.exists()
            finally:
                session.close()
        _reset_env()


def test_startup_recovery_resumes_due_retry_attempts_from_durable_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=temp_path / "remote-execution")
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=26,
                    ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                lane = _seed_lane(
                    session,
                    product=product,
                    repo=repo,
                    work_item=work_item,
                    claimed_at=datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc),
                )
                retry_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
                SchedulerService(session).transition_lane_state(
                    lane.lane_id,
                    "RetryPending",
                    reason="runtime.transient",
                    error_detail="retry me",
                    retry_due_at=retry_due_at,
                    observed_at=datetime(2026, 3, 16, 11, 5, tzinfo=timezone.utc),
                    source_kind="recovery",
                )
                session.commit()
            finally:
                session.close()

        with TestClient(app):
            session = get_session_factory()()
            try:
                lanes = (
                    session.query(OrchestrationLane)
                    .order_by(OrchestrationLane.attempt.asc(), OrchestrationLane.created_at.asc())
                    .all()
                )
                assert [lane.attempt for lane in lanes] == [1, 2]
                assert [lane.state for lane in lanes] == ["Cancelled", "Claimed"]
                assert lanes[0].last_error == "retry me"
            finally:
                session.close()
        _reset_env()


def test_startup_recovery_cleans_orphaned_active_environments() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                work_item = _seed_work_item(
                    session,
                    repo=repo,
                    project=project,
                    issue_number=27,
                    ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                )
                lane = _seed_lane(
                    session,
                    product=product,
                    repo=repo,
                    work_item=work_item,
                    claimed_at=datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc),
                )
                environment = _provision_lane(session, lane.lane_id)
                workspace_path = Path(environment.workspace_uri.removeprefix("file://"))
                lane.state = "HandedOff"
                session.commit()
                assert workspace_path.exists()
            finally:
                session.close()

        with TestClient(app):
            session = get_session_factory()()
            try:
                environment = session.query(ExecutionEnvironment).one()
                assert environment.status == "Terminated"
                assert environment.terminated_at is not None
            finally:
                session.close()
        _reset_env()


def test_reconcile_quarantines_products_after_repeated_contract_violations() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, repo, project = _seed_product(session, clone_url=clone_url)
                for issue_number in (31, 32, 33):
                    work_item = _seed_work_item(
                        session,
                        repo=repo,
                        project=project,
                        issue_number=issue_number,
                        ready_at=datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=issue_number),
                    )
                    lane = _seed_lane(
                        session,
                        product=product,
                        repo=repo,
                        work_item=work_item,
                        claimed_at=datetime(2026, 3, 16, 11, 0, tzinfo=timezone.utc),
                    )
                    _provision_lane(session, lane.lane_id)

                updated_config = deepcopy(product.effective_config)
                updated_config["execution"]["container_image"] = "ghcr.io/aegroup/agent-core-runner:candidate"
                product.effective_config = updated_config

                summary = LaneRecoveryService(session).reconcile_active_lanes(
                    now=datetime(2026, 3, 16, 12, 30, tzinfo=timezone.utc)
                )
                session.commit()
                session.refresh(product)

                lanes = session.query(OrchestrationLane).order_by(OrchestrationLane.attempt.asc()).all()
                signals = session.query(OperationalSignal).filter(OperationalSignal.signal_type == "product.quarantined").all()

                assert summary.failed == 3
                assert summary.quarantined_products == 1
                assert product.status == "Quarantined"
                assert product.setup_state == "setup-needed"
                assert all(lane.state == "FailedTerminal" for lane in lanes)
                assert len(signals) == 1
            finally:
                session.close()
        _reset_env()
