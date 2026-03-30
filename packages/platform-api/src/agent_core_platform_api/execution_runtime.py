from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable, Literal, Protocol
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.governance import build_runtime_identity
from agent_core_platform_api.models import (
    ACTIVE_LANE_OWNERSHIP_STATES,
    ExecutionEnvironment,
    OrchestrationLane,
    RepositoryBinding,
    Secret,
)
from agent_core_platform_api.product_contract import SUPPORTED_EXECUTION_PROFILES
from agent_core_platform_api.scheduler import SchedulerService


ACTIVE_ENVIRONMENT_STATUSES = frozenset({"Provisioning", "Ready", "Running"})
TERMINAL_LANE_STATES = frozenset({"HandedOff", "Cancelled", "FailedTerminal"})
SUPPORTED_RUNTIME_PROVIDERS = frozenset({"aks", "docker"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _uri_to_path(uri: str | None) -> Path | None:
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        return None
    raw_path = unquote(parsed.path) if parsed.scheme == "file" else uri
    if not raw_path:
        return None
    return Path(raw_path).resolve()


def _normalize_clone_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return str(Path(unquote(parsed.path)).resolve())
    if not parsed.scheme and Path(value).exists():
        return str(Path(value).resolve())
    return value.rstrip("/")


def _branch_name_for_lane(lane: OrchestrationLane) -> str:
    issue_number = lane.work_item.issue_number
    return f"orcha/issue-{issue_number}-attempt-{lane.attempt}"


class LaneProvisioningError(RuntimeError):
    """Raised when a lane cannot be provisioned safely."""


class UnsafeContinuationError(LaneProvisioningError):
    """Raised when an active environment cannot be reused across a changed boundary."""


@dataclass(frozen=True)
class RuntimeProvisionRequest:
    environment_id: str
    lane_id: str
    branch_name: str
    container_image: str


@dataclass(frozen=True)
class RuntimeProvisionResult:
    runtime_provider: str
    container_handle: str
    workspace_uri: str
    artifact_uri: str
    log_uri: str
    cache_uri: str
    workspace_path: Path
    artifact_path: Path
    log_path: Path
    cache_path: Path
    status: str = "Ready"
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeCleanupRequest:
    environment_id: str
    container_handle: str | None
    workspace_uri: str | None
    artifact_uri: str | None
    log_uri: str | None
    cache_uri: str | None
    disposition: Literal["terminate", "quarantine"]
    reason: str | None = None


@dataclass(frozen=True)
class RuntimeCleanupResult:
    status: str
    terminated_at: datetime
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceHydrationResult:
    checkout_revision: str
    branch_reused: bool
    remote_branch_found: bool


class RuntimeProvider(Protocol):
    name: str

    def provision(self, request: RuntimeProvisionRequest) -> RuntimeProvisionResult:
        ...

    def can_reuse(self, environment: ExecutionEnvironment) -> bool:
        ...

    def cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupResult:
        ...


def _slug_segment(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    collapsed = "-".join(segment for segment in normalized.split("-") if segment)
    return collapsed or "lane"


def _docker_container_name(namespace: str, environment_id: str) -> str:
    safe_namespace = _slug_segment(namespace)
    safe_environment = "".join(character for character in environment_id if character.isalnum()).lower()[:16]
    return f"orcha-{safe_namespace}-lane-{safe_environment or 'env'}"


class AksRuntimeProvider:
    name = "aks"

    def __init__(self, *, root: Path | None = None, namespace: str | None = None):
        settings = get_settings()
        self.root = (root or Path(settings.remote_execution_root)).expanduser().resolve()
        self.namespace = namespace or settings.runtime_provider_namespace

    def provision(self, request: RuntimeProvisionRequest) -> RuntimeProvisionResult:
        lane_root = self.root / "lanes" / request.environment_id
        workspace_path = (lane_root / "workspace").resolve()
        artifact_path = (lane_root / "artifacts").resolve()
        log_path = (lane_root / "logs").resolve()
        cache_path = (lane_root / "cache").resolve()
        for path in (artifact_path, log_path, cache_path):
            path.mkdir(parents=True, exist_ok=True)
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        workspace_path.mkdir(parents=True, exist_ok=True)
        return RuntimeProvisionResult(
            runtime_provider=self.name,
            container_handle=f"aks://{self.namespace}/lanes/{request.environment_id}",
            workspace_uri=workspace_path.as_uri(),
            artifact_uri=artifact_path.as_uri(),
            log_uri=log_path.as_uri(),
            cache_uri=cache_path.as_uri(),
            workspace_path=workspace_path,
            artifact_path=artifact_path,
            log_path=log_path,
            cache_path=cache_path,
            provider_metadata={
                "namespace": self.namespace,
                "branch_name": request.branch_name,
                "container_image": request.container_image,
                "runtime_contract": {
                    "mode": "filesystem-simulated",
                    "container_lifecycle": "deferred",
                    "note": "AKS remote container lifecycle is not implemented in this provider.",
                },
            },
        )

    def can_reuse(self, environment: ExecutionEnvironment) -> bool:
        paths = [
            _uri_to_path(environment.workspace_uri),
            _uri_to_path(environment.artifact_uri),
            _uri_to_path(environment.log_uri),
            _uri_to_path(environment.cache_uri),
        ]
        return all(path is not None and path.exists() for path in paths)

    def cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupResult:
        workspace_path = _uri_to_path(request.workspace_uri)
        artifact_path = _uri_to_path(request.artifact_uri)
        log_path = _uri_to_path(request.log_uri)
        cache_path = _uri_to_path(request.cache_uri)
        terminated_at = _now()
        workspace_removed = False

        if request.disposition == "terminate" and workspace_path is not None and workspace_path.exists():
            shutil.rmtree(workspace_path)
            workspace_removed = True

        if artifact_path is not None:
            artifact_path.mkdir(parents=True, exist_ok=True)
            marker = artifact_path / "cleanup.json"
            marker.write_text(
                json.dumps(
                    {
                        "disposition": request.disposition,
                        "reason": request.reason,
                        "terminated_at": terminated_at.isoformat(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        for path in (log_path, cache_path):
            if path is not None:
                path.mkdir(parents=True, exist_ok=True)

        return RuntimeCleanupResult(
            status="Quarantined" if request.disposition == "quarantine" else "Terminated",
            terminated_at=terminated_at,
            provider_metadata={
                "disposition": request.disposition,
                "workspace_removed": workspace_removed,
            },
        )


class DockerRuntimeProvider:
    name = "docker"
    WORKSPACE_CONTAINER_PATH = "/workspace"
    ARTIFACT_CONTAINER_PATH = "/artifacts"
    LOG_CONTAINER_PATH = "/logs"
    CACHE_CONTAINER_PATH = "/cache"
    KEEPALIVE_COMMAND = ("-c", "while true; do sleep 30; done")

    def __init__(
        self,
        *,
        root: Path | None = None,
        namespace: str | None = None,
        docker_bin: str = "docker",
        docker_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    ):
        settings = get_settings()
        self.root = (root or Path(settings.remote_execution_root)).expanduser().resolve()
        self.namespace = namespace or settings.runtime_provider_namespace
        self.docker_bin = docker_bin
        self.docker_runner = docker_runner or self._default_docker_runner

    def provision(self, request: RuntimeProvisionRequest) -> RuntimeProvisionResult:
        lane_root = self.root / "lanes" / request.environment_id
        workspace_path = (lane_root / "workspace").resolve()
        artifact_path = (lane_root / "artifacts").resolve()
        log_path = (lane_root / "logs").resolve()
        cache_path = (lane_root / "cache").resolve()
        for path in (artifact_path, log_path, cache_path):
            path.mkdir(parents=True, exist_ok=True)
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
        workspace_path.mkdir(parents=True, exist_ok=True)

        container_name = _docker_container_name(self.namespace, request.environment_id)
        labels = {
            "orcha.runtime_provider": self.name,
            "orcha.environment_id": request.environment_id,
            "orcha.lane_id": request.lane_id,
            "orcha.branch_name": request.branch_name,
        }
        mount_paths = {
            "workspace": str(workspace_path),
            "artifacts": str(artifact_path),
            "logs": str(log_path),
            "cache": str(cache_path),
        }
        mount_targets = {
            "workspace": self.WORKSPACE_CONTAINER_PATH,
            "artifacts": self.ARTIFACT_CONTAINER_PATH,
            "logs": self.LOG_CONTAINER_PATH,
            "cache": self.CACHE_CONTAINER_PATH,
        }
        # Best effort cleanup for previous interrupted runs with the same deterministic name.
        self.docker_runner([self.docker_bin, "rm", "-f", container_name])

        run_command = [self.docker_bin, "run", "--detach", "--name", container_name]
        for key, value in labels.items():
            run_command.extend(["--label", f"{key}={value}"])
        for mount_key, host_path in mount_paths.items():
            run_command.extend(["--mount", f"type=bind,src={host_path},dst={mount_targets[mount_key]}"])
        run_command.extend(
            [
                "--workdir",
                self.WORKSPACE_CONTAINER_PATH,
                "--entrypoint",
                "/bin/sh",
                "-e",
                f"ORCHA_WORKSPACE_PATH={self.WORKSPACE_CONTAINER_PATH}",
                "-e",
                f"ORCHA_ARTIFACT_PATH={self.ARTIFACT_CONTAINER_PATH}",
                "-e",
                f"ORCHA_LOG_PATH={self.LOG_CONTAINER_PATH}",
                "-e",
                f"ORCHA_CACHE_PATH={self.CACHE_CONTAINER_PATH}",
                request.container_image,
                *self.KEEPALIVE_COMMAND,
            ]
        )
        run_result = self.docker_runner(run_command)
        if run_result.returncode != 0:
            raise LaneProvisioningError(
                "Docker runtime provisioning failed to start container "
                f"{container_name}: {run_result.stderr.strip()}"
            )

        reported_container_id = run_result.stdout.strip()
        inspected = self._inspect_container(container_name)
        state_payload = inspected.get("State") if isinstance(inspected.get("State"), dict) else {}
        container_id = str(inspected.get("Id") or reported_container_id or container_name)
        lifecycle = {
            "status": state_payload.get("Status"),
            "running": bool(state_payload.get("Running")),
            "started_at": state_payload.get("StartedAt"),
            "finished_at": state_payload.get("FinishedAt"),
            "exit_code": state_payload.get("ExitCode"),
        }
        if not lifecycle["running"]:
            self.docker_runner([self.docker_bin, "rm", "-f", container_name])
            raise LaneProvisioningError(
                f"Docker runtime started container {container_name} but it is not running: {lifecycle!r}"
            )

        return RuntimeProvisionResult(
            runtime_provider=self.name,
            container_handle=f"docker://{container_id}",
            workspace_uri=workspace_path.as_uri(),
            artifact_uri=artifact_path.as_uri(),
            log_uri=log_path.as_uri(),
            cache_uri=cache_path.as_uri(),
            workspace_path=workspace_path,
            artifact_path=artifact_path,
            log_path=log_path,
            cache_path=cache_path,
            provider_metadata={
                "namespace": self.namespace,
                "branch_name": request.branch_name,
                "container_image": request.container_image,
                "container_name": container_name,
                "container_id": container_id,
                "container_lifecycle": lifecycle,
                "labels": labels,
                "mount_paths": mount_paths,
                "mount_targets": mount_targets,
            },
        )

    def can_reuse(self, environment: ExecutionEnvironment) -> bool:
        paths = [
            _uri_to_path(environment.workspace_uri),
            _uri_to_path(environment.artifact_uri),
            _uri_to_path(environment.log_uri),
            _uri_to_path(environment.cache_uri),
        ]
        if not all(path is not None and path.exists() for path in paths):
            return False
        container_reference = self._container_reference_from_handle(environment.container_handle)
        if not container_reference:
            return False
        inspection = self._inspect_container(container_reference, raise_on_error=False)
        if inspection is None:
            return False
        state_payload = inspection.get("State") if isinstance(inspection.get("State"), dict) else {}
        return bool(state_payload.get("Running"))

    def cleanup(self, request: RuntimeCleanupRequest) -> RuntimeCleanupResult:
        workspace_path = _uri_to_path(request.workspace_uri)
        artifact_path = _uri_to_path(request.artifact_uri)
        log_path = _uri_to_path(request.log_uri)
        cache_path = _uri_to_path(request.cache_uri)
        terminated_at = _now()
        workspace_removed = False
        container_removed = False
        container_stopped = False

        container_reference = self._container_reference_from_handle(request.container_handle)
        pre_cleanup_state: dict[str, Any] | None = None
        post_cleanup_state: dict[str, Any] | None = None
        cleanup_command: list[str] | None = None
        cleanup_return_code: int | None = None
        cleanup_stderr: str | None = None
        if container_reference:
            inspected = self._inspect_container(container_reference, raise_on_error=False)
            if inspected is not None and isinstance(inspected.get("State"), dict):
                pre_cleanup_state = dict(inspected["State"])
            if request.disposition == "terminate":
                cleanup_command = [self.docker_bin, "rm", "-f", container_reference]
                result = self.docker_runner(cleanup_command)
                cleanup_return_code = result.returncode
                cleanup_stderr = result.stderr.strip()
                container_removed = result.returncode == 0
            else:
                cleanup_command = [self.docker_bin, "stop", container_reference]
                result = self.docker_runner(cleanup_command)
                cleanup_return_code = result.returncode
                cleanup_stderr = result.stderr.strip()
                container_stopped = result.returncode == 0
                post_inspection = self._inspect_container(container_reference, raise_on_error=False)
                if post_inspection is not None and isinstance(post_inspection.get("State"), dict):
                    post_cleanup_state = dict(post_inspection["State"])

        if request.disposition == "terminate" and workspace_path is not None and workspace_path.exists():
            shutil.rmtree(workspace_path)
            workspace_removed = True

        if artifact_path is not None:
            artifact_path.mkdir(parents=True, exist_ok=True)
            marker = artifact_path / "cleanup.json"
            marker.write_text(
                json.dumps(
                    {
                        "disposition": request.disposition,
                        "reason": request.reason,
                        "terminated_at": terminated_at.isoformat(),
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        for path in (log_path, cache_path):
            if path is not None:
                path.mkdir(parents=True, exist_ok=True)

        return RuntimeCleanupResult(
            status="Quarantined" if request.disposition == "quarantine" else "Terminated",
            terminated_at=terminated_at,
            provider_metadata={
                "disposition": request.disposition,
                "workspace_removed": workspace_removed,
                "container_removed": container_removed,
                "container_stopped": container_stopped,
                "container_reference": container_reference,
                "container_pre_cleanup_state": pre_cleanup_state,
                "container_post_cleanup_state": post_cleanup_state,
                "cleanup_command": cleanup_command,
                "cleanup_return_code": cleanup_return_code,
                "cleanup_stderr": cleanup_stderr,
            },
        )

    def _default_docker_runner(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

    def _container_reference_from_handle(self, handle: str | None) -> str | None:
        if handle and handle.startswith("docker://"):
            return handle.removeprefix("docker://")
        return None

    def _inspect_container(
        self,
        container_reference: str,
        *,
        raise_on_error: bool = True,
    ) -> dict[str, Any] | None:
        result = self.docker_runner([self.docker_bin, "inspect", container_reference])
        if result.returncode != 0:
            if raise_on_error:
                raise LaneProvisioningError(
                    f"Docker runtime failed to inspect container {container_reference}: {result.stderr.strip()}"
                )
            return None
        payload = self._parse_inspection_json(result.stdout)
        if payload is None:
            if raise_on_error:
                raise LaneProvisioningError(
                    f"Docker runtime returned invalid inspect payload for container {container_reference}."
                )
            return None
        return payload

    def _parse_inspection_json(self, stdout: str) -> dict[str, Any] | None:
        raw = stdout.strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
        if isinstance(payload, dict):
            return payload
        return None


def build_runtime_provider(*, settings=None) -> RuntimeProvider:
    resolved_settings = settings or get_settings()
    provider_name = resolved_settings.runtime_provider.strip().lower()
    if provider_name == "aks":
        return AksRuntimeProvider(
            root=Path(resolved_settings.remote_execution_root),
            namespace=resolved_settings.runtime_provider_namespace,
        )
    if provider_name == "docker":
        return DockerRuntimeProvider(
            root=Path(resolved_settings.remote_execution_root),
            namespace=resolved_settings.runtime_provider_namespace,
        )
    raise RuntimeError(
        f"Unsupported AGENT_CORE_RUNTIME_PROVIDER: {resolved_settings.runtime_provider}. "
        f"Expected one of: {', '.join(sorted(SUPPORTED_RUNTIME_PROVIDERS))}."
    )


class GitWorkspaceHydrator:
    def __init__(self, *, git_bin: str = "git"):
        self.git_bin = git_bin

    def hydrate(
        self,
        *,
        repository_clone_url: str,
        workspace_path: Path,
        default_branch: str,
        branch_name: str,
    ) -> WorkspaceHydrationResult:
        normalized_clone_url = _normalize_clone_url(repository_clone_url)
        self._prepare_checkout(workspace_path=workspace_path, repository_clone_url=repository_clone_url)
        current_remote = self._git_capture(workspace_path, "remote", "get-url", "origin")
        if _normalize_clone_url(current_remote) != normalized_clone_url:
            shutil.rmtree(workspace_path)
            self._prepare_checkout(workspace_path=workspace_path, repository_clone_url=repository_clone_url)

        self._git(workspace_path, "fetch", "--prune", "origin")
        remote_branch_ref = f"refs/remotes/origin/{branch_name}"
        remote_branch_found = self._git_ref_exists(workspace_path, remote_branch_ref)
        checkout_ref = remote_branch_ref if remote_branch_found else f"refs/remotes/origin/{default_branch}"
        self._git(workspace_path, "checkout", "-B", branch_name, checkout_ref)
        checkout_revision = self._git_capture(workspace_path, "rev-parse", "HEAD")
        return WorkspaceHydrationResult(
            checkout_revision=checkout_revision,
            branch_reused=remote_branch_found,
            remote_branch_found=remote_branch_found,
        )

    def _prepare_checkout(self, *, workspace_path: Path, repository_clone_url: str) -> None:
        if (workspace_path / ".git").exists():
            return
        if workspace_path.exists():
            if any(workspace_path.iterdir()):
                shutil.rmtree(workspace_path)
        else:
            workspace_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(["clone", "--origin", "origin", "--no-checkout", repository_clone_url, str(workspace_path)])

    def _git(self, workspace_path: Path, *args: str) -> None:
        self._run(["-C", str(workspace_path), *args])

    def _git_capture(self, workspace_path: Path, *args: str) -> str:
        return self._run(["-C", str(workspace_path), *args], capture_output=True).strip()

    def _git_ref_exists(self, workspace_path: Path, ref_name: str) -> bool:
        result = subprocess.run(
            [self.git_bin, "-C", str(workspace_path), "show-ref", "--verify", "--quiet", ref_name],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _run(self, args: list[str], *, capture_output: bool = False) -> str:
        result = subprocess.run(
            [self.git_bin, *args],
            check=True,
            capture_output=capture_output,
            text=True,
        )
        return result.stdout if capture_output else ""


class ExecutionEnvironmentService:
    def __init__(
        self,
        session: Session,
        *,
        provider: RuntimeProvider | None = None,
        hydrator: GitWorkspaceHydrator | None = None,
    ):
        self.session = session
        self.provider = provider or build_runtime_provider()
        self.hydrator = hydrator or GitWorkspaceHydrator()

    def provision_claimed_lane(
        self,
        lane_id,
        *,
        repository_clone_url: str | None = None,
        allow_continuation: bool = True,
    ) -> ExecutionEnvironment:
        lane = self._load_lane(lane_id)
        if lane.claimed_at is None:
            raise LaneProvisioningError("Lane must be claimed before provisioning.")
        if lane.state in TERMINAL_LANE_STATES:
            raise LaneProvisioningError(f"Lane is already in terminal state: {lane.state}")

        execution = self._execution_config(lane)
        manifest_fingerprint = self._manifest_fingerprint(lane)
        secret_fingerprint = self._secret_fingerprint(lane)
        branch_name = _branch_name_for_lane(lane)
        lane.branch_name = branch_name

        environment = lane.execution_environment or self._environment_for_lane(lane)
        if environment is not None and environment.status in ACTIVE_ENVIRONMENT_STATUSES:
            if not allow_continuation:
                raise LaneProvisioningError("Lane already has an active execution environment.")
            if not self._continuation_is_safe(
                environment=environment,
                lane=lane,
                manifest_fingerprint=manifest_fingerprint,
                secret_fingerprint=secret_fingerprint,
            ):
                raise UnsafeContinuationError(
                    "Continuation reuse is blocked because the product, repository, manifest, or secrets changed."
                )
            if self.provider.can_reuse(environment):
                return environment

        if environment is None:
            environment = ExecutionEnvironment(
                lane_id=lane.lane_id,
                runtime_provider=self.provider.name,
                container_image=execution["container_image"],
                status="Provisioning",
            )
            self.session.add(environment)
            self.session.flush()
        lane.execution_environment = environment
        environment.runtime_provider = self.provider.name
        environment.container_image = execution["container_image"]
        environment.status = "Provisioning"
        environment.terminated_at = None
        environment.quarantine_reason = None

        provision_result = self.provider.provision(
            RuntimeProvisionRequest(
                environment_id=str(environment.execution_environment_id),
                lane_id=str(lane.lane_id),
                branch_name=branch_name,
                container_image=execution["container_image"],
            )
        )

        hydration_result = self.hydrator.hydrate(
            repository_clone_url=repository_clone_url or self._repository_clone_url(lane.repo),
            workspace_path=provision_result.workspace_path,
            default_branch=lane.repo.default_branch,
            branch_name=branch_name,
        )

        provider_metadata = dict(environment.provider_metadata or {})
        provider_metadata.update(provision_result.provider_metadata)
        provider_metadata["hydration"] = {
            "branch_reused": hydration_result.branch_reused,
            "remote_branch_found": hydration_result.remote_branch_found,
        }
        provider_metadata["runtime_identity"] = build_runtime_identity(lane)
        provider_metadata["credential_scope"] = {
            "org_id": str(lane.product.org_id),
            "product_id": str(lane.product_id),
            "repo_id": str(lane.repo_id),
            "lane_id": str(lane.lane_id),
            "branch_name": branch_name,
        }

        environment.container_handle = provision_result.container_handle
        environment.workspace_uri = provision_result.workspace_uri
        environment.artifact_uri = provision_result.artifact_uri
        environment.log_uri = provision_result.log_uri
        environment.cache_uri = provision_result.cache_uri
        environment.status = provision_result.status
        environment.checkout_revision = hydration_result.checkout_revision
        environment.manifest_fingerprint = manifest_fingerprint
        environment.secret_fingerprint = secret_fingerprint
        environment.provider_metadata = provider_metadata

        lane.execution_environment_id = environment.execution_environment_id
        scheduler = SchedulerService(self.session)
        scheduler.transition_lane_state(lane.lane_id, "Provisioning", reason="execution.provisioning")
        self.session.flush()
        return environment

    def finalize_lane_environment(
        self,
        lane_id,
        *,
        final_state: str,
        disposition: Literal["terminate", "quarantine"] = "terminate",
        reason: str | None = None,
    ) -> ExecutionEnvironment:
        lane = self._load_lane(lane_id)
        if final_state not in TERMINAL_LANE_STATES:
            raise LaneProvisioningError(f"Lane cleanup requires a terminal final state, got: {final_state}")
        environment = lane.execution_environment or self._environment_for_lane(lane)
        if environment is None:
            raise LaneProvisioningError("Lane does not have an execution environment.")

        cleanup_result = self.provider.cleanup(
            RuntimeCleanupRequest(
                environment_id=str(environment.execution_environment_id),
                container_handle=environment.container_handle,
                workspace_uri=environment.workspace_uri,
                artifact_uri=environment.artifact_uri,
                log_uri=environment.log_uri,
                cache_uri=environment.cache_uri,
                disposition=disposition,
                reason=reason,
            )
        )
        provider_metadata = dict(environment.provider_metadata or {})
        provider_metadata["cleanup"] = cleanup_result.provider_metadata
        environment.provider_metadata = provider_metadata
        environment.status = cleanup_result.status
        environment.terminated_at = cleanup_result.terminated_at
        environment.quarantine_reason = reason if disposition == "quarantine" else None

        SchedulerService(self.session).transition_lane_state(
            lane.lane_id,
            final_state,
            reason=reason or f"execution.cleanup.{disposition}",
            error_detail=reason if final_state == "FailedTerminal" else None,
            observed_at=cleanup_result.terminated_at,
            source_kind="runtime",
        )
        self.session.flush()
        return environment

    def continuation_is_safe(self, lane_id) -> bool:
        lane = self._load_lane(lane_id)
        environment = lane.execution_environment or self._environment_for_lane(lane)
        if environment is None:
            return False
        return self._continuation_is_safe(
            environment=environment,
            lane=lane,
            manifest_fingerprint=self._manifest_fingerprint(lane),
            secret_fingerprint=self._secret_fingerprint(lane),
        )

    def _load_lane(self, lane_id) -> OrchestrationLane:
        lane = self.session.get(OrchestrationLane, lane_id)
        if lane is None:
            raise LaneProvisioningError(f"Lane not found: {lane_id}")
        if lane.repo is None or lane.product is None or lane.work_item is None:
            raise LaneProvisioningError("Lane is missing required product, repository, or work-item context.")
        return lane

    def _environment_for_lane(self, lane: OrchestrationLane) -> ExecutionEnvironment | None:
        environment = (
            self.session.query(ExecutionEnvironment)
            .filter(ExecutionEnvironment.lane_id == lane.lane_id)
            .one_or_none()
        )
        if environment is not None:
            lane.execution_environment = environment
        return environment

    def _execution_config(self, lane: OrchestrationLane) -> dict[str, Any]:
        effective_config = lane.product.effective_config if isinstance(lane.product.effective_config, dict) else {}
        execution = dict(effective_config.get("execution", {}))
        profile = execution.get("profile") or lane.product.execution_profile or "standard-python"
        defaults = SUPPORTED_EXECUTION_PROFILES.get(profile)
        if defaults is None:
            raise LaneProvisioningError(f"Unsupported execution profile: {profile}")
        execution.setdefault("profile", profile)
        execution.setdefault("container_image", defaults["container_image"])
        execution.setdefault("workspace_strategy", defaults["workspace_strategy"])
        return execution

    def _manifest_fingerprint(self, lane: OrchestrationLane) -> str:
        effective_config = lane.product.effective_config if isinstance(lane.product.effective_config, dict) else {}
        return _json_fingerprint(
            {
                "product_id": str(lane.product_id),
                "repo_id": str(lane.repo_id),
                "execution_profile": lane.product.execution_profile,
                "effective_config": effective_config,
            }
        )

    def _secret_fingerprint(self, lane: OrchestrationLane) -> str:
        keys = self._required_secret_keys(lane)
        if not keys:
            return _json_fingerprint([])
        secrets = {
            secret.key: secret
            for secret in self.session.query(Secret).filter(Secret.key.in_(keys)).all()
        }
        payload = []
        for key in keys:
            secret = secrets.get(key)
            payload.append(
                {
                    "key": key,
                    "has_value": bool(secret and secret.has_value),
                    "updated_at": secret.updated_at.isoformat() if secret and secret.updated_at else None,
                }
            )
        return _json_fingerprint(payload)

    def _required_secret_keys(self, lane: OrchestrationLane) -> list[str]:
        effective_config = lane.product.effective_config if isinstance(lane.product.effective_config, dict) else {}
        activation = effective_config.get("activation", {})
        execution = effective_config.get("execution", {})
        profile = execution.get("profile") or lane.product.execution_profile or "standard-python"
        keys = {
            str(key).strip()
            for key in activation.get("required_secret_keys", [])
            if isinstance(key, str) and key.strip()
        }
        defaults = SUPPORTED_EXECUTION_PROFILES.get(profile, {})
        keys.update(
            str(key).strip()
            for key in defaults.get("required_secret_keys", [])
            if isinstance(key, str) and str(key).strip()
        )
        return sorted(keys)

    def _continuation_is_safe(
        self,
        *,
        environment: ExecutionEnvironment,
        lane: OrchestrationLane,
        manifest_fingerprint: str,
        secret_fingerprint: str,
    ) -> bool:
        return (
            environment.status in ACTIVE_ENVIRONMENT_STATUSES
            and environment.manifest_fingerprint == manifest_fingerprint
            and environment.secret_fingerprint == secret_fingerprint
            and environment.runtime_provider == self.provider.name
            and environment.lane_id == lane.lane_id
            and lane.state in ACTIVE_LANE_OWNERSHIP_STATES
            and lane.repo_id == lane.repo.repo_id
            and lane.product_id == lane.product.product_id
        )

    def _repository_clone_url(self, repo: RepositoryBinding) -> str:
        if isinstance(repo.raw_payload, dict):
            clone_url = repo.raw_payload.get("clone_url") or repo.raw_payload.get("ssh_url")
            if isinstance(clone_url, str) and clone_url.strip():
                return clone_url.strip()
        return f"https://github.com/{repo.owner}/{repo.name}.git"
