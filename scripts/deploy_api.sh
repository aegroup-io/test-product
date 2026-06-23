#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/deploy_common.sh"

ENVIRONMENT="${ENVIRONMENT:-dev}"
ENV_FILE="${ENV_FILE:-}"
IMAGE="${IMAGE:-}"
TAG="${ORCHA_API_IMAGE_TAG:-}"
NAMESPACE="${NAMESPACE:-}"
SERVICE_NAME="${SERVICE_NAME:-}"
DEPLOYMENT_TEMPLATE="${DEPLOYMENT_TEMPLATE:-${ROOT_DIR}/api/deploy/deployment.yaml.jinja}"
SERVICE_TEMPLATE="${SERVICE_TEMPLATE:-${ROOT_DIR}/api/deploy/service.yaml.jinja}"
SERVICE_ACCOUNT_TEMPLATE="${SERVICE_ACCOUNT_TEMPLATE:-${ROOT_DIR}/api/deploy/service-account.yaml.jinja}"
API_ENV_FILE="${API_ENV_FILE:-}"
API_SERVICE_TYPE="${ORCHA_API_SERVICE_TYPE:-}"
API_SERVICE_URL="${ORCHA_API_SERVICE_URL:-}"
SKIP_BUILD="false"
SKIP_APPLY="false"
SKIP_APIM="false"
SKIP_SECRET="false"
DRY_RUN="false"
RENDERED_DEPLOYMENT_FILE=""
RENDERED_SERVICE_FILE=""
RENDERED_SERVICE_ACCOUNT_FILE=""
GENERATED_API_ENV_FILE=""
SECRET_HASH="no-secret"

usage() {
  cat <<'USAGE'
Usage: deploy_api.sh [options]

Options:
  --env <name>           Environment suffix (default: dev)
  --env-file <path>      Env file to load before resolving defaults (default: scripts/.env.<env>)
  --image <image>        Full image reference (default: <acr>/orcha-api:<tag>)
  --tag <tag>            Image tag (default: $ORCHA_API_IMAGE_TAG or current git SHA)
  --namespace <name>     Kubernetes namespace (default: Terraform aks_namespace or orcha-<env>)
  --service-name <name>  Kubernetes service name (default: orcha-api)
  --service-type <type>  Kubernetes Service type (default: ClusterIP for dev, LoadBalancer otherwise)
  --service-url <url>    Backend URL for APIM sync; required when APIM sync cannot discover a LoadBalancer
  --deployment <path>    Deployment template (default: api/deploy/deployment.yaml.jinja)
  --service <path>       Service template (default: api/deploy/service.yaml.jinja)
  --service-account <p>  ServiceAccount/RBAC template (default: api/deploy/service-account.yaml.jinja)
  --api-env-file <path>  Secret env file (default: api/.env.<env>)
  --no-build             Skip image build/push
  --no-apply             Skip Kubernetes apply
  --no-apim              Skip APIM sync
  --no-secret            Skip Kubernetes secret sync
  --dry-run              Print planned commands without executing external deploy actions
  -h, --help             Show help
USAGE
}

cleanup() {
  if [[ -n "${RENDERED_DEPLOYMENT_FILE}" && -f "${RENDERED_DEPLOYMENT_FILE}" ]]; then
    rm -f "${RENDERED_DEPLOYMENT_FILE}"
  fi
  if [[ -n "${RENDERED_SERVICE_FILE}" && -f "${RENDERED_SERVICE_FILE}" ]]; then
    rm -f "${RENDERED_SERVICE_FILE}"
  fi
  if [[ -n "${RENDERED_SERVICE_ACCOUNT_FILE}" && -f "${RENDERED_SERVICE_ACCOUNT_FILE}" ]]; then
    rm -f "${RENDERED_SERVICE_ACCOUNT_FILE}"
  fi
  if [[ -n "${GENERATED_API_ENV_FILE}" && -f "${GENERATED_API_ENV_FILE}" ]]; then
    rm -f "${GENERATED_API_ENV_FILE}"
  fi
}
trap cleanup EXIT

