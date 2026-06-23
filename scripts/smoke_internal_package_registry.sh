#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${ORCHA_NPM_REGISTRY_URL:-}" || -z "${ORCHA_PYPI_SIMPLE_INDEX_URL:-}" ]]; then
  echo "SKIP internal package registry smoke: set ORCHA_NPM_REGISTRY_URL and ORCHA_PYPI_SIMPLE_INDEX_URL to run live package-client checks."
  python3 "$repo_root/scripts/validate_internal_package_sources.py" --repo-root "$repo_root"
  exit 0
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/orcha-internal-registry-smoke.XXXXXX")"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

npm_auth_scope="${ORCHA_NPM_AUTH_SCOPE:-${ORCHA_NPM_REGISTRY_URL#http://}}"
npm_auth_scope="${npm_auth_scope#https://}"
npm_auth_scope="${npm_auth_scope%/}/"

render_template() {
  local template_path="$1"
  local output_path="$2"
  python3 - "$template_path" "$output_path" <<'PY'
from __future__ import annotations

import os
from pathlib import Path
import sys

template = Path(sys.argv[1]).read_text(encoding="utf-8")
replacements = {
    "__ORCHA_NPM_REGISTRY_URL__": os.environ["ORCHA_NPM_REGISTRY_URL"].rstrip("/") + "/",
    "__ORCHA_NPM_AUTH_SCOPE__": os.environ["ORCHA_NPM_AUTH_SCOPE_RENDERED"],
    "__ORCHA_NPM_TOKEN__": os.environ.get("ORCHA_NPM_TOKEN", ""),
    "__ORCHA_PYPI_SIMPLE_INDEX_URL__": os.environ["ORCHA_PYPI_SIMPLE_INDEX_URL"].rstrip("/") + "/",
}
for key, value in replacements.items():
    template = template.replace(key, value)
Path(sys.argv[2]).write_text(template, encoding="utf-8")
PY
}

export ORCHA_NPM_AUTH_SCOPE_RENDERED="$npm_auth_scope"
render_template "$repo_root/.orcha/package-registry/npmrc.template" "$tmp_dir/.npmrc"
render_template "$repo_root/.orcha/package-registry/pip.conf.template" "$tmp_dir/pip.conf"
render_template "$repo_root/.orcha/package-registry/uv.toml.template" "$tmp_dir/uv.toml"

python3 "$repo_root/scripts/validate_internal_package_sources.py" \
  --repo-root "$tmp_dir" \
  --expected-npm-registry "$ORCHA_NPM_REGISTRY_URL" \
  --expected-pypi-index "$ORCHA_PYPI_SIMPLE_INDEX_URL" \
  --skip-template-check

unset PIP_EXTRA_INDEX_URL UV_EXTRA_INDEX_URL
export PIP_CONFIG_FILE="$tmp_dir/pip.conf"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
export UV_INDEX_URL="${ORCHA_PYPI_SIMPLE_INDEX_URL%/}/"
export npm_config_userconfig="$tmp_dir/.npmrc"

if [[ -n "${ORCHA_INTERNAL_NPM_SMOKE_PACKAGE:-}" ]]; then
  npm view "$ORCHA_INTERNAL_NPM_SMOKE_PACKAGE" version --userconfig "$tmp_dir/.npmrc" >/dev/null
fi

if [[ -n "${ORCHA_INTERNAL_PYPI_SMOKE_PACKAGE:-}" ]]; then
  python3 -m pip download --no-deps --dest "$tmp_dir/python-downloads" "$ORCHA_INTERNAL_PYPI_SMOKE_PACKAGE" >/dev/null
fi

if [[ -n "${ORCHA_INTERNAL_NPM_NEGATIVE_PACKAGE:-}" ]]; then
  if npm view "$ORCHA_INTERNAL_NPM_NEGATIVE_PACKAGE" version --userconfig "$tmp_dir/.npmrc" >/dev/null 2>&1; then
    echo "FAIL expected npm package to be unavailable from the internal registry: $ORCHA_INTERNAL_NPM_NEGATIVE_PACKAGE" >&2
    exit 1
  fi
fi

if [[ -n "${ORCHA_INTERNAL_PYPI_NEGATIVE_PACKAGE:-}" ]]; then
  if python3 -m pip download --no-deps --dest "$tmp_dir/python-negative-downloads" "$ORCHA_INTERNAL_PYPI_NEGATIVE_PACKAGE" >/dev/null 2>&1; then
    echo "FAIL expected PyPI package to be unavailable from the internal registry: $ORCHA_INTERNAL_PYPI_NEGATIVE_PACKAGE" >&2
    exit 1
  fi
fi

echo "OK internal package registry smoke completed against internal package sources only."
