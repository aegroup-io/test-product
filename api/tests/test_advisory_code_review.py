from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_review_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "run_advisory_code_review.py"
    spec = importlib.util.spec_from_file_location("run_advisory_code_review", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_args_defaults_to_workspace_write_without_override(monkeypatch) -> None:
    review_module = _load_review_module()
    monkeypatch.delenv("CODEX_SANDBOX_MODE", raising=False)

    args = review_module.parse_args(["--pr-number", "57"])

    assert args.sandbox == "workspace-write"


def test_parse_args_honors_sandbox_override(monkeypatch) -> None:
    review_module = _load_review_module()
    monkeypatch.setenv("CODEX_SANDBOX_MODE", "danger-full-access")

    args = review_module.parse_args(["--pr-number", "57"])

    assert args.sandbox == "danger-full-access"


def test_build_codex_command_uses_requested_sandbox(tmp_path: Path) -> None:
    review_module = _load_review_module()

    command = review_module.build_codex_command(
        model="gpt-5",
        output_json_path=tmp_path / "review.json",
        sandbox="danger-full-access",
    )

    assert command[:3] == ["codex", "--dangerously-bypass-approvals-and-sandbox", "exec"]
    assert "-m" in command
    assert "--output-schema" in command


def test_build_codex_command_keeps_explicit_sandbox_for_non_bypass_modes(tmp_path: Path) -> None:
    review_module = _load_review_module()

    command = review_module.build_codex_command(
        model=None,
        output_json_path=tmp_path / "review.json",
        sandbox="workspace-write",
    )

    assert command[:6] == ["codex", "-s", "workspace-write", "-a", "never", "exec"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in command


def test_parse_args_rejects_invalid_sandbox_override(monkeypatch) -> None:
    review_module = _load_review_module()
    monkeypatch.setenv("CODEX_SANDBOX_MODE", "invalid-mode")

    with pytest.raises(SystemExit):
        review_module.parse_args(["--pr-number", "57"])
