#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-}"
DOCKERFILE="${DOCKERFILE:-}"
CONTEXT_DIR="${CONTEXT_DIR:-.}"
PLATFORM="${PLATFORM:-linux/amd64}"
BUILDER_NAME="${BUILDER_NAME:-agentcore-builder}"
NO_LOGIN=0
NO_PUSH=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: build_push_container_image.sh [options]

Generic container image build/push helper for product repos that adopt agent-core.

Options:
  --image <ref>          Full image reference to build
  --dockerfile <path>    Dockerfile path to use
  --context <path>       Docker build context (default: .)
  --platform <value>     Target platform (default: linux/amd64; use local/native for host build)
  --builder-name <name>  docker buildx builder name (default: agentcore-builder)
  --no-login             Skip registry login even when the target is Azure Container Registry
  --no-push              Build only; do not push the image
  --dry-run              Print planned commands without executing them
  -h, --help             Show this help text
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
  if [[ "${DRY_RUN}" == "1" ]]; then
    return
  fi
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${hint}" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      [[ $# -lt 2 ]] && { echo "Error: --image requires a value." >&2; usage; exit 2; }
      IMAGE="$2"
      shift 2
      ;;
    --image=*)
      IMAGE="${1#*=}"
      shift
      ;;
    --dockerfile)
      [[ $# -lt 2 ]] && { echo "Error: --dockerfile requires a value." >&2; usage; exit 2; }
      DOCKERFILE="$2"
      shift 2
      ;;
    --dockerfile=*)
      DOCKERFILE="${1#*=}"
      shift
      ;;
    --context)
      [[ $# -lt 2 ]] && { echo "Error: --context requires a value." >&2; usage; exit 2; }
      CONTEXT_DIR="$2"
      shift 2
      ;;
    --context=*)
      CONTEXT_DIR="${1#*=}"
      shift
      ;;
    --platform)
      [[ $# -lt 2 ]] && { echo "Error: --platform requires a value." >&2; usage; exit 2; }
      PLATFORM="$2"
      shift 2
      ;;
    --platform=*)
      PLATFORM="${1#*=}"
      shift
      ;;
    --builder-name)
      [[ $# -lt 2 ]] && { echo "Error: --builder-name requires a value." >&2; usage; exit 2; }
      BUILDER_NAME="$2"
      shift 2
      ;;
    --builder-name=*)
      BUILDER_NAME="${1#*=}"
      shift
      ;;
    --no-login)
      NO_LOGIN=1
      shift
      ;;
    --no-push)
      NO_PUSH=1
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

if [[ -z "${IMAGE}" ]]; then
  echo "Error: --image is required." >&2
  usage
  exit 2
fi

if [[ -z "${DOCKERFILE}" ]]; then
  echo "Error: --dockerfile is required." >&2
  usage
  exit 2
fi

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "Dockerfile not found: ${DOCKERFILE}" >&2
  exit 1
fi

if [[ ! -d "${CONTEXT_DIR}" ]]; then
  echo "Context directory not found: ${CONTEXT_DIR}" >&2
  exit 1
fi

if [[ "${PLATFORM}" == "local" || "${PLATFORM}" == "native" ]]; then
  PLATFORM=""
fi

REGISTRY="${IMAGE%%/*}"
if [[ "${REGISTRY}" == *.azurecr.io && "${NO_LOGIN}" != "1" && "${NO_PUSH}" != "1" ]]; then
  ACR_NAME="${REGISTRY%%.azurecr.io}"
  require_command "az" "Azure CLI is required to login to ACR (${REGISTRY})."
  run_or_print az acr login --name "${ACR_NAME}"
fi

require_command "docker" "Docker is required to build container images."

if [[ -n "${PLATFORM}" ]]; then
  require_command "docker" "Docker is required to run buildx."
  if [[ "${DRY_RUN}" != "1" ]]; then
    if ! docker buildx version >/dev/null 2>&1; then
      echo "Docker buildx is required for cross-platform builds (${PLATFORM})." >&2
      exit 1
    fi
    if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
      run_or_print docker buildx create --use --name "${BUILDER_NAME}"
    else
      run_or_print docker buildx use "${BUILDER_NAME}"
    fi
  else
    run_or_print docker buildx inspect "${BUILDER_NAME}"
    run_or_print docker buildx create --use --name "${BUILDER_NAME}"
  fi

  BUILD_ARGS=(
    docker buildx build
    --platform "${PLATFORM}"
    -t "${IMAGE}"
    -f "${DOCKERFILE}"
    "${CONTEXT_DIR}"
  )
  if [[ "${NO_PUSH}" == "1" ]]; then
    BUILD_ARGS+=(--load)
  else
    BUILD_ARGS+=(--push)
  fi
  run_or_print "${BUILD_ARGS[@]}"
  exit 0
fi

run_or_print docker build -t "${IMAGE}" -f "${DOCKERFILE}" "${CONTEXT_DIR}"
if [[ "${NO_PUSH}" != "1" ]]; then
  run_or_print docker push "${IMAGE}"
fi
