#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_postgres_runtime.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"

TIMEOUT_SECONDS="${AGENT_CORE_LOCAL_STOP_TIMEOUT_SECONDS:-10}"
STOP_POSTGRES=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apps-only)
      STOP_POSTGRES=0
      shift
      ;;
    --timeout)
      TIMEOUT_SECONDS="${2:-10}"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! "${TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] || [[ "${TIMEOUT_SECONDS}" -lt 1 ]]; then
  echo "Error: --timeout must be a positive integer" >&2
  exit 1
fi

SERVICES=(api web worker mcp docs)
failed=0

stop_service() {
  local service="$1"
  local pid_file pid waited=0

  pid_file="$(agent_core_local_service_pid_file "${service}")"
  if [[ ! -f "${pid_file}" ]]; then
    echo "[INFO] ${service}: no tracked process for namespace ${AGENT_CORE_WORKTREE_NAMESPACE}"
    return 0
  fi

  pid="$(<"${pid_file}")"
  if ! agent_core_local_service_pid_matches "${service}" "${pid}"; then
    if ! agent_core_pid_is_running "${pid}"; then
      echo "[INFO] ${service}: removing stale pid file ${pid_file}"
      agent_core_clear_local_service_pid "${service}"
      return 0
    fi
    echo "[WARN] ${service}: pid file ${pid_file} does not match the expected process; leaving it untouched"
    failed=1
    return 0
  fi

  echo "[INFO] ${service}: stopping pid ${pid}"
  kill "${pid}" >/dev/null 2>&1 || true
  while agent_core_pid_is_running "${pid}"; do
    if [[ "${waited}" -ge "${TIMEOUT_SECONDS}" ]]; then
      echo "[WARN] ${service}: process ${pid} did not exit within ${TIMEOUT_SECONDS}s"
      failed=1
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done

  agent_core_clear_local_service_pid "${service}"
  echo "[OK] ${service}: stopped"
}

echo "Stopping namespace ${AGENT_CORE_WORKTREE_NAMESPACE} (dev root: ${AGENT_CORE_LOCAL_DEV_ROOT})"
for service in "${SERVICES[@]}"; do
  stop_service "${service}"
done

if [[ "${STOP_POSTGRES}" -eq 1 ]]; then
  if ! agent_core_stop_local_postgres; then
    failed=1
  fi
fi

if [[ "${failed}" -ne 0 ]]; then
  echo "Local stop completed with warnings for namespace ${AGENT_CORE_WORKTREE_NAMESPACE}."
  exit 1
fi

echo "Local stop completed for namespace ${AGENT_CORE_WORKTREE_NAMESPACE}."