ORIG_ARGS=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENVIRONMENT="${2:-${ENVIRONMENT}}"
      shift 2
      ;;
    --env=*)
      ENVIRONMENT="${1#*=}"
      shift
      ;;
    --env-file)
      ENV_FILE="${2:-${ENV_FILE}}"
      shift 2
      ;;
    --env-file=*)
      ENV_FILE="${1#*=}"
      shift
      ;;
    *)
      shift
      ;;
  esac
done
if ((${#ORIG_ARGS[@]} > 0)); then
  set -- "${ORIG_ARGS[@]}"
else
  set --
fi

if [[ -z "${ENV_FILE}" ]]; then
  ENV_FILE="${SCRIPT_DIR}/.env.${ENVIRONMENT}"
fi
DEFAULT_ENV_FILE="${SCRIPT_DIR}/.env.${ENVIRONMENT}"
orcha_load_env_file "${ENV_FILE}"

NAMESPACE="${ORCHA_AKS_NAMESPACE:-${NAMESPACE:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "aks_namespace")}}"
if [[ -z "${NAMESPACE}" ]]; then
  NAMESPACE="orcha-${ENVIRONMENT}"
fi

SERVICE_NAME="${ORCHA_API_SERVICE_NAME:-${SERVICE_NAME:-orcha-api}}"
API_SECRET_NAME="${ORCHA_API_SECRET_NAME:-orcha-api-secrets}"
API_SERVICE_ACCOUNT_NAME="${ORCHA_API_SERVICE_ACCOUNT_NAME:-orcha-api}"
API_ENV_FILE="${API_ENV_FILE:-${ROOT_DIR}/api/.env.${ENVIRONMENT}}"
DEFAULT_API_ENV_FILE="${ROOT_DIR}/api/.env.${ENVIRONMENT}"
ACR_LOGIN_SERVER="${ORCHA_ACR_LOGIN_SERVER:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "acr_login_server")}"
AKS_RESOURCE_GROUP="${ORCHA_AKS_RESOURCE_GROUP:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "aks_resource_group")}"
AKS_CLUSTER_NAME="${ORCHA_AKS_CLUSTER_NAME:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "aks_cluster_name")}"
APIM_RESOURCE_GROUP="${ORCHA_APIM_RESOURCE_GROUP:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "apim_resource_group_name")}"
APIM_NAME="${ORCHA_APIM_NAME:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "apim_name")}"
APIM_API_ID="${ORCHA_APIM_API_ID:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "apim_api_id")}"
APIM_API_PATH="${ORCHA_APIM_API_PATH:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "apim_api_path")}"
PUBLIC_API_BASE_URL="${ORCHA_PUBLIC_API_BASE_URL:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "public_api_base_url")}"
POSTGRES_DATABASE_URL="${ORCHA_DATABASE_URL:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "postgres_database_url")}"
KEY_VAULT_NAME="${ORCHA_KEY_VAULT_NAME:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "key_vault_name")}"
ENTRA_TENANT_ID="${ORCHA_ENTRA_TENANT_ID:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "entra_tenant_id")}"
GRAPH_CLIENT_ID="${ORCHA_GRAPH_CLIENT_ID:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "graph_client_id")}"
GRAPH_CLIENT_SECRET="${ORCHA_GRAPH_CLIENT_SECRET:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "graph_client_secret")}"
RUNTIME_API_TOKEN="${ORCHA_RUNTIME_API_TOKEN:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "runtime_api_token")}"
GIT_FILES_NAME="${ORCHA_GIT_FILES_NAME:-orcha-git-files}"
GIT_STORAGE_CLASS="${ORCHA_GIT_STORAGE_CLASS:-azurefile-csi}"
GIT_STORAGE_ACCOUNT_NAME="${ORCHA_GIT_STORAGE_ACCOUNT_NAME:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "git_storage_account_name")}"
GIT_STORAGE_ACCOUNT_KEY="${ORCHA_GIT_STORAGE_ACCOUNT_KEY:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "git_storage_account_key")}"
GIT_FILE_SHARE_NAME="${ORCHA_GIT_FILE_SHARE_NAME:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "git_file_share_name")}"
GIT_FILE_SHARE_QUOTA_GB="${ORCHA_GIT_FILE_SHARE_QUOTA_GB:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "git_file_share_quota_gb")}"
SHARED_GIT_MOUNT_PATH="${ORCHA_SHARED_GIT_MOUNT_PATH:-/mnt/git-files}"
if [[ -z "${ENTRA_TENANT_ID}" ]]; then
  ENTRA_TENANT_ID="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.entra_tenant_id), "")')"
fi
if [[ -z "${GRAPH_CLIENT_ID}" ]]; then
  GRAPH_CLIENT_ID="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.api_app_client_id), "")')"
fi
if [[ -z "${GRAPH_CLIENT_SECRET}" ]]; then
  GRAPH_CLIENT_SECRET="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.api_app_client_secret), "")')"
fi
if [[ -z "${GIT_STORAGE_ACCOUNT_NAME}" ]]; then
  GIT_STORAGE_ACCOUNT_NAME="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.git_storage_account_name), "")')"
fi
if [[ -z "${GIT_STORAGE_ACCOUNT_KEY}" ]]; then
  GIT_STORAGE_ACCOUNT_KEY="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.git_storage_account_key), "")')"
fi
if [[ -z "${GIT_FILE_SHARE_NAME}" ]]; then
  GIT_FILE_SHARE_NAME="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.git_file_share_name), "")')"
fi
if [[ -z "${GIT_FILE_SHARE_QUOTA_GB}" ]]; then
  GIT_FILE_SHARE_QUOTA_GB="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.git_file_share_quota_gb), "")')"
fi
GRAPH_TENANT_ID="${ORCHA_GRAPH_TENANT_ID:-${ENTRA_TENANT_ID}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      [[ $# -lt 2 ]] && { echo "Error: --env requires a value." >&2; usage; exit 1; }
      ENVIRONMENT="$2"
      shift 2
      ;;
    --env=*)
      ENVIRONMENT="${1#*=}"
      shift
      ;;
    --env-file)
      [[ $# -lt 2 ]] && { echo "Error: --env-file requires a value." >&2; usage; exit 1; }
      ENV_FILE="$2"
      shift 2
      ;;
    --env-file=*)
      ENV_FILE="${1#*=}"
      shift
      ;;
    --image)
      [[ $# -lt 2 ]] && { echo "Error: --image requires a value." >&2; usage; exit 1; }
      IMAGE="$2"
      shift 2
      ;;
    --image=*)
      IMAGE="${1#*=}"
      shift
      ;;
    --tag)
      [[ $# -lt 2 ]] && { echo "Error: --tag requires a value." >&2; usage; exit 1; }
      TAG="$2"
      shift 2
      ;;
    --tag=*)
      TAG="${1#*=}"
      shift
      ;;
    --namespace)
      [[ $# -lt 2 ]] && { echo "Error: --namespace requires a value." >&2; usage; exit 1; }
      NAMESPACE="$2"
      shift 2
      ;;
    --namespace=*)
      NAMESPACE="${1#*=}"
      shift
      ;;
    --service-name)
      [[ $# -lt 2 ]] && { echo "Error: --service-name requires a value." >&2; usage; exit 1; }
      SERVICE_NAME="$2"
      shift 2
      ;;
    --service-name=*)
      SERVICE_NAME="${1#*=}"
      shift
      ;;
    --service-type)
      [[ $# -lt 2 ]] && { echo "Error: --service-type requires a value." >&2; usage; exit 1; }
      API_SERVICE_TYPE="$2"
      shift 2
      ;;
    --service-type=*)
      API_SERVICE_TYPE="${1#*=}"
      shift
      ;;
    --service-url)
      [[ $# -lt 2 ]] && { echo "Error: --service-url requires a value." >&2; usage; exit 1; }
      API_SERVICE_URL="$2"
      shift 2
      ;;
    --service-url=*)
      API_SERVICE_URL="${1#*=}"
      shift
      ;;
    --deployment)
      [[ $# -lt 2 ]] && { echo "Error: --deployment requires a value." >&2; usage; exit 1; }
      DEPLOYMENT_TEMPLATE="$2"
      shift 2
      ;;
    --deployment=*)
      DEPLOYMENT_TEMPLATE="${1#*=}"
      shift
      ;;
    --service)
      [[ $# -lt 2 ]] && { echo "Error: --service requires a value." >&2; usage; exit 1; }
      SERVICE_TEMPLATE="$2"
      shift 2
      ;;
    --service=*)
      SERVICE_TEMPLATE="${1#*=}"
      shift
      ;;
    --service-account)
      [[ $# -lt 2 ]] && { echo "Error: --service-account requires a value." >&2; usage; exit 1; }
      SERVICE_ACCOUNT_TEMPLATE="$2"
      shift 2
      ;;
    --service-account=*)
      SERVICE_ACCOUNT_TEMPLATE="${1#*=}"
      shift
      ;;
    --api-env-file)
      [[ $# -lt 2 ]] && { echo "Error: --api-env-file requires a value." >&2; usage; exit 1; }
      API_ENV_FILE="$2"
      shift 2
      ;;
    --api-env-file=*)
      API_ENV_FILE="${1#*=}"
      shift
      ;;
    --no-build)
      SKIP_BUILD="true"
      shift
      ;;
    --no-apply)
      SKIP_APPLY="true"
      shift
      ;;
    --no-apim)
      SKIP_APIM="true"
      shift
      ;;
    --no-secret)
      SKIP_SECRET="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$1'." >&2
      usage
      exit 1
      ;;
  esac
