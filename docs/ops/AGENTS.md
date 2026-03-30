# Product Repo Agent Notes

This is the canonical copy of the repo bootstrap guidance mirrored at the repo root in `AGENTS.md`.

## Scope
- These notes apply to repositories that adopt the `agent-core` factory baseline.
- Product-domain behavior stays local unless it has been explicitly promoted into shared baseline.

## Start Here
- Architecture context: `../architecture/README.md`
- Harness workflows: `../harness/README.md`
- Planning area: `../planning/README.md`
- Issue and PR rules: `PROJECT_PLANNING.md`

## Core Rules
- Use `gh` for issues, pull requests, and project operations.
- One pursued issue = one worktree off `dev` = one branch = one PR lane.
- If another coding lane may run at the same time, do not work from the shared repo checkout; create a dedicated worktree first and use `../harness/worktree-bootstrap.md`.
- Keep changes inside the issue Outcome, Requirements, Acceptance criteria, and Non-goals.
- Run the narrowest relevant checks first, then broader smoke checks as needed.
- Before a PR is reviewable, make the PR body match `../../.github/pull_request_template.md` exactly.
- A reviewable PR must contain exactly one `Closes #<issue-number>` link. Use `Part of #<issue-number>` or plain issue references for related epics or sibling issues.
- Before asking for merge, run `python3 scripts/run_merge_readiness_audit.py --pr-number <pr-number>` and clear any blockers it reports.
- Do not commit secrets, `.env.*` files, or Terraform backend config.
- Human reviewers merge PRs into `dev`.

## Local Extensions
- Add product-specific repo maps and area entrypoints in local docs once the product structure stabilizes.
- Keep this file short. Put long workflow guidance in `docs/harness/` or repo-local skills.
