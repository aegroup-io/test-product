# Terraform Backend

This document is the canonical contract for the baseline Azure Terraform backend bootstrap helper.

## Purpose

Use the Terraform backend helper to provision or standardize the Azure storage backend that product repos use for Terraform state.

The current helper assumes the platform baseline documented in [`../architecture/platform-stack.md`](../architecture/platform-stack.md):

- Azure
- Terraform
- Azure Storage for remote state

## Components

The current delivery baseline consists of:

- [`../../scripts/bootstrap_terraform_backend.sh`](../../scripts/bootstrap_terraform_backend.sh)
- [`terraform-entrypoint-validation.md`](terraform-entrypoint-validation.md) for validating the repo-local Terraform entrypoint before or after backend bootstrap

## Contract

Inputs may be provided with CLI flags:

- `--env`
- `--location`
- `--resource-group`
- `--storage-account`
- `--container`
- `--state-key`
- `--workdir`
- `--backend-config`
- `--subscription-id`
- `--use-sas`
- `--sas-token`
- `--sas-auto`
- `--overwrite-backend`
- `--render-only`
- `--dry-run`

The current defaults are:

- environment: `dev`
- location: `eastus2`
- container: `tfstate`
- state key: `<env>.terraform.tfstate`
- workdir: `infra/environments/<env>`
- backend config path: `<workdir>/backend.tf`

`--render-only` writes backend config without calling Azure CLI or Terraform. `--dry-run` prints the planned commands without executing them.

## Local Reproduction

Render only:

```bash
bash scripts/bootstrap_terraform_backend.sh \
  --resource-group product-dev-tfstate \
  --storage-account productdevtfstate \
  --render-only
```

Dry-run:

```bash
bash scripts/bootstrap_terraform_backend.sh \
  --resource-group product-dev-tfstate \
  --storage-account productdevtfstate \
  --dry-run
```

## Future Expansion

Later delivery-core extractions may add:

- repo-level wrappers around this helper
- environment-specific naming conventions
- Terraform module or environment scaffolding
- state-health verification or drift checks
