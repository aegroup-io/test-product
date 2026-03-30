from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import selectors
import subprocess
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from agent_core_platform_worker.config import WorkerConfig


DEFAULT_TURN_PREFIX = "codex-turn"
LAUNCH_REQUEST_FILENAME = "runner-launch-request.json"
PROMPT_FILENAME = "codex-prompt.md"
LAST_MESSAGE_FILENAME = "codex-last-message.md"
RESULT_FILENAME = "codex-run-result.json"
JSONL_LOG_FILENAME = "codex-output.jsonl"
RAW_LOG_FILENAME = "codex-output.raw.log"


@dataclass(frozen=True)
class LaunchPaths:
    workspace_path: Path
    artifact_path: Path
    log_path: Path
    cache_path: Path


@dataclass(frozen=True)
class LaunchArtifacts:
    launch_request_path: Path
    prompt_path: Path
    last_message_path: Path
    result_path: Path
    jsonl_log_path: Path
    raw_log_path: Path


@dataclass(frozen=True)
class CodexExecutionOutcome:
    success: bool
    exit_code: int
    execution_backend: str
    thread_id: str | None
    turn_id: str | None
    last_message: str | None
    changed_files: list[str]
    error_message: str | None
    prompt_path: Path
    launch_request_path: Path
    last_message_path: Path
    result_path: Path
    jsonl_log_path: Path
    raw_log_path: Path
    raw_line_count: int
    json_event_count: int


@dataclass
class _ExecutionState:
    thread_id: str | None = None
    turn_id: str | None = None
    turn_index: int = 0
    last_message: str | None = None
    changed_files: list[str] = field(default_factory=list)
    raw_line_count: int = 0
    json_event_count: int = 0


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


def resolve_launch_paths(launch: dict[str, Any]) -> LaunchPaths:
    destinations = launch.get("artifact_destinations")
    if not isinstance(destinations, dict):
        raise RuntimeError("Launch payload is missing artifact destinations.")

    workspace_path = _uri_to_path(destinations.get("workspace_uri"))
    artifact_path = _uri_to_path(destinations.get("artifact_uri"))
    log_path = _uri_to_path(destinations.get("log_uri"))
    cache_path = _uri_to_path(destinations.get("cache_uri"))
    if workspace_path is None or artifact_path is None or log_path is None or cache_path is None:
        raise RuntimeError("Launch payload contained invalid workspace or artifact paths.")

    for path in (artifact_path, log_path, cache_path):
        path.mkdir(parents=True, exist_ok=True)
    if not workspace_path.exists():
        raise RuntimeError(f"Lane workspace does not exist: {workspace_path}")
    return LaunchPaths(
        workspace_path=workspace_path,
        artifact_path=artifact_path,
        log_path=log_path,
        cache_path=cache_path,
    )


