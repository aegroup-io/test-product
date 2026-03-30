#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "advisory-code-review"
SCHEMA_PATH = REPO_ROOT / "scripts" / "schemas" / "advisory_code_review.schema.json"
RUBRIC_PATH = REPO_ROOT / "docs" / "harness" / "advisory-code-review.md"
COMMENT_MARKER = "<!-- codex-advisory-review-v1 -->"
ISSUE_LINK_RE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b")
SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
RESULT_FINDINGS = "findings"
RESULT_NO_FINDINGS = "no-findings"
RESULT_UNAVAILABLE = "review-unavailable"


def run_command(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )


def parse_linked_issue_numbers(pr_body: str) -> list[int]:
    return [int(match.group(1)) for match in ISSUE_LINK_RE.finditer(pr_body or "")]


def fetch_pr_context(pr_number: int) -> dict[str, Any]:
    completed = run_command(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,body,isDraft,baseRefName,headRefName,headRefOid,url,files",
        ]
    )
    return json.loads(completed.stdout)


def fetch_issue_context(issue_number: int) -> dict[str, Any]:
    completed = run_command(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "number,title,body,url,labels",
        ]
    )
    return json.loads(completed.stdout)


def maybe_fetch_issue_context(issue_number: int) -> dict[str, Any] | None:
    try:
        return fetch_issue_context(issue_number)
    except subprocess.CalledProcessError:
        return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def git_rev_parse(ref: str) -> str:
    completed = run_command(["git", "rev-parse", ref])
    return completed.stdout.strip()


def ensure_checkout_matches_pr_head(pr_context: dict[str, Any], *, workspace_head_sha: str) -> None:
    expected_head_sha = str(pr_context.get("headRefOid", "")).strip()
    if not expected_head_sha or workspace_head_sha == expected_head_sha:
        return
    raise SystemExit(
        "Current checkout "
        f"{workspace_head_sha[:12]} does not match pull request #{pr_context['number']} head "
        f"{expected_head_sha[:12]} ({pr_context['headRefName']}). "
        f"Check out the pull request head first, for example: gh pr checkout {pr_context['number']}"
    )


def build_prompt(
    *,
    base_ref: str,
    pr_context: dict[str, Any],
    pr_context_path: Path,
    issue_context_path: Path | None,
    workspace_head_sha: str,
    checkout_verified: bool,
    rubric_text: str,
) -> str:
    issue_context_note = (
        f"- Linked issue context is available at `{display_path(issue_context_path)}`.\n"
        if issue_context_path
        else "- No linked issue context file was generated from the pull request body.\n"
    )
    checkout_note = (
        "- The runner verified that the current workspace HEAD matches the requested pull-request head before invoking Codex.\n"
        if checkout_verified
        else "- Dry-run mode did not verify that the current workspace HEAD matches the requested pull-request head.\n"
    )
    return f"""You are running the repo-level advisory code review flow.

Review pull request #{pr_context['number']} against the git base ref `{base_ref}`.

Use the repo-local review rubric below as the canonical standard. Also read the referenced repo files from the rubric when needed.

{rubric_text}

Runtime review context:
- Pull-request metadata is available at `{display_path(pr_context_path)}`.
- Requested pull-request head ref is `{pr_context['headRefName']}` at `{pr_context['headRefOid']}`.
- Current workspace HEAD is `{workspace_head_sha}`.
{issue_context_note}- Repository root is `{REPO_ROOT}`.
{checkout_note}

Execution requirements:
- Inspect the diff against `{base_ref}` plus enough nearby code to understand the behavior change.
- Focus on correctness, regressions, missing tests, risky behavior, and evidence gaps.
- Ignore style-only nits.
- Findings must be severity-ordered: high, then medium, then low.
- If there are no concrete findings, return `result = "no-findings"` with an empty findings list and an explicit summary saying no findings were found.

Return JSON that matches the provided schema exactly.
"""


