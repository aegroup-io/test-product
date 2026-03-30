#!/usr/bin/env bash
set -euo pipefail

WORKDIR="infra/environments/dev"

usage() {
  cat <<'EOF'
Usage: validate_terraform_entrypoint.sh [options]

Validate a repo-local Terraform entrypoint in a temporary copy of infra/.

Options:
  --workdir <path>   Terraform workdir relative to repo root (default: infra/environments/dev)
  -h, --help         Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workdir)
      [[ $# -lt 2 ]] && { echo "Error: --workdir requires a value." >&2; usage; exit 2; }
      WORKDIR="$2"
      shift 2
      ;;
    --workdir=*)
      WORKDIR="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

case "${WORKDIR}" in
  infra/*) ;;
  *)
    echo "Error: --workdir must live under infra/." >&2
    exit 2
    ;;
esac

if ! command -v terraform >/dev/null 2>&1; then
  echo "Terraform is required to validate the repo-local entrypoint." >&2
  exit 1
fi

REPO_ROOT="$(pwd)"
SOURCE_INFRA_ROOT="${REPO_ROOT}/infra"
SOURCE_WORKDIR="${REPO_ROOT}/${WORKDIR}"

if [[ ! -d "${SOURCE_INFRA_ROOT}" ]]; then
  echo "Error: missing infra/ at repo root." >&2
  exit 1
fi

if [[ ! -d "${SOURCE_WORKDIR}" ]]; then
  echo "Error: Terraform workdir not found: ${WORKDIR}" >&2
  exit 1
fi

TEMP_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "${TEMP_ROOT}"
}
trap cleanup EXIT

cp -R "${SOURCE_INFRA_ROOT}" "${TEMP_ROOT}/infra"
find "${TEMP_ROOT}/${WORKDIR}" -maxdepth 1 -type f -name 'backend*.tf' -delete

terraform -chdir="${TEMP_ROOT}/${WORKDIR}" fmt -check -diff -no-color
terraform -chdir="${TEMP_ROOT}/${WORKDIR}" init -backend=false -input=false -no-color >/dev/null
terraform -chdir="${TEMP_ROOT}/${WORKDIR}" validate -no-color

echo "OK terraform entrypoint validation passed (${WORKDIR})."
