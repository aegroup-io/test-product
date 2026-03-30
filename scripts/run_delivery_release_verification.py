#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / ".agent-core" / "delivery-release-verification.json"
DEFAULT_OUTPUT_DIR = "artifacts/delivery-release-verification"


class StepFailure(RuntimeError):
    def __init__(self, step: dict[str, Any]) -> None:
        super().__init__(step.get("name", "step failed"))
        self.step = step


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "release"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Delivery release verification config must be a JSON object.")
    return payload


def require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Config requires a non-empty '{key}' value.")
    return value.strip()


def optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Optional field '{key}' must be a non-empty string when provided.")
    return value.strip()


def optional_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SystemExit(f"Optional field '{key}' must be a boolean when provided.")
    return value


def optional_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SystemExit(f"Optional field '{key}' must be a list of non-empty strings when provided.")
    return [item.strip() for item in value]


def optional_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("metadata")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SystemExit("Optional field 'metadata' must be an object when provided.")
    return value


def resolve_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def ensure_file(path_value: str, *, label: str) -> None:
    if not resolve_repo_path(path_value).exists():
        raise SystemExit(f"{label} not found: {path_value}")


def run_command_step(name: str, command: list[str]) -> dict[str, Any]:
    print(f"Running {name}...")
    started_at = utc_now()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")

    step = {
        "name": name,
        "command": command,
        "result": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "started_at": started_at,
        "completed_at": utc_now(),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise StepFailure(step)
    return step


def verify_required_paths(required_paths: list[str]) -> dict[str, Any]:
    print("Running verify_required_paths...")
    missing_paths = [path for path in required_paths if not resolve_repo_path(path).exists()]
    step = {
        "name": "verify_required_paths",
        "result": "passed" if not missing_paths else "failed",
        "verified_paths": required_paths,
        "missing_paths": missing_paths,
        "started_at": utc_now(),
        "completed_at": utc_now(),
    }
    if missing_paths:
        raise StepFailure(step)
    return step


def build_report(
    *,
    release_id: str,
    config_path: Path,
    output_dir: str,
    metadata: dict[str, Any],
    required_paths: list[str],
    steps: list[dict[str, Any]],
    result: str,
    started_at: str,
) -> dict[str, Any]:
    return {
        "release_id": release_id,
        "config_path": str(config_path),
        "output_dir": output_dir,
        "metadata": metadata,
        "required_paths": required_paths,
        "result": result,
        "started_at": started_at,
        "completed_at": utc_now(),
        "steps": steps,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Delivery Release Verification",
        "",
        f"- release id: `{report['release_id']}`",
        f"- result: `{report['result']}`",
        f"- config: `{report['config_path']}`",
        f"- generated: `{report['completed_at']}`",
    ]
    metadata = report.get("metadata") or {}
    if metadata:
        lines.extend(["", "## Metadata"])
        for key in sorted(metadata):
            lines.append(f"- {key}: `{metadata[key]}`")
    required_paths = report.get("required_paths") or []
    if required_paths:
        lines.extend(["", "## Required Paths"])
        for path_value in required_paths:
            lines.append(f"- `{path_value}`")
    lines.extend(["", "## Steps"])
    for step in report.get("steps", []):
        lines.append(f"- `{step['name']}`: `{step['result']}`")
    lines.append("")
    return "\n".join(lines)


def write_reports(report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir = resolve_repo_path(report["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(report["release_id"])
    json_path = output_dir / f"{slug}.json"
    markdown_path = output_dir / f"{slug}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    try:
        json_label = json_path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        json_label = json_path.resolve()
    try:
        markdown_label = markdown_path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        markdown_label = markdown_path.resolve()
    print(f"Wrote release report: {json_label}")
    print(f"Wrote release summary: {markdown_label}")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run repo-local delivery release verification.")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        type=Path,
        help="JSON config to execute (defaults to .agent-core/delivery-release-verification.json).",
    )
    args = parser.parse_args(argv)

    config_path = args.config.resolve()
    payload = read_json(config_path)
    release_id = require_string(payload, "release_id")
    metadata = optional_metadata(payload)
    required_paths = optional_string_list(payload, "required_paths")
    run_local_harness = optional_bool(payload, "run_local_harness", default=True)
    run_delivery_smoke = optional_bool(payload, "run_delivery_smoke", default=True)
    delivery_smoke_config = optional_string(payload, "delivery_smoke_config") or ".agent-core/delivery-baseline-smoke.json"
    output_dir = optional_string(payload, "output_dir") or DEFAULT_OUTPUT_DIR

    if run_delivery_smoke:
        ensure_file(delivery_smoke_config, label="delivery_smoke_config")

    started_at = utc_now()
    steps: list[dict[str, Any]] = []
    result = "passed"

    try:
        if run_local_harness:
            steps.append(run_command_step("local_harness", ["bash", "scripts/smoke_local.sh"]))
        if run_delivery_smoke:
            steps.append(
                run_command_step(
                    "delivery_baseline_smoke",
                    [
                        sys.executable,
                        "scripts/run_delivery_baseline_smoke.py",
                        "--config",
                        delivery_smoke_config,
                    ],
                )
            )
        steps.append(verify_required_paths(required_paths))
    except StepFailure as exc:
        result = "failed"
        steps.append(exc.step)
    report = build_report(
        release_id=release_id,
        config_path=config_path,
        output_dir=output_dir,
        metadata=metadata,
        required_paths=required_paths,
        steps=steps,
        result=result,
        started_at=started_at,
    )
    write_reports(report)
    if result != "passed":
        return 1
    print("OK delivery release verification completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
