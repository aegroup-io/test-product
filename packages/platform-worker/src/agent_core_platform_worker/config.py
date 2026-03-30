from __future__ import annotations

import os
from dataclasses import dataclass


def _split_csv(value: str | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class WorkerConfig:
    api_base_url: str
    request_timeout_seconds: float
    api_token: str | None
    live_runner_enabled: bool
    live_runner_version: str
    live_runner_capabilities: tuple[str, ...]
    live_runner_max_launches_per_poll: int
    live_runner_codex_bin: str
    live_runner_codex_model: str | None
    live_runner_codex_sandbox: str
    live_runner_heartbeat_interval_seconds: float


def _optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def load_config() -> WorkerConfig:
    token = os.getenv("AGENT_CORE_API_TOKEN")
    token = token.strip() if token and token.strip() else None
    return WorkerConfig(
        api_base_url=os.getenv("AGENT_CORE_API_BASE_URL", "http://127.0.0.1:8000"),
        request_timeout_seconds=float(os.getenv("AGENT_CORE_WORKER_TIMEOUT_SECONDS", "10")),
        api_token=token,
        live_runner_enabled=_as_bool(os.getenv("AGENT_CORE_LIVE_RUNNER_ENABLED"), default=True),
        live_runner_version=os.getenv("AGENT_CORE_LIVE_RUNNER_VERSION", "agent-core-platform-worker/codex-live"),
        live_runner_capabilities=_split_csv(
            os.getenv("AGENT_CORE_LIVE_RUNNER_CAPABILITIES"),
            default=("stream-events",),
        ),
        live_runner_max_launches_per_poll=max(1, int(os.getenv("AGENT_CORE_LIVE_RUNNER_MAX_POLLS", "1"))),
        live_runner_codex_bin=os.getenv("AGENT_CORE_LIVE_RUNNER_CODEX_BIN", "codex"),
        live_runner_codex_model=_optional_string(os.getenv("AGENT_CORE_LIVE_RUNNER_CODEX_MODEL")),
        live_runner_codex_sandbox=os.getenv("AGENT_CORE_LIVE_RUNNER_CODEX_SANDBOX", "workspace-write").strip()
        or "workspace-write",
        live_runner_heartbeat_interval_seconds=max(
            1.0,
            float(os.getenv("AGENT_CORE_LIVE_RUNNER_HEARTBEAT_INTERVAL_SECONDS", "30")),
        ),
    )
