# Terraform Entrypoint Validation

This document is the canonical contract for the baseline local Terraform entrypoint validation helper.

## Purpose

Use the validation helper to prove that the repo-local Terraform entrypoint still parses, formats cleanly, and validates without mutating the checked-out repo.

The current helper assumes the platform baseline documented in [`../architecture/platform-stack.md`](../architecture/platform-stack.md):

- Azure
- Terraform
- product-owned Terraform entrypoints under the repo's environment tree

## Components

The current delivery baseline consists of:

- [`../../scripts/validate_terraform_entrypoint.sh`](../../scripts/validate_terraform_entrypoint.sh)

## Contract

Inputs may be provided with CLI flags:

- `--workdir`

The current defaults are:

- workdir: the repo's default dev Terraform entrypoint

The helper copies the repo's infra subtree to a temporary directory, removes generated `backend*.tf` files, then runs:

```bash
terraform fmt -check
terraform init -backend=false
terraform validate
```

Running in a temp copy avoids leaving Terraform working-directory artifacts or lockfiles in the checked-out repo when the check is used as part of baseline local smoke.

## Local Reproduction

Run from repo root:

```bash
bash scripts/validate_terraform_entrypoint.sh
```

Or point at a different environment entrypoint:

```bash
bash scripts/validate_terraform_entrypoint.sh --workdir infra/environments/staging
```

## Future Expansion

Later delivery-core extractions may add:

- Terraform module contract checks
- environment-specific policy checks
- baseline output expectations for downstream delivery wrappers
