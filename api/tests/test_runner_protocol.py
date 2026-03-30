from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

import agent_core_platform_api.runner_protocol as runner_protocol_module
from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.execution_runtime import ExecutionEnvironmentService
from agent_core_platform_api.models import Organization, Secret
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.runner_protocol import (
    RunnerHandshake,
    RunnerProtocolError,
    RunnerProtocolService,
    RuntimeEvent,
)
from agent_core_platform_api.work_item_normalization import (
    RUNNER_CAPABILITY_REPAIR_REASON,
    RUNNER_HANDSHAKE_TIMEOUT_REPAIR_REASON,
    RUNNER_HEARTBEAT_TIMEOUT_REPAIR_REASON,
)
from agent_core_platform_api.secret_crypto import encrypt_secret
from orcha_api.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _seed_claimed_lane(
    session,
    *,
    clone_url: str,
    issue_number: int,
    title: str,
):
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    effective_config = {
        "execution": {
            "profile": "standard-python",
            "container_image": "ghcr.io/aegroup/agent-core-runner:stable",
            "workspace_strategy": "branch-per-lane",
            "max_concurrent_lanes": 4,
        },
        "activation": {
            "required_secret_keys": [],
        },
    }
    product = store.create_product(
        org_id=org.org_id,
        key="orcha",
        name="Orcha",
        status="Active",
        baseline_channel="stable",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
        setup_state="adopted",
        effective_config=deepcopy(effective_config),
        operator_overrides={},
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id=f"R_kgDOFixture{issue_number}",
        owner="aegroup-io",
        name="orcha",
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="adopted",
        raw_payload={"clone_url": clone_url},
    )
    work_item = store.create_work_item(
        repo_id=repo.repo_id,
        github_issue_node_id=f"I_kwDOFixture{issue_number}",
        issue_number=issue_number,
        title=title,
        body=f"Fixture lane for issue {issue_number}.",
        status="Ready",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        linked_prs=[],
    )
    lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=work_item.work_item_id,
        attempt=1,
        state="Claimed",
        claimed_at=_now(),
    )
    session.flush()
    return lane


def _provision_lane(session, *, clone_url: str, issue_number: int, title: str):
    lane = _seed_claimed_lane(session, clone_url=clone_url, issue_number=issue_number, title=title)
    environment = ExecutionEnvironmentService(session).provision_claimed_lane(lane.lane_id)
    session.flush()
    return lane, environment


def _prepare_and_handshake(
    session,
    *,
    clone_url: str,
    issue_number: int = 15,
    policy: dict | None = None,
):
    lane, environment = _provision_lane(
        session,
        clone_url=clone_url,
        issue_number=issue_number,
        title="Integrate the agent-core runner protocol",
    )
    service = RunnerProtocolService(session)
    launch_request = service.prepare_lane_session(
        lane.lane_id,
        instruction_bundle={
            "system_prompt": "Operate within repo policy.",
            "task": f"Work issue {issue_number}.",
        },
        policy=policy or {"approval_posture": "operator-gated"},
        secret_references=["github/app", "openai/runtime"],
        tool_permissions=["git.read", "shell.exec"],
        required_capabilities=["approval-gates", "stream-events"],
    )
    heartbeat_at = _now()
    agent_session = service.record_handshake(
        lane.lane_id,
        RunnerHandshake(
            runner_session_id=f"runner-session-{issue_number}",
            runner_version="agent-core/0.15.0",
            capabilities=["stream-events", "approval-gates"],
            environment_identity=environment.container_handle or "aks://missing",
            heartbeat_at=heartbeat_at,
            thread_id=f"thread-{issue_number}",
        ),
    )
    session.flush()
    return service, lane, environment, launch_request, agent_session, heartbeat_at


def test_prepare_lane_session_and_handshake_persist_runner_metadata() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                service, lane, environment, launch_request, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                )
                session.commit()

                assert launch_request.lane_id == str(lane.lane_id)
                assert launch_request.agent_session_id == str(agent_session.agent_session_id)
                assert launch_request.lane_metadata["branch_name"] == lane.branch_name
                assert launch_request.lane_metadata["environment_identity"] == environment.container_handle
                assert launch_request.issue_context["issue_number"] == 15
                assert launch_request.policy["approval_posture"] == "operator-gated"
                assert launch_request.secret_references == ["github/app", "openai/runtime"]
                assert launch_request.tool_permissions == ["git.read", "shell.exec"]
                assert launch_request.required_capabilities == ["approval-gates", "stream-events"]

                assert agent_session.runner_session_id == "runner-session-15"
                assert agent_session.runner_version == "agent-core/0.15.0"
                assert agent_session.capabilities == ["approval-gates", "stream-events"]
                assert agent_session.environment_identity == environment.container_handle
                assert agent_session.thread_id == "thread-15"
                assert agent_session.status == "running"
                assert agent_session.heartbeat_at == heartbeat_at
                assert lane.state == "Running"
                assert environment.heartbeat_at == heartbeat_at
                assert [event.event_type for event in agent_session.events] == ["session_started"]
                assert agent_session.events[0].payload["runner_session_id"] == "runner-session-15"

                projection = service.rebuild_session_projection(lane.lane_id)
                assert projection.status == "running"
                assert projection.last_event == "session_started"
                assert projection.heartbeat_at == heartbeat_at
            finally:
                session.close()
        _reset_env()


