# Project Planning

This document defines the baseline issue, branch, and pull-request execution model for repos that adopt the `agent-core` harness.

## Core Model

Issues are the unit of execution.

Pull requests must map cleanly to one issue lane.

## Pull Request Rules

PR packaging rules:

- one issue lane = one worktree = one branch = one reviewable PR
- a reviewable PR body must include exactly one `Closes #<issue-number>` link
- related epics or sibling issues should be referenced with `Part of #<issue-number>` or plain links, not additional closing keywords
- if the implementation actually spans multiple child issues, either split the PR or explicitly retarget the work to the parent epic before opening review

## Review Readiness

Before a PR is reviewable:

1. Run the exact changed-area validation commands.
2. Keep the PR body aligned with `.github/pull_request_template.md`.
3. Make sure `## Demo / Evidence` and `## Docs` explicitly say what was checked or why the section is not applicable.
4. Run `python3 scripts/run_merge_readiness_audit.py --pr-number <pr-number>` and clear blockers.

Human reviewers still decide whether listed risks are acceptable before merge.
