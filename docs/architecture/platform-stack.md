# Platform Stack

This product baseline assumes a fixed delivery stack inherited from `agent-core`.

## Baseline Assumptions

The current platform stack is:

- Azure as the cloud platform
- Terraform for infrastructure definition and environment entrypoints
- AKS for backend service workloads
- Azure App Service for the primary web application
- APIM fronting public API traffic
- Azure Database for PostgreSQL as the default relational database baseline
- Azure Container Registry for container image publication

These are baseline platform assumptions for products seeded from `agent-core`, not optional repo-local conventions.

## What This Means For Product Repos

Product repos should:

- keep Azure, Terraform, Kubernetes, App Service, and APIM workflows aligned with the shared baseline
- build thin product-specific wrappers on top of baseline helpers when service names or manifests differ
- avoid re-inventing core delivery mechanics that the platform already manages centrally

Product repos may still add local deployment overlays, but those overlays should preserve the baseline stack contract unless the platform itself changes.
