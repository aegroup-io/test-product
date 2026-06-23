#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


SLOT_MODULUS = 1000
WORKTREE_HASH_LENGTH = 6
MAX_NAMESPACE_LABEL_LENGTH = 32
MAX_POSTGRES_IDENTIFIER_LENGTH = 63
ISSUE_PATTERN = re.compile(r"(?:^|[/_-])issue-(\d+)(?:$|[/_-])", re.IGNORECASE)
PORT_BASES = {
    "AGENT_CORE_LOCAL_WEB_PORT": 5100,
    "AGENT_CORE_LOCAL_DATABASE_PORT": 6100,
    "AGENT_CORE_LOCAL_API_PORT": 7100,
    "AGENT_CORE_LOCAL_MCP_PORT": 8100,
    "AGENT_CORE_DOCS_PORT": 9100,
}
OUTPUT_ORDER = [
    "AGENT_CORE_WORKTREE_PATH",
    "AGENT_CORE_WORKTREE_BRANCH",
    "AGENT_CORE_WORKTREE_ISSUE_NUMBER",
    "AGENT_CORE_WORKTREE_SOURCE",
    "AGENT_CORE_WORKTREE_LABEL",
    "AGENT_CORE_WORKTREE_HASH",
    "AGENT_CORE_WORKTREE_SLOT",
    "AGENT_CORE_WORKTREE_NAMESPACE",
    "AGENT_CORE_PRODUCT_KEY",
    "AGENT_CORE_LOCAL_DEV_ROOT",
    "AGENT_CORE_LOCAL_ARTIFACT_ROOT",
    "AGENT_CORE_LOCAL_PID_ROOT",
    "AGENT_CORE_LOCAL_JOB_ROOT",
    "AGENT_CORE_LOCAL_DATABASE_HOST",
    "AGENT_CORE_LOCAL_DATABASE_PORT",
    "AGENT_CORE_LOCAL_DATABASE_NAME",
    "AGENT_CORE_LOCAL_DATABASE_URL",
    "AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME",
    "AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME",
    "AGENT_CORE_LOCAL_API_HOST",
    "AGENT_CORE_LOCAL_API_PORT",
    "AGENT_CORE_LOCAL_API_URL",
    "AGENT_CORE_API_BASE_URL",
    "VITE_API_BASE_URL",
    "AGENT_CORE_LOCAL_WEB_HOST",
    "AGENT_CORE_LOCAL_WEB_PORT",
    "AGENT_CORE_LOCAL_WEB_URL",
    "VITE_ENTRA_REDIRECT_URI",
    "AGENT_CORE_LOCAL_MCP_HOST",
    "AGENT_CORE_LOCAL_MCP_PORT",
    "AGENT_CORE_LOCAL_MCP_URL",
    "AGENT_CORE_DOCS_HOST",
    "AGENT_CORE_DOCS_PORT",
    "AGENT_CORE_LOCAL_DOCS_URL",
]


@dataclass(frozen=True)
class NamespaceContract:
    values: dict[str, str]


def slugify(value: str, *, fallback: str = "worktree") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or fallback


def compact_label(value: str) -> str:
    slug = slugify(value)
    if len(slug) <= MAX_NAMESPACE_LABEL_LENGTH:
        return slug
    return slug[:MAX_NAMESPACE_LABEL_LENGTH].rstrip("-")


def postgres_identifier(value: str, *, fallback: str = "agent_core") -> str:
    identifier = slugify(value, fallback=fallback).replace("-", "_")
    identifier = re.sub(r"[^a-z0-9_]+", "_", identifier)
    identifier = re.sub(r"_+", "_", identifier).strip("_")
    if len(identifier) > MAX_POSTGRES_IDENTIFIER_LENGTH:
        identifier = identifier[:MAX_POSTGRES_IDENTIFIER_LENGTH].rstrip("_")
    return identifier or fallback


def detect_branch(worktree_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree_path), "branch", "--show-current"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def parse_issue_number(value: str) -> str:
    match = ISSUE_PATTERN.search(value)
    return match.group(1) if match else ""


def choose_label(
    *,
    namespace_override: str,
    issue_number: str,
    branch_name: str,
    worktree_path: Path,
) -> tuple[str, str]:
    if namespace_override:
        return compact_label(namespace_override), "override"
    if issue_number:
        return f"issue-{issue_number}", "issue"
    if branch_name:
        return compact_label(branch_name.split("/")[-1]), "branch"
    return compact_label(worktree_path.name), "path"


def path_hash(worktree_path: Path) -> tuple[str, int]:
    digest = hashlib.sha256(str(worktree_path).encode("utf-8")).hexdigest()
    slot = int(digest[:8], 16) % SLOT_MODULUS
    return digest, slot