done

REMOTE_EXECUTION_ROOT="${ORCHA_REMOTE_EXECUTION_ROOT:-${SHARED_GIT_MOUNT_PATH}/${NAMESPACE}/remote-execution}"

if [[ "${SKIP_SECRET}" != "true" && "${ENV_FILE}" == "${DEFAULT_ENV_FILE}" && "${API_ENV_FILE}" == "${DEFAULT_API_ENV_FILE}" ]]; then
  if [[ -x "${ROOT_DIR}/scripts/load-env.sh" ]]; then
    bash "${ROOT_DIR}/scripts/load-env.sh" --env "${ENVIRONMENT}" --mode remote --force >/dev/null
    orcha_load_env_file "${ENV_FILE}"
    KEY_VAULT_NAME="${ORCHA_KEY_VAULT_NAME:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "key_vault_name")}"
    RUNTIME_API_TOKEN="${ORCHA_RUNTIME_API_TOKEN:-$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "runtime_api_token")}"
    if [[ -z "${RUNTIME_API_TOKEN}" ]]; then
      RUNTIME_API_TOKEN="$(orcha_key_vault_secret_value "${KEY_VAULT_NAME}" "agent-core-runtime-api-token")"
    fi
    if [[ -z "${RUNTIME_API_TOKEN}" ]]; then
      RUNTIME_API_TOKEN="$(orcha_env_file_value "${API_ENV_FILE}" "AGENT_CORE_API_TOKEN")"
    fi
  fi
