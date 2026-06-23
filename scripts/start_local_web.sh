#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_DIR="${ROOT_DIR}/web"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"

export VITE_API_BASE_URL="${VITE_API_BASE_URL:-${AGENT_CORE_LOCAL_API_URL:-http://127.0.0.1:8000}}"
export VITE_ENTRA_REDIRECT_URI="${VITE_ENTRA_REDIRECT_URI:-${AGENT_CORE_LOCAL_WEB_URL:-http://127.0.0.1:5173}}"
export VITE_AUTH_DISABLED="${VITE_AUTH_DISABLED:-1}"

cd "${WEB_DIR}"
npm install
agent_core_record_local_service_pid web
exec npm run dev -- --strictPort --host "${AGENT_CORE_LOCAL_WEB_HOST:-127.0.0.1}" --port "${AGENT_CORE_LOCAL_WEB_PORT:-5173}"
