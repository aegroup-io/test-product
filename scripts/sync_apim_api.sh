#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-}"
APIM_NAME="${APIM_NAME:-}"
API_ID="${API_ID:-}"
API_PATH="${API_PATH:-}"
OPENAPI_PATH="${OPENAPI_PATH:-}"
SERVICE_URL="${SERVICE_URL:-}"
SERVICE_NAME="${SERVICE_NAME:-}"
NAMESPACE="${NAMESPACE:-}"
AKS_RESOURCE_GROUP="${AKS_RESOURCE_GROUP:-}"
AKS_CLUSTER_NAME="${AKS_CLUSTER_NAME:-}"
SERVICE_SCHEME="${SERVICE_SCHEME:-http}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: sync_apim_api.sh [options]

Sync an APIM API definition from an OpenAPI document and point it at a backend service URL.

Options:
  --resource-group <name>  Azure resource group for APIM
  --apim <name>            APIM service name
  --api-id <id>            APIM API identifier
  --api-path <path>        APIM path value (default: empty)
  --openapi-path <path>    OpenAPI document to import
  --service-url <url>      Backend service URL for APIM
  --service-name <name>    AKS service name to resolve when --service-url is omitted
  --namespace <name>       Kubernetes namespace for --service-name
  --aks-rg <name>          AKS resource group for optional credential refresh
  --aks-name <name>        AKS cluster name for optional credential refresh
  --service-scheme <name>  Scheme to use when resolving an AKS service (default: http)
  --dry-run                Print planned commands without executing them
  -h, --help               Show this help text
EOF
}

print_command() {
  printf '%q ' "$@"
}

run_or_print() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'DRY-RUN '
    print_command "$@"
    printf '\n'
    return
  fi
  "$@"
}

