# Delivery Baseline Smoke

This document is the canonical contract for the managed delivery baseline smoke runner.

## Purpose

Use the delivery baseline smoke runner to execute one repo-local config that composes the baseline Azure delivery helpers already managed by `agent-core`.

This is the current downstream proof point for a seeded product repo:

- Terraform backend rendering
- container image dry-run
- AKS workload dry-run
- APIM sync dry-run
- App Service zip packaging
- optional remote smoke probes

## Components

The current delivery baseline consists of:

- [`../../scripts/run_delivery_baseline_smoke.py`](../../scripts/run_delivery_baseline_smoke.py)
- [`../../scripts/schemas/delivery_baseline_smoke.schema.json`](../../scripts/schemas/delivery_baseline_smoke.schema.json)
- [`../../.github/workflows/delivery-baseline-smoke.yml`](../../.github/workflows/delivery-baseline-smoke.yml)

## Config Contract

By default the runner looks for:

- [`.agent-core/delivery-baseline-smoke.json`](../../.agent-core/delivery-baseline-smoke.json)

Supported top-level sections are:

- `terraform_backend`
- `container_image`
- `aks_workload`
- `apim`
- `app_service`
- `remote_smoke`

Every section is optional, but when present it must satisfy the schema in [`../../scripts/schemas/delivery_baseline_smoke.schema.json`](../../scripts/schemas/delivery_baseline_smoke.schema.json).

The runner composes baseline helpers rather than re-implementing delivery logic:

- Terraform backend runs in `--render-only` mode
- container image runs in `--dry-run` mode
- AKS workload runs in `--dry-run` mode
- APIM sync runs in `--dry-run` mode
- App Service packages locally with `--no-deploy`
- remote smoke performs real probes when URLs are provided

## Local Reproduction

Run the default config:

```bash
python3 scripts/run_delivery_baseline_smoke.py
```

Run an explicit config:

```bash
python3 scripts/run_delivery_baseline_smoke.py \
  --config .agent-core/delivery-baseline-smoke.json
```

## Future Expansion

Later delivery-core extractions may add:

- environment-specific config inheritance
- artifact manifests or release metadata
- CI-oriented config profiles for internal runners