def test_prepare_lane_session_preserves_supplied_graph_context(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                lane, _ = _provision_lane(
                    session,
                    clone_url=clone_url,
                    issue_number=27,
                    title="Preserve provided graph context",
                )
                supplied_graph_context = {
                    "scope": "lane",
                    "lane_id": str(lane.lane_id),
                    "nodes": [{"key": "provided-node"}],
                }

                def _unexpected_graph_context(*_args, **_kwargs):
                    raise AssertionError("graph context should not be recomputed when already supplied")

                monkeypatch.setattr(
                    runner_protocol_module.GraphContextService,
                    "build_lane_prompt_context",
                    _unexpected_graph_context,
                )

                launch_request = RunnerProtocolService(session).prepare_lane_session(
                    lane.lane_id,
                    instruction_bundle={
                        "task": "Use the provided graph context.",
                        "graph_context": supplied_graph_context,
                    },
                )

                assert launch_request.instruction_bundle["graph_context"] == supplied_graph_context
            finally:
                session.close()
        _reset_env()


def test_runtime_events_persist_and_projection_rebuilds_session_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                service, lane, _, _, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="turn_started",
                        observed_at=heartbeat_at + timedelta(seconds=5),
                        summary="Started turn 1.",
                        turn_id="turn-1",
                    ),
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="tool_call_started",
                        observed_at=heartbeat_at + timedelta(seconds=8),
                        summary="Running repo diff tool.",
                        tool_name="repo.diff",
                        turn_id="turn-1",
                    ),
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="tool_call_finished",
                        observed_at=heartbeat_at + timedelta(seconds=12),
                        summary="Repo diff tool completed.",
                        turn_id="turn-1",
                        token_usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
                        tool_name="repo.diff",
                        tool_status="succeeded",
                    ),
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="token_usage_reported",
                        observed_at=heartbeat_at + timedelta(seconds=14),
                        summary="Aggregated token usage updated.",
                        token_usage={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
                    ),
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="status_summary",
                        observed_at=heartbeat_at + timedelta(seconds=16),
                        summary="Ready to continue from the synthesized plan.",
                        payload={"headline": "Synthesized execution plan", "resume_token": "resume-1"},
                    ),
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="turn_completed",
                        observed_at=heartbeat_at + timedelta(seconds=18),
                        summary="Turn 1 completed.",
                        turn_id="turn-1",
                    ),
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="session_completed",
                        observed_at=heartbeat_at + timedelta(seconds=20),
                        summary="Runner finished cleanly.",
                    ),
                )
                session.commit()

                assert agent_session.turn_count == 1
                assert agent_session.tool_call_count == 1
                assert agent_session.input_tokens == 30
                assert agent_session.output_tokens == 7
                assert agent_session.total_tokens == 37
                assert agent_session.status == "completed"
                assert lane.state == "HandedOff"
                assert lane.finished_at == heartbeat_at + timedelta(seconds=20)
                assert [event.sequence for event in agent_session.events] == list(range(1, 8 + 1))
                assert agent_session.events[3].tool_name == "repo.diff"
                assert agent_session.events[3].tool_status == "succeeded"
                assert agent_session.continuation_summary == {
                    "headline": "Synthesized execution plan",
                    "resume_token": "resume-1",
                    "summary": "Ready to continue from the synthesized plan.",
                    "updated_at": (heartbeat_at + timedelta(seconds=16)).isoformat(),
                }

                projection = service.rebuild_session_projection(lane.lane_id)
                assert projection.status == "completed"
                assert projection.last_event == "session_completed"
                assert projection.turn_count == 1
                assert projection.tool_call_count == 1
                assert projection.total_tokens == 37
                assert projection.continuation_summary == agent_session.continuation_summary
                assert projection.heartbeat_at == heartbeat_at + timedelta(seconds=20)
            finally:
                session.close()
        _reset_env()