fi

if [[ "${SKIP_SECRET}" != "true" && -z "${RUNTIME_API_TOKEN}" ]]; then
  echo "Unable to resolve runtime API token. Run terraform apply for infra/environments/${ENVIRONMENT} so deploy can regenerate its env files automatically." >&2
  exit 1
fi

API_CRYPTO_SEED="${AGENT_CORE_CRYPTO_SEED:-${ORCHA_CRYPTO_SEED:-}}"
if [[ -z "${API_CRYPTO_SEED}" ]]; then
  API_CRYPTO_SEED="$(orcha_env_file_value "${API_ENV_FILE}" "AGENT_CORE_CRYPTO_SEED")"
fi
if [[ -z "${API_CRYPTO_SEED}" ]]; then
  API_CRYPTO_SEED="orcha-local-dev"
fi

if [[ -z "${TAG}" ]]; then
  TAG="$(orcha_default_image_tag "${ROOT_DIR}" "dev")"
fi

if [[ "${SKIP_SECRET}" != "true" ]]; then
  GENERATED_API_ENV_FILE="/tmp/orcha-api-env-${ENVIRONMENT}-$$.env"
  orcha_merge_env_file \
    "${GENERATED_API_ENV_FILE}" \
    "${API_ENV_FILE}" \
    "AGENT_CORE_DATABASE_URL=${POSTGRES_DATABASE_URL}" \
    "AGENT_CORE_CRYPTO_SEED=${API_CRYPTO_SEED}" \
    "AGENT_CORE_PUBLIC_API_BASE_URL=${PUBLIC_API_BASE_URL}" \
    "AGENT_CORE_API_TOKEN=${RUNTIME_API_TOKEN}" \
    "AGENT_CORE_API_TOKEN_ROLES=worker" \
    "AGENT_CORE_ORCHESTRATION_LOOP_ENABLED=1" \
    "AGENT_CORE_ENTRA_TENANT_ID=${ENTRA_TENANT_ID}" \
    "AGENT_CORE_GRAPH_CLIENT_ID=${GRAPH_CLIENT_ID}" \
    "AGENT_CORE_GRAPH_CLIENT_SECRET=${GRAPH_CLIENT_SECRET}" \
    "AGENT_CORE_GRAPH_TENANT_ID=${GRAPH_TENANT_ID}"
  if [[ -s "${GENERATED_API_ENV_FILE}" ]]; then
    API_ENV_FILE="${GENERATED_API_ENV_FILE}"
  fi
