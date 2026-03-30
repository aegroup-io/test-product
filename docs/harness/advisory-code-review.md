# Advisory Code Review

This document is the canonical rubric and operating contract for the repo-level advisory Codex review flow.

## Purpose

Use the advisory review flow to add a correctness-focused agent pass to pull requests before human merge.

The review is advisory only:

- it does not replace CI or human review
- it does not approve or merge pull requests
- it must prioritize bugs, regressions, risky behavior, and missing evidence over style-only commentary

## Canonical Rubric

The advisory reviewer must ground its review in repo-local standards, in this order:

1. `AGENTS.md`
2. `docs/harness/`
3. `docs/architecture/`
4. `docs/planning/`
5. any additional product-local standards explicitly referenced by those documents

The reviewer should inspect the diff plus enough nearby context to understand behavior changes.

## Review Scope

Focus on:

- behavior regressions
- missing or weak tests for the changed area
- risky auth, permissions, routing, queue, execution, or deploy changes
- repo-standard drift with an actual correctness or maintainability risk
- pull-request evidence gaps when the claimed validation does not match the changed area

Do not focus on:

- style-only nits
- speculative refactors unrelated to the changed behavior
- duplicate commentary already fully covered by failing CI

## Output Contract

The review must produce one of these outcomes:

- `findings`: one or more severity-ordered findings
- `no-findings`: explicit statement that no concrete review findings were found
- `review-unavailable`: the harness could not run the advisory review and wrote an explanatory fallback artifact instead

Each finding must include:

- severity: `high`, `medium`, or `low`
- concise title
- affected file and line when practical
- why it matters
- recommended next action
- supporting evidence tied to the actual diff or surrounding code

## Artifact Contract

The advisory review flow writes a predictable artifact bundle under `artifacts/advisory-code-review/` or the CI-provided output directory:

- `pr-context.json`
- `issue-context.json` when the pull request body links an issue with a closing keyword and the linked issue lookup succeeds
- `review-prompt.md`
- `review.json`
- `review.md`

CI uploads that bundle as an artifact and updates a single pull-request comment with the rendered `review.md` body.

## Local Reproduction

Prerequisites:

- `codex` installed locally
- Codex logged in already, or an `OPENAI_API_KEY` available for `codex login --with-api-key`
- `gh` authenticated for repo and pull-request access when reviewing a GitHub pull request

Run locally from repo root:

```bash
gh pr checkout 101
python3 scripts/run_advisory_code_review.py --base-ref origin/dev --pr-number 101
```

If you do not want to switch your current checkout, run the command from a dedicated worktree that is already on the pull-request head.

Optional model override:

```bash
CODEX_REVIEW_MODEL=gpt-5 python3 scripts/run_advisory_code_review.py --base-ref origin/dev --pr-number 101
```

Optional sandbox override:

```bash
CODEX_SANDBOX_MODE=danger-full-access python3 scripts/run_advisory_code_review.py --base-ref origin/dev --pr-number 101
```

## CI Configuration

Use [`github-repo-bootstrap.md`](github-repo-bootstrap.md) as the canonical rollout checklist when enabling this workflow in another product repo.

Repository secret required for the CI reviewer:

- `OPENAI_API_KEY`

Optional repository variable:

- `CODEX_REVIEW_MODEL`

GitHub-hosted runners should set `CODEX_SANDBOX_MODE=danger-full-access` for the advisory job.
The harness maps that mode to Codex's explicit sandbox-bypass flag because those runners are already
isolated at the VM level, and Codex `workspace-write` can fail there when its `bwrap` network
sandbox setup is denied by the host kernel policy.

If the secret is missing, or if a manual dispatch targets a fork pull request, the workflow reports the advisory review as unavailable instead of failing the pull request.