def test_approval_and_human_input_events_pause_lane_with_explicit_wait_reasons() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                service, lane, _, _, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="approval_requested",
                        observed_at=heartbeat_at + timedelta(seconds=3),
                        summary="Awaiting operator approval to push branch updates.",
                        payload={"reason": "push branch updates"},
                    ),
                )

                assert agent_session.status == "awaiting_approval"
                assert agent_session.wait_reason == "Awaiting operator approval to push branch updates."
                assert agent_session.requires_human_input is False
                assert lane.state == "AwaitingApproval"

                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="turn_started",
                        observed_at=heartbeat_at + timedelta(seconds=5),
                        summary="Turn resumed after approval.",
                        turn_id="turn-2",
                    ),
                )

                assert agent_session.status == "running"
                assert agent_session.wait_reason is None
                assert lane.state == "Running"

                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="human_input_requested",
                        observed_at=heartbeat_at + timedelta(seconds=8),
                        summary="Awaiting maintainer answer on the migration strategy.",
                        payload={"reason": "Need maintainer confirmation"},
                    ),
                )
                session.commit()

                assert agent_session.status == "awaiting_human_input"
                assert agent_session.wait_reason == "Awaiting maintainer answer on the migration strategy."
                assert agent_session.requires_human_input is True
                assert lane.state == "AwaitingGitHub"

                projection = service.rebuild_session_projection(lane.lane_id)
                assert projection.status == "awaiting_human_input"
                assert projection.wait_reason == "Awaiting maintainer answer on the migration strategy."
                assert projection.requires_human_input is True
            finally:
                session.close()
        _reset_env()


def test_high_trust_approval_requests_do_not_pause_lane() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                service, lane, _, _, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                    issue_number=16,
                    policy={"approval_posture": "high-trust"},
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="approval_requested",
                        observed_at=heartbeat_at + timedelta(seconds=2),
                        summary="Tool class is auto-approved for high-trust posture.",
                    ),
                )
                session.commit()

                assert agent_session.status == "running"
                assert agent_session.wait_reason is None
                assert agent_session.requires_human_input is False
                assert lane.state == "Running"
            finally:
                session.close()
        _reset_env()


def test_blocked_governance_actions_fail_lane_with_policy_error() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                service, lane, _, _, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                    issue_number=17,
                    policy={
                        "approval_posture": "high-trust",
                        "action_policies": {"repo_write": "blocked"},
                    },
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="approval_requested",
                        observed_at=heartbeat_at + timedelta(seconds=2),
                        summary="Attempting to push repo changes.",
                        payload={"action_type": "repo_write", "reason": "push repo changes"},
                    ),
                )
                session.commit()

                assert agent_session.status == "failed"
                assert agent_session.last_error_category == "policy"
                assert lane.state == "FailedTerminal"
                assert "blocked requested action" in (lane.last_error or "").lower()
                assert agent_session.events[-1].event_type == "session_failed"
                assert agent_session.events[-1].payload["action_type"] == "repo_write"
            finally:
                session.close()
        _reset_env()


def test_runner_protocol_redacts_secret_values_from_events_and_summaries() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                session.add(
                    Secret(
                        key="runtime-token",
                        name="Runtime Token",
                        kind="ai_api_key",
                        value_ciphertext=encrypt_secret("super-secret-token"),
                    )
                )
                session.flush()
                service, lane, _, _, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                    issue_number=18,
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="status_summary",
                        observed_at=heartbeat_at + timedelta(seconds=3),
                        summary="Fetched super-secret-token during bootstrap.",
                        payload={"token_preview": "super-secret-token", "headline": "Runtime secret used."},
                    ),
                )
                session.commit()

                persisted = agent_session.events[-1]
                assert persisted.summary == "Fetched [REDACTED_SECRET] during bootstrap."
                assert persisted.payload["token_preview"] == "[REDACTED_SECRET]"
                assert agent_session.continuation_summary["summary"] == "Fetched [REDACTED_SECRET] during bootstrap."
                assert agent_session.continuation_summary["token_preview"] == "[REDACTED_SECRET]"
            finally:
                session.close()
        _reset_env()


