#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-dev}"
LOCATION="${LOCATION:-eastus2}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-}"
CONTAINER_NAME="${CONTAINER_NAME:-tfstate}"
STATE_KEY="${STATE_KEY:-}"
WORKDIR="${WORKDIR:-}"
BACKEND_CONFIG="${BACKEND_CONFIG:-}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZ_SUBSCRIPTION_ID:-}}"
USE_SAS="${USE_SAS:-false}"
SAS_TOKEN="${SAS_TOKEN:-}"
SAS_EXPIRY="${SAS_EXPIRY:-}"
SAS_AUTO="${SAS_AUTO:-false}"
OVERWRITE_BACKEND=0
RENDER_ONLY=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: bootstrap_terraform_backend.sh [options]

Bootstrap an Azure-backed Terraform state backend for a product repo.

Options:
  --env <name>              Environment suffix (default: dev)
  --location <name>         Azure location (default: eastus2)
  --resource-group <name>   Resource group for the Terraform backend
  --storage-account <name>  Storage account for the Terraform backend
  --container <name>        Blob container name (default: tfstate)
  --state-key <name>        State key (default: <env>.terraform.tfstate)
  --workdir <path>          Terraform workdir (default: infra/environments/<env>)
  --backend-config <path>   Backend config path (default: <workdir>/backend.tf)
  --subscription-id <id>    Azure subscription ID (default: AZ_SUBSCRIPTION_ID or active az account)
  --use-sas                 Write backend config with a SAS token
  --sas-token <token>       Explicit SAS token to write
  --sas-expiry <timestamp>  Expiry used when generating SAS automatically
  --sas-auto                Generate a SAS token automatically
  --overwrite-backend       Overwrite an existing backend config
  --render-only             Only write the backend config; skip Azure provisioning and terraform init
  --dry-run                 Print planned commands without executing them
  -h, --help                Show this help text
EOF
}

run_or_print() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'DRY-RUN '
    printf '%q ' "$@"
    printf '\n'
    return
  fi
  "$@"
}

require_command() {
  local command_name="$1"
  local hint="$2"
  if [[ "${DRY_RUN}" == "1" || "${RENDER_ONLY}" == "1" ]]; then
    return
  fi
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${hint}" >&2
    exit 1
  fi
}

