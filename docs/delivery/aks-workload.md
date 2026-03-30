# AKS Workload Deploy

This document is the canonical contract for the baseline Azure AKS workload deploy helper.

## Purpose

Use the AKS workload helper to apply one or more Kubernetes manifests, optionally sync a secret from an env file, and wait for rollout.

The current helper assumes the platform baseline documented in [`../architecture/platform-stack.md`](../architecture/platform-stack.md):

- Azure
- AKS
- `kubectl`-driven workload deployment

## Components

The current delivery baseline consists of:

- [`../../scripts/deploy_aks_workload.sh`](../../scripts/deploy_aks_workload.sh)

## Contract

Inputs may be provided with CLI flags:

- `--namespace`
- `--manifest` (repeatable)
- `--workload-name`
- `--rollout-kind`
- `--rollout-timeout`
- `--secret-name`
- `--secret-env-file`
- `--no-namespace-create`
- `--no-wait`
- `--dry-run`

The current defaults are:

- rollout kind: `deployment`
- rollout timeout: `300s`

When both `--secret-name` and `--secret-env-file` are provided, the helper performs the standard `kubectl create secret ... --dry-run=client -o yaml | kubectl apply -f -` pattern before applying manifests.

`--dry-run` prints the planned namespace, secret, apply, and rollout commands without calling `kubectl`. `--no-wait` skips rollout status checks, which is useful for jobs or repo-local validation runs.

## Local Reproduction

Dry-run an API-style workload deploy:

```bash
bash scripts/deploy_aks_workload.sh \
  --namespace product-dev \
  --manifest api/deploy/deployment.yaml \
  --manifest api/deploy/service.yaml \
  --workload-name product-api \
  --secret-name product-api-secrets \
  --secret-env-file api/.env.dev \
  --dry-run
```

Apply without waiting:

```bash
bash scripts/deploy_aks_workload.sh \
  --namespace product-dev \
  --manifest worker/deploy/deployment.yaml \
  --workload-name product-worker \
  --no-wait
```

## Future Expansion

Later delivery-core extractions may add:

- manifest templating or image substitution helpers
- baseline autoscaling helpers for HPA or KEDA
- APIM update wrappers that compose after successful AKS rollout
