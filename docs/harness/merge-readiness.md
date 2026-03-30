# Merge Readiness

This document is the canonical contract for the repo-level merge-readiness auditor.

## Purpose

Use the merge-readiness flow to give maintainers one place to inspect whether a pull request is ready for human merge review.

The merge-readiness flow is advisory only:

- it never merges a pull request
- it never replaces human release judgment
- it aggregates the linked issue, testing note, demo note, docs note, advisory review status, and baseline check state into one summary

## Required Pre-review Workflow

Use this sequence before asking a human to merge:

1. Work from the dedicated issue worktree, not a shared checkout.
2. Run the exact local validation commands for the changed area.
3. If the change is user-visible, capture demo evidence or local visual-gate artifacts before updating the PR.
4. Keep the PR in draft until the body matches `.github/pull_request_template.md`.
5. Ensure the PR body has exactly one `Closes #<issue-number>` link. Use `Part of #...` for related epics or sibling issues.
6. Run the local readiness audit and clear any blockers before asking for review:

```bash
python3 scripts/run_merge_readiness_audit.py --pr-number <pr-number>
```

## Pull Request Body Contract

The readiness auditor expects the pull request body to follow the repo template in [../../.github/pull_request_template.md](../../.github/pull_request_template.md):

- `## Summary`
- `## Testing`
- `## Demo / Evidence`
- `## Docs`
- `## Follow-ups / Risks`
- `Closes #<issue-number>`

The `Docs` and `Demo / Evidence` sections may say `Not applicable.` when that is genuinely true, but the readiness summary will call that out so the human reviewer can judge it explicitly.

The body must include exactly one closing link. If the branch is part of a larger epic, mention the epic in `## Summary` or with `Part of #<issue-number>` instead of adding multiple closing keywords.

## Readiness Contract

The auditor verifies:

- exactly one linked issue closure in the pull request body
- meaningful testing evidence in the pull request body
- explicit demo applicability, with stronger enforcement when changed files look user-visible
- explicit docs applicability
- explicit follow-ups and risks
- advisory code review status from the managed advisory comment
- baseline repo-harness check state
- optional visual-gate state when a repo later adds that workflow
- human merge remains the final step

The output is one of:

- `ready`
- `ready-with-risks`
- `not-ready`

## Artifacts

The readiness flow writes:

- `pr-context.json`
- `issue-context.json` when a single linked issue is available
- `readiness.json`
- `readiness.md`

CI uploads that bundle as the `merge-readiness` artifact and updates a single pull request comment from the rendered `readiness.md`.

The GitHub workflow refreshes that summary on pull request edits, review events, and when `Repo Harness` or `Advisory Code Review` complete for the pull request.

## Repo Bootstrap Dependency

The merge-readiness workflow does not need its own secret, but it depends on upstream baseline workflows for a complete summary.

Use [github-repo-bootstrap.md](github-repo-bootstrap.md) as the canonical per-repo setup checklist for those dependencies.

## Local Reproduction

Run locally from repo root:

```bash
python3 scripts/run_merge_readiness_audit.py --self-test
python3 scripts/run_merge_readiness_audit.py --pr-number 12
```

The self-test exercises the managed baseline without GitHub calls. The `--pr-number` form reads pull request metadata from GitHub via `gh`.
Run it from the dedicated worktree or from another checkout that is not carrying unrelated lane state.

## Maintainer Usage

Before merging:

1. Read the single merge-readiness comment.
2. Clear any listed blockers.
3. Decide explicitly whether listed risks are acceptable.
4. Merge only after human review is satisfied.
