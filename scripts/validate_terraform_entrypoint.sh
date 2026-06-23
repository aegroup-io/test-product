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

REPO_ROOT="$(pwd)"
SOURCE_INFRA_ROOT="${REPO_ROOT}/infra"
SOURCE_WORKDIR="${REPO_ROOT}/${WORKDIR}"

if [[ ! -d "${SOURCE_INFRA_ROOT}" ]]; then
  echo "SKIP terraform entrypoint validation: missing infra/ at repo root."
  exit 0
fi

if ! command -v terraform >/dev/null 2>&1; then
  echo "Terraform is required to validate the repo-local entrypoint." >&2
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

if [[ "${WORKDIR}" == "infra/environments/dev" ]]; then
  dev_variables="${SOURCE_WORKDIR}/variables.tf"
  dev_tfvars_example="${SOURCE_WORKDIR}/terraform.tfvars.example"

  terraform_variable_default() {
    local variable_name="$1"
    local file_path="$2"
    awk -v variable_name="${variable_name}" '
      $1 == "variable" && $2 == "\"" variable_name "\"" { inside = 1 }
      inside && $1 == "default" {
        value = $3
        gsub(/"/, "", value)
        print value
        exit
      }
      inside && $1 == "}" { inside = 0 }
    ' "${file_path}"
  }

  require_variable_default() {
    local variable_name="$1"
    local expected_value="$2"
    local actual_value
    actual_value="$(terraform_variable_default "${variable_name}" "${dev_variables}")"
    if [[ "${actual_value}" != "${expected_value}" ]]; then
      echo "Error: dev ${variable_name} default must be ${expected_value}; found ${actual_value:-<missing>}." >&2
      exit 1
    fi
  }

  require_tfvars_example_value() {
    local variable_name="$1"
    local expected_value="$2"
    if ! grep -Eq "^${variable_name}[[:space:]]*=[[:space:]]*\"${expected_value}\"" "${dev_tfvars_example}"; then
      echo "Error: dev terraform.tfvars.example must set ${variable_name} = \"${expected_value}\"." >&2
      exit 1
    fi
  }

  require_variable_default "app_service_sku_name" "B1"
  require_variable_default "postgres_sku_name" "B_Standard_B1ms"
  require_tfvars_example_value "app_service_sku_name" "B1"
  require_tfvars_example_value "postgres_sku_name" "B_Standard_B1ms"
fi

echo "OK terraform entrypoint validation passed (${WORKDIR})."
