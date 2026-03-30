# Container Image

This document is the canonical contract for the baseline container-image build and push helper.

## Purpose

Use the container-image helper to provide one generic build/push script that product repos can adopt before they need product-specific deploy wrappers.

The baseline helper focuses on:

- one explicit image reference
- one Dockerfile path
- one build context
- optional Azure Container Registry login when the target registry ends with `.azurecr.io`
- a dry-run mode so the contract can be validated without Docker auth

## Components

The current delivery baseline consists of:

- [`../../scripts/build_push_container_image.sh`](../../scripts/build_push_container_image.sh)

## Contract

Inputs may be provided with CLI flags:

- `--image`
- `--dockerfile`
- `--context`
- `--platform`
- `--builder-name`
- `--no-login`
- `--no-push`
- `--dry-run`

The current defaults are:

- context: `.`
- platform: linux/amd64
- builder name: `agentcore-builder`

Use `--platform local` or `--platform native` to fall back to a plain local Docker build instead of `buildx`.

If the image registry ends with `.azurecr.io`, the helper will run `az acr login` before a push unless `--no-login` or `--no-push` is used.

## Local Reproduction

Run locally from repo root:

```bash
bash scripts/build_push_container_image.sh \
  --image example.azurecr.io/team/app:dev \
  --dockerfile ./Dockerfile \
  --context . \
  --dry-run
```

The dry-run mode prints the exact commands that would execute, which makes it safe for bootstrap verification and repo-local smoke tests.

For local coding-lane runtime validation, this helper is also used by
[`../../scripts/smoke_local_container.sh`](../../scripts/smoke_local_container.sh) to build the
`orcha/coding-lane-smoke:*` image before executing the runner contract inside the provider-managed
Docker lane container.

## Future Expansion

Later delivery-core extractions may add:

- registry-auth adapters beyond Azure Container Registry
- repo-local workflow wrappers around the helper
- release tagging conventions
- provenance or artifact publication hooks
