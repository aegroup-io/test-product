# Delivery Docs

`docs/delivery/` is the canonical home for delivery-core workflows in a product repo that adopts the `agent-core` baseline.

Put docs here when they answer questions like:

- How do maintainers verify a deployed environment?
- What deployment or release checks should stay aligned across products?
- Which delivery workflows are baseline and which are product-specific overlays?

Current extracted docs:

- [`aks-workload.md`](aks-workload.md) for the baseline Azure AKS workload deploy helper contract.
- [`apim-sync.md`](apim-sync.md) for the baseline Azure API Management sync helper contract.
- [`app-service-zip.md`](app-service-zip.md) for the baseline Azure App Service zip packaging and deploy helper contract.
- [`container-image.md`](container-image.md) for the baseline container-image build/push helper contract.
- [`delivery-baseline-smoke.md`](delivery-baseline-smoke.md) for the managed repo-level delivery smoke composition contract.
- [`delivery-release-verification.md`](delivery-release-verification.md) for the managed repo-level release verification contract.
- [`remote-smoke.md`](remote-smoke.md) for the baseline remote post-deploy verification contract.
- [`terraform-backend.md`](terraform-backend.md) for the Azure Terraform backend bootstrap contract.
- [`terraform-entrypoint-validation.md`](terraform-entrypoint-validation.md) for the baseline local Terraform entrypoint validation contract.

Future delivery-core docs may cover:

- deployment bootstrap
- release promotion
- baseline Terraform or infra module conventions
- environment verification checklists

Keep product-topology specifics out of this folder unless they have been deliberately promoted into baseline delivery core.
