#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if command -v uv >/dev/null 2>&1; then
  exec uv run --project api --extra dev python scripts/run_local_container_lane_smoke.py "$@"
fi

if [[ -x "${ROOT_DIR}/.venv312/bin/python" ]]; then
  export PYTHONPATH="api/src:packages/platform-api/src:packages/agent-runtime/src${PYTHONPATH:+:${PYTHONPATH}}"
  exec "${ROOT_DIR}/.venv312/bin/python" scripts/run_local_container_lane_smoke.py "$@"
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  export PYTHONPATH="api/src:packages/platform-api/src:packages/agent-runtime/src${PYTHONPATH:+:${PYTHONPATH}}"
  exec "${ROOT_DIR}/.venv/bin/python" scripts/run_local_container_lane_smoke.py "$@"
fi

echo "smoke_local_container.sh requires either 'uv' on PATH or a repo-local .venv312/.venv with API dev dependencies installed." >&2
exit 1
