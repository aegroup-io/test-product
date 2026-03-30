#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-}"
WORKLOAD_NAME="${WORKLOAD_NAME:-}"
ROLLOUT_KIND="${ROLLOUT_KIND:-deployment}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-300s}"
DRY_RUN=0
SKIP_NAMESPACE_CREATE=0
SKIP_WAIT=0
SECRET_NAME="${SECRET_NAME:-}"
SECRET_ENV_FILE="${SECRET_ENV_FILE:-}"
MANIFESTS=()

usage() {
  cat <<'EOF'
Usage: deploy_aks_workload.sh [options]

Apply one or more workload manifests to AKS, optionally sync an env-file secret, and wait for rollout.

Options:
  --namespace <name>         Kubernetes namespace to target
  --manifest <path>          Manifest to apply (repeatable)
  --workload-name <name>     Workload name to wait on after apply
  --rollout-kind <kind>      Rollout kind to wait on (default: deployment)
  --rollout-timeout <value>  kubectl rollout timeout (default: 300s)
  --secret-name <name>       Secret name to sync from env file
  --secret-env-file <path>   Env file used with --secret-name
  --no-namespace-create      Do not create namespace when missing
  --no-wait                  Skip rollout wait
  --dry-run                  Print planned kubectl commands without executing them
  -h, --help                 Show this help text
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

ensure_namespace() {
  local get_cmd=(kubectl get namespace "${NAMESPACE}")
  local create_cmd=(kubectl create namespace "${NAMESPACE}")

  if [[ "${SKIP_NAMESPACE_CREATE}" == "1" ]]; then
    return
  fi

  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'DRY-RUN '
    print_command "${get_cmd[@]}"
    printf '|| '
    print_command "${create_cmd[@]}"
    printf '\n'
    return
  fi

  if ! "${get_cmd[@]}" >/dev/null 2>&1; then
    "${create_cmd[@]}"
  fi
}

apply_secret() {
  local create_cmd=(
    kubectl create secret generic "${SECRET_NAME}"
    "--from-env-file=${SECRET_ENV_FILE}"
    -n "${NAMESPACE}"
    --dry-run=client
    -o yaml
  )
  local apply_cmd=(kubectl apply -f -)

  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'DRY-RUN '
    print_command "${create_cmd[@]}"
    printf '| '
    print_command "${apply_cmd[@]}"
    printf '\n'
    return
  fi

  "${create_cmd[@]}" | "${apply_cmd[@]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      [[ $# -lt 2 ]] && { echo "Error: --namespace requires a value." >&2; usage; exit 2; }
      NAMESPACE="$2"
      shift 2
      ;;
    --namespace=*)
      NAMESPACE="${1#*=}"
      shift
      ;;
    --manifest)
      [[ $# -lt 2 ]] && { echo "Error: --manifest requires a value." >&2; usage; exit 2; }
      MANIFESTS+=("$2")
      shift 2
      ;;
    --manifest=*)
      MANIFESTS+=("${1#*=}")
      shift
      ;;
    --workload-name)
      [[ $# -lt 2 ]] && { echo "Error: --workload-name requires a value." >&2; usage; exit 2; }
      WORKLOAD_NAME="$2"
      shift 2
      ;;
    --workload-name=*)
      WORKLOAD_NAME="${1#*=}"
      shift
      ;;
    --rollout-kind)
      [[ $# -lt 2 ]] && { echo "Error: --rollout-kind requires a value." >&2; usage; exit 2; }
      ROLLOUT_KIND="$2"
      shift 2
      ;;
    --rollout-kind=*)
      ROLLOUT_KIND="${1#*=}"
      shift
      ;;
    --rollout-timeout)
      [[ $# -lt 2 ]] && { echo "Error: --rollout-timeout requires a value." >&2; usage; exit 2; }
      ROLLOUT_TIMEOUT="$2"
      shift 2
      ;;
    --rollout-timeout=*)
      ROLLOUT_TIMEOUT="${1#*=}"
      shift
      ;;
    --secret-name)
      [[ $# -lt 2 ]] && { echo "Error: --secret-name requires a value." >&2; usage; exit 2; }
      SECRET_NAME="$2"
      shift 2
      ;;
    --secret-name=*)
      SECRET_NAME="${1#*=}"
      shift
      ;;
    --secret-env-file)
      [[ $# -lt 2 ]] && { echo "Error: --secret-env-file requires a value." >&2; usage; exit 2; }
      SECRET_ENV_FILE="$2"
      shift 2
      ;;
    --secret-env-file=*)
      SECRET_ENV_FILE="${1#*=}"
      shift
      ;;
    --no-namespace-create)
      SKIP_NAMESPACE_CREATE=1
      shift
      ;;
    --no-wait)
      SKIP_WAIT=1
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

if [[ -z "${NAMESPACE}" ]]; then
  echo "Error: --namespace is required." >&2
  exit 2
fi

if (( ${#MANIFESTS[@]} == 0 )); then
  echo "Error: at least one --manifest is required." >&2
  exit 2
fi

for manifest_path in "${MANIFESTS[@]}"; do
  if [[ ! -f "${manifest_path}" ]]; then
    echo "Manifest not found: ${manifest_path}" >&2
    exit 1
  fi
done

if [[ -n "${SECRET_NAME}" || -n "${SECRET_ENV_FILE}" ]]; then
  if [[ -z "${SECRET_NAME}" || -z "${SECRET_ENV_FILE}" ]]; then
    echo "Error: --secret-name and --secret-env-file must be provided together." >&2
    exit 2
  fi
  if [[ ! -f "${SECRET_ENV_FILE}" ]]; then
    echo "Secret env file not found: ${SECRET_ENV_FILE}" >&2
    exit 1
  fi
fi

if [[ "${SKIP_WAIT}" != "1" && -z "${WORKLOAD_NAME}" ]]; then
  echo "Error: --workload-name is required unless --no-wait is set." >&2
  exit 2
fi

if [[ "${DRY_RUN}" != "1" ]] && ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required to deploy AKS workloads." >&2
  exit 1
fi

ensure_namespace

if [[ -n "${SECRET_NAME}" ]]; then
  apply_secret
fi

for manifest_path in "${MANIFESTS[@]}"; do
  run_or_print kubectl -n "${NAMESPACE}" apply -f "${manifest_path}"
done

if [[ "${SKIP_WAIT}" != "1" ]]; then
  run_or_print kubectl rollout status "${ROLLOUT_KIND}/${WORKLOAD_NAME}" -n "${NAMESPACE}" --timeout="${ROLLOUT_TIMEOUT}"
fi
