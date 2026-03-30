#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "merge-readiness"
COMMENT_MARKER = "<!-- merge-readiness-audit-v1 -->"
ADVISORY_COMMENT_MARKER = "<!-- codex-advisory-review-v1 -->"
VISUAL_COMMENT_MARKER = "<!-- visual-gate-v1 -->"
ISSUE_LINK_RE = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
NOT_APPLICABLE_RE = re.compile(r"(?i)\b(n/?a|not applicable|none required|no docs change required)\b")
OPEN_QUESTION_RE = re.compile(r"(?i)\b(todo|tbd|open question|to be decided|decide later)\b")

SECTION_SUMMARY = "Summary"
SECTION_TESTING = "Testing"
SECTION_DEMO = "Demo / Evidence"
SECTION_DOCS = "Docs"
SECTION_FOLLOWUPS = "Follow-ups / Risks"

READINESS_READY = "ready"
READINESS_READY_WITH_RISKS = "ready-with-risks"
READINESS_NOT_READY = "not-ready"

BASELINE_CHECK_NAMES = ("harness",)
VISUAL_CHECK_NAMES = {
    "gate": "visual-gate",
    "bypass": "visual-gate-bypass",
}
USER_VISIBLE_PREFIXES = (
    "app/",
    "frontend/",
    "public/",
    "ui/",
    "web/",
)
USER_VISIBLE_SUFFIXES = (
    ".css",
    ".gif",
    ".html",
    ".jpeg",
    ".jpg",
    ".jsx",
    ".png",
    ".svg",
    ".tsx",
    ".vue",
)


