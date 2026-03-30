#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="${ROOT_DIR}/api"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_python_runtime.sh"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_postgres_runtime.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"
agent_core_apply_local_postgres_contract

API_MODULE="$(agent_core_product_factory_field "runtime_wrappers.api_module" "agent_core_starter_api")"
export AGENT_CORE_AUTH_DISABLED="${AGENT_CORE_AUTH_DISABLED:-1}"
export AGENT_CORE_ORCHESTRATION_LOOP_ENABLED="${AGENT_CORE_ORCHESTRATION_LOOP_ENABLED:-1}"
export AGENT_CORE_DATABASE_URL="${AGENT_CORE_DATABASE_URL:-${AGENT_CORE_LOCAL_DATABASE_URL}}"

if [[ "${AGENT_CORE_DATABASE_URL}" == "${AGENT_CORE_LOCAL_DATABASE_URL}" ]]; then
  agent_core_start_local_postgres
fi

cd "${API_DIR}"
agent_core_record_local_service_pid api
if command -v uv >/dev/null 2>&1; then
  exec uv run --extra dev uvicorn "${API_MODULE}.main:app" \
    --reload \
    --host "${AGENT_CORE_LOCAL_API_HOST:-127.0.0.1}" \
    --port "${AGENT_CORE_LOCAL_API_PORT:-8000}"
fi

PYTHON_BIN="$(agent_core_ensure_repo_python "${ROOT_DIR}")"
agent_core_ensure_repo_python_modules "${PYTHON_BIN}" \
  alembic cryptography fastapi httpx jose psycopg sqlalchemy uvicorn yaml -- \
  -e "${ROOT_DIR}/packages/platform-api" \
  -e "${ROOT_DIR}/api[dev]"
export PYTHONPATH="${ROOT_DIR}/api/src:${ROOT_DIR}/packages/platform-api/src${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PYTHON_BIN}" -m uvicorn "${API_MODULE}.main:app" \
  --reload \
  --host "${AGENT_CORE_LOCAL_API_HOST:-127.0.0.1}" \
  --port "${AGENT_CORE_LOCAL_API_PORT:-8000}"