fi

if [[ -z "${IMAGE}" ]]; then
  if [[ -n "${ACR_LOGIN_SERVER}" ]]; then
    IMAGE="${ACR_LOGIN_SERVER}/orcha-api:${TAG}"
  else
    IMAGE="orcha-api:${TAG}"
  fi
fi

if [[ -z "${API_SERVICE_TYPE}" ]]; then
  if [[ "${ENVIRONMENT}" == "dev" ]]; then
    if [[ "${SKIP_APIM}" == "true" || -n "${API_SERVICE_URL}" ]]; then
      API_SERVICE_TYPE="ClusterIP"
    else
      API_SERVICE_TYPE="LoadBalancer"
    fi
  else
    API_SERVICE_TYPE="LoadBalancer"
  fi
fi

case "${API_SERVICE_TYPE}" in
  ClusterIP|LoadBalancer|NodePort) ;;
  *)
    echo "Error: --service-type must be ClusterIP, LoadBalancer, or NodePort." >&2
    exit 1
    ;;
esac

if [[ "${SKIP_APIM}" != "true" && -z "${API_SERVICE_URL}" && "${API_SERVICE_TYPE}" != "LoadBalancer" ]]; then
  echo "Unable to sync APIM for ${API_SERVICE_TYPE} service ${SERVICE_NAME}. Set ORCHA_API_SERVICE_URL or pass --service-url, deploy with --service-type LoadBalancer, or use --no-apim for an internal-only dev deploy." >&2
  exit 1
fi

if [[ ! -f "${DEPLOYMENT_TEMPLATE}" ]]; then
  echo "Deployment template not found: ${DEPLOYMENT_TEMPLATE}" >&2
  exit 1
fi
if [[ ! -f "${SERVICE_TEMPLATE}" ]]; then
  echo "Service template not found: ${SERVICE_TEMPLATE}" >&2
  exit 1
fi
if [[ ! -f "${SERVICE_ACCOUNT_TEMPLATE}" ]]; then
  echo "ServiceAccount/RBAC template not found: ${SERVICE_ACCOUNT_TEMPLATE}" >&2
  exit 1
fi

if [[ "${SKIP_SECRET}" != "true" && -f "${API_ENV_FILE}" ]]; then
  SECRET_HASH="$(python3 - <<'PY' "${API_ENV_FILE}"
from pathlib import Path
import hashlib
import sys

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
fi

RENDERED_DEPLOYMENT_FILE="/tmp/orcha-api-deployment-${ENVIRONMENT}-$$.yaml"
RENDERED_SERVICE_FILE="/tmp/orcha-api-service-${ENVIRONMENT}-$$.yaml"
RENDERED_SERVICE_ACCOUNT_FILE="/tmp/orcha-api-service-account-${ENVIRONMENT}-$$.yaml"
orcha_render_template \
  "${SERVICE_ACCOUNT_TEMPLATE}" \
  "${RENDERED_SERVICE_ACCOUNT_FILE}" \
  "service_account_name=${API_SERVICE_ACCOUNT_NAME}"
