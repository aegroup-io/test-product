#!/usr/bin/env bash
set -euo pipefail

python3 scripts/validate_repo_harness_assets.py
python3 scripts/validate_internal_package_sources.py
bash scripts/smoke_internal_package_registry.sh
bash scripts/validate_terraform_entrypoint.sh
python3 scripts/run_merge_readiness_audit.py --self-test --output-dir artifacts/merge-readiness-self-test
python3 -m compileall scripts
