# Repo Harness

This document is the canonical contract for the baseline repo-harness workflow and validator.

## Purpose

Use the repo harness to verify that a product repo still contains the managed baseline files it adopted from `agent-core`.

The current baseline harness focuses on:

- required managed files existing at the expected paths
- managed markdown files resolving their repo-local path references
- the managed merge-readiness self-test remaining runnable locally
- giving maintainers a fast signal when the adopted baseline has drifted or been partially removed

## Components

The baseline harness currently consists of:

- [`../../.github/workflows/repo-harness.yml`](../../.github/workflows/repo-harness.yml)
- [`../../scripts/bootstrap_local_namespace.py`](../../scripts/bootstrap_local_namespace.py)
- [`../../scripts/local_namespace.sh`](../../scripts/local_namespace.sh)
- [`../../scripts/local_postgres_runtime.sh`](../../scripts/local_postgres_runtime.sh)
- [`../../scripts/local_python_runtime.sh`](../../scripts/local_python_runtime.sh)
- [`../../scripts/start_local_api.sh`](../../scripts/start_local_api.sh)
- [`../../scripts/start_local_postgres.sh`](../../scripts/start_local_postgres.sh)
- [`../../scripts/start_local_web.sh`](../../scripts/start_local_web.sh)
- [`../../scripts/start_local_worker.sh`](../../scripts/start_local_worker.sh)
- [`../../scripts/start_local_mcp.sh`](../../scripts/start_local_mcp.sh)
- [`../../scripts/start_local_docs.sh`](../../scripts/start_local_docs.sh)
- [`../../scripts/stop_local_environment.sh`](../../scripts/stop_local_environment.sh)
- [`../../scripts/validate_repo_harness_assets.py`](../../scripts/validate_repo_harness_assets.py)
- [`../../scripts/smoke_local.sh`](../../scripts/smoke_local.sh)

## Current Scope

The baseline harness validates the currently extracted managed assets:

- root and canonical agent notes
- docs skeleton files
- extracted security review prompt
- issue templates
- pull request template
- the repo harness workflow, local smoke, validator, and managed local-start scripts themselves
- the managed merge-readiness audit self-test

It does not validate product-domain runtime behavior.

## Local Reproduction

Run locally from repo root:

```bash
bash scripts/smoke_local.sh
```

## CI Contract

The repo harness workflow is intentionally lightweight:

- it checks out the repo
- runs `bash scripts/smoke_local.sh`

This workflow is meant to be a baseline guardrail, not a full product CI replacement.

## Future Expansion

Later baseline extractions may add:

- additional harness docs
- stronger validation tied to manifest adoption state
