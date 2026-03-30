#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="${ROOT_DIR}/docs"
VENV_DIR="${ROOT_DIR}/.venv-docs"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/local_namespace.sh"
agent_core_apply_local_namespace_contract "${ROOT_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"
python3 -m pip install -r "${DOCS_DIR}/requirements-docs.txt"

cd "${ROOT_DIR}"
agent_core_record_local_service_pid docs
exec mkdocs serve -f mkdocs.yml --dev-addr "${AGENT_CORE_DOCS_HOST:-127.0.0.1}:${AGENT_CORE_DOCS_PORT:-9100}"
