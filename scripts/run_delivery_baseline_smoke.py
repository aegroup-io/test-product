#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / ".agent-core" / "delivery-baseline-smoke.json"


def run_command(command: list[str], *, cwd: Path = REPO_ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True, text=True)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Delivery baseline config must be a JSON object.")
    return payload


def require_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"Config section '{key}' must be an object.")
    return value


def require_string(section: dict[str, Any], key: str, *, section_name: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Config section '{section_name}' requires a non-empty '{key}' value.")
    return value.strip()


def require_string_list(section: dict[str, Any], key: str, *, section_name: str) -> list[str]:
    value = section.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise SystemExit(f"Config section '{section_name}' requires a non-empty string list at '{key}'.")
    return [item.strip() for item in value]


def optional_string(section: dict[str, Any], key: str, *, allow_empty: bool = False) -> str | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"Optional field '{key}' must be a string when provided.")
    if allow_empty:
        return value
    if not value.strip():
        raise SystemExit(f"Optional field '{key}' must be a non-empty string when provided.")
    return value.strip()


def optional_bool(section: dict[str, Any], key: str) -> bool | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise SystemExit(f"Optional field '{key}' must be a boolean when provided.")
    return value


def ensure_file(path_value: str, *, label: str) -> None:
    path = (REPO_ROOT / path_value).resolve()
    if not path.exists():
        raise SystemExit(f"{label} not found: {path_value}")


def run_terraform_backend(section: dict[str, Any]) -> None:
    resource_group = require_string(section, "resource_group", section_name="terraform_backend")
    storage_account = require_string(section, "storage_account", section_name="terraform_backend")
    command = [
        "bash",
        "scripts/bootstrap_terraform_backend.sh",
        "--resource-group",
        resource_group,
        "--storage-account",
        storage_account,
    ]
    for key, flag in (
        ("env", "--env"),
        ("location", "--location"),
        ("container", "--container"),
        ("state_key", "--state-key"),
        ("workdir", "--workdir"),
        ("backend_config", "--backend-config"),
    ):
        value = optional_string(section, key)
        if value:
            command.extend([flag, value])
    command.append("--render-only")
    run_command(command)


def run_container_image(section: dict[str, Any]) -> None:
    image = require_string(section, "image", section_name="container_image")
    dockerfile = require_string(section, "dockerfile", section_name="container_image")
    context = require_string(section, "context", section_name="container_image")
    ensure_file(dockerfile, label="container_image.dockerfile")
    ensure_file(context, label="container_image.context")
    command = [
        "bash",
        "scripts/build_push_container_image.sh",
        "--image",
        image,
        "--dockerfile",
        dockerfile,
        "--context",
        context,
    ]
    for key, flag in (
        ("platform", "--platform"),
        ("builder_name", "--builder-name"),
    ):
        value = optional_string(section, key)
        if value:
            command.extend([flag, value])
    if optional_bool(section, "no_login"):
        command.append("--no-login")
    if optional_bool(section, "no_push"):
        command.append("--no-push")
    command.append("--dry-run")
    run_command(command)


def run_aks_workload(section: dict[str, Any]) -> None:
    namespace = require_string(section, "namespace", section_name="aks_workload")
    manifests = require_string_list(section, "manifests", section_name="aks_workload")
    workload_name = require_string(section, "workload_name", section_name="aks_workload")
    for manifest in manifests:
        ensure_file(manifest, label="aks_workload.manifest")
    command = [
        "bash",
        "scripts/deploy_aks_workload.sh",
        "--namespace",
        namespace,
    ]
    for manifest in manifests:
        command.extend(["--manifest", manifest])
    command.extend(["--workload-name", workload_name])
    for key, flag in (
        ("rollout_kind", "--rollout-kind"),
        ("rollout_timeout", "--rollout-timeout"),
        ("secret_name", "--secret-name"),
        ("secret_env_file", "--secret-env-file"),
    ):
        value = optional_string(section, key)
        if value:
            if key == "secret_env_file":
                ensure_file(value, label="aks_workload.secret_env_file")
            command.extend([flag, value])
    if optional_bool(section, "no_namespace_create"):
        command.append("--no-namespace-create")
    if optional_bool(section, "no_wait"):
        command.append("--no-wait")
    command.append("--dry-run")
    run_command(command)


