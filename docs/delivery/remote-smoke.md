# Remote Smoke

This document is the canonical contract for the baseline remote post-deploy smoke probe.

## Purpose

Use the remote smoke flow to verify that a deployed product environment is reachable after deployment without assuming a specific cloud provider, Terraform layout, or product topology.

The baseline remote smoke currently focuses on:

- a primary app URL
- an optional API base URL
- simple HTTP reachability checks
- a strict mode for CI or release gating

## Components

The current delivery baseline consists of:

- [`../../scripts/smoke_remote.sh`](../../scripts/smoke_remote.sh)
- [`../../.github/workflows/remote-smoke.yml`](../../.github/workflows/remote-smoke.yml)

## Contract

Inputs may be provided either as CLI arguments or environment variables:

- `--app-url` or `REMOTE_APP_URL`
- `--app-health-path` or `REMOTE_APP_HEALTH_PATH`
- `--api-url` or `REMOTE_API_URL`
- `--api-health-path` or `REMOTE_API_HEALTH_PATH`
- `--timeout` or `REMOTE_SMOKE_TIMEOUT_SECONDS`

The current defaults are:

- app probe path: `/`
- API probe path: `/health`
- timeout: `10` seconds

If no URLs are configured, the probe warns and exits successfully by default. Use `--strict` when a workflow should fail on missing or unreachable targets.

## Local Reproduction

Run locally from repo root:

```bash
bash scripts/smoke_remote.sh --app-url https://example.internal --api-url https://api.example.internal --strict
```

If your repo later exposes Terraform outputs or platform-specific deploy metadata, map those outputs into the CLI args or `REMOTE_*` env vars at the workflow layer. The baseline script intentionally does not assume where those URLs come from.

## GitHub Workflow

Use the manual workflow in [`../../.github/workflows/remote-smoke.yml`](../../.github/workflows/remote-smoke.yml) when maintainers want a quick post-deploy reachability check without changing product-specific CI.

## Future Expansion

Later delivery-core extractions may add:

- authenticated probes
- environment-specific URL resolution helpers
- artifact output for release evidence
- stronger release-gating behavior
