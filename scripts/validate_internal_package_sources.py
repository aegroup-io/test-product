#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_API_SRC = REPO_ROOT / "packages" / "platform-api" / "src"
sys.path.insert(0, str(PLATFORM_API_SRC))

try:
    from agent_core_platform_api.internal_package_sources import public_package_source_diagnostics  # noqa: E402
except ModuleNotFoundError:
    PUBLIC_NPM_HOSTS = {"registry.npmjs.org"}
    PUBLIC_PYPI_HOSTS = {"pypi.org", "pypi.python.org", "files.pythonhosted.org"}
    SKIPPED_DIR_NAMES = {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".yarn",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
    MANAGED_TEMPLATE_PATHS = (
        ".orcha/package-registry/npmrc.template",
        ".orcha/package-registry/pip.conf.template",
        ".orcha/package-registry/uv.toml.template",
        ".orcha/package-registry/package-registry.env.example",
    )
    MANAGED_PACKAGE_REGISTRY_PATHS = (
        *MANAGED_TEMPLATE_PATHS,
        "scripts/validate_internal_package_sources.py",
        "scripts/smoke_internal_package_registry.sh",
    )

    _URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
    _EXTRA_INDEX_RE = re.compile(
        r"(?i)(?:^|\s|=)(?:--extra-index-url|extra-index-url|PIP_EXTRA_INDEX_URL|UV_EXTRA_INDEX_URL)\b"
    )
    _NPM_REGISTRY_RE = re.compile(r"(?im)^\s*(?:@[^:\s]+:\s*)?registry\s*=\s*(?P<value>\S+)\s*$")
    _PYTHON_INDEX_RE = re.compile(r"(?im)^\s*(?:index-url|index_url)\s*=\s*(?P<value>\S+)\s*$")

    @dataclass(frozen=True)
    class PackageSourceDiagnostic:
        code: str
        severity: str
        message: str
        path: str
        line: int | None = None
        source_kind: str = "config"

    def normalize_repo_relative_path(path: str | Path) -> str:
        value = str(path).strip().replace("\\", "/")
        if not value:
            return ""
        while value.startswith("./"):
            value = value[2:]
        return str(PurePosixPath(value))

    def public_package_source_diagnostics(
        repo_root: Path,
        *,
        expected_npm_registry_url: str | None = None,
        expected_pypi_simple_index_url: str | None = None,
        include_lockfiles: bool = False,
        require_managed_templates: bool = False,
    ) -> list[PackageSourceDiagnostic]:
        root = repo_root.resolve()
        diagnostics: list[PackageSourceDiagnostic] = []
        if require_managed_templates:
            diagnostics.extend(_validate_managed_templates(root))

        for path in _iter_scanned_files(root, include_lockfiles=include_lockfiles):
            rel_path = normalize_repo_relative_path(path.relative_to(root))
            source_kind = _source_kind(rel_path)
            text = _read_text(path)
            if text is None:
                continue
            diagnostics.extend(_scan_text(rel_path, text, source_kind=source_kind))
            diagnostics.extend(
                _validate_expected_registry_lines(
                    rel_path,
                    text,
                    expected_npm_registry_url=expected_npm_registry_url,
                    expected_pypi_simple_index_url=expected_pypi_simple_index_url,
                )
            )

        return sorted(
            diagnostics,
            key=lambda item: (item.severity != "error", item.path, item.line or 0, item.code),
        )

    def _validate_managed_templates(root: Path) -> list[PackageSourceDiagnostic]:
        diagnostics: list[PackageSourceDiagnostic] = []
        required_placeholders = {
            ".orcha/package-registry/npmrc.template": ("__ORCHA_NPM_REGISTRY_URL__",),
            ".orcha/package-registry/pip.conf.template": ("__ORCHA_PYPI_SIMPLE_INDEX_URL__",),
            ".orcha/package-registry/uv.toml.template": ("__ORCHA_PYPI_SIMPLE_INDEX_URL__",),
            ".orcha/package-registry/package-registry.env.example": (
                "ORCHA_NPM_REGISTRY_URL",
                "ORCHA_PYPI_SIMPLE_INDEX_URL",
            ),
        }
        for rel_path in MANAGED_PACKAGE_REGISTRY_PATHS:
            path = root / rel_path
            if not path.exists():
                diagnostics.append(
                    PackageSourceDiagnostic(
                        code="package_registry.managed_asset_missing",
                        severity="error",
                        message=f"Managed internal package-registry asset is missing: {rel_path}",
                        path=rel_path,
                        source_kind="template",
                    )
                )
                continue
            text = _read_text(path) or ""
            for placeholder in required_placeholders.get(rel_path, ()):
                if placeholder not in text:
                    diagnostics.append(
                        PackageSourceDiagnostic(
                            code="package_registry.managed_template_placeholder_missing",
                            severity="error",
                            message=f"Managed package-registry template is missing placeholder `{placeholder}`.",
                            path=rel_path,
                            source_kind="template",
                        )
                    )
        return diagnostics

    def _iter_scanned_files(root: Path, *, include_lockfiles: bool) -> Iterable[Path]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if any(part in SKIPPED_DIR_NAMES for part in relative.parts):
                continue
            rel_path = normalize_repo_relative_path(relative)
            if _is_package_config_path(rel_path) or _is_install_surface_path(rel_path):
                yield path
                continue
            if include_lockfiles and _is_lockfile_path(rel_path):
                yield path

    def _is_package_config_path(rel_path: str) -> bool:
        name = Path(rel_path).name
        if rel_path in MANAGED_TEMPLATE_PATHS:
            return True
        if name in {".npmrc", "npmrc", "pip.conf", "pip.ini", "uv.toml", "pyproject.toml"}:
            return True
        return name.startswith("requirements") and name.endswith(".txt")

    def _is_install_surface_path(rel_path: str) -> bool:
        name = Path(rel_path).name
        if rel_path.startswith(".github/workflows/") and name.endswith((".yml", ".yaml")):
            return True
        if rel_path.startswith("scripts/") and name.endswith((".sh", ".bash")):
            return True
        if name in {"Dockerfile", "Makefile"}:
            return True
        return name.endswith(".Dockerfile")

    def _is_lockfile_path(rel_path: str) -> bool:
        name = Path(rel_path).name
        return name in {"package-lock.json", "npm-shrinkwrap.json", "uv.lock", "poetry.lock", "Pipfile.lock"}

    def _source_kind(rel_path: str) -> str:
        if rel_path in MANAGED_TEMPLATE_PATHS:
            return "template"
        if _is_lockfile_path(rel_path):
            return "lockfile"
        if _is_install_surface_path(rel_path):
            return "install-script"
        return "config"

    def _read_text(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    def _scan_text(rel_path: str, text: str, *, source_kind: str) -> list[PackageSourceDiagnostic]:
        diagnostics: list[PackageSourceDiagnostic] = []
        line_starts = _line_starts(text)
        lockfile = source_kind == "lockfile"

        for match in _URL_RE.finditer(text):
            url = match.group(0).rstrip(".,;)]}'\"")
            host = urlsplit(url).netloc.lower()
            line = _line_for_offset(line_starts, match.start())
            if host in PUBLIC_NPM_HOSTS:
                diagnostics.append(
                    PackageSourceDiagnostic(
                        code="package_registry.public_npm_source",
                        severity="warning" if lockfile else "error",
                        message=f"Public npm registry URL is not allowed for internal-only package installs: {url}",
                        path=rel_path,
                        line=line,
                        source_kind=source_kind,
                    )
                )
            elif host in PUBLIC_PYPI_HOSTS:
                diagnostics.append(
                    PackageSourceDiagnostic(
                        code="package_registry.public_pypi_source",
                        severity="warning" if lockfile else "error",
                        message=f"Public PyPI package source URL is not allowed for internal-only package installs: {url}",
                        path=rel_path,
                        line=line,
                        source_kind=source_kind,
                    )
                )

        for index, line_text in enumerate(text.splitlines(), start=1):
            stripped = line_text.strip()
            if stripped.startswith("#") or stripped.startswith("unset PIP_EXTRA_INDEX_URL"):
                continue
            if _EXTRA_INDEX_RE.search(line_text):
                diagnostics.append(
                    PackageSourceDiagnostic(
                        code="package_registry.python_extra_index",
                        severity="error",
                        message="Python package installs must not use extra-index-url fallback sources.",
                        path=rel_path,
                        line=index,
                        source_kind=source_kind,
                    )
                )
        return diagnostics

    def _validate_expected_registry_lines(
        rel_path: str,
        text: str,
        *,
        expected_npm_registry_url: str | None,
        expected_pypi_simple_index_url: str | None,
    ) -> list[PackageSourceDiagnostic]:
        diagnostics: list[PackageSourceDiagnostic] = []
        expected_npm = _normalize_url(expected_npm_registry_url)
        expected_pypi = _normalize_url(expected_pypi_simple_index_url)
        if expected_npm and Path(rel_path).name in {".npmrc", "npmrc"}:
            for match in _NPM_REGISTRY_RE.finditer(text):
                actual = match.group("value")
                if actual.startswith("${") or actual.startswith("__"):
                    continue
                if _normalize_url(actual) != expected_npm:
                    diagnostics.append(
                        PackageSourceDiagnostic(
                            code="package_registry.npm_registry_mismatch",
                            severity="error",
                            message=f"npm registry `{actual}` does not match the configured internal Pulp registry.",
                            path=rel_path,
                            line=text[: match.start()].count("\n") + 1,
                            source_kind="config",
                        )
                    )
        if expected_pypi and Path(rel_path).name in {"pip.conf", "pip.ini", "uv.toml"}:
            for match in _PYTHON_INDEX_RE.finditer(text):
                actual = match.group("value").strip("\"'")
                if actual.startswith("${") or actual.startswith("__"):
                    continue
                if _normalize_url(actual) != expected_pypi:
                    diagnostics.append(
                        PackageSourceDiagnostic(
                            code="package_registry.pypi_index_mismatch",
                            severity="error",
                            message=f"Python index URL `{actual}` does not match the configured internal Pulp simple index.",
                            path=rel_path,
                            line=text[: match.start()].count("\n") + 1,
                            source_kind="config",
                        )
                    )
        return diagnostics

    def _normalize_url(value: str | None) -> str:
        if not value:
            return ""
        return str(value).strip().rstrip("/") + "/"

    def _line_starts(text: str) -> list[int]:
        starts = [0]
        for match in re.finditer(r"\n", text):
            starts.append(match.end())
        return starts

    def _line_for_offset(starts: list[int], offset: int) -> int:
        line = 1
        for index, start in enumerate(starts, start=1):
            if start > offset:
                break
            line = index
        return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate internal-only npm and PyPI package sources.")
    parser.add_argument(
        "--repo-root",
        default=REPO_ROOT,
        type=Path,
        help="Repository root to validate.",
    )
    parser.add_argument(
        "--expected-npm-registry",
        default=None,
        help="Expected internal npm registry URL. Literal .npmrc registry lines must match when provided.",
    )
    parser.add_argument(
        "--expected-pypi-index",
        default=None,
        help="Expected internal PyPI simple index URL. Literal pip/uv index lines must match when provided.",
    )
    parser.add_argument(
        "--include-lockfiles",
        action="store_true",
        help="Also scan lockfiles for public package artifact URLs.",
    )
    parser.add_argument(
        "--skip-template-check",
        action="store_true",
        help="Do not require the managed internal package registry templates to be present.",
    )
    args = parser.parse_args(argv)

    diagnostics = public_package_source_diagnostics(
        args.repo_root.resolve(),
        expected_npm_registry_url=args.expected_npm_registry,
        expected_pypi_simple_index_url=args.expected_pypi_index,
        include_lockfiles=args.include_lockfiles,
        require_managed_templates=not args.skip_template_check,
    )
    for item in diagnostics:
        location = f"{item.path}:{item.line}" if item.line is not None else item.path
        print(f"{item.severity.upper()} {location} {item.code}: {item.message}")

    errors = [item for item in diagnostics if item.severity == "error"]
    if errors:
        print(f"FAILED internal package source validation with {len(errors)} error(s).")
        return 1
    print(
        "OK internal package source validation passed "
        f"({len(diagnostics)} advisory package-source diagnostic(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
