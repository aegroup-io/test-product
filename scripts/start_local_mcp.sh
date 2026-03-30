#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_DIR="${ROOT_DIR}/mcp"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_python_runtime.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"

MCP_MODULE="$(agent_core_product_factory_field "runtime_wrappers.mcp_module" "agent_core_starter_mcp")"
export AGENT_CORE_API_BASE_URL="${AGENT_CORE_API_BASE_URL:-${AGENT_CORE_LOCAL_API_URL:-http://127.0.0.1:8000}}"

cd "${MCP_DIR}"
agent_core_record_local_service_pid mcp
if command -v uv >/dev/null 2>&1; then
  exec uv run --extra dev uvicorn "${MCP_MODULE}.main:app" \
    --reload \
    --host "${AGENT_CORE_LOCAL_MCP_HOST:-127.0.0.1}" \
    --port "${AGENT_CORE_LOCAL_MCP_PORT:-8081}"
fi

PYTHON_BIN="$(agent_core_ensure_repo_python "${ROOT_DIR}")"
agent_core_ensure_repo_python_modules "${PYTHON_BIN}" fastapi uvicorn -- \
  -e "${ROOT_DIR}/mcp[dev]"
export PYTHONPATH="${ROOT_DIR}/mcp/src${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PYTHON_BIN}" -m uvicorn "${MCP_MODULE}.main:app" \
  --reload \
  --host "${AGENT_CORE_LOCAL_MCP_HOST:-127.0.0.1}" \
  --port "${AGENT_CORE_LOCAL_MCP_PORT:-8081}"
