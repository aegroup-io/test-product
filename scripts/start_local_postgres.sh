#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_postgres_runtime.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"
agent_core_start_local_postgres
