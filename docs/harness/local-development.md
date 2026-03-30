# Local Development

This document is the baseline local-development contract for a product repo that adopts the `agent-core` harness.

## Purpose

Use these checks to verify that the adopted baseline assets are still intact and runnable in the local repo.

## Worktree-first Execution

For agent work or any situation where more than one coding lane may exist at once, use a dedicated git worktree before running local commands. Do not reuse the shared repo checkout for concurrent lanes.

Example:

```bash
git worktree add -b issue-123-example ../product-issue-123 dev
cd ../product-issue-123
eval "$(python3 scripts/bootstrap_local_namespace.py --format shell)"
```

The shared checkout is acceptable only when you are sure no other active lane is using it.

## Worktree Namespace Bootstrap

Inspect the derived namespace contract for the current worktree:

```bash
python3 scripts/bootstrap_local_namespace.py
```

The managed local start scripts apply this contract automatically.

See [`worktree-bootstrap.md`](worktree-bootstrap.md) for the contract details.

## Managed Start Scripts

Run each service from repo root in its own terminal:

```bash
bash scripts/start_local_postgres.sh
bash scripts/start_local_api.sh
bash scripts/start_local_web.sh
bash scripts/start_local_worker.sh
bash scripts/start_local_mcp.sh
bash scripts/start_local_docs.sh
```

`scripts/start_local_api.sh` automatically starts the namespaced local Postgres container when
`AGENT_CORE_DATABASE_URL` is unset. Use `scripts/start_local_postgres.sh` only when you want the
database running before the API starts.

If `uv` is not available, the Python service launchers (`start_local_api.sh`,
`start_local_worker.sh`, and `start_local_mcp.sh`) bootstrap a repo-local `.venv` on first run
and install the required dependencies there before starting the service.

The default local database runtime is Docker-backed Postgres. Set `AGENT_CORE_DATABASE_URL` to an
existing PostgreSQL instance when you want to bypass Docker for local work.

`scripts/start_local_api.sh` now enables the live orchestration loop by default for local/dev
worktrees. Override `AGENT_CORE_ORCHESTRATION_LOOP_ENABLED=0` only when you need a static API
process for focused debugging.

Stop the tracked local processes and the namespaced Postgres container for the current worktree:

```bash
bash scripts/stop_local_environment.sh
```

Use `--apps-only` when you want to leave Postgres running:

```bash
bash scripts/stop_local_environment.sh --apps-only
```

## Baseline Local Checks

Run from repo root:

```bash
bash scripts/smoke_local.sh
```

These checks validate the currently extracted harness baseline:

- required managed files are present
- managed markdown files resolve their local path references
- the repo-local Terraform entrypoint validates against the fixed stack contract
- the managed merge-readiness audit can run in local self-test mode
- local harness scripts compile

For direct inspection, the smoke script currently runs:

```bash
python3 scripts/validate_repo_harness_assets.py
bash scripts/validate_terraform_entrypoint.sh
python3 scripts/run_merge_readiness_audit.py --self-test --output-dir artifacts/merge-readiness-self-test
python3 -m compileall scripts
```

## Notes

- This baseline check does not validate product-domain runtime behavior.
- Product repos should add their own product-domain smoke workflows as runtime and delivery layers are added.
