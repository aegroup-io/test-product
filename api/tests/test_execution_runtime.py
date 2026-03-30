from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.execution_runtime import (
    AksRuntimeProvider,
    DockerRuntimeProvider,
    ExecutionEnvironmentService,
    LaneProvisioningError,
    RuntimeCleanupRequest,
    UnsafeContinuationError,
)
from agent_core_platform_api.models import Organization, Secret
from agent_core_platform_api.orcha_state import OrchaStateStore
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


def _create_remote_branch(source_repo: Path, *, branch_name: str) -> str:
    _git(source_repo, "checkout", "-B", branch_name, "dev")
    (source_repo / "branch.txt").write_text(f"{branch_name}\n", encoding="utf-8")
    _git(source_repo, "add", "branch.txt")
    _git(source_repo, "commit", "-m", f"Create {branch_name}")
    _git(source_repo, "push", "-u", "origin", branch_name)
    branch_sha = _git(source_repo, "rev-parse", "HEAD")
    _git(source_repo, "checkout", "dev")
    return branch_sha


def _seed_claimed_lane(session, *, clone_url: str, required_secret_keys: list[str] | None = None):
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
            "required_secret_keys": list(required_secret_keys or []),
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
        github_repository_node_id="R_kgDOFixture",
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
        github_issue_node_id="I_kwDOFixture14",
        issue_number=14,
        title="Provision remote execution environments",
        body="Fixture lane for issue 14.",
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
    return product, repo, work_item, lane


def test_provision_claimed_lane_hydrates_workspace_and_finalizes_cleanup() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        source_repo, clone_url = _build_remote_repo(temp_path)
        dev_sha = _git(source_repo, "rev-parse", "dev")

        with TestClient(app):
            session = get_session_factory()()
            try:
                _, _, _, lane = _seed_claimed_lane(session, clone_url=clone_url)
                service = ExecutionEnvironmentService(session)

                environment = service.provision_claimed_lane(lane.lane_id)
                session.commit()

                workspace_path = Path(environment.workspace_uri.removeprefix("file://"))
                artifact_path = Path(environment.artifact_uri.removeprefix("file://"))

                assert environment.runtime_provider == "aks"
                assert environment.status == "Ready"
                assert environment.checkout_revision == dev_sha
                assert environment.log_uri is not None
                assert environment.cache_uri is not None
                assert environment.manifest_fingerprint
                assert environment.secret_fingerprint
                assert lane.branch_name == "orcha/issue-14-attempt-1"
                assert lane.state == "Provisioning"
                assert (workspace_path / ".git").exists()
                assert _git(workspace_path, "rev-parse", "--abbrev-ref", "HEAD") == lane.branch_name
                assert _git(workspace_path, "rev-parse", "HEAD") == dev_sha

                finalized = service.finalize_lane_environment(
                    lane.lane_id,
                    final_state="HandedOff",
                    disposition="terminate",
                )
                session.commit()

                assert finalized.status == "Terminated"
                assert finalized.terminated_at is not None
                assert not workspace_path.exists()
                assert (artifact_path / "cleanup.json").exists()
                assert lane.state == "HandedOff"
            finally:
                session.close()
        _reset_env()


def test_provision_claimed_lane_reuses_remote_branch_head_when_present() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        source_repo, clone_url = _build_remote_repo(temp_path)
        branch_name = "orcha/issue-14-attempt-1"
        branch_sha = _create_remote_branch(source_repo, branch_name=branch_name)

        with TestClient(app):
            session = get_session_factory()()
            try:
                _, _, _, lane = _seed_claimed_lane(session, clone_url=clone_url)
                service = ExecutionEnvironmentService(session)

                environment = service.provision_claimed_lane(lane.lane_id)
                session.commit()

                assert environment.checkout_revision == branch_sha
                assert environment.provider_metadata["hydration"]["branch_reused"] is True
                assert environment.provider_metadata["hydration"]["remote_branch_found"] is True
            finally:
                session.close()
        _reset_env()


def test_provision_claimed_lane_reuses_only_safe_continuations() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                product, _, _, lane = _seed_claimed_lane(
                    session,
                    clone_url=clone_url,
                    required_secret_keys=["runtime-token"],
                )
                secret = Secret(
                    key="runtime-token",
                    name="Runtime Token",
                    kind="shared_secret",
                    value_ciphertext="ciphertext-v1",
                )
                session.add(secret)
                session.flush()

                service = ExecutionEnvironmentService(session)
                first = service.provision_claimed_lane(lane.lane_id)
                session.commit()

                second = service.provision_claimed_lane(lane.lane_id)
                assert second.execution_environment_id == first.execution_environment_id

                original_config = deepcopy(product.effective_config)
                updated_config = deepcopy(product.effective_config)
                updated_config["execution"]["container_image"] = "ghcr.io/aegroup/agent-core-runner:candidate"
                product.effective_config = updated_config
                session.flush()
                with pytest.raises(UnsafeContinuationError):
                    service.provision_claimed_lane(lane.lane_id)

                product.effective_config = original_config
                session.flush()
                safe_again = service.provision_claimed_lane(lane.lane_id)
                assert safe_again.execution_environment_id == first.execution_environment_id

                secret.value_ciphertext = "ciphertext-v2"
                secret.last_rotated_at = _now()
                secret.updated_at = _now()
                session.flush()
                with pytest.raises(UnsafeContinuationError):
                    service.provision_claimed_lane(lane.lane_id)
            finally:
                session.close()
        _reset_env()


