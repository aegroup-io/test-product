# APIM Sync

This document is the canonical contract for the baseline Azure API Management sync helper.

## Purpose

Use the APIM sync helper to import or refresh an APIM API from an OpenAPI document and point APIM at the current backend service URL.

The current helper assumes the platform baseline documented in [`../architecture/platform-stack.md`](../architecture/platform-stack.md):

- Azure
- APIM
- AKS-backed API services or an equivalent backend service URL

## Components

The current delivery baseline consists of:

- [`../../scripts/sync_apim_api.sh`](../../scripts/sync_apim_api.sh)

## Contract

Inputs may be provided with CLI flags:

- `--resource-group`
- `--apim`
- `--api-id`
- `--api-path`
- `--openapi-path`
- `--service-url`
- `--service-name`
- `--namespace`
- `--aks-rg`
- `--aks-name`
- `--service-scheme`
- `--dry-run`

The current defaults are:

- API path: empty string
- service scheme: `http`

Provide `--service-url` when the backend URL is already known. Otherwise, provide `--service-name` and `--namespace` so the helper can resolve a LoadBalancer address from AKS, optionally refreshing credentials first with `--aks-rg` and `--aks-name`.

`--dry-run` prints the APIM discovery and sync commands without calling Azure CLI or `kubectl`.

## Local Reproduction

Dry-run with a direct backend URL:

```bash
bash scripts/sync_apim_api.sh \
  --resource-group product-dev \
  --apim product-dev-apim \
  --api-id product-api \
  --api-path "" \
  --openapi-path infra/openapi/product.openapi.json \
  --service-url http://product-api.internal \
  --dry-run
```

Dry-run with AKS service resolution:

```bash
bash scripts/sync_apim_api.sh \
  --resource-group product-dev \
  --apim product-dev-apim \
  --api-id product-api \
  --openapi-path infra/openapi/product.openapi.json \
  --service-name product-api \
  --namespace product-dev \
  --aks-rg product-dev-rg \
  --aks-name product-dev-aks \
  --dry-run
```

## Future Expansion

Later delivery-core extractions may add:

- repo-local wrappers that generate OpenAPI documents before sync
- policy or release helpers for APIM revisions
- APIM smoke checks that compose after sync