def render_codex_prompt(launch: dict[str, Any], *, paths: LaunchPaths) -> str:
    instruction_bundle = dict(launch.get("instruction_bundle") or {})
    issue_context = dict(launch.get("issue_context") or {})
    lane_metadata = dict(launch.get("lane_metadata") or {})
    policy = dict(launch.get("policy") or {})
    secret_references = list(launch.get("secret_references") or [])
    tool_permissions = list(launch.get("tool_permissions") or [])
    required_capabilities = list(launch.get("required_capabilities") or [])

    sections = [
        "# Orcha Lane Task",
        "",
        "You are executing a real Orcha coding lane against the hydrated repository checkout already present in this workspace.",
        "Follow repo-local instructions before making changes, especially `AGENTS.md`, docs referenced from it, and any issue-specific guidance in the repo.",
        "",
        "## Task",
        instruction_bundle.get("task") or "No explicit task was provided.",
        "",
        "## System Prompt",
        instruction_bundle.get("system_prompt") or "No explicit system prompt was provided.",
        "",
        "## Issue Body",
        instruction_bundle.get("issue_body") or "(empty)",
        "",
        "## Lane Metadata",
        "```json",
        json.dumps(lane_metadata, indent=2, sort_keys=True),
        "```",
        "",
        "## Issue Context",
        "```json",
        json.dumps(issue_context, indent=2, sort_keys=True),
        "```",
        "",
        "## Instruction Bundle",
        "```json",
        json.dumps(instruction_bundle, indent=2, sort_keys=True),
        "```",
        "",
        "## Policy Snapshot",
        "```json",
        json.dumps(policy, indent=2, sort_keys=True),
        "```",
        "",
        "## Runtime Context",
        "```json",
        json.dumps(
            {
                "workspace_path": str(paths.workspace_path),
                "artifact_path": str(paths.artifact_path),
                "log_path": str(paths.log_path),
                "cache_path": str(paths.cache_path),
                "secret_references": secret_references,
                "tool_permissions": tool_permissions,
                "required_capabilities": required_capabilities,
            },
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Expectations",
        "- Work only within the current issue scope and repo policy.",
        "- Use the existing branch/workspace; do not create a second clone.",
        "- Leave the repository in a coherent state and summarize the work in the final response.",
    ]
    return "\n".join(sections).strip() + "\n"


def prepare_launch_artifacts(launch: dict[str, Any], *, paths: LaunchPaths) -> LaunchArtifacts:
    launch_request_path = paths.artifact_path / LAUNCH_REQUEST_FILENAME
    prompt_path = paths.artifact_path / PROMPT_FILENAME
    last_message_path = paths.artifact_path / LAST_MESSAGE_FILENAME
    result_path = paths.artifact_path / RESULT_FILENAME
    jsonl_log_path = paths.log_path / JSONL_LOG_FILENAME
    raw_log_path = paths.log_path / RAW_LOG_FILENAME

    launch_request_path.write_text(
        json.dumps(launch, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt_path.write_text(render_codex_prompt(launch, paths=paths), encoding="utf-8")
    return LaunchArtifacts(
        launch_request_path=launch_request_path,
        prompt_path=prompt_path,
        last_message_path=last_message_path,
        result_path=result_path,
        jsonl_log_path=jsonl_log_path,
        raw_log_path=raw_log_path,
    )


def build_codex_command(
    *,
    config: WorkerConfig,
    paths: LaunchPaths,
    artifacts: LaunchArtifacts,
) -> list[str]:
    command = [config.live_runner_codex_bin]
    if config.live_runner_codex_sandbox == "danger-full-access":
        command.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        command.extend(["-a", "never"])
    command.extend(["exec"])
    if config.live_runner_codex_model:
        command.extend(["-m", config.live_runner_codex_model])
    command.extend(
        [
            "--json",
            "--color",
            "never",
            "--cd",
            str(paths.workspace_path),
        ]
    )
    if config.live_runner_codex_sandbox != "danger-full-access":
        command.extend(["--sandbox", config.live_runner_codex_sandbox])
    for writable_dir in (paths.artifact_path, paths.log_path, paths.cache_path):
        command.extend(["--add-dir", str(writable_dir)])
    command.extend(
        [
            "--output-last-message",
            str(artifacts.last_message_path),
            "-",
        ]
    )
    return command


def _shorten(text: str | None, *, limit: int = 240) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 3, 0)] + "..."


def _relativize_path(value: str | None, *, workspace_path: Path) -> str | None:
    if not value:
        return None
    candidate = Path(value).resolve()
    try:
        return str(candidate.relative_to(workspace_path))
    except ValueError:
        return str(candidate)


def _turn_id(state: _ExecutionState) -> str | None:
    return state.turn_id


def _translate_codex_event(
    payload: dict[str, Any],
    *,
    state: _ExecutionState,
    workspace_path: Path,
) -> list[dict[str, Any]]:
    codex_event_type = str(payload.get("type") or "").strip()
    if not codex_event_type:
        return []

    translated: list[dict[str, Any]] = []
    if codex_event_type == "thread.started":
        thread_id = str(payload.get("thread_id") or "").strip() or None
        state.thread_id = thread_id
        translated.append(
            {
                "event_type": "status_summary",
                "summary": "Codex thread started.",
                "payload": {"source": "codex", "codex_event_type": codex_event_type},
                "thread_id": state.thread_id,
                "turn_id": _turn_id(state),
            }
        )
        return translated

    if codex_event_type == "turn.started":
        state.turn_index += 1
        state.turn_id = f"{DEFAULT_TURN_PREFIX}-{state.turn_index}"
        translated.append(
            {
                "event_type": "turn_started",
                "summary": "Codex turn started.",
                "payload": {"source": "codex"},
                "thread_id": state.thread_id,
                "turn_id": state.turn_id,
            }
        )
        return translated

    if codex_event_type == "turn.completed":
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        token_usage = {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(
                usage.get("total_tokens")
                or ((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
            ),
        }
        translated.append(
            {
                "event_type": "token_usage_reported",
                "summary": "Codex reported token usage.",
                "payload": {"source": "codex"},
                "thread_id": state.thread_id,
                "turn_id": _turn_id(state),
                "token_usage": token_usage,
            }
        )
        translated.append(
            {
                "event_type": "turn_completed",
                "summary": "Codex turn completed.",
                "payload": {"source": "codex"},
                "thread_id": state.thread_id,
                "turn_id": _turn_id(state),
            }
        )
        return translated

    item = payload.get("item") if isinstance(payload.get("item"), dict) else None
    item_type = str(item.get("type") or "").strip() if item is not None else ""
    item_id = str(item.get("id") or "").strip() if item is not None else ""

    if codex_event_type == "item.started" and item_type == "command_execution":
        command = str(item.get("command") or "").strip()
        translated.append(
            {
                "event_type": "tool_call_started",
                "summary": _shorten(f"Codex started command: {command}", limit=180),
                "payload": {"source": "codex", "item_id": item_id, "command": command},
                "thread_id": state.thread_id,
                "turn_id": _turn_id(state),
                "tool_name": "shell.exec",
                "tool_status": "started",
            }
        )
        return translated

    if codex_event_type == "item.completed" and item_type == "command_execution":
        command = str(item.get("command") or "").strip()
        aggregated_output = str(item.get("aggregated_output") or "")
        translated.append(
            {
                "event_type": "tool_call_finished",
                "summary": _shorten(f"Codex finished command: {command}", limit=180),
                "payload": {
                    "source": "codex",
                    "item_id": item_id,
                    "command": command,
                    "exit_code": int(item.get("exit_code") or 0),
                    "output_preview": _shorten(aggregated_output, limit=500),
                },
                "thread_id": state.thread_id,
                "turn_id": _turn_id(state),
                "tool_name": "shell.exec",
                "tool_status": str(item.get("status") or "completed"),
            }
        )
        return translated

    if codex_event_type == "item.completed" and item_type == "file_change":
        for change in item.get("changes") or []:
            if not isinstance(change, dict):
                continue
            relative_path = _relativize_path(str(change.get("path") or ""), workspace_path=workspace_path)
            if relative_path:
                state.changed_files.append(relative_path)
            translated.append(
                {
                    "event_type": "artifact_created",
                    "summary": _shorten(
                        f"Codex recorded file change: {relative_path or change.get('path')}",
                        limit=180,
                    ),
                    "payload": {
                        "source": "codex",
                        "item_id": item_id,
                        "path": relative_path or str(change.get("path") or ""),
                        "change_kind": str(change.get("kind") or "updated"),
                    },
                    "thread_id": state.thread_id,
                    "turn_id": _turn_id(state),
                }
            )
        return translated

    if codex_event_type == "item.completed" and item_type == "agent_message":
        text = str(item.get("text") or "")
        state.last_message = text.strip() or state.last_message
        translated.append(
            {
                "event_type": "status_summary",
                "summary": _shorten(text, limit=240) or "Codex produced an assistant message.",
                "payload": {"source": "codex", "item_id": item_id},
                "thread_id": state.thread_id,
                "turn_id": _turn_id(state),
            }
        )
        return translated

    translated.append(
        {
            "event_type": "status_summary",
            "summary": _shorten(f"Codex event: {codex_event_type}", limit=180) or "Codex emitted an event.",
            "payload": {"source": "codex", "codex_event_type": codex_event_type},
            "thread_id": state.thread_id,
            "turn_id": _turn_id(state),
        }
    )
    return translated


def _write_result_artifact(*, artifacts: LaunchArtifacts, outcome: CodexExecutionOutcome) -> None:
    payload = {
        "success": outcome.success,
        "exit_code": outcome.exit_code,
        "execution_backend": outcome.execution_backend,
        "thread_id": outcome.thread_id,
        "turn_id": outcome.turn_id,
        "last_message": outcome.last_message,
        "changed_files": outcome.changed_files,
        "error_message": outcome.error_message,
        "prompt_path": str(outcome.prompt_path),
        "launch_request_path": str(outcome.launch_request_path),
        "last_message_path": str(outcome.last_message_path),
        "jsonl_log_path": str(outcome.jsonl_log_path),
        "raw_log_path": str(outcome.raw_log_path),
        "raw_line_count": outcome.raw_line_count,
        "json_event_count": outcome.json_event_count,
    }
    artifacts.result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_codex_launch(
    launch: dict[str, Any],
    *,
    config: WorkerConfig,
    event_callback: Callable[[dict[str, Any]], None],
    heartbeat_callback: Callable[[str | None, str | None], None] | None = None,
    popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> CodexExecutionOutcome:
    paths = resolve_launch_paths(launch)
    artifacts = prepare_launch_artifacts(launch, paths=paths)
    command = build_codex_command(config=config, paths=paths, artifacts=artifacts)
    state = _ExecutionState()

    process: subprocess.Popen[str] | None = None
    exit_code = 1
    error_message: str | None = None
    try:
        process = popen_factory(
            command,
            cwd=paths.workspace_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Codex runner did not expose stdin/stdout pipes.")
        prompt_text = artifacts.prompt_path.read_text(encoding="utf-8")
        process.stdin.write(prompt_text)
        process.stdin.close()

        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        saw_stdout_eof = False
        with artifacts.jsonl_log_path.open("w", encoding="utf-8") as jsonl_log, artifacts.raw_log_path.open(
            "w", encoding="utf-8"
        ) as raw_log:
            while True:
                timeout = max(config.live_runner_heartbeat_interval_seconds, 0.5)
                selected = selector.select(timeout=timeout)
                if selected:
                    for key, _ in selected:
                        line = key.fileobj.readline()
                        if line == "":
                            saw_stdout_eof = True
                            try:
                                selector.unregister(key.fileobj)
                            except KeyError:
                                pass
                            continue
                        raw_log.write(line)
                        raw_log.flush()
                        state.raw_line_count += 1
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            payload = json.loads(stripped)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        jsonl_log.write(json.dumps(payload, sort_keys=True) + "\n")
                        jsonl_log.flush()
                        state.json_event_count += 1
                        for translated_event in _translate_codex_event(payload, state=state, workspace_path=paths.workspace_path):
                            event_callback(translated_event)
                else:
                    if process.poll() is not None or saw_stdout_eof:
                        break
                    if heartbeat_callback is not None:
                        heartbeat_callback(state.thread_id, state.turn_id)

                if process.poll() is not None and (saw_stdout_eof or not selected):
                    break
        exit_code = process.wait()
    except Exception as exc:
        error_message = str(exc)
        if process is not None and process.poll() is None:
            process.kill()
            exit_code = process.wait()
        else:
            exit_code = exit_code or 1

    if state.last_message and not artifacts.last_message_path.exists():
        artifacts.last_message_path.write_text(state.last_message + "\n", encoding="utf-8")

    success = error_message is None and exit_code == 0
    if not success and error_message is None:
        error_message = f"Codex runner exited with code {exit_code}."

    outcome = CodexExecutionOutcome(
        success=success,
        exit_code=exit_code,
        execution_backend="host-codex",
        thread_id=state.thread_id,
        turn_id=state.turn_id,
        last_message=state.last_message,
        changed_files=sorted(set(state.changed_files)),
        error_message=error_message,
        prompt_path=artifacts.prompt_path,
        launch_request_path=artifacts.launch_request_path,
        last_message_path=artifacts.last_message_path,
        result_path=artifacts.result_path,
        jsonl_log_path=artifacts.jsonl_log_path,
        raw_log_path=artifacts.raw_log_path,
        raw_line_count=state.raw_line_count,
        json_event_count=state.json_event_count,
    )
    _write_result_artifact(artifacts=artifacts, outcome=outcome)
    return outcome
