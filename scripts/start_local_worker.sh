#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_DIR="${ROOT_DIR}/worker"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_python_runtime.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"

WORKER_MODULE="$(agent_core_product_factory_field "runtime_wrappers.worker_module" "agent_core_starter_worker")"
export AGENT_CORE_API_BASE_URL="${AGENT_CORE_API_BASE_URL:-${AGENT_CORE_LOCAL_API_URL:-http://127.0.0.1:8000}}"
export AGENT_CORE_LOCAL_JOB_ROOT="${AGENT_CORE_LOCAL_JOB_ROOT:-${AGENT_CORE_LOCAL_DEV_ROOT}/worker-jobs}"
mkdir -p "${AGENT_CORE_LOCAL_JOB_ROOT}"

cd "${WORKER_DIR}"
agent_core_record_local_service_pid worker
if command -v uv >/dev/null 2>&1; then
  exec uv run --extra dev python -m "${WORKER_MODULE}.devserver" --job-root "${AGENT_CORE_LOCAL_JOB_ROOT}"
fi

PYTHON_BIN="$(agent_core_ensure_repo_python "${ROOT_DIR}")"
agent_core_ensure_repo_python_modules "${PYTHON_BIN}" httpx pydantic -- \
  -e "${ROOT_DIR}/packages/platform-worker" \
  -e "${ROOT_DIR}/worker[dev]"
export PYTHONPATH="${ROOT_DIR}/worker/src:${ROOT_DIR}/packages/platform-worker/src${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PYTHON_BIN}" -m "${WORKER_MODULE}.devserver" --job-root "${AGENT_CORE_LOCAL_JOB_ROOT}"