@pytest.mark.parametrize(
    ("scenario", "expected_timeout_type", "expected_category"),
    [
        ("handshake", "handshake_timeout", "integration"),
        ("heartbeat", "no_heartbeat_timeout", "agent_runtime"),
        ("approval", "approval_wait_timeout", "policy"),
    ],
)
def test_runner_protocol_timeouts_map_to_expected_categories(
    scenario: str,
    expected_timeout_type: str,
    expected_category: str,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                lane, _ = _provision_lane(
                    session,
                    clone_url=clone_url,
                    issue_number=20,
                    title="Timeout mapping fixture",
                )
                service = RunnerProtocolService(session)
                service.prepare_lane_session(
                    lane.lane_id,
                    instruction_bundle={"task": "Run timeout scenario."},
                    policy={"approval_posture": "operator-gated"},
                    required_capabilities=["stream-events"],
                )
                now = _now()

                if scenario == "heartbeat":
                    service.record_handshake(
                        lane.lane_id,
                        RunnerHandshake(
                            runner_session_id="runner-timeout",
                            runner_version="agent-core/0.15.0",
                            capabilities=["stream-events"],
                            environment_identity=lane.execution_environment.container_handle or "aks://missing",
                            heartbeat_at=now,
                        ),
                    )
                    as_of = now + timedelta(seconds=get_settings().runner_heartbeat_timeout_seconds + 1)
                elif scenario == "approval":
                    service.record_handshake(
                        lane.lane_id,
                        RunnerHandshake(
                            runner_session_id="runner-timeout",
                            runner_version="agent-core/0.15.0",
                            capabilities=["stream-events"],
                            environment_identity=lane.execution_environment.container_handle or "aks://missing",
                            heartbeat_at=now,
                        ),
                    )
                    wait_started = now + timedelta(seconds=2)
                    service.record_event(
                        lane.lane_id,
                        RuntimeEvent(
                            event_type="approval_requested",
                            observed_at=wait_started,
                            summary="Awaiting approval for a write action.",
                        ),
                    )
                    as_of = wait_started + timedelta(seconds=get_settings().runner_approval_wait_timeout_seconds + 1)
                else:
                    as_of = now + timedelta(seconds=get_settings().runner_startup_timeout_seconds + 1)

                evaluation = service.evaluate_timeouts(lane.lane_id, as_of=as_of)
                session.commit()

                assert evaluation is not None
                assert evaluation.timeout_type == expected_timeout_type
                assert evaluation.error_category == expected_category
                assert lane.state == "FailedTerminal"
                assert lane.last_error is not None
                assert lane.agent_session.status == "failed"
                assert lane.agent_session.last_error_category == expected_category
                assert lane.agent_session.last_event == "session_failed"
                if scenario == "handshake":
                    assert lane.work_item.requires_repair is True
                    assert RUNNER_HANDSHAKE_TIMEOUT_REPAIR_REASON in lane.work_item.repair_reasons
                    assert "repair-needed" in lane.work_item.eligibility_flags
                    assert "eligible" not in lane.work_item.eligibility_flags
                elif scenario == "heartbeat":
                    assert lane.work_item.requires_repair is True
                    assert RUNNER_HEARTBEAT_TIMEOUT_REPAIR_REASON in lane.work_item.repair_reasons
                    assert "repair-needed" in lane.work_item.eligibility_flags
                    assert "eligible" not in lane.work_item.eligibility_flags
                else:
                    assert lane.work_item.requires_repair is False
            finally:
                session.close()
        _reset_env()


def test_session_failed_event_normalizes_repo_contract_errors() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                service, lane, _, _, agent_session, heartbeat_at = _prepare_and_handshake(
                    session,
                    clone_url=clone_url,
                    issue_number=21,
                )
                service.record_event(
                    lane.lane_id,
                    RuntimeEvent(
                        event_type="session_failed",
                        observed_at=heartbeat_at + timedelta(seconds=4),
                        summary="Repository contract check failed before patch application.",
                        payload={"error": "missing required file"},
                        error_category="repo contract",
                    ),
                )
                session.commit()

                assert agent_session.status == "failed"
                assert agent_session.last_error_category == "repo_contract"
                assert lane.state == "FailedTerminal"
                assert lane.last_error == "Repository contract check failed before patch application."
                assert agent_session.events[-1].error_category == "repo_contract"
            finally:
                session.close()
        _reset_env()


def test_missing_runner_capabilities_flag_work_item_for_runtime_repair() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                lane, environment = _provision_lane(
                    session,
                    clone_url=clone_url,
                    issue_number=22,
                    title="Runner capability mismatch fixture",
                )
                service = RunnerProtocolService(session)
                service.prepare_lane_session(
                    lane.lane_id,
                    instruction_bundle={"task": "Exercise handshake capability mismatch."},
                    policy={"approval_posture": "operator-gated"},
                    required_capabilities=["approval-gates", "stream-events"],
                )

                with pytest.raises(RunnerProtocolError, match="missing required capabilities: approval-gates"):
                    service.record_handshake(
                        lane.lane_id,
                        RunnerHandshake(
                            runner_session_id="runner-capability-mismatch",
                            runner_version="agent-core/0.15.0",
                            capabilities=["stream-events"],
                            environment_identity=environment.container_handle or "aks://missing",
                            heartbeat_at=_now(),
                        ),
                    )
                session.commit()

                assert lane.state == "FailedTerminal"
                assert lane.last_error == "Runner handshake missing required capabilities: approval-gates"
                assert lane.work_item.requires_repair is True
                assert RUNNER_CAPABILITY_REPAIR_REASON in lane.work_item.repair_reasons
                assert "repair-needed" in lane.work_item.eligibility_flags
                assert "eligible" not in lane.work_item.eligibility_flags
            finally:
                session.close()
        _reset_env()
