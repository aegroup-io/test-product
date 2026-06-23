#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


REPO_TOP_LEVELS = {
    ".agent-core",
    ".github",
    "api",
    "docs",
    "infra",
    "mcp",
    "packages",
    "scripts",
    "skills",
    "web",
    "worker",
}

REQUIRED_FILES = [
    "AGENTS.md",
    ".agent-core/delivery-baseline-smoke.json",
    ".agent-core/delivery-release-verification.json",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/spike.yml",
    ".github/ISSUE_TEMPLATE/api.yml",
    ".github/workflows/advisory-code-review.yml",
    ".github/workflows/delivery-baseline-smoke.yml",
    ".github/workflows/delivery-release-verification.yml",
    ".github/workflows/merge-readiness.yml",
    ".github/workflows/remote-smoke.yml",
    ".github/workflows/repo-harness.yml",
    ".orcha/package-registry/npmrc.template",
    ".orcha/package-registry/pip.conf.template",
    ".orcha/package-registry/uv.toml.template",
    ".orcha/package-registry/package-registry.env.example",
    "docs/architecture/README.md",
    "docs/architecture/platform-stack.md",
    "docs/delivery/README.md",
    "docs/delivery/aks-workload.md",
    "docs/delivery/apim-sync.md",
    "docs/delivery/app-service-zip.md",
    "docs/delivery/container-image.md",
    "docs/delivery/delivery-baseline-smoke.md",
    "docs/delivery/delivery-release-verification.md",
    "docs/delivery/remote-smoke.md",
    "docs/delivery/terraform-backend.md",
    "docs/delivery/terraform-entrypoint-validation.md",
    "docs/harness/advisory-code-review.md",
    "docs/harness/merge-readiness.md",
    "docs/harness/README.md",
    "docs/harness/github-repo-bootstrap.md",
    "docs/harness/internal-package-registry.md",
    "docs/harness/local-development.md",
    "docs/harness/worktree-bootstrap.md",
    "docs/harness/repo-harness.md",
    "docs/ops/AGENTS.md",
    "docs/ops/PROJECT_PLANNING.md",
    "docs/planning/README.md",
    "docs/agents/security/zap-security-reviewer.md",
    "scripts/bootstrap_terraform_backend.sh",
    "scripts/bootstrap_local_namespace.py",
    "scripts/build_push_container_image.sh",
    "scripts/deploy_aks_workload.sh",
    "scripts/deploy_app_service_zip.sh",
    "scripts/load-env.sh",
    "scripts/local_namespace.sh",
    "scripts/local_postgres_runtime.sh",
    "scripts/local_python_runtime.sh",
    "scripts/sync_apim_api.sh",
    "scripts/validate_terraform_entrypoint.sh",
    "scripts/validate_internal_package_sources.py",
    "scripts/smoke_internal_package_registry.sh",
    "scripts/run_advisory_code_review.py",
    "scripts/run_delivery_baseline_smoke.py",
    "scripts/run_delivery_release_verification.py",
    "scripts/run_merge_readiness_audit.py",
    "scripts/smoke_remote.sh",
    "scripts/schemas/advisory_code_review.schema.json",
    "scripts/schemas/delivery_baseline_smoke.schema.json",
    "scripts/schemas/delivery_release_verification.schema.json",
    "scripts/smoke_local.sh",
    "scripts/start_local_api.sh",
    "scripts/start_local_postgres.sh",
    "scripts/start_local_web.sh",
    "scripts/start_local_worker.sh",
    "scripts/start_local_mcp.sh",
    "scripts/start_local_docs.sh",
    "scripts/stop_local_environment.sh",
    "scripts/validate_repo_harness_assets.py",
]

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
CODE_FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]+)?\s*$")


@dataclass
class ValidationResult:
    checked_files: int = 0
    checked_markdown_files: int = 0
    checked_refs: int = 0


def iter_non_fenced_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return lines