def test_provision_claimed_lane_rewrites_legacy_branch_names() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                _, _, _, lane = _seed_claimed_lane(session, clone_url=clone_url)
                lane.branch_name = "orcha/issue-14"
                session.flush()
                service = ExecutionEnvironmentService(session)

                environment = service.provision_claimed_lane(lane.lane_id)
                session.commit()

                workspace_path = Path(environment.workspace_uri.removeprefix("file://"))
                assert lane.branch_name == "orcha/issue-14-attempt-1"
                assert _git(workspace_path, "rev-parse", "--abbrev-ref", "HEAD") == "orcha/issue-14-attempt-1"
            finally:
                session.close()
        _reset_env()


def test_finalize_lane_environment_rejects_non_terminal_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                _, _, _, lane = _seed_claimed_lane(session, clone_url=clone_url)
                service = ExecutionEnvironmentService(session)
                service.provision_claimed_lane(lane.lane_id)
                session.commit()

                with pytest.raises(LaneProvisioningError):
                    service.finalize_lane_environment(lane.lane_id, final_state="Running")
            finally:
                session.close()
        _reset_env()


def test_provider_cleanup_reports_workspace_removed_only_when_deleted() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        provider = AksRuntimeProvider(root=Path(temp_dir), namespace="test-namespace")
        request = RuntimeCleanupRequest(
            environment_id="env-1",
            container_handle="aks://test-namespace/lanes/env-1",
            workspace_uri=(Path(temp_dir) / "missing-workspace").resolve().as_uri(),
            artifact_uri=(Path(temp_dir) / "artifacts").resolve().as_uri(),
            log_uri=(Path(temp_dir) / "logs").resolve().as_uri(),
            cache_uri=(Path(temp_dir) / "cache").resolve().as_uri(),
            disposition="terminate",
        )

        result = provider.cleanup(request)

        assert result.status == "Terminated"
        assert result.provider_metadata["workspace_removed"] is False


