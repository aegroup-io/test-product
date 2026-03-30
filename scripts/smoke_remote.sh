#!/usr/bin/env bash
set -euo pipefail

APP_URL="${REMOTE_APP_URL:-}"
APP_HEALTH_PATH="${REMOTE_APP_HEALTH_PATH:-/}"
API_URL="${REMOTE_API_URL:-}"
API_HEALTH_PATH="${REMOTE_API_HEALTH_PATH:-/health}"
TIMEOUT_SECONDS="${REMOTE_SMOKE_TIMEOUT_SECONDS:-10}"
STRICT=0
FAILURES=0
CHECKS_RUN=0

usage() {
  cat <<'EOF'
Usage: smoke_remote.sh [options]

Generic remote post-deploy smoke probe for product repos that adopt agent-core.

Options:
  --app-url <url>           Primary app URL (default: REMOTE_APP_URL)
  --app-health-path <path>  App probe path (default: / or REMOTE_APP_HEALTH_PATH)
  --api-url <url>           API base URL (default: REMOTE_API_URL)
  --api-health-path <path>  API probe path (default: /health or REMOTE_API_HEALTH_PATH)
  --timeout <seconds>       Curl timeout per request (default: 10)
  --strict                  Exit non-zero on missing targets or failed probes
  -h, --help                Show this help text
EOF
}

build_url() {
  local base_url="$1"
  local probe_path="$2"
  local normalized_path="${probe_path}"
  if [[ -z "${normalized_path}" ]]; then
    normalized_path="/"
  elif [[ "${normalized_path}" != /* ]]; then
    normalized_path="/${normalized_path}"
  fi
  echo "${base_url%/}${normalized_path}"
}

record_missing() {
  local label="$1"
  if [[ "${STRICT}" == "1" ]]; then
    echo "[FAIL] Missing ${label} URL. Provide it with CLI args or REMOTE_* env vars." >&2
    FAILURES=$((FAILURES + 1))
  else
    echo "[WARN] Missing ${label} URL. Skipping that remote probe."
  fi
}

probe_url() {
  local label="$1"
  local base_url="$2"
  local probe_path="$3"

  if [[ -z "${base_url}" ]]; then
    record_missing "${label}"
    return
  fi

  local target_url
  target_url="$(build_url "${base_url}" "${probe_path}")"
  CHECKS_RUN=$((CHECKS_RUN + 1))
  echo "Checking ${label}: ${target_url}"
  if curl -fsS --max-time "${TIMEOUT_SECONDS}" "${target_url}" >/dev/null 2>&1; then
    echo "[OK] ${label} reachable"
    return
  fi

  if [[ "${STRICT}" == "1" ]]; then
    echo "[FAIL] ${label} not reachable at ${target_url}" >&2
    FAILURES=$((FAILURES + 1))
  else
    echo "[WARN] ${label} not reachable at ${target_url}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-url)
      [[ $# -lt 2 ]] && { echo "Error: --app-url requires a value." >&2; usage; exit 2; }
      APP_URL="$2"
      shift 2
      ;;
    --app-health-path)
      [[ $# -lt 2 ]] && { echo "Error: --app-health-path requires a value." >&2; usage; exit 2; }
      APP_HEALTH_PATH="$2"
      shift 2
      ;;
    --api-url)
      [[ $# -lt 2 ]] && { echo "Error: --api-url requires a value." >&2; usage; exit 2; }
      API_URL="$2"
      shift 2
      ;;
    --api-health-path)
      [[ $# -lt 2 ]] && { echo "Error: --api-health-path requires a value." >&2; usage; exit 2; }
      API_HEALTH_PATH="$2"
      shift 2
      ;;
    --timeout)
      [[ $# -lt 2 ]] && { echo "Error: --timeout requires a value." >&2; usage; exit 2; }
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --strict)
      STRICT=1
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

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

probe_url "app" "${APP_URL}" "${APP_HEALTH_PATH}"
probe_url "api" "${API_URL}" "${API_HEALTH_PATH}"

if [[ "${CHECKS_RUN}" == "0" && "${STRICT}" != "1" ]]; then
  echo "[WARN] No remote targets were configured."
fi

if [[ "${FAILURES}" -gt 0 ]]; then
  exit 1
fi

echo "Remote smoke completed."