resolve_service_url() {
  if [[ -n "${SERVICE_URL}" ]]; then
    return
  fi

  if [[ -n "${AKS_RESOURCE_GROUP}" || -n "${AKS_CLUSTER_NAME}" ]]; then
    if [[ -z "${AKS_RESOURCE_GROUP}" || -z "${AKS_CLUSTER_NAME}" ]]; then
      echo "Error: --aks-rg and --aks-name must be provided together." >&2
      exit 2
    fi
    run_or_print az aks get-credentials \
      --resource-group "${AKS_RESOURCE_GROUP}" \
      --name "${AKS_CLUSTER_NAME}" \
      --overwrite-existing
  fi

  if [[ "${DRY_RUN}" == "1" ]]; then
    run_or_print kubectl get svc "${SERVICE_NAME}" -n "${NAMESPACE}" -o "jsonpath={.status.loadBalancer.ingress[0].ip}"
    run_or_print kubectl get svc "${SERVICE_NAME}" -n "${NAMESPACE}" -o "jsonpath={.status.loadBalancer.ingress[0].hostname}"
    SERVICE_URL="${SERVICE_SCHEME}://<aks-service-endpoint>"
    return
  fi

  local service_endpoint=""
  service_endpoint="$(kubectl get svc "${SERVICE_NAME}" -n "${NAMESPACE}" -o 'jsonpath={.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  if [[ -z "${service_endpoint}" ]]; then
    service_endpoint="$(kubectl get svc "${SERVICE_NAME}" -n "${NAMESPACE}" -o 'jsonpath={.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  fi

  if [[ -z "${service_endpoint}" ]]; then
    echo "Unable to resolve service endpoint for ${SERVICE_NAME} in namespace ${NAMESPACE}." >&2
    exit 1
  fi

  SERVICE_URL="${SERVICE_SCHEME}://${service_endpoint}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group)
      [[ $# -lt 2 ]] && { echo "Error: --resource-group requires a value." >&2; usage; exit 2; }
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --resource-group=*)
      RESOURCE_GROUP="${1#*=}"
      shift
      ;;
    --apim)
      [[ $# -lt 2 ]] && { echo "Error: --apim requires a value." >&2; usage; exit 2; }
      APIM_NAME="$2"
      shift 2
      ;;
    --apim=*)
      APIM_NAME="${1#*=}"
      shift
      ;;
    --api-id)
      [[ $# -lt 2 ]] && { echo "Error: --api-id requires a value." >&2; usage; exit 2; }
      API_ID="$2"
      shift 2
      ;;
    --api-id=*)
      API_ID="${1#*=}"
      shift
      ;;
    --api-path)
      [[ $# -lt 2 ]] && { echo "Error: --api-path requires a value." >&2; usage; exit 2; }
      API_PATH="$2"
      shift 2
      ;;
    --api-path=*)
      API_PATH="${1#*=}"
      shift
      ;;
    --openapi-path)
      [[ $# -lt 2 ]] && { echo "Error: --openapi-path requires a value." >&2; usage; exit 2; }
      OPENAPI_PATH="$2"
      shift 2
      ;;
    --openapi-path=*)
      OPENAPI_PATH="${1#*=}"
      shift
      ;;
    --service-url)
      [[ $# -lt 2 ]] && { echo "Error: --service-url requires a value." >&2; usage; exit 2; }
      SERVICE_URL="$2"
      shift 2
      ;;
    --service-url=*)
      SERVICE_URL="${1#*=}"
      shift
      ;;
    --service-name)
      [[ $# -lt 2 ]] && { echo "Error: --service-name requires a value." >&2; usage; exit 2; }
      SERVICE_NAME="$2"
      shift 2
      ;;
    --service-name=*)
      SERVICE_NAME="${1#*=}"
      shift
      ;;
    --namespace)
      [[ $# -lt 2 ]] && { echo "Error: --namespace requires a value." >&2; usage; exit 2; }
      NAMESPACE="$2"
      shift 2
      ;;
    --namespace=*)
      NAMESPACE="${1#*=}"
      shift
      ;;
    --aks-rg)
      [[ $# -lt 2 ]] && { echo "Error: --aks-rg requires a value." >&2; usage; exit 2; }
      AKS_RESOURCE_GROUP="$2"
      shift 2
      ;;
    --aks-rg=*)
      AKS_RESOURCE_GROUP="${1#*=}"
      shift
      ;;
    --aks-name)
      [[ $# -lt 2 ]] && { echo "Error: --aks-name requires a value." >&2; usage; exit 2; }
      AKS_CLUSTER_NAME="$2"
      shift 2
      ;;
    --aks-name=*)
      AKS_CLUSTER_NAME="${1#*=}"
      shift
      ;;
    --service-scheme)
      [[ $# -lt 2 ]] && { echo "Error: --service-scheme requires a value." >&2; usage; exit 2; }
      SERVICE_SCHEME="$2"
      shift 2
      ;;
    --service-scheme=*)
      SERVICE_SCHEME="${1#*=}"
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

if [[ -z "${RESOURCE_GROUP}" || -z "${APIM_NAME}" || -z "${API_ID}" || -z "${OPENAPI_PATH}" ]]; then
  echo "Error: --resource-group, --apim, --api-id, and --openapi-path are required." >&2
  exit 2
fi

if [[ ! -f "${OPENAPI_PATH}" ]]; then
  echo "OpenAPI document not found: ${OPENAPI_PATH}" >&2
  exit 1
fi

if [[ -z "${SERVICE_URL}" ]]; then
  if [[ -z "${SERVICE_NAME}" || -z "${NAMESPACE}" ]]; then
    echo "Error: provide --service-url or both --service-name and --namespace." >&2
    exit 2
  fi
fi

if [[ "${DRY_RUN}" != "1" ]] && ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI is required to sync APIM APIs." >&2
  exit 1
fi

if [[ "${DRY_RUN}" != "1" && -z "${SERVICE_URL}" ]] && ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required to resolve AKS service endpoints." >&2
  exit 1
fi

resolve_service_url

if [[ "${DRY_RUN}" == "1" ]]; then
  run_or_print az apim api revision list \
    --resource-group "${RESOURCE_GROUP}" \
    --service-name "${APIM_NAME}" \
    --api-id "${API_ID}" \
    --query "[?isCurrent==\`true\`].apiRevision | [0]" \
    -o tsv
  printf 'DRY-RUN if current revision missing: '
  print_command az apim api import \
    --resource-group "${RESOURCE_GROUP}" \
    --service-name "${APIM_NAME}" \
    --api-id "${API_ID}" \
    --path "${API_PATH}" \
    --specification-format OpenApi \
    --specification-path "${OPENAPI_PATH}" \
    --service-url "${SERVICE_URL}"
  printf '\n'
  printf 'DRY-RUN if current revision exists: '
  print_command az apim api import \
    --resource-group "${RESOURCE_GROUP}" \
    --service-name "${APIM_NAME}" \
    --api-id "${API_ID}" \
    --api-revision "<current-revision>" \
    --path "${API_PATH}" \
    --specification-format OpenApi \
    --specification-path "${OPENAPI_PATH}"
  printf '\n'
  printf 'DRY-RUN if current revision exists: '
  print_command az apim api update \
    --resource-group "${RESOURCE_GROUP}" \
    --service-name "${APIM_NAME}" \
    --api-id "${API_ID}" \
    --service-url "${SERVICE_URL}"
  printf '\n'
  exit 0
fi

current_revision="$(
  az apim api revision list \
    --resource-group "${RESOURCE_GROUP}" \
    --service-name "${APIM_NAME}" \
    --api-id "${API_ID}" \
    --query "[?isCurrent==\`true\`].apiRevision | [0]" \
    -o tsv
)"

if [[ -z "${current_revision}" ]]; then
  az apim api import \
    --resource-group "${RESOURCE_GROUP}" \
    --service-name "${APIM_NAME}" \
    --api-id "${API_ID}" \
    --path "${API_PATH}" \
    --specification-format OpenApi \
    --specification-path "${OPENAPI_PATH}" \
    --service-url "${SERVICE_URL}"
  echo "Created APIM API ${API_ID} with service URL ${SERVICE_URL}"
  exit 0
fi

az apim api import \
  --resource-group "${RESOURCE_GROUP}" \
  --service-name "${APIM_NAME}" \
  --api-id "${API_ID}" \
  --api-revision "${current_revision}" \
  --path "${API_PATH}" \
  --specification-format OpenApi \
  --specification-path "${OPENAPI_PATH}"

az apim api update \
  --resource-group "${RESOURCE_GROUP}" \
  --service-name "${APIM_NAME}" \
  --api-id "${API_ID}" \
  --service-url "${SERVICE_URL}"

echo "Updated APIM API ${API_ID} revision ${current_revision} with service URL ${SERVICE_URL}"