def is_path_reference(candidate: str) -> bool:
    cleaned = candidate.strip().rstrip(".,:;)")
    if not cleaned or "://" in cleaned or cleaned.startswith("#"):
        return False
    if cleaned.startswith("/"):
        return False
    if cleaned.startswith("artifacts/"):
        return False
    if any(marker in cleaned for marker in ("*", "<", ">", "{", "}")):
        return False
    if any(ch.isspace() for ch in cleaned):
        return False
    if cleaned.startswith(("./", "../")):
        return True
    if "/" in cleaned:
        return True
    return cleaned in {"AGENTS.md", "README.md", "SKILL.md"}


def extract_references(text: str) -> list[str]:
    refs: list[str] = []
    for line in iter_non_fenced_lines(text):
        matches = MARKDOWN_LINK_RE.findall(line)
        matches.extend(INLINE_CODE_RE.findall(line))
        for ref in matches:
            candidate = ref.strip()
            if is_path_reference(candidate):
                refs.append(candidate)
    return refs


def resolve_reference(base_file: Path, ref: str, root: Path) -> Path | None:
    candidate = ref.strip().rstrip(".,:;)")
    if not candidate:
        return None
    if candidate.startswith(("./", "../")):
        return (base_file.parent / candidate).resolve()
    first_segment = candidate.split("/", 1)[0]
    if first_segment in REPO_TOP_LEVELS or candidate in {"AGENTS.md", "README.md"}:
        return (root / candidate).resolve()
    return (base_file.parent / candidate).resolve()


def validate_required_files(root: Path, errors: list[str], stats: ValidationResult) -> None:
    for rel_path in REQUIRED_FILES:
        stats.checked_files += 1
        if not (root / rel_path).exists():
            errors.append(f"required file missing: {rel_path}")


def validate_markdown_refs(root: Path, errors: list[str], stats: ValidationResult) -> None:
    markdown_files = [
        root / "AGENTS.md",
        root / "docs/architecture/README.md",
        root / "docs/architecture/platform-stack.md",
        root / "docs/delivery/README.md",
        root / "docs/delivery/aks-workload.md",
        root / "docs/delivery/apim-sync.md",
        root / "docs/delivery/app-service-zip.md",
        root / "docs/delivery/container-image.md",
        root / "docs/delivery/delivery-baseline-smoke.md",
        root / "docs/delivery/delivery-release-verification.md",
        root / "docs/delivery/remote-smoke.md",
        root / "docs/delivery/terraform-backend.md",
        root / "docs/delivery/terraform-entrypoint-validation.md",
        root / "docs/harness/advisory-code-review.md",
        root / "docs/harness/merge-readiness.md",
        root / "docs/harness/README.md",
        root / "docs/harness/github-repo-bootstrap.md",
        root / "docs/harness/internal-package-registry.md",
        root / "docs/harness/local-development.md",
        root / "docs/harness/worktree-bootstrap.md",
        root / "docs/harness/repo-harness.md",
        root / "docs/ops/AGENTS.md",
        root / "docs/ops/PROJECT_PLANNING.md",
        root / "docs/planning/README.md",
        root / "docs/agents/security/zap-security-reviewer.md",
        root / ".github/pull_request_template.md",
    ]
    for markdown_file in markdown_files:
        if not markdown_file.exists():
            continue
        stats.checked_markdown_files += 1
        text = markdown_file.read_text(encoding="utf-8")
        for ref in extract_references(text):
            resolved = resolve_reference(markdown_file, ref, root)
            if resolved is None:
                continue
            stats.checked_refs += 1
            if not resolved.exists():
                errors.append(
                    f"{markdown_file.relative_to(root)}: referenced path does not exist: {ref}"
                )


def run_validation(root: Path) -> tuple[list[str], ValidationResult]:
    errors: list[str] = []
    stats = ValidationResult()

    validate_required_files(root, errors, stats)
    validate_markdown_refs(root, errors, stats)

    return errors, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate adopted agent-core harness assets.")
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Repository root to validate (defaults to the current repo).",
    )
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    errors, stats = run_validation(root)
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        print(f"FAILED repo harness validation with {len(errors)} error(s).")
        return 1

    print(
        "OK repo harness validation passed "
        f"({stats.checked_files} required files, {stats.checked_markdown_files} markdown files, "
        f"{stats.checked_refs} path refs)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