def sort_findings(review_payload: dict[str, Any]) -> dict[str, Any]:
    findings = list(review_payload.get("findings", []))
    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity", "")).lower(), 99),
            str(item.get("file", "")),
            int(item.get("line") or 0),
            str(item.get("title", "")),
        )
    )
    review_payload["findings"] = findings
    return review_payload


def render_review_markdown(
    review_payload: dict[str, Any],
    *,
    pr_context: dict[str, Any],
    issue_context: dict[str, Any] | None,
    unavailable_reason: str | None = None,
) -> str:
    lines = [COMMENT_MARKER, "## Codex Advisory Review", ""]
    lines.append(f"- Pull request: #{pr_context['number']} `{pr_context['title']}`")
    lines.append(f"- Base branch: `{pr_context['baseRefName']}`")
    lines.append(f"- Head branch: `{pr_context['headRefName']}`")
    lines.append("- Advisory only: human review and merge remain required")
    if issue_context:
        lines.append(f"- Linked issue: #{issue_context['number']} `{issue_context['title']}`")
    lines.append("- Rubric: `docs/harness/advisory-code-review.md`")
    lines.append("")

    if unavailable_reason:
        lines.append("### Status")
        lines.append("")
        lines.append(f"Review unavailable: {unavailable_reason}")
        return "\n".join(lines) + "\n"

    result = review_payload["result"]
    summary = review_payload["summary"].strip()
    validation = review_payload["validation_assessment"].strip()
    residual_risks = [risk.strip() for risk in review_payload.get("residual_risks", []) if risk.strip()]

    if result == RESULT_UNAVAILABLE:
        lines.append("### Status")
        lines.append("")
        lines.append(f"Review unavailable: {summary}")
        lines.append("")
        lines.append("### Validation Assessment")
        lines.append("")
        lines.append(validation)
        lines.append("")
        lines.append("### Residual Risks")
        lines.append("")
        if residual_risks:
            for risk in residual_risks:
                lines.append(f"- {risk}")
        else:
            lines.append("- None noted.")
        return "\n".join(lines) + "\n"

    lines.append("### Result")
    lines.append("")
    if result == RESULT_NO_FINDINGS:
        lines.append(f"No findings. {summary}")
    else:
        lines.append(f"Findings present. {summary}")
    lines.append("")

    lines.append("### Validation Assessment")
    lines.append("")
    lines.append(validation)
    lines.append("")

    findings = review_payload.get("findings", [])
    lines.append("### Findings")
    lines.append("")
    if not findings:
        lines.append("- No concrete findings.")
    else:
        for idx, finding in enumerate(findings, start=1):
            location = finding["file"]
            if finding.get("line"):
                location = f"{location}:{finding['line']}"
            lines.append(f"{idx}. [{finding['severity'].upper()}] {finding['title']}")
            lines.append(f"   Location: `{location}`")
            lines.append(f"   Risk: {finding['risk']}")
            lines.append(f"   Recommendation: {finding['recommendation']}")
            lines.append(f"   Evidence: {finding['evidence']}")
    lines.append("")

    lines.append("### Residual Risks")
    lines.append("")
    if residual_risks:
        for risk in residual_risks:
            lines.append(f"- {risk}")
    else:
        lines.append("- None noted.")

    return "\n".join(lines) + "\n"


def default_codex_sandbox_mode() -> str:
    configured = os.getenv("CODEX_SANDBOX_MODE", "").strip()
    return configured or "workspace-write"


def normalize_sandbox_mode(value: str, *, parser: argparse.ArgumentParser) -> str:
    normalized = value.strip()
    if normalized not in SANDBOX_MODES:
        parser.error(
            f"--sandbox must be one of {', '.join(SANDBOX_MODES)}; "
            f"got {value!r} from arguments or CODEX_SANDBOX_MODE."
        )
    return normalized


def build_codex_command(*, model: str | None, output_json_path: Path, sandbox: str) -> list[str]:
    command = ["codex"]
    if sandbox == "danger-full-access":
        command.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        command.extend(
            [
                "-s",
                sandbox,
                "-a",
                "never",
            ]
        )
    command.append("exec")
    if model:
        command.extend(["-m", model])
    command.extend(
        [
            "--color",
            "never",
            "--output-schema",
            str(SCHEMA_PATH),
            "-o",
            str(output_json_path),
            "-",
        ]
    )
    return command