def test_docker_provider_records_mounts_and_cleanup_container_removal() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        commands: list[list[str]] = []
        container_name = "orcha-test-namespace-lane-env1"
        container_id = "deadc0de1234567890"
        inspect_payload = json.dumps(
            [
                {
                    "Id": container_id,
                    "State": {
                        "Status": "running",
                        "Running": True,
                        "StartedAt": "2026-03-18T00:00:00Z",
                        "FinishedAt": "0001-01-01T00:00:00Z",
                        "ExitCode": 0,
                    },
                }
            ]
        )

        def _docker_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            if command == ["docker", "rm", "-f", container_name]:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="No such container")
            if command[0:2] == ["docker", "run"]:
                return subprocess.CompletedProcess(command, 0, stdout=f"{container_id}\n", stderr="")
            if command[0:2] == ["docker", "inspect"]:
                return subprocess.CompletedProcess(command, 0, stdout=inspect_payload, stderr="")
            if command == ["docker", "rm", "-f", container_id]:
                return subprocess.CompletedProcess(command, 0, stdout=container_id, stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        provider = DockerRuntimeProvider(
            root=Path(temp_dir),
            namespace="test-namespace",
            docker_runner=_docker_runner,
        )
        provisioned = provider.provision(
            request=type(
                "Request",
                (),
                {
                    "environment_id": "env-1",
                    "lane_id": "lane-1",
                    "branch_name": "orcha/issue-55-attempt-1",
                    "container_image": "orcha/coding-lane-smoke:dev",
                },
            )(),
        )

        assert provisioned.runtime_provider == "docker"
        assert provisioned.container_handle == f"docker://{container_id}"
        assert provisioned.provider_metadata["container_name"] == container_name
        assert provisioned.provider_metadata["container_id"] == container_id
        assert provisioned.provider_metadata["container_lifecycle"]["running"] is True
        assert provisioned.provider_metadata["mount_paths"]["workspace"] == str(provisioned.workspace_path)
        expected_run_command = [
            "docker",
            "run",
            "--detach",
            "--name",
            container_name,
            "--label",
            "orcha.runtime_provider=docker",
            "--label",
            "orcha.environment_id=env-1",
            "--label",
            "orcha.lane_id=lane-1",
            "--label",
            "orcha.branch_name=orcha/issue-55-attempt-1",
            "--mount",
            f"type=bind,src={provisioned.workspace_path},dst=/workspace",
            "--mount",
            f"type=bind,src={provisioned.artifact_path},dst=/artifacts",
            "--mount",
            f"type=bind,src={provisioned.log_path},dst=/logs",
            "--mount",
            f"type=bind,src={provisioned.cache_path},dst=/cache",
            "--workdir",
            "/workspace",
            "--entrypoint",
            "/bin/sh",
            "-e",
            "ORCHA_WORKSPACE_PATH=/workspace",
            "-e",
            "ORCHA_ARTIFACT_PATH=/artifacts",
            "-e",
            "ORCHA_LOG_PATH=/logs",
            "-e",
            "ORCHA_CACHE_PATH=/cache",
            "orcha/coding-lane-smoke:dev",
            "-c",
            "while true; do sleep 30; done",
        ]
        assert commands[0] == ["docker", "rm", "-f", container_name]
        assert commands[1] == expected_run_command
        assert commands[2] == ["docker", "inspect", container_name]
        assert provider.can_reuse(
            type(
                "Environment",
                (),
                {
                    "container_handle": provisioned.container_handle,
                    "workspace_uri": provisioned.workspace_uri,
                    "artifact_uri": provisioned.artifact_uri,
                    "log_uri": provisioned.log_uri,
                    "cache_uri": provisioned.cache_uri,
                },
            )()
        )
        assert commands[3] == ["docker", "inspect", container_id]

        cleanup = provider.cleanup(
            RuntimeCleanupRequest(
                environment_id="env-1",
                container_handle=provisioned.container_handle,
                workspace_uri=provisioned.workspace_uri,
                artifact_uri=provisioned.artifact_uri,
                log_uri=provisioned.log_uri,
                cache_uri=provisioned.cache_uri,
                disposition="terminate",
                reason="cleanup",
            )
        )

        assert cleanup.status == "Terminated"
        assert cleanup.provider_metadata["workspace_removed"] is True
        assert cleanup.provider_metadata["container_removed"] is True
        assert cleanup.provider_metadata["container_reference"] == container_id
        assert commands[4] == ["docker", "inspect", container_id]
        assert commands[5] == ["docker", "rm", "-f", container_id]
        assert len(commands) == 6


def test_docker_provider_quarantine_stops_container_and_preserves_workspace() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        commands: list[list[str]] = []
        container_id = "feedface1234567890"
        inspect_running = json.dumps([{"Id": container_id, "State": {"Status": "running", "Running": True}}])
        inspect_stopped = json.dumps([{"Id": container_id, "State": {"Status": "exited", "Running": False}}])

        def _docker_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            if command[0:2] == ["docker", "inspect"] and len(commands) == 1:
                return subprocess.CompletedProcess(command, 0, stdout=inspect_running, stderr="")
            if command[0:2] == ["docker", "stop"]:
                return subprocess.CompletedProcess(command, 0, stdout=container_id, stderr="")
            if command[0:2] == ["docker", "inspect"] and len(commands) == 3:
                return subprocess.CompletedProcess(command, 0, stdout=inspect_stopped, stderr="")
            return subprocess.CompletedProcess(command, 0, stdout=inspect_running, stderr="")

        provider = DockerRuntimeProvider(
            root=Path(temp_dir),
            namespace="test-namespace",
            docker_runner=_docker_runner,
        )
        workspace = Path(temp_dir) / "workspace"
        artifacts = Path(temp_dir) / "artifacts"
        logs = Path(temp_dir) / "logs"
        cache = Path(temp_dir) / "cache"
        for path in (workspace, artifacts, logs, cache):
            path.mkdir(parents=True, exist_ok=True)

        cleanup = provider.cleanup(
            RuntimeCleanupRequest(
                environment_id="env-2",
                container_handle=f"docker://{container_id}",
                workspace_uri=workspace.resolve().as_uri(),
                artifact_uri=artifacts.resolve().as_uri(),
                log_uri=logs.resolve().as_uri(),
                cache_uri=cache.resolve().as_uri(),
                disposition="quarantine",
                reason="investigate",
            )
        )

        assert cleanup.status == "Quarantined"
        assert cleanup.provider_metadata["container_removed"] is False
        assert cleanup.provider_metadata["container_stopped"] is True
        assert cleanup.provider_metadata["workspace_removed"] is False
        assert workspace.exists()
        assert commands == [
            ["docker", "inspect", container_id],
            ["docker", "stop", container_id],
            ["docker", "inspect", container_id],
        ]
