# Orcha

Orcha is a GitHub-native orchestration control plane. It tracks product contracts, mirrors GitHub
state into durable local tables, exposes operator read models through a versioned API, and ships an
operator-facing web UI for fleet, product, lane, baseline, and graph review.

The original product contract lives in [`SPEC.md`](SPEC.md). Durable design decisions and system
boundaries live under [`docs/architecture/`](docs/architecture/README.md).

## What Is Implemented Today

The current `dev` branch includes:

- a versioned operator API for product, lane, baseline, graph, and webhook-replay actions
- an Orcha-native operator UI for fleet, product, lane, baseline, and graph views
- product adoption and seeding flows
- GitHub webhook intake plus persisted delivery ledger and mirror tables
- standards pack and managed-asset drift tracking
- durable lane, execution-environment, session, and recovery models
- repo harness validation, merge-readiness self-test, and Terraform entrypoint validation

## Current Boundary

This repo is ready for control-plane review: API contracts, operator UI, GitHub mirror behavior,
baseline management, graph overlays, and restart-safe recovery are all present and test-backed.

Full end-to-end coding-lane execution is not complete yet. The main follow-up work is tracked in:

- #54 wire live scheduling and runner launch for end-to-end coding lanes
- #55 add Docker-backed coding lane runtime smoke and local container validation

If you are reviewing the control plane locally, you do not need Docker today. Docker is expected to
become part of the local coding-lane validation path as #55 lands.

## Repo Map

- [`SPEC.md`](SPEC.md): original product specification and v1 definition of done
- [`docs/architecture/`](docs/architecture/README.md): durable architecture and system boundaries
- [`docs/harness/`](docs/harness/README.md): local workflow, worktree rules, and harness guidance
- [`.orcha/product.yaml`](.orcha/product.yaml): product contract used by Orcha
- [`.orcha/components.yaml`](.orcha/components.yaml): declared component graph seed
- [`api/`](api): FastAPI wrapper for the Orcha API service
- [`packages/platform-api/`](packages/platform-api): core control-plane implementation
- [`web/`](web): Orcha operator UI
- [`packages/web-shell/`](packages/web-shell): shared shell components reused by the web app
- [`worker/`](worker): worker wrapper
- [`packages/platform-worker/`](packages/platform-worker): shared worker runtime
- [`mcp/`](mcp): MCP wrapper service
- [`infra/`](infra): Terraform entrypoint scaffold and delivery baseline

## Local Review Prerequisites

Install these before using the managed start scripts:

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) on `PATH`, or let the Python start scripts bootstrap a repo-local `.venv` on first run
- Node.js 22.12+ and `npm`
- Git
- Docker Desktop for the default local Postgres runtime

Optional:

- an existing PostgreSQL instance when you want to set `AGENT_CORE_DATABASE_URL` and bypass Docker

## Local Review Workflow

This repo expects worktree-first local development when more than one lane may exist at once.
Start with:

```bash
git worktree add -b codex/issue-<issue-number>-<slug> ../orcha-issue-<issue-number> dev
cd ../orcha-issue-<issue-number>
python3 scripts/bootstrap_local_namespace.py
```

The namespace bootstrap prints the derived local URLs and port assignments for the current worktree.

Run the baseline local checks from repo root:

```bash
bash scripts/smoke_local.sh
```

Start each service in its own terminal:

```bash
bash scripts/start_local_postgres.sh
bash scripts/start_local_api.sh
bash scripts/start_local_web.sh
bash scripts/start_local_worker.sh
bash scripts/start_local_mcp.sh
bash scripts/start_local_docs.sh
```

If `uv` is not installed, the API, worker, and MCP start scripts will create a repo-local `.venv`
the first time they run and install the required Python dependencies into it.

`bash scripts/start_local_api.sh` automatically starts the namespaced local Postgres container when
`AGENT_CORE_DATABASE_URL` is unset. Use `bash scripts/start_local_postgres.sh` only when you want
the database ready before the API starts, or set `AGENT_CORE_DATABASE_URL` to an existing
PostgreSQL instance to bypass Docker.

Stop the tracked local services and the namespaced Postgres container with:

```bash
bash scripts/stop_local_environment.sh
```

Use `--apps-only` if you want to leave Postgres running:

```bash
bash scripts/stop_local_environment.sh --apps-only
```

## Verification Commands

The narrow, high-signal checks for this repo are:

```bash
bash scripts/smoke_local.sh
uv run --project api --extra dev pytest
uv run --project worker --extra dev pytest
uv run --project mcp pytest
cd web && npm install && npm test && npm run build
```

## Key Architecture Entry Points

Start here when orienting yourself in the codebase:

- [`docs/architecture/operator-api-v1.md`](docs/architecture/operator-api-v1.md)
- [`docs/architecture/operator-web-ui.md`](docs/architecture/operator-web-ui.md)
- [`docs/architecture/github-mirror-and-repair.md`](docs/architecture/github-mirror-and-repair.md)
- [`docs/architecture/durable-scheduling-and-lane-claiming.md`](docs/architecture/durable-scheduling-and-lane-claiming.md)
- [`docs/architecture/remote-execution-environments.md`](docs/architecture/remote-execution-environments.md)
- [`docs/architecture/runner-protocol-and-session-events.md`](docs/architecture/runner-protocol-and-session-events.md)
- [`docs/architecture/retry-recovery-and-reconciliation.md`](docs/architecture/retry-recovery-and-reconciliation.md)
- [`docs/architecture/component-graph-and-topology-ingest.md`](docs/architecture/component-graph-and-topology-ingest.md)
- [`docs/architecture/observability-and-operator-notifications.md`](docs/architecture/observability-and-operator-notifications.md)

## Notes

- The root README is an entrypoint, not the full contract. Use `SPEC.md` and `docs/architecture/`
  for deeper details.
- Issue and PR packaging rules live in [`docs/ops/PROJECT_PLANNING.md`](docs/ops/PROJECT_PLANNING.md).
- Repo-level contributor instructions live in [`AGENTS.md`](AGENTS.md).
