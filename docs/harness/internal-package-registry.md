# Internal Package Registry

This document defines the product harness contract for installing npm and PyPI
packages only from the Orcha-managed internal Pulp registry.

## Managed Templates

The managed package-client templates live in:

- [.orcha/package-registry/npmrc.template](../../.orcha/package-registry/npmrc.template)
- [.orcha/package-registry/pip.conf.template](../../.orcha/package-registry/pip.conf.template)
- [.orcha/package-registry/uv.toml.template](../../.orcha/package-registry/uv.toml.template)
- [.orcha/package-registry/package-registry.env.example](../../.orcha/package-registry/package-registry.env.example)

The templates are rendered by
[`../../scripts/smoke_internal_package_registry.sh`](../../scripts/smoke_internal_package_registry.sh)
from environment-owned registry URLs and read-only credentials. Do not commit
rendered files containing credentials.

## Required Package Sources

Product npm installs must use the internal Pulp npm endpoint as the default
registry, or as an explicitly approved scope registry when a repo is split by
scope. The baseline endpoint shape is:

```text
https://pulp.example.com/pulp/content/default/orcha/npm/
```

Product Python installs must use the internal Pulp PyPI simple index as the
primary index for both `pip` and `uv`:

```text
https://pulp.example.com/pypi/orcha-pypi/simple/
```

Do not use `extra-index-url`, `PIP_EXTRA_INDEX_URL`, or `UV_EXTRA_INDEX_URL`.
Public fallback means the package was not approved and materialized through
Orcha, so the install must fail closed.

## Validation

Run the managed validation locally:

```bash
python3 scripts/validate_internal_package_sources.py
```

Include lockfiles when validating a migrated product repo:

```bash
python3 scripts/validate_internal_package_sources.py --include-lockfiles
```

The validator fails on direct public install sources such as npmjs and PyPI
client registries, and reports lockfile public artifact URLs as advisory
diagnostics until the product lockfile has been regenerated against Pulp.

## Smoke

Run the internal-only smoke after the Pulp read endpoints are configured:

```bash
export ORCHA_NPM_REGISTRY_URL=https://pulp.example.com/pulp/content/default/orcha/npm/
export ORCHA_NPM_AUTH_SCOPE=pulp.example.com/pulp/content/default/orcha/npm/
export ORCHA_NPM_TOKEN="$PULP_READ_TOKEN"
export ORCHA_PYPI_SIMPLE_INDEX_URL=https://pulp.example.com/pypi/orcha-pypi/simple/
export ORCHA_INTERNAL_NPM_SMOKE_PACKAGE='@scope/materialized-package@1.0.0'
export ORCHA_INTERNAL_NPM_NEGATIVE_PACKAGE='@scope/not-materialized-package@0.0.1'
export ORCHA_INTERNAL_PYPI_SMOKE_PACKAGE='materialized-package==1.0.0'
export ORCHA_INTERNAL_PYPI_NEGATIVE_PACKAGE='not-materialized-package==0.0.1'
bash scripts/smoke_internal_package_registry.sh
```

The positive packages should already have approved materialization records in
Orcha. The negative packages must not be materialized; the smoke fails if a
negative package can be installed from the internal registry.
