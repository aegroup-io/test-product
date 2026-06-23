# Harness Docs

`docs/harness/` is the canonical home for internal repo-development workflows in a product repo that adopts the `agent-core` baseline.

Put docs here when they answer questions like:

- How do contributors bring the repo up locally?
- How should contributors validate, review, and package changes?
- How do issue, branch, PR, and merge workflows operate in this repo?

Common baseline docs will eventually cover:

- repo bootstrap
- repo harness validation
- advisory review
- merge readiness
- local development
- worktree bootstrap
- skill authoring

Current extracted docs:

- [`advisory-code-review.md`](advisory-code-review.md) for the advisory Codex review rubric and artifact contract.
- [`agent-core-product-codex-lane-smoke.md`](agent-core-product-codex-lane-smoke.md) for the local dogfood path that creates a fresh `agent-core` product repo and runs a real Codex lane against it.
- [`github-repo-bootstrap.md`](github-repo-bootstrap.md) for the baseline GitHub Actions rollout path.
- [`internal-package-registry.md`](internal-package-registry.md) for the managed npm and PyPI internal registry templates, validation, and smoke path.
- [`local-development.md`](local-development.md) for the managed local start scripts and baseline local harness checks.
- [`local-container-lane-smoke.md`](local-container-lane-smoke.md) for the Docker-backed coding-lane build and smoke workflow.
- [`merge-readiness.md`](merge-readiness.md) for the merge-readiness summary contract used before human merge.
- [`local-agents-full-stack.md`](local-agents-full-stack.md) for the local API, web, worker, MCP, Sessions, and agent-run smoke workflow.
- [`repo-harness.md`](repo-harness.md) for the baseline harness workflow and validator.
- [`requirements-issue-taxonomy.md`](requirements-issue-taxonomy.md) for the generated requirements issue body, label, relationship, and readiness contract.
- [`worktree-bootstrap.md`](worktree-bootstrap.md) for the local worktree namespace contract used by the managed start scripts.
- [`../ops/PROJECT_PLANNING.md`](../ops/PROJECT_PLANNING.md) for the issue, worktree, branch, and PR-lane rules that sit above the harness flows.

Keep durable system boundaries and product-domain architecture out of this folder.