def run_command(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def gh_repo_args() -> list[str]:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    return ["--repo", repo] if repo else []


def github_repo_slug() -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repo:
        return repo
    completed = run_command(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    return completed.stdout.strip()


def fetch_pr_context(pr_number: int) -> dict[str, Any]:
    repo = github_repo_slug()
    completed = run_command(["gh", "api", f"repos/{repo}/pulls/{pr_number}"])
    pull_request = json.loads(completed.stdout)
    files = fetch_pr_files(pr_number)
    reviews = fetch_pr_reviews(pr_number)
    payload = {
        "number": pull_request["number"],
        "title": pull_request["title"],
        "body": pull_request.get("body") or "",
        "isDraft": bool(pull_request.get("draft")),
        "baseRefName": pull_request["base"]["ref"],
        "headRefName": pull_request["head"]["ref"],
        "headRefOid": pull_request["head"]["sha"],
        "url": pull_request["html_url"],
        "files": files,
        "mergeStateStatus": str(pull_request.get("mergeable_state") or "").upper(),
        "reviewDecision": derive_review_decision(reviews),
        "statusCheckRollup": fetch_check_runs(pull_request["head"]["sha"]),
    }
    payload["comments"] = fetch_pr_comments(pr_number)
    payload["reviews"] = reviews
    return payload


def fetch_pr_comments(pr_number: int) -> list[dict[str, Any]]:
    completed = run_command(
        [
            "gh",
            "api",
            f"repos/{github_repo_slug()}/issues/{pr_number}/comments?per_page=100",
        ]
    )
    comments = json.loads(completed.stdout)
    return [
        {
            "body": str(comment.get("body") or ""),
            "createdAt": str(comment.get("created_at") or ""),
            "author": {"login": ((comment.get("user") or {}).get("login") or "")},
        }
        for comment in comments
    ]


def fetch_pr_files(pr_number: int) -> list[dict[str, Any]]:
    completed = run_command(
        [
            "gh",
            "api",
            f"repos/{github_repo_slug()}/pulls/{pr_number}/files?per_page=100",
        ]
    )
    files = json.loads(completed.stdout)
    return [
        {
            "path": str(file_entry.get("filename") or ""),
            "additions": int(file_entry.get("additions") or 0),
            "deletions": int(file_entry.get("deletions") or 0),
        }
        for file_entry in files
        if file_entry.get("filename")
    ]


def fetch_pr_reviews(pr_number: int) -> list[dict[str, Any]]:
    completed = run_command(
        [
            "gh",
            "api",
            f"repos/{github_repo_slug()}/pulls/{pr_number}/reviews?per_page=100",
        ]
    )
    reviews = json.loads(completed.stdout)
    return [
        {
            "state": str(review.get("state") or ""),
            "submittedAt": str(review.get("submitted_at") or ""),
            "body": str(review.get("body") or ""),
            "author": {"login": ((review.get("user") or {}).get("login") or "")},
        }
        for review in reviews
    ]


def derive_review_decision(reviews: list[dict[str, Any]]) -> str:
    latest_reviews: dict[str, dict[str, Any]] = {}
    for review in reviews:
        author_login = str((review.get("author") or {}).get("login") or "").strip()
        if not author_login:
            continue
        existing = latest_reviews.get(author_login)
        review_key = str(review.get("submittedAt") or "")
        existing_key = str(existing.get("submittedAt") or "") if existing else ""
        if existing is None or review_key >= existing_key:
            latest_reviews[author_login] = review

    latest_states = {str(review.get("state") or "").upper() for review in latest_reviews.values()}
    if "CHANGES_REQUESTED" in latest_states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in latest_states:
        return "APPROVED"
    return ""


def fetch_check_runs(head_sha: str) -> list[dict[str, Any]]:
    completed = run_command(
        [
            "gh",
            "api",
            f"repos/{github_repo_slug()}/commits/{head_sha}/check-runs?per_page=100",
            "-H",
            "Accept: application/vnd.github+json",
        ]
    )
    payload = json.loads(completed.stdout)
    check_runs = payload.get("check_runs", [])
    return [
        {
            "name": str(check_run.get("name") or ""),
            "status": str(check_run.get("status") or "").upper(),
            "conclusion": str(check_run.get("conclusion") or "").upper(),
            "detailsUrl": str(check_run.get("details_url") or ""),
            "startedAt": str(check_run.get("started_at") or ""),
            "completedAt": str(check_run.get("completed_at") or ""),
        }
        for check_run in check_runs
        if check_run.get("name")
    ]


def fetch_issue_context(issue_number: int) -> dict[str, Any] | None:
    try:
        completed = run_command(
            [
                "gh",
                "issue",
                "view",
                str(issue_number),
                *gh_repo_args(),
                "--json",
                "number,title,body,state,url",
            ]
        )
    except subprocess.CalledProcessError:
        return None
    return json.loads(completed.stdout)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_linked_issue_numbers(pr_body: str) -> list[int]:
    return [int(match.group(1)) for match in ISSUE_LINK_RE.finditer(pr_body or "")]


def parse_markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in (markdown or "").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def meaningful_section_lines(section_text: str) -> list[str]:
    stripped_comments = HTML_COMMENT_RE.sub("", section_text or "")
    meaningful: list[str] = []
    for raw_line in stripped_comments.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in {"-", "*"}:
            continue
        meaningful.append(line)
    return meaningful


def section_has_content(section_text: str) -> bool:
    return bool(meaningful_section_lines(section_text))


def section_is_not_applicable(section_text: str) -> bool:
    joined = "\n".join(meaningful_section_lines(section_text))
    return bool(joined and NOT_APPLICABLE_RE.search(joined))


def section_has_open_questions(section_text: str) -> bool:
    joined = "\n".join(meaningful_section_lines(section_text))
    return bool(joined and OPEN_QUESTION_RE.search(joined))


def latest_by_name(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = str(entry.get("name") or entry.get("context") or "").strip()
        if not name:
            continue
        existing = latest.get(name)
        entry_key = str(entry.get("completedAt") or entry.get("startedAt") or "")
        existing_key = str(existing.get("completedAt") or existing.get("startedAt") or "") if existing else ""
        if existing is None or entry_key >= existing_key:
            latest[name] = entry
    return latest


def latest_comment_with_marker(comments: list[dict[str, Any]], marker: str) -> dict[str, Any] | None:
    matching = [comment for comment in comments if marker in str(comment.get("body") or "")]
    if not matching:
        return None
    matching.sort(key=lambda comment: str(comment.get("createdAt") or ""))
    return matching[-1]


def status_label(entry: dict[str, Any] | None) -> str:
    if not entry:
        return "missing"
    status = str(entry.get("status") or "").lower()
    conclusion = str(entry.get("conclusion") or "").lower()
    if status and status != "completed":
        return status
    return conclusion or status or "unknown"


def requires_demo_evidence(changed_files: list[str]) -> bool:
    return any(
        path.startswith(USER_VISIBLE_PREFIXES) or path.endswith(USER_VISIBLE_SUFFIXES)
        for path in changed_files
    )


def advisory_status(comment: dict[str, Any] | None) -> str:
    if not comment:
        return "missing"
    body = str(comment.get("body") or "")
    if "Review unavailable:" in body:
        return "unavailable"
    if "Findings present." in body:
        return "findings"
    if "No findings." in body:
        return "no-findings"
    return "unknown"


def visual_status(checks_by_name: dict[str, dict[str, Any]]) -> str:
    visual_gate = checks_by_name.get(VISUAL_CHECK_NAMES["gate"])
    visual_bypass = checks_by_name.get(VISUAL_CHECK_NAMES["bypass"])
    visual_gate_state = status_label(visual_gate)
    visual_bypass_state = status_label(visual_bypass)
    if visual_gate_state == "success":
        return "captured"
    if visual_bypass_state == "success":
        return "not-required"
    if visual_gate and visual_gate_state != "skipped":
        return visual_gate_state
    if visual_bypass:
        return visual_bypass_state
    return "missing"


def evaluate_readiness(pr_context: dict[str, Any], issue_context: dict[str, Any] | None) -> dict[str, Any]:
    body = str(pr_context.get("body") or "")
    sections = parse_markdown_sections(body)
    linked_issues = parse_linked_issue_numbers(body)
    files = [entry["path"] for entry in pr_context.get("files", [])]
    checks_by_name = latest_by_name(pr_context.get("statusCheckRollup", []))
    advisory_comment = latest_comment_with_marker(pr_context.get("comments", []), ADVISORY_COMMENT_MARKER)
    visual_comment = latest_comment_with_marker(pr_context.get("comments", []), VISUAL_COMMENT_MARKER)
    advisory = advisory_status(advisory_comment)
    visual = visual_status(checks_by_name)

    blockers: list[str] = []
    risks: list[str] = []
    notes: list[str] = []

    if pr_context.get("baseRefName") != "dev":
        blockers.append(f"PR targets `{pr_context.get('baseRefName')}` instead of `dev`.")
    if pr_context.get("isDraft"):
        blockers.append("PR is still draft.")

    if len(linked_issues) != 1:
        blockers.append("PR body must include exactly one closing link like `Closes #<issue-number>`.")
    elif issue_context is None:
        risks.append(f"Linked issue `#{linked_issues[0]}` could not be loaded from GitHub.")

    if not section_has_content(sections.get(SECTION_SUMMARY, "")):
        blockers.append("PR body is missing a meaningful `## Summary` section.")
    if not section_has_content(sections.get(SECTION_TESTING, "")):
        blockers.append("PR body is missing a meaningful `## Testing` section.")
    if not section_has_content(sections.get(SECTION_FOLLOWUPS, "")):
        blockers.append("PR body is missing a meaningful `## Follow-ups / Risks` section.")

    docs_text = sections.get(SECTION_DOCS, "")
    if not section_has_content(docs_text):
        risks.append("PR body does not state whether docs were updated or not applicable.")
    if section_has_open_questions(docs_text):
        blockers.append("`## Docs` contains unresolved TODO/TBD text.")

    followups_text = sections.get(SECTION_FOLLOWUPS, "")
    if section_has_open_questions(followups_text):
        blockers.append("`## Follow-ups / Risks` contains unresolved TODO/TBD text.")

    demo_text = sections.get(SECTION_DEMO, "")
    demo_present = section_has_content(demo_text)
    demo_not_applicable = section_is_not_applicable(demo_text)
    demo_required = requires_demo_evidence(files)

    if demo_required and not demo_present:
        blockers.append("Changed files appear user-visible, but `## Demo / Evidence` is empty.")
    if demo_required and demo_not_applicable:
        blockers.append("`## Demo / Evidence` says not applicable even though user-visible files changed.")
    if not demo_present and not demo_required:
        risks.append("PR body does not state whether demo evidence was provided or not applicable.")
    if visual == "captured" and not demo_present:
        blockers.append("Visual gate captured UI evidence, but the PR body does not summarize it under `## Demo / Evidence`.")
    if visual == "captured" and visual_comment is None:
        risks.append("Visual gate passed, but no visual gate PR comment was found.")
    if visual in {"failure", "timed_out", "cancelled", "action_required"}:
        blockers.append(f"Visual gate reported `{visual}`.")
    if visual in {"in_progress", "queued", "requested", "waiting", "pending"}:
        blockers.append("Visual gate has not finished yet.")
    if visual == "missing" and demo_required:
        risks.append("Visual gate has not reported yet; relying on PR body demo evidence only.")

    if advisory == "findings":
        blockers.append("Advisory code review reported findings that still need human resolution.")
    elif advisory in {"missing", "unknown"}:
        risks.append("Advisory code review comment is missing or unparseable.")
    elif advisory == "unavailable":
        risks.append("Advisory code review was unavailable for this PR.")

    baseline_check_statuses: dict[str, str] = {}
    for check_name in BASELINE_CHECK_NAMES:
        state = status_label(checks_by_name.get(check_name))
        baseline_check_statuses[check_name] = state
        if state in {"failure", "timed_out", "cancelled", "action_required"}:
            blockers.append(f"Baseline check `{check_name}` reported `{state}`.")
        elif state in {"in_progress", "queued", "requested", "waiting", "pending"}:
            blockers.append(f"Baseline check `{check_name}` has not finished yet.")
        elif state == "missing":
            risks.append(f"Baseline check `{check_name}` has not reported on the PR yet.")

    if pr_context.get("reviewDecision") == "CHANGES_REQUESTED":
        blockers.append("GitHub review state is `CHANGES_REQUESTED`.")

    if issue_context:
        notes.append(f"Linked issue state: `{issue_context.get('state', 'UNKNOWN')}`.")
    if pr_context.get("mergeStateStatus") not in {"CLEAN", "HAS_HOOKS", "UNKNOWN"}:
        risks.append(f"GitHub merge state is `{pr_context['mergeStateStatus']}`.")

    if blockers:
        result = READINESS_NOT_READY
        summary = f"{len(blockers)} blocking readiness gap(s) were found."
    elif risks:
        result = READINESS_READY_WITH_RISKS
        summary = f"No blockers were found, but {len(risks)} readiness risk(s) remain for human review."
    else:
        result = READINESS_READY
        summary = "The PR meets the current merge-readiness contract and is ready for human merge review."

    return {
        "result": result,
        "summary": summary,
        "blockers": blockers,
        "risks": risks,
        "notes": notes,
        "linked_issue_numbers": linked_issues,
        "sections": {
            SECTION_SUMMARY: section_has_content(sections.get(SECTION_SUMMARY, "")),
            SECTION_TESTING: section_has_content(sections.get(SECTION_TESTING, "")),
            SECTION_DEMO: demo_present,
            SECTION_DOCS: section_has_content(docs_text),
            SECTION_FOLLOWUPS: section_has_content(followups_text),
        },
        "evidence": {
            "advisory_review": advisory,
            "visual_gate": visual,
            "baseline_checks": baseline_check_statuses,
            "docs_note": "not-applicable" if section_is_not_applicable(docs_text) else ("present" if section_has_content(docs_text) else "missing"),
            "demo_note": "not-applicable" if demo_not_applicable else ("present" if demo_present else "missing"),
        },
    }


def render_readiness_markdown(
    readiness: dict[str, Any],
    *,
    pr_context: dict[str, Any],
    issue_context: dict[str, Any] | None,
) -> str:
    result_label = readiness["result"].upper().replace("-", " ")
    lines = [COMMENT_MARKER, "## Merge Readiness", ""]
    lines.append(f"- PR: #{pr_context['number']} `{pr_context['title']}`")
    lines.append(f"- Base branch: `{pr_context['baseRefName']}`")
    lines.append(f"- Head branch: `{pr_context['headRefName']}`")
    if issue_context:
        lines.append(f"- Linked issue: #{issue_context['number']} `{issue_context['title']}`")
    lines.append("- Human merge remains required")
    lines.append("- Contract: `docs/harness/merge-readiness.md`")
    lines.append("")
    lines.append("### Result")
    lines.append("")
    lines.append(f"**{result_label}**. {readiness['summary']}")
    lines.append("")

    lines.append("### Blockers")
    lines.append("")
    if readiness["blockers"]:
        for blocker in readiness["blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- None.")
    lines.append("")

    lines.append("### Risks")
    lines.append("")
    if readiness["risks"]:
        for risk in readiness["risks"]:
            lines.append(f"- {risk}")
    else:
        lines.append("- None.")
    lines.append("")

    evidence = readiness["evidence"]
    lines.append("### Evidence Snapshot")
    lines.append("")
    lines.append(f"- Advisory review: `{evidence['advisory_review']}`")
    lines.append(f"- Visual evidence: `{evidence['visual_gate']}`")
    baseline_checks = evidence["baseline_checks"]
    for check_name, state in baseline_checks.items():
        lines.append(f"- Baseline check `{check_name}`: `{state}`")
    lines.append(f"- `## Testing`: `{'present' if readiness['sections'][SECTION_TESTING] else 'missing'}`")
    lines.append(f"- `## Demo / Evidence`: `{evidence['demo_note']}`")
    lines.append(f"- `## Docs`: `{evidence['docs_note']}`")
    lines.append(f"- `## Follow-ups / Risks`: `{'present' if readiness['sections'][SECTION_FOLLOWUPS] else 'missing'}`")
    lines.append("")

    lines.append("### Maintainer Use")
    lines.append("")
    lines.append("- Use this summary as the single merge-readiness view before human review or merge.")
    lines.append("- Clear blockers first; treat listed risks as explicit human judgment calls.")

    return "\n".join(lines) + "\n"


def build_self_test_context() -> tuple[dict[str, Any], dict[str, Any]]:
    pr_context = {
        "number": 7,
        "title": "Baseline merge-readiness self-test",
        "body": """
## Summary
- Exercise the managed merge-readiness baseline.

## Testing
- `bash scripts/smoke_local.sh`

## Demo / Evidence
- Not applicable.

## Docs
- Updated docs/harness/merge-readiness.md.

## Follow-ups / Risks
- None.

Closes #7
""".strip(),
        "isDraft": False,
        "baseRefName": "dev",
        "headRefName": "codex/self-test-merge-readiness",
        "headRefOid": "selftest0000000000000000000000000000000000",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "",
        "files": [{"path": "scripts/run_merge_readiness_audit.py"}],
        "comments": [
            {
                "body": f"{ADVISORY_COMMENT_MARKER}\nNo findings. The advisory reviewer did not detect concrete issues.",
                "createdAt": "2026-03-11T00:00:00Z",
                "author": {"login": "codex"},
            }
        ],
        "statusCheckRollup": [
            {
                "name": "harness",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "completedAt": "2026-03-11T00:00:01Z",
            }
        ],
        "url": "https://example.invalid/pr/7",
        "reviews": [],
    }
    issue_context = {
        "number": 7,
        "title": "Exercise the baseline merge-readiness flow",
        "state": "OPEN",
        "url": "https://example.invalid/issues/7",
    }
    return pr_context, issue_context


def run_self_test(output_dir: Path) -> int:
    pr_context, issue_context = build_self_test_context()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "pr-context.json", pr_context)
    write_json(output_dir / "issue-context.json", issue_context)
    readiness = evaluate_readiness(pr_context, issue_context)
    if readiness["result"] != READINESS_READY:
        raise SystemExit(f"Self-test expected `{READINESS_READY}` but got `{readiness['result']}`.")
    write_json(output_dir / "readiness.json", readiness)
    markdown = render_readiness_markdown(readiness, pr_context=pr_context, issue_context=issue_context)
    (output_dir / "readiness.md").write_text(markdown, encoding="utf-8")
    print(f"OK merge-readiness self-test passed at {output_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit merge readiness for a pull request.")
    parser.add_argument("--pr-number", type=int, help="GitHub pull request number.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated readiness artifacts.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the built-in baseline self-test without GitHub API calls.",
    )
    args = parser.parse_args(argv)
    if not args.self_test and args.pr_number is None:
        parser.error("--pr-number is required unless --self-test is used")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.resolve()
    if args.self_test:
        return run_self_test(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    pr_context = fetch_pr_context(args.pr_number)
    write_json(output_dir / "pr-context.json", pr_context)

    linked_issues = parse_linked_issue_numbers(str(pr_context.get("body") or ""))
    issue_context = fetch_issue_context(linked_issues[0]) if len(linked_issues) == 1 else None
    if issue_context:
        write_json(output_dir / "issue-context.json", issue_context)

    readiness = evaluate_readiness(pr_context, issue_context)
    write_json(output_dir / "readiness.json", readiness)

    markdown = render_readiness_markdown(readiness, pr_context=pr_context, issue_context=issue_context)
    (output_dir / "readiness.md").write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