def run_codex_review(prompt_text: str, *, model: str | None, output_json_path: Path, sandbox: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as prompt_file:
        prompt_file.write(prompt_text)
        prompt_path = Path(prompt_file.name)
    try:
        command = build_codex_command(
            model=model,
            output_json_path=output_json_path,
            sandbox=sandbox,
        )
        run_command(command, input_text=prompt_path.read_text(encoding="utf-8"))
    finally:
        prompt_path.unlink(missing_ok=True)


def write_unavailable_report(
    *,
    output_dir: Path,
    pr_context: dict[str, Any],
    issue_context: dict[str, Any] | None,
    reason: str,
) -> None:
    review_payload = {
        "result": RESULT_UNAVAILABLE,
        "summary": reason,
        "validation_assessment": "Advisory review did not run.",
        "residual_risks": [],
        "findings": [],
    }
    write_json(output_dir / "review.json", review_payload)
    markdown = render_review_markdown(
        review_payload,
        pr_context=pr_context,
        issue_context=issue_context,
        unavailable_reason=reason,
    )
    (output_dir / "review.md").write_text(markdown, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or render the advisory Codex code review flow.")
    parser.add_argument("--base-ref", default="origin/dev", help="Git base ref to review against.")
    parser.add_argument("--pr-number", type=int, required=True, help="GitHub pull-request number.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated review artifacts.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("CODEX_REVIEW_MODEL", "").strip() or None,
        help="Optional Codex model override.",
    )
    parser.add_argument(
        "--sandbox",
        default=default_codex_sandbox_mode(),
        help=(
            "Codex sandbox mode. Defaults to CODEX_SANDBOX_MODE when set, "
            "otherwise workspace-write."
        ),
    )
    parser.add_argument(
        "--write-unavailable",
        help="Write an unavailable review artifact instead of invoking Codex.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render prompt and context artifacts without invoking Codex.",
    )
    args = parser.parse_args(argv)
    args.sandbox = normalize_sandbox_mode(args.sandbox, parser=parser)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    pr_context = fetch_pr_context(args.pr_number)
    write_json(output_dir / "pr-context.json", pr_context)

    issue_numbers = parse_linked_issue_numbers(pr_context.get("body", ""))
    issue_context = maybe_fetch_issue_context(issue_numbers[0]) if issue_numbers else None
    if issue_context:
        write_json(output_dir / "issue-context.json", issue_context)

    if args.write_unavailable:
        write_unavailable_report(
            output_dir=output_dir,
            pr_context=pr_context,
            issue_context=issue_context,
            reason=args.write_unavailable,
        )
        return 0

    workspace_head_sha = git_rev_parse("HEAD")
    checkout_verified = False
    if not args.dry_run:
        ensure_checkout_matches_pr_head(pr_context, workspace_head_sha=workspace_head_sha)
        checkout_verified = True

    rubric_text = RUBRIC_PATH.read_text(encoding="utf-8")
    prompt_text = build_prompt(
        base_ref=args.base_ref,
        pr_context=pr_context,
        pr_context_path=output_dir / "pr-context.json",
        issue_context_path=(output_dir / "issue-context.json") if issue_context else None,
        workspace_head_sha=workspace_head_sha,
        checkout_verified=checkout_verified,
        rubric_text=rubric_text,
    )
    (output_dir / "review-prompt.md").write_text(prompt_text, encoding="utf-8")

    if args.dry_run:
        return 0

    run_codex_review(
        prompt_text,
        model=args.model,
        output_json_path=output_dir / "review.json",
        sandbox=args.sandbox,
    )

    review_payload = json.loads((output_dir / "review.json").read_text(encoding="utf-8"))
    review_payload = sort_findings(review_payload)
    write_json(output_dir / "review.json", review_payload)

    markdown = render_review_markdown(
        review_payload,
        pr_context=pr_context,
        issue_context=issue_context,
    )
    (output_dir / "review.md").write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