def detect_product_key(worktree_path: Path, env: Mapping[str, str]) -> str:
    override = env.get("AGENT_CORE_PRODUCT_KEY", "").strip()
    if override:
        return slugify(override, fallback="agent-core")

    factory_path = worktree_path / ".agent-core" / "product-factory.json"
    if not factory_path.exists():
        return slugify(worktree_path.name, fallback="agent-core")

    try:
        payload = json.loads(factory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return slugify(worktree_path.name, fallback="agent-core")

    product = payload.get("product")
    if not isinstance(product, dict):
        return slugify(worktree_path.name, fallback="agent-core")

    raw_key = str(product.get("key") or "").strip()
    if not raw_key:
        return slugify(worktree_path.name, fallback="agent-core")
    return slugify(raw_key, fallback="agent-core")


def override_or(default: str, env: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return default


def resolve_port(default: int, env: Mapping[str, str], *keys: str) -> str:
    raw = override_or(str(default), env, *keys)
    try:
        value = int(raw)
    except ValueError as exc:
        joined = ", ".join(keys)
        raise ValueError(f"Invalid port override for {joined}: {raw}") from exc
    if value <= 0 or value > 65535:
        joined = ", ".join(keys)
        raise ValueError(f"Port override out of range for {joined}: {value}")
    return str(value)


def build_contract(
    *,
    worktree_path: str | Path | None = None,
    branch_name: str | None = None,
    issue_number: str | int | None = None,
    namespace_override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> NamespaceContract:
    env_map = env or os.environ
    resolved_worktree = Path(
        worktree_path
        or env_map.get("AGENT_CORE_WORKTREE_PATH")
        or os.getcwd()
    ).expanduser().resolve()

    branch = (
        branch_name
        or env_map.get("AGENT_CORE_WORKTREE_BRANCH")
        or detect_branch(resolved_worktree)
    ).strip()
    issue = (
        str(issue_number).strip()
        if issue_number is not None
        else env_map.get("AGENT_CORE_WORKTREE_ISSUE_NUMBER", "").strip()
    )
    if not issue:
        issue = parse_issue_number(branch) or parse_issue_number(resolved_worktree.name)

    namespace_seed = (
        namespace_override
        or env_map.get("AGENT_CORE_WORKTREE_NAMESPACE", "")
    ).strip()
    digest, slot = path_hash(resolved_worktree)
    label, source = choose_label(
        namespace_override=namespace_seed,
        issue_number=issue,
        branch_name=branch,
        worktree_path=resolved_worktree,
    )
    namespace = namespace_seed and compact_label(namespace_seed)
    if not namespace:
        namespace = f"{label}-{digest[:WORKTREE_HASH_LENGTH]}"
    product_key = detect_product_key(resolved_worktree, env_map)

    temp_root = Path(
        override_or(str(Path("/tmp") / "agent_core"), env_map, "AGENT_CORE_LOCAL_TEMP_ROOT")
    ).expanduser().resolve()
    dev_root = (temp_root / "worktrees" / namespace).resolve()
    artifact_root = (dev_root / "artifacts").resolve()
    pid_root = (dev_root / "pids").resolve()
    job_root = (dev_root / "worker-jobs").resolve()

    database_host = override_or("127.0.0.1", env_map, "AGENT_CORE_LOCAL_DATABASE_HOST")
    database_port = resolve_port(
        PORT_BASES["AGENT_CORE_LOCAL_DATABASE_PORT"] + slot,
        env_map,
        "AGENT_CORE_LOCAL_DATABASE_PORT",
    )
    database_name = postgres_identifier(
        override_or(product_key, env_map, "AGENT_CORE_LOCAL_DATABASE_NAME"),
        fallback="agent_core",
    )
    database_user = override_or("postgres", env_map, "AGENT_CORE_LOCAL_DATABASE_USER")
    database_password = override_or("postgres", env_map, "AGENT_CORE_LOCAL_DATABASE_PASSWORD")
    api_host = override_or("127.0.0.1", env_map, "AGENT_CORE_LOCAL_API_HOST")
    web_host = override_or("127.0.0.1", env_map, "AGENT_CORE_LOCAL_WEB_HOST")
    mcp_host = override_or("127.0.0.1", env_map, "AGENT_CORE_LOCAL_MCP_HOST")
    docs_host = override_or("127.0.0.1", env_map, "AGENT_CORE_DOCS_HOST")

    web_port = resolve_port(PORT_BASES["AGENT_CORE_LOCAL_WEB_PORT"] + slot, env_map, "AGENT_CORE_LOCAL_WEB_PORT")
    api_port = resolve_port(PORT_BASES["AGENT_CORE_LOCAL_API_PORT"] + slot, env_map, "AGENT_CORE_LOCAL_API_PORT")
    mcp_port = resolve_port(PORT_BASES["AGENT_CORE_LOCAL_MCP_PORT"] + slot, env_map, "AGENT_CORE_LOCAL_MCP_PORT")
    docs_port = resolve_port(PORT_BASES["AGENT_CORE_DOCS_PORT"] + slot, env_map, "AGENT_CORE_DOCS_PORT")

    values = {
        "AGENT_CORE_WORKTREE_PATH": str(resolved_worktree),
        "AGENT_CORE_WORKTREE_BRANCH": branch,
        "AGENT_CORE_WORKTREE_ISSUE_NUMBER": issue,
        "AGENT_CORE_WORKTREE_SOURCE": source,
        "AGENT_CORE_WORKTREE_LABEL": label,
        "AGENT_CORE_WORKTREE_HASH": digest[:WORKTREE_HASH_LENGTH],
        "AGENT_CORE_WORKTREE_SLOT": str(slot),
        "AGENT_CORE_WORKTREE_NAMESPACE": namespace,
        "AGENT_CORE_PRODUCT_KEY": product_key,
        "AGENT_CORE_LOCAL_DEV_ROOT": str(dev_root),
        "AGENT_CORE_LOCAL_ARTIFACT_ROOT": str(artifact_root),
        "AGENT_CORE_LOCAL_PID_ROOT": str(pid_root),
        "AGENT_CORE_LOCAL_JOB_ROOT": str(job_root),
        "AGENT_CORE_LOCAL_DATABASE_HOST": database_host,
        "AGENT_CORE_LOCAL_DATABASE_PORT": database_port,
        "AGENT_CORE_LOCAL_DATABASE_NAME": database_name,
        "AGENT_CORE_LOCAL_DATABASE_URL": (
            f"postgresql+psycopg://{database_user}:{database_password}@"
            f"{database_host}:{database_port}/{database_name}"
        ),
        "AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME": f"agent-core-pg-{namespace}",
        "AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME": f"agent-core-pg-data-{namespace}",
        "AGENT_CORE_LOCAL_API_HOST": api_host,
        "AGENT_CORE_LOCAL_API_PORT": api_port,
        "AGENT_CORE_LOCAL_API_URL": f"http://{api_host}:{api_port}",
        "AGENT_CORE_API_BASE_URL": f"http://{api_host}:{api_port}",
        "VITE_API_BASE_URL": f"http://{api_host}:{api_port}",
        "AGENT_CORE_LOCAL_WEB_HOST": web_host,
        "AGENT_CORE_LOCAL_WEB_PORT": web_port,
        "AGENT_CORE_LOCAL_WEB_URL": f"http://{web_host}:{web_port}",
        "VITE_ENTRA_REDIRECT_URI": f"http://{web_host}:{web_port}",
        "AGENT_CORE_LOCAL_MCP_HOST": mcp_host,
        "AGENT_CORE_LOCAL_MCP_PORT": mcp_port,
        "AGENT_CORE_LOCAL_MCP_URL": f"http://{mcp_host}:{mcp_port}",
        "AGENT_CORE_DOCS_HOST": docs_host,
        "AGENT_CORE_DOCS_PORT": docs_port,
        "AGENT_CORE_LOCAL_DOCS_URL": f"http://{docs_host}:{docs_port}",
    }
    return NamespaceContract(values=values)


def format_shell(contract: NamespaceContract) -> str:
    lines = []
    for key in OUTPUT_ORDER:
        value = contract.values[key]
        lines.append(f"export {key}={shlex.quote(value)}")
    return "\n".join(lines)


def format_text(contract: NamespaceContract) -> str:
    values = contract.values
    return "\n".join(
        [
            "Local worktree namespace contract",
            f"  Worktree: {values['AGENT_CORE_WORKTREE_PATH']}",
            f"  Namespace: {values['AGENT_CORE_WORKTREE_NAMESPACE']} ({values['AGENT_CORE_WORKTREE_SOURCE']})",
            f"  Branch: {values['AGENT_CORE_WORKTREE_BRANCH'] or '<none>'}",
            f"  Issue: {values['AGENT_CORE_WORKTREE_ISSUE_NUMBER'] or '<none>'}",
            f"  Slot: {values['AGENT_CORE_WORKTREE_SLOT']}",
            (
                "  Postgres: "
                f"{values['AGENT_CORE_LOCAL_DATABASE_HOST']}:"
                f"{values['AGENT_CORE_LOCAL_DATABASE_PORT']}/"
                f"{values['AGENT_CORE_LOCAL_DATABASE_NAME']}"
            ),
            f"  API: {values['AGENT_CORE_LOCAL_API_URL']}",
            f"  Web: {values['AGENT_CORE_LOCAL_WEB_URL']}",
            f"  MCP: {values['AGENT_CORE_LOCAL_MCP_URL']}",
            f"  Docs: {values['AGENT_CORE_LOCAL_DOCS_URL']}",
            f"  Dev root: {values['AGENT_CORE_LOCAL_DEV_ROOT']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive a deterministic local-development namespace contract for the current worktree."
    )
    parser.add_argument("--worktree-path", help="Override the worktree path to derive from.")
    parser.add_argument("--branch-name", help="Override the branch name used when deriving the namespace.")
    parser.add_argument("--issue-number", help="Override the issue number used when deriving the namespace.")
    parser.add_argument("--namespace", help="Override the derived namespace label.")
    parser.add_argument(
        "--format",
        choices=("text", "shell", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    contract = build_contract(
        worktree_path=args.worktree_path,
        branch_name=args.branch_name,
        issue_number=args.issue_number,
        namespace_override=args.namespace,
    )
    if args.format == "shell":
        print(format_shell(contract))
        return 0
    if args.format == "json":
        print(json.dumps(contract.values, indent=2))
        return 0
    print(format_text(contract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
