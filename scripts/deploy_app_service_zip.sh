#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-}"
ZIP_PATH="${ZIP_PATH:-}"
STAGING_DIR="${STAGING_DIR:-}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
APP_NAME="${APP_NAME:-}"
APP_HOSTNAME="${APP_HOSTNAME:-}"
DEPLOY_TRACK_STATUS="true"
DEPLOY_ASYNC="false"
NO_DEPLOY=0
DRY_RUN=0
INCLUDE_FILES=()

usage() {
  cat <<'EOF'
Usage: deploy_app_service_zip.sh [options]

Package a directory into an App Service zip artifact and optionally deploy it with Azure CLI.

Options:
  --source-dir <path>      Directory to package
  --include-file <path>    Extra file to copy into the zip root (repeatable)
  --zip <path>             Zip output path (default: /tmp/app-service-package.zip)
  --staging-dir <path>     Staging directory (default: /tmp/app-service-package)
  --resource-group <name>  Azure resource group for deployment
  --app-name <name>        Azure App Service name for deployment
  --hostname <host>        Optional hostname to echo after deploy
  --no-deploy              Package only; do not call az webapp deploy
  --no-wait                Do not wait for app startup during deploy
  --dry-run                Print planned commands without executing them
  -h, --help               Show this help text
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-dir)
      [[ $# -lt 2 ]] && { echo "Error: --source-dir requires a value." >&2; usage; exit 2; }
      SOURCE_DIR="$2"
      shift 2
      ;;
    --source-dir=*)
      SOURCE_DIR="${1#*=}"
      shift
      ;;
    --include-file)
      [[ $# -lt 2 ]] && { echo "Error: --include-file requires a value." >&2; usage; exit 2; }
      INCLUDE_FILES+=("$2")
      shift 2
      ;;
    --include-file=*)
      INCLUDE_FILES+=("${1#*=}")
      shift
      ;;
    --zip)
      [[ $# -lt 2 ]] && { echo "Error: --zip requires a value." >&2; usage; exit 2; }
      ZIP_PATH="$2"
      shift 2
      ;;
    --zip=*)
      ZIP_PATH="${1#*=}"
      shift
      ;;
    --staging-dir)
      [[ $# -lt 2 ]] && { echo "Error: --staging-dir requires a value." >&2; usage; exit 2; }
      STAGING_DIR="$2"
      shift 2
      ;;
    --staging-dir=*)
      STAGING_DIR="${1#*=}"
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
    --app-name)
      [[ $# -lt 2 ]] && { echo "Error: --app-name requires a value." >&2; usage; exit 2; }
      APP_NAME="$2"
      shift 2
      ;;
    --app-name=*)
      APP_NAME="${1#*=}"
      shift
      ;;
    --hostname)
      [[ $# -lt 2 ]] && { echo "Error: --hostname requires a value." >&2; usage; exit 2; }
      APP_HOSTNAME="$2"
      shift 2
      ;;
    --hostname=*)
      APP_HOSTNAME="${1#*=}"
      shift
      ;;
    --no-deploy)
      NO_DEPLOY=1
      shift
      ;;
    --no-wait)
      DEPLOY_TRACK_STATUS="false"
      DEPLOY_ASYNC="true"
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

ZIP_PATH="${ZIP_PATH:-/tmp/app-service-package.zip}"
STAGING_DIR="${STAGING_DIR:-/tmp/app-service-package}"

if [[ -z "${SOURCE_DIR}" ]]; then
  echo "Error: --source-dir is required." >&2
  exit 2
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Source directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

if (( ${#INCLUDE_FILES[@]} > 0 )); then
  for include_path in "${INCLUDE_FILES[@]}"; do
    if [[ ! -f "${include_path}" ]]; then
      echo "Include file not found: ${include_path}" >&2
      exit 1
    fi
  done
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  run_or_print rm -rf "${STAGING_DIR}"
  run_or_print mkdir -p "${STAGING_DIR}"
  run_or_print cp -R "${SOURCE_DIR}/." "${STAGING_DIR}/"
  if (( ${#INCLUDE_FILES[@]} > 0 )); then
    for include_path in "${INCLUDE_FILES[@]}"; do
      run_or_print cp "${include_path}" "${STAGING_DIR}/$(basename "${include_path}")"
    done
  fi
  run_or_print python3 -c "print('zip ${STAGING_DIR} to ${ZIP_PATH}')"
  if [[ "${NO_DEPLOY}" != "1" ]]; then
    run_or_print az webapp deploy \
      --resource-group "${RESOURCE_GROUP}" \
      --name "${APP_NAME}" \
      --type zip \
      --src-path "${ZIP_PATH}" \
      --track-status "${DEPLOY_TRACK_STATUS}" \
      --async "${DEPLOY_ASYNC}"
  fi
  exit 0
fi

rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"
cp -R "${SOURCE_DIR}/." "${STAGING_DIR}/"
if (( ${#INCLUDE_FILES[@]} > 0 )); then
  for include_path in "${INCLUDE_FILES[@]}"; do
    cp "${include_path}" "${STAGING_DIR}/$(basename "${include_path}")"
  done
fi

mkdir -p "$(dirname "${ZIP_PATH}")"
rm -f "${ZIP_PATH}"
PACKAGE_ROOT="${STAGING_DIR}" PACKAGE_ZIP="${ZIP_PATH}" python3 <<'PY'
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

package_root = Path(os.environ["PACKAGE_ROOT"]).resolve()
package_zip = Path(os.environ["PACKAGE_ZIP"]).resolve()

with ZipFile(package_zip, "w", ZIP_DEFLATED) as archive:
    for path in sorted(package_root.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(package_root))
PY

echo "Packaged App Service zip: ${ZIP_PATH}"

if [[ "${NO_DEPLOY}" == "1" ]]; then
  exit 0
fi

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI is required to deploy App Service zips." >&2
  exit 1
fi

if [[ -z "${RESOURCE_GROUP}" || -z "${APP_NAME}" ]]; then
  echo "Missing resource group or app name. Pass --resource-group and --app-name." >&2
  exit 1
fi

run_or_print az webapp deploy \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${APP_NAME}" \
  --type zip \
  --src-path "${ZIP_PATH}" \
  --track-status "${DEPLOY_TRACK_STATUS}" \
  --async "${DEPLOY_ASYNC}"

if [[ -n "${APP_HOSTNAME}" ]]; then
  echo "Deployed: https://${APP_HOSTNAME}"
fi
