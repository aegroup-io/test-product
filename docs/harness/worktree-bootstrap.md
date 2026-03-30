# Worktree Bootstrap

This document is the baseline worktree namespace contract for repos that adopt the `agent-core` local start scripts.

## Purpose

The managed local start scripts derive ports, URLs, PID roots, worker job roots, and the local
Postgres contract from the current worktree path. That keeps parallel worktrees from colliding on
the same localhost ports.

This is not just a convenience feature. For concurrent agent or contributor work, the dedicated worktree is the default execution model. A branch in the shared checkout is not sufficient isolation.

Inspect the current contract with:

```bash
python3 scripts/bootstrap_local_namespace.py
python3 scripts/bootstrap_local_namespace.py --format json
python3 scripts/bootstrap_local_namespace.py --format shell
```

## Derived Values

The baseline contract currently derives:

- `AGENT_CORE_WORKTREE_NAMESPACE`
- `AGENT_CORE_LOCAL_DEV_ROOT`
- `AGENT_CORE_LOCAL_PID_ROOT`
- `AGENT_CORE_LOCAL_JOB_ROOT`
- `AGENT_CORE_LOCAL_DATABASE_URL`
- `AGENT_CORE_LOCAL_API_URL`
- `AGENT_CORE_LOCAL_WEB_URL`
- `AGENT_CORE_LOCAL_MCP_URL`
- `AGENT_CORE_LOCAL_DOCS_URL`

The slot used for ports is stable for the same worktree path and different for different worktrees.

## Default Port Ranges

- postgres: `6100 + slot`
- web: `5100 + slot`
- api: `7100 + slot`
- mcp: `8100 + slot`
- docs: `9100 + slot`

## Local Start Scripts

These managed scripts consume the contract automatically:

- [`../../scripts/start_local_postgres.sh`](../../scripts/start_local_postgres.sh)
- [`../../scripts/start_local_api.sh`](../../scripts/start_local_api.sh)
- [`../../scripts/start_local_web.sh`](../../scripts/start_local_web.sh)
- [`../../scripts/start_local_worker.sh`](../../scripts/start_local_worker.sh)
- [`../../scripts/start_local_mcp.sh`](../../scripts/start_local_mcp.sh)
- [`../../scripts/start_local_docs.sh`](../../scripts/start_local_docs.sh)
- [`../../scripts/stop_local_environment.sh`](../../scripts/stop_local_environment.sh)
