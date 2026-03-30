# App Service Zip Deploy

This document is the canonical contract for the baseline Azure App Service zip packaging and deploy helper.

## Purpose

Use the App Service zip helper to package a built web or docs artifact and optionally deploy it to Azure App Service.

The current helper assumes the platform baseline documented in [`../architecture/platform-stack.md`](../architecture/platform-stack.md):

- Azure
- App Service
- zip-based application package deployment

## Components

The current delivery baseline consists of:

- [`../../scripts/deploy_app_service_zip.sh`](../../scripts/deploy_app_service_zip.sh)

## Contract

Inputs may be provided with CLI flags:

- `--source-dir`
- `--include-file` (repeatable)
- `--zip`
- `--staging-dir`
- `--resource-group`
- `--app-name`
- `--hostname`
- `--no-deploy`
- `--no-wait`
- `--dry-run`

The current defaults are:

- zip path: `/tmp/app-service-package.zip`
- staging dir: `/tmp/app-service-package`

Use `--include-file` for runtime entrypoints such as `server.js` that must live at the zip root alongside the built asset directory.

`--no-deploy` packages the artifact locally without calling Azure CLI. `--dry-run` prints the planned copy, zip, and deploy commands without executing them.

## Local Reproduction

Package only:

```bash
bash scripts/deploy_app_service_zip.sh \
  --source-dir web/dist \
  --include-file web/server.js \
  --no-deploy
```

Dry-run:

```bash
bash scripts/deploy_app_service_zip.sh \
  --source-dir web/dist \
  --include-file web/server.js \
  --resource-group product-dev \
  --app-name product-dev-web \
  --dry-run
```

## App Service Settings

Product repos should still ensure App Service settings match the packaged runtime. For the current web-server pattern, that normally includes:

- `WEBSITES_PORT=8080`

## Future Expansion

Later delivery-core extractions may add:

- product-specific wrappers for web and docs deployment
- environment-specific hostname conventions
- deployment artifact metadata or release notes