orcha_render_template \
  "${DEPLOYMENT_TEMPLATE}" \
  "${RENDERED_DEPLOYMENT_FILE}" \
  "image=${IMAGE}" \
  "namespace=${NAMESPACE}" \
  "remote_execution_root=${REMOTE_EXECUTION_ROOT}" \
  "secret_name=${API_SECRET_NAME}" \
  "shared_git_mount_path=${SHARED_GIT_MOUNT_PATH}" \
  "shared_git_pvc_name=${GIT_FILES_NAME}" \
  "service_account_name=${API_SERVICE_ACCOUNT_NAME}" \
  "secret_hash=${SECRET_HASH}"
orcha_render_template \
  "${SERVICE_TEMPLATE}" \
  "${RENDERED_SERVICE_FILE}" \
  "service_type=${API_SERVICE_TYPE}"

if [[ "${SKIP_BUILD}" != "true" ]]; then
  BUILD_ARGS=(
    bash "${ROOT_DIR}/scripts/build_push_container_image.sh"
    --image "${IMAGE}"
    --dockerfile "${ROOT_DIR}/api/Dockerfile"
    --context "${ROOT_DIR}"
  )
  if [[ "${DRY_RUN}" == "true" ]]; then
    BUILD_ARGS+=(--dry-run)
  fi
  "${BUILD_ARGS[@]}"
fi

if [[ "${SKIP_APPLY}" != "true" ]]; then
  orcha_ensure_git_files \
    "${NAMESPACE}" \
    "${GIT_FILES_NAME}" \
    "${GIT_STORAGE_CLASS}" \
    "${GIT_STORAGE_ACCOUNT_NAME}" \
    "${GIT_STORAGE_ACCOUNT_KEY}" \
    "${GIT_FILE_SHARE_NAME}" \
    "${GIT_FILE_SHARE_QUOTA_GB:-20}" \
    "${DRY_RUN}"
  APPLY_ARGS=(
    bash "${ROOT_DIR}/scripts/deploy_aks_workload.sh"
    --namespace "${NAMESPACE}"
    --manifest "${RENDERED_SERVICE_ACCOUNT_FILE}"
    --manifest "${RENDERED_DEPLOYMENT_FILE}"
    --manifest "${RENDERED_SERVICE_FILE}"
    --workload-name "${SERVICE_NAME}"
  )
  if [[ "${SKIP_SECRET}" != "true" && -f "${API_ENV_FILE}" ]]; then
    APPLY_ARGS+=(--secret-name "${API_SECRET_NAME}" --secret-env-file "${API_ENV_FILE}")
  fi
  if [[ "${DRY_RUN}" == "true" ]]; then
    APPLY_ARGS+=(--dry-run)
  fi
  "${APPLY_ARGS[@]}"
fi

if [[ "${SKIP_APIM}" != "true" ]]; then
  if [[ -z "${APIM_RESOURCE_GROUP}" || -z "${APIM_NAME}" || -z "${APIM_API_ID}" ]]; then
    echo "Unable to resolve APIM settings. Set ORCHA_APIM_RESOURCE_GROUP, ORCHA_APIM_NAME, and ORCHA_APIM_API_ID or apply Terraform first." >&2
    exit 1
  fi

  APIM_ARGS=(
    bash "${ROOT_DIR}/scripts/sync_orcha_apim.sh"
    --resource-group "${APIM_RESOURCE_GROUP}"
    --apim "${APIM_NAME}"
    --api-id "${APIM_API_ID}"
    --api-path "${APIM_API_PATH:-orcha}"
  )
  if [[ -n "${API_SERVICE_URL}" ]]; then
    APIM_ARGS+=(--service-url "${API_SERVICE_URL}")
  else
    APIM_ARGS+=(--service-name "${SERVICE_NAME}" --namespace "${NAMESPACE}")
    if [[ -n "${AKS_RESOURCE_GROUP}" && -n "${AKS_CLUSTER_NAME}" ]]; then
      APIM_ARGS+=(--aks-rg "${AKS_RESOURCE_GROUP}" --aks-name "${AKS_CLUSTER_NAME}")
    fi
  fi
  if [[ "${DRY_RUN}" == "true" ]]; then
    APIM_ARGS+=(--dry-run)
  fi
  "${APIM_ARGS[@]}"
fi