def run_apim(section: dict[str, Any]) -> None:
    resource_group = require_string(section, "resource_group", section_name="apim")
    apim_name = require_string(section, "apim_name", section_name="apim")
    api_id = require_string(section, "api_id", section_name="apim")
    openapi_path = require_string(section, "openapi_path", section_name="apim")
    ensure_file(openapi_path, label="apim.openapi_path")
    command = [
        "bash",
        "scripts/sync_apim_api.sh",
        "--resource-group",
        resource_group,
        "--apim",
        apim_name,
        "--api-id",
        api_id,
        "--openapi-path",
        openapi_path,
    ]
    api_path = optional_string(section, "api_path", allow_empty=True)
    if api_path is not None:
        command.extend(["--api-path", api_path])
    service_url = optional_string(section, "service_url")
    if service_url:
        command.extend(["--service-url", service_url])
    else:
        service_name = require_string(section, "service_name", section_name="apim")
        namespace = require_string(section, "namespace", section_name="apim")
        command.extend(["--service-name", service_name, "--namespace", namespace])
        for key, flag in (
            ("aks_resource_group", "--aks-rg"),
            ("aks_cluster_name", "--aks-name"),
            ("service_scheme", "--service-scheme"),
        ):
            value = optional_string(section, key)
            if value:
                command.extend([flag, value])
    command.append("--dry-run")
    run_command(command)


def run_app_service(section: dict[str, Any]) -> None:
    source_dir = require_string(section, "source_dir", section_name="app_service")
    include_files = require_string_list(section, "include_files", section_name="app_service")
    ensure_file(source_dir, label="app_service.source_dir")
    for include_file in include_files:
        ensure_file(include_file, label="app_service.include_file")
    command = [
        "bash",
        "scripts/deploy_app_service_zip.sh",
        "--source-dir",
        source_dir,
    ]
    for include_file in include_files:
        command.extend(["--include-file", include_file])
    for key, flag in (
        ("zip_path", "--zip"),
        ("staging_dir", "--staging-dir"),
        ("resource_group", "--resource-group"),
        ("app_name", "--app-name"),
        ("hostname", "--hostname"),
    ):
        value = optional_string(section, key)
        if value:
            command.extend([flag, value])
    command.append("--no-deploy")
    run_command(command)


def run_remote_smoke(section: dict[str, Any]) -> None:
    command = ["bash", "scripts/smoke_remote.sh"]
    app_url = optional_string(section, "app_url")
    api_url = optional_string(section, "api_url")
    if app_url:
        command.extend(["--app-url", app_url])
    if api_url:
        command.extend(["--api-url", api_url])
    if optional_bool(section, "strict"):
        command.append("--strict")
    run_command(command)


def run_from_config(payload: dict[str, Any]) -> None:
    section_handlers: list[tuple[str, Any]] = [
        ("terraform_backend", run_terraform_backend),
        ("container_image", run_container_image),
        ("aks_workload", run_aks_workload),
        ("apim", run_apim),
        ("app_service", run_app_service),
        ("remote_smoke", run_remote_smoke),
    ]
    for section_name, handler in section_handlers:
        if section_name not in payload:
            continue
        print(f"Running {section_name}...")
        handler(require_object(payload, section_name))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a repo-local delivery baseline smoke config.")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        type=Path,
        help="JSON config to execute (defaults to .agent-core/delivery-baseline-smoke.json).",
    )
    args = parser.parse_args(argv)
    payload = read_json(args.config.resolve())
    run_from_config(payload)
    print("OK delivery baseline smoke completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
