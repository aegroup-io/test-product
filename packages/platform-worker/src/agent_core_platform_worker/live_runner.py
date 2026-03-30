from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

import httpx

from agent_core_platform_worker.codex_runner import CodexExecutionOutcome, run_codex_launch
from agent_core_platform_worker.config import WorkerConfig, load_config


class RunnerAPIClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str] | None = None) -> Any: ...

    def post(self, url: str, *, headers: dict[str, str] | None = None, json: dict[str, Any] | None = None) -> Any: ...


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_headers(config: WorkerConfig) -> dict[str, str]:
    if not config.api_token:
        return {}
    return {"Authorization": f"Bearer {config.api_token}"}


def _capabilities_from_launch(_: dict[str, Any], config: WorkerConfig) -> list[str]:
    configured = sorted(
        {
            value.strip()
            for value in config.live_runner_capabilities
            if isinstance(value, str) and value.strip()
        }
    )
    return configured or ["stream-events"]


def _environment_identity_from_launch(launch: dict[str, Any]) -> str:
    lane_metadata = launch.get("lane_metadata")
    if isinstance(lane_metadata, dict):
        value = lane_metadata.get("environment_identity")
        if isinstance(value, str) and value.strip():
            return value.strip()
    lane_id = str(launch.get("lane_id") or "unknown-lane")
    return f"runner://{lane_id}"


def _ensure_success(response: Any, *, context: str) -> None:
    status_code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= status_code < 300:
        return
    body_preview = str(getattr(response, "text", ""))[:200]
    raise RuntimeError(f"{context} failed with status {status_code}: {body_preview}")


def _post_event(
    client: RunnerAPIClient,
    lane_id: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    context: str,
) -> None:
    event_payload = dict(payload)
    event_payload.setdefault("observed_at", _iso_now())
    response = client.post(f"/v1/runner/lanes/{lane_id}/events", headers=headers, json=event_payload)
    _ensure_success(response, context=context)


def _post_heartbeat(
    client: RunnerAPIClient,
    lane_id: str,
    *,
    headers: dict[str, str],
    thread_id: str | None,
    turn_id: str | None,
) -> None:
    heartbeat_payload = {
        "heartbeat_at": _iso_now(),
        "thread_id": thread_id,
        "turn_id": turn_id,
    }
    response = client.post(f"/v1/runner/lanes/{lane_id}/heartbeat", headers=headers, json=heartbeat_payload)
    _ensure_success(response, context=f"Runner heartbeat for lane {lane_id}")


def _terminal_event_from_outcome(outcome: CodexExecutionOutcome) -> dict[str, Any]:
    payload = {
        "source": "platform-worker",
        "runner": "codex",
        "execution_backend": outcome.execution_backend,
        "changed_files": outcome.changed_files,
        "prompt_path": str(outcome.prompt_path),
        "launch_request_path": str(outcome.launch_request_path),
        "last_message_path": str(outcome.last_message_path),
        "result_path": str(outcome.result_path),
        "jsonl_log_path": str(outcome.jsonl_log_path),
        "raw_log_path": str(outcome.raw_log_path),
        "exit_code": outcome.exit_code,
        "json_event_count": outcome.json_event_count,
        "raw_line_count": outcome.raw_line_count,
    }
    if outcome.success:
        summary = outcome.last_message or "Codex lane completed successfully."
        return {
            "event_type": "session_completed",
            "summary": summary,
            "payload": payload,
            "thread_id": outcome.thread_id,
            "turn_id": outcome.turn_id,
        }
    error_payload = dict(payload)
    error_payload["error"] = outcome.error_message or "Codex lane execution failed."
    return {
        "event_type": "session_failed",
        "summary": outcome.error_message or "Codex lane execution failed.",
        "payload": error_payload,
        "thread_id": outcome.thread_id,
        "turn_id": outcome.turn_id,
        "error_category": "agent_runtime",
    }


def _dispatch_launch(client: RunnerAPIClient, launch: dict[str, Any], *, headers: dict[str, str], config: WorkerConfig) -> None:
    lane_id = str(launch.get("lane_id") or "").strip()
    if not lane_id:
        raise RuntimeError("Launch payload is missing lane_id.")

    handshake_payload = {
        "runner_session_id": f"worker-runner-{uuid4().hex}",
        "runner_version": config.live_runner_version,
        "capabilities": _capabilities_from_launch(launch, config),
        "environment_identity": _environment_identity_from_launch(launch),
        "heartbeat_at": _iso_now(),
        "thread_id": f"worker-thread-{lane_id}",
    }
    handshake = client.post(f"/v1/runner/lanes/{lane_id}/handshake", headers=headers, json=handshake_payload)
    _ensure_success(handshake, context=f"Runner handshake for lane {lane_id}")

    _post_event(
        client,
        lane_id,
        headers=headers,
        payload={
            "event_type": "status_summary",
            "summary": "Live worker accepted launch and started a real Codex execution.",
            "payload": {"source": "platform-worker", "mode": "codex-exec"},
            "thread_id": handshake_payload["thread_id"],
        },
        context=f"Runner status event for lane {lane_id}",
    )

    outcome = run_codex_launch(
        launch,
        config=config,
        event_callback=lambda payload: _post_event(
            client,
            lane_id,
            headers=headers,
            payload=payload,
            context=f"Runner streamed event for lane {lane_id}",
        ),
        heartbeat_callback=lambda thread_id, turn_id: _post_heartbeat(
            client,
            lane_id,
            headers=headers,
            thread_id=thread_id,
            turn_id=turn_id,
        ),
    )
    _post_event(
        client,
        lane_id,
        headers=headers,
        payload=_terminal_event_from_outcome(outcome),
        context=f"Runner terminal event for lane {lane_id}",
    )


def process_pending_runner_launches(
    client: RunnerAPIClient,
    *,
    config: WorkerConfig | None = None,
    max_launches: int | None = None,
) -> int:
    resolved_config = config or load_config()
    if not resolved_config.live_runner_enabled:
        return 0

    headers = _request_headers(resolved_config)
    processed = 0
    launch_limit = max_launches if max_launches is not None else resolved_config.live_runner_max_launches_per_poll
    for _ in range(max(launch_limit, 1)):
        launch_response = client.get("/v1/runner/launches/next", headers=headers)
        status_code = int(getattr(launch_response, "status_code", 0) or 0)
        if status_code == 204:
            break
        _ensure_success(launch_response, context="Runner launch poll")
        launch_payload = launch_response.json()
        if not isinstance(launch_payload, dict):
            raise RuntimeError("Runner launch endpoint returned a non-object payload.")
        _dispatch_launch(client, launch_payload, headers=headers, config=resolved_config)
        processed += 1
    return processed


def poll_and_process_runner_launches(*, config: WorkerConfig | None = None) -> int:
    resolved_config = config or load_config()
    if not resolved_config.live_runner_enabled:
        return 0
    with httpx.Client(
        base_url=resolved_config.api_base_url.rstrip("/"),
        timeout=resolved_config.request_timeout_seconds,
    ) as client:
        return process_pending_runner_launches(client, config=resolved_config)
