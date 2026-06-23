#!/usr/bin/env bash
set -euo pipefail

agent_core_python_meets_min_version() {
  local python_bin="$1"

  "${python_bin}" - <<'PY' >/dev/null
import sys

raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

agent_core_find_bootstrap_python() {
  local candidate
  local resolved

  for candidate in python3.13 python3.12 python3.11 python3; do
    if ! resolved="$(command -v "${candidate}" 2>/dev/null)"; then
      continue
    fi
    if agent_core_python_meets_min_version "${resolved}"; then
      printf '%s\n' "${resolved}"
      return 0
    fi
  done

  return 1
}

agent_core_repo_python_bin() {
  local root_dir="$1"

  if [[ -x "${root_dir}/.venv312/bin/python" ]]; then
    printf '%s\n' "${root_dir}/.venv312/bin/python"
    return 0
  fi

  if [[ -x "${root_dir}/.venv/bin/python" ]]; then
    printf '%s\n' "${root_dir}/.venv/bin/python"
    return 0
  fi

  return 1
}

agent_core_ensure_repo_python() {
  local root_dir="$1"

  local python_bin
  if python_bin="$(agent_core_repo_python_bin "${root_dir}")"; then
    printf '%s\n' "${python_bin}"
    return 0
  fi

  if ! python_bin="$(agent_core_find_bootstrap_python)"; then
    echo "No repo-local .venv312/.venv exists and no Python 3.11+ interpreter is on PATH. Install Python 3.11+ or uv." >&2
    return 1
  fi

  local venv_dir="${root_dir}/.venv"
  echo "Bootstrapping repo-local virtualenv at ${venv_dir}" >&2
  "${python_bin}" -m venv "${venv_dir}"
  "${venv_dir}/bin/python" -m pip install --upgrade pip setuptools wheel >&2
  printf '%s\n' "${venv_dir}/bin/python"
}

agent_core_ensure_repo_python_modules() {
  local python_bin="$1"
  shift

  local -a module_names=()
  while (($#)); do
    if [[ "$1" == "--" ]]; then
      shift
      break
    fi
    module_names+=("$1")
    shift
  done

  if ((${#module_names[@]} > 0)); then
    if "${python_bin}" - "${module_names[@]}" <<'PY' >/dev/null
import importlib.util
import sys

missing = [name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
    then
      return 0
    fi
  fi

  if (($# == 0)); then
    return 0
  fi

  echo "Installing missing Python dependencies into ${python_bin%/bin/python}" >&2
  "${python_bin}" -m pip install "$@" >&2
}