write_backend_config() {
  local target_path="$1"
  mkdir -p "$(dirname "${target_path}")"
  if [[ "${USE_SAS}" == "true" ]]; then
    local token="${SAS_TOKEN#\?}"
    if [[ -z "${token}" ]]; then
      token="__REPLACE_WITH_SAS_TOKEN__"
    fi
    cat > "${target_path}" <<EOF
terraform {
  backend "azurerm" {
    resource_group_name  = "${RESOURCE_GROUP}"
    storage_account_name = "${STORAGE_ACCOUNT}"
    container_name       = "${CONTAINER_NAME}"
    key                  = "${STATE_KEY}"
    sas_token            = "${token}"
  }
}
EOF
    return
  fi

  cat > "${target_path}" <<EOF
terraform {
  backend "azurerm" {
    resource_group_name  = "${RESOURCE_GROUP}"
    storage_account_name = "${STORAGE_ACCOUNT}"
    container_name       = "${CONTAINER_NAME}"
    key                  = "${STATE_KEY}"
    use_azuread_auth     = true
  }
}
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      [[ $# -lt 2 ]] && { echo "Error: --env requires a value." >&2; usage; exit 2; }
      ENVIRONMENT="$2"
      shift 2
      ;;
    --env=*)
      ENVIRONMENT="${1#*=}"
      shift
      ;;
    --location)
      [[ $# -lt 2 ]] && { echo "Error: --location requires a value." >&2; usage; exit 2; }
      LOCATION="$2"
      shift 2
      ;;
    --location=*)
      LOCATION="${1#*=}"
      shift
      ;;
    --resource-group)
      [[ $# -lt 2 ]] && { echo "Error: --resource-group requires a value." >&2; usage; exit 2; }
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --resource-group=*)
      RESOURCE_GROUP="${1#*=}"
      shift
      ;;
    --storage-account)
      [[ $# -lt 2 ]] && { echo "Error: --storage-account requires a value." >&2; usage; exit 2; }
      STORAGE_ACCOUNT="$2"
      shift 2
      ;;
    --storage-account=*)
      STORAGE_ACCOUNT="${1#*=}"
      shift
      ;;
    --container)
      [[ $# -lt 2 ]] && { echo "Error: --container requires a value." >&2; usage; exit 2; }
      CONTAINER_NAME="$2"
      shift 2
      ;;
    --container=*)
      CONTAINER_NAME="${1#*=}"
      shift
      ;;
    --state-key)
      [[ $# -lt 2 ]] && { echo "Error: --state-key requires a value." >&2; usage; exit 2; }
      STATE_KEY="$2"
      shift 2
      ;;
    --state-key=*)
      STATE_KEY="${1#*=}"
      shift
      ;;
    --workdir)
      [[ $# -lt 2 ]] && { echo "Error: --workdir requires a value." >&2; usage; exit 2; }
      WORKDIR="$2"
      shift 2
      ;;
    --workdir=*)
      WORKDIR="${1#*=}"
      shift
      ;;
    --backend-config)
      [[ $# -lt 2 ]] && { echo "Error: --backend-config requires a value." >&2; usage; exit 2; }
      BACKEND_CONFIG="$2"
      shift 2
      ;;
    --backend-config=*)
      BACKEND_CONFIG="${1#*=}"
      shift
      ;;
    --subscription-id)
      [[ $# -lt 2 ]] && { echo "Error: --subscription-id requires a value." >&2; usage; exit 2; }
      SUBSCRIPTION_ID="$2"
      shift 2
      ;;
    --subscription-id=*)
      SUBSCRIPTION_ID="${1#*=}"
      shift
      ;;
    --use-sas)
      USE_SAS="true"
      shift
      ;;
    --sas-token)
      [[ $# -lt 2 ]] && { echo "Error: --sas-token requires a value." >&2; usage; exit 2; }
      SAS_TOKEN="$2"
      shift 2
      ;;
    --sas-token=*)
      SAS_TOKEN="${1#*=}"
      shift
      ;;
    --sas-expiry)
      [[ $# -lt 2 ]] && { echo "Error: --sas-expiry requires a value." >&2; usage; exit 2; }
      SAS_EXPIRY="$2"
      shift 2
      ;;
    --sas-expiry=*)
      SAS_EXPIRY="${1#*=}"
      shift
      ;;
    --sas-auto)
      SAS_AUTO="true"
      USE_SAS="true"
      shift
      ;;
    --overwrite-backend)
      OVERWRITE_BACKEND=1
      shift
      ;;
    --render-only)
      RENDER_ONLY=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
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

STATE_KEY="${STATE_KEY:-${ENVIRONMENT}.terraform.tfstate}"
WORKDIR="${WORKDIR:-infra/environments/${ENVIRONMENT}}"
BACKEND_CONFIG="${BACKEND_CONFIG:-${WORKDIR}/backend.tf}"

if [[ -z "${RESOURCE_GROUP}" ]]; then
  echo "Error: --resource-group is required." >&2
  exit 2
fi

if [[ -z "${STORAGE_ACCOUNT}" ]]; then
  echo "Error: --storage-account is required." >&2
  exit 2
fi

if [[ -f "${BACKEND_CONFIG}" && "${OVERWRITE_BACKEND}" != "1" ]]; then
  echo "backend config already exists; not overwriting (${BACKEND_CONFIG})."
  if [[ "${RENDER_ONLY}" == "1" || "${DRY_RUN}" == "1" ]]; then
    exit 0
  fi
  require_command "terraform" "Terraform is required."
  run_or_print terraform -chdir="${WORKDIR}" init -migrate-state -force-copy
  exit 0
fi

