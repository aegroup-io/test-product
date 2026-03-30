#!/usr/bin/env bash

agent_core_apply_local_namespace_contract() {
  local root_dir="$1"
  local bootstrap="${root_dir}/scripts/bootstrap_local_namespace.py"

  if [[ "${AGENT_CORE_DISABLE_LOCAL_NAMESPACE_BOOTSTRAP:-0}" == "1" ]]; then
    export AGENT_CORE_REPO_ROOT="${root_dir}"
    return 0
  fi

  if [[ ! -x "${bootstrap}" ]]; then
    echo "Missing bootstrap script: ${bootstrap}" >&2
    return 1
  fi

  export AGENT_CORE_REPO_ROOT="${root_dir}"
  export AGENT_CORE_WORKTREE_PATH="${AGENT_CORE_WORKTREE_PATH:-${root_dir}}"
  eval "$("${bootstrap}" --worktree-path "${AGENT_CORE_WORKTREE_PATH}" --format shell)"
}

agent_core_product_factory_field() {
  local field_path="$1"
  local fallback="${2:-}"
  local factory_path="${AGENT_CORE_REPO_ROOT:-$(pwd)}/.agent-core/product-factory.json"
  python3 - "${factory_path}" "${field_path}" "${fallback}" <<'PY'
import json
import sys
from pathlib import Path

factory_path = Path(sys.argv[1])
field_path = sys.argv[2]
fallback = sys.argv[3]

if not factory_path.exists():
    print(fallback)
    raise SystemExit(0)

payload = json.loads(factory_path.read_text(encoding="utf-8"))
value = payload
for part in field_path.split("."):
    if isinstance(value, dict) and part in value:
        value = value[part]
    else:
        print(fallback)
        raise SystemExit(0)

if isinstance(value, str) and value:
    print(value)
else:
    print(fallback)
PY
}

agent_core_local_pid_dir() {
  printf '%s\n' "${AGENT_CORE_LOCAL_PID_ROOT:-${AGENT_CORE_LOCAL_DEV_ROOT}/pids}"
}

agent_core_local_service_pid_file() {
  local service="$1"
  printf '%s/%s.pid\n' "$(agent_core_local_pid_dir)" "${service}"
}

agent_core_record_local_service_pid() {
  local service="$1"
  local pid_dir
  pid_dir="$(agent_core_local_pid_dir)"
  mkdir -p "${pid_dir}"
  printf '%s\n' "$$" > "$(agent_core_local_service_pid_file "${service}")"
}

agent_core_pid_is_running() {
  local pid="$1"
  local stat

  if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    return 1
  fi

  stat="$(ps -o stat= -p "${pid}" 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -z "${stat}" || "${stat}" == Z* ]]; then
    return 1
  fi

  return 0
}

agent_core_read_local_service_pid() {
  local service="$1"
  local pid_file
  pid_file="$(agent_core_local_service_pid_file "${service}")"
  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi
  cat "${pid_file}"
}

agent_core_expected_local_service_signature() {
  local service="$1"
  case "${service}" in
    api)
      local api_module
      api_module="$(agent_core_product_factory_field "runtime_wrappers.api_module" "agent_core_starter_api")"
      printf '%s\n' "${api_module}.main:app"
      ;;
    web)
      printf '%s\n' "npm run dev"
      ;;
    worker)
      local worker_module
      worker_module="$(agent_core_product_factory_field "runtime_wrappers.worker_module" "agent_core_starter_worker")"
      printf '%s\n' "${worker_module}.devserver"
      ;;
    mcp)
      local mcp_module
      mcp_module="$(agent_core_product_factory_field "runtime_wrappers.mcp_module" "agent_core_starter_mcp")"
      printf '%s\n' "${mcp_module}.main:app"
      ;;
    docs)
      printf '%s\n' "mkdocs serve -f mkdocs.yml"
      ;;
    *)
      return 1
      ;;
  esac
}

agent_core_local_service_pid_matches() {
  local service="$1"
  local pid="$2"
  local signature command

  if ! agent_core_pid_is_running "${pid}"; then
    return 1
  fi

  signature="$(agent_core_expected_local_service_signature "${service}" || true)"
  if [[ -z "${signature}" ]]; then
    return 1
  fi

  command="$(ps -o command= -p "${pid}" 2>/dev/null || true)"
  [[ -n "${command}" && "${command}" == *"${signature}"* ]]
}

agent_core_clear_local_service_pid() {
  local service="$1"
  rm -f "$(agent_core_local_service_pid_file "${service}")"
}
