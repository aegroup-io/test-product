# Delivery Release Verification

This document is the canonical contract for the managed delivery release verification runner.

## Purpose

Use the delivery release verification runner to compose repo-local release checks into one repeatable report artifact.

The current release layer stays deliberately thin:

- local harness smoke
- delivery baseline smoke
- required artifact/path verification
- JSON and Markdown release reports

## Components

The current delivery baseline consists of:

- [`../../scripts/run_delivery_release_verification.py`](../../scripts/run_delivery_release_verification.py)
- [`../../scripts/schemas/delivery_release_verification.schema.json`](../../scripts/schemas/delivery_release_verification.schema.json)
- [`../../.github/workflows/delivery-release-verification.yml`](../../.github/workflows/delivery-release-verification.yml)

## Config Contract

By default the runner looks for:

- [`.agent-core/delivery-release-verification.json`](../../.agent-core/delivery-release-verification.json)

Supported fields are:

- `release_id`
- `delivery_smoke_config`
- `output_dir`
- `run_local_harness`
- `run_delivery_smoke`
- `required_paths`
- `metadata`

The config schema lives at [`../../scripts/schemas/delivery_release_verification.schema.json`](../../scripts/schemas/delivery_release_verification.schema.json).

The runner writes release artifacts under `artifacts/delivery-release-verification/` by default:

- `<release-id>.json`
- `<release-id>.md`

## Local Reproduction

Run the default config:

```bash
python3 scripts/run_delivery_release_verification.py
```

Run an explicit config:

```bash
python3 scripts/run_delivery_release_verification.py \
  --config .agent-core/delivery-release-verification.json
```

## Future Expansion

Later delivery-core extractions may add:

- signed or promoted release metadata
- environment-specific release profiles
- links to remote deployment evidence or incident gates