if [[ "${RENDER_ONLY}" != "1" && "${DRY_RUN}" == "1" ]]; then
  EFFECTIVE_SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-<active-az-account>}"
  run_or_print az account set --subscription "${EFFECTIVE_SUBSCRIPTION_ID}"
  run_or_print az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --subscription "${EFFECTIVE_SUBSCRIPTION_ID}" --output none
  run_or_print az storage account create \
    --name "${STORAGE_ACCOUNT}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --min-tls-version TLS1_2 \
    --allow-blob-public-access false \
    --subscription "${EFFECTIVE_SUBSCRIPTION_ID}" \
    --output none
  run_or_print az storage container create \
    --name "${CONTAINER_NAME}" \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --subscription "${EFFECTIVE_SUBSCRIPTION_ID}" \
    --output none
  if [[ "${USE_SAS}" == "true" && "${SAS_AUTO}" == "true" ]]; then
    run_or_print python3 -c "print('generate sas expiry/token')"
  fi
  run_or_print python3 -c "print('write backend config to ${BACKEND_CONFIG}')"
elif [[ "${RENDER_ONLY}" != "1" && "${DRY_RUN}" != "1" ]]; then
  require_command "az" "Azure CLI (az) is required."
  require_command "terraform" "Terraform is required."

  if ! az account show >/dev/null 2>&1; then
    echo "Azure CLI is not logged in. Run 'az login' first." >&2
    exit 1
  fi

  if [[ -z "${SUBSCRIPTION_ID}" ]]; then
    SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
  fi

  run_or_print az account set --subscription "${SUBSCRIPTION_ID}"
  run_or_print az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --subscription "${SUBSCRIPTION_ID}" --output none

  if az storage account show \
    --name "${STORAGE_ACCOUNT}" \
    --resource-group "${RESOURCE_GROUP}" \
    --subscription "${SUBSCRIPTION_ID}" \
    --output none >/dev/null 2>&1; then
    echo "Storage account exists; skipping create."
  else
    run_or_print az storage account create \
      --name "${STORAGE_ACCOUNT}" \
      --resource-group "${RESOURCE_GROUP}" \
      --location "${LOCATION}" \
      --sku Standard_LRS \
      --kind StorageV2 \
      --min-tls-version TLS1_2 \
      --allow-blob-public-access false \
      --subscription "${SUBSCRIPTION_ID}" \
      --output none
  fi

  run_or_print az storage container create \
    --name "${CONTAINER_NAME}" \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --subscription "${SUBSCRIPTION_ID}" \
    --output none

  if [[ "${USE_SAS}" == "true" && "${SAS_AUTO}" == "true" && -z "${SAS_TOKEN}" ]]; then
    if [[ -z "${SAS_EXPIRY}" ]]; then
      SAS_EXPIRY="$(python3 - <<'PY'
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%MZ"))
PY
)"
    fi
    ACCOUNT_KEY="$(az storage account keys list --resource-group "${RESOURCE_GROUP}" --account-name "${STORAGE_ACCOUNT}" --query "[0].value" -o tsv)"
    SAS_TOKEN="$(az storage account generate-sas \
      --account-name "${STORAGE_ACCOUNT}" \
      --account-key "${ACCOUNT_KEY}" \
      --services b \
      --resource-types sco \
      --permissions acdlpruw \
      --expiry "${SAS_EXPIRY}" \
      --https-only \
      -o tsv)"
  fi
else
  echo "Skipping Azure provisioning and terraform init (${RENDER_ONLY} render-only, ${DRY_RUN} dry-run)."
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  run_or_print terraform -chdir="${WORKDIR}" init -migrate-state -force-copy
  echo "DRY-RUN skip backend config write"
  exit 0
fi

write_backend_config "${BACKEND_CONFIG}"
echo "Wrote backend config: ${BACKEND_CONFIG}"

if [[ "${RENDER_ONLY}" == "1" ]]; then
  exit 0
fi

run_or_print terraform -chdir="${WORKDIR}" init -migrate-state -force-copy
