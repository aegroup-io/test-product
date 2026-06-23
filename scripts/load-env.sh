#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT_DIR}/scripts/deploy_common.sh"

ENVIRONMENT="dev"
MODE="remote"
FORCE="false"

usage() {
  cat <<'USAGE'
Usage: load-env.sh [options]

Generate repo-local env files from Terraform outputs for the selected environment.

Options:
  --env <name>     Environment suffix (default: dev)
  --mode <mode>    Env generation mode (supported: remote; default: remote)
  --force          Overwrite existing generated env files
  -h, --help       Show help
USAGE
}

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
    --mode)
      [[ $# -lt 2 ]] && { echo "Error: --mode requires a value." >&2; usage; exit 1; }
      MODE="$2"
      shift 2
      ;;
    --mode=*)
      MODE="${1#*=}"
      shift
      ;;
    --force)
      FORCE="true"
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

if [[ "${MODE}" != "remote" ]]; then
  echo "Error: only --mode remote is currently supported." >&2
  exit 1
fi

TF_WORKDIR="${ROOT_DIR}/infra/environments/${ENVIRONMENT}"
if [[ ! -d "${TF_WORKDIR}" ]]; then
  echo "Terraform environment not found: ${TF_WORKDIR}" >&2
  exit 1
fi
if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is required to generate env files." >&2
  exit 1
fi

if ! TF_OUTPUT="$(terraform -chdir="${TF_WORKDIR}" output -json 2>/dev/null)"; then
  echo "terraform output failed for ${TF_WORKDIR}. Run terraform init/apply first." >&2
  exit 1
fi
if [[ -z "${TF_OUTPUT}" ]]; then
  echo "terraform output returned no data for ${TF_WORKDIR}. Run terraform apply first." >&2
  exit 1
fi

KEY_VAULT_NAME="$(orcha_tf_output "${ROOT_DIR}" "${ENVIRONMENT}" "key_vault_name")"
ENTRA_TENANT_ID_FALLBACK="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.entra_tenant_id), "")')"
GRAPH_CLIENT_ID_FALLBACK="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.api_app_client_id), "")')"
GRAPH_CLIENT_SECRET_FALLBACK="$(orcha_tf_eval "${ROOT_DIR}" "${ENVIRONMENT}" 'try(tostring(data.terraform_remote_state.shared[0].outputs.api_app_client_secret), "")')"
RUNTIME_API_TOKEN_FALLBACK="$(orcha_key_vault_secret_value "${KEY_VAULT_NAME}" "agent-core-runtime-api-token")"

export ROOT_DIR
export ENVIRONMENT
export FORCE
export TF_OUTPUT
export KEY_VAULT_NAME
export ENTRA_TENANT_ID_FALLBACK
export GRAPH_CLIENT_ID_FALLBACK
export GRAPH_CLIENT_SECRET_FALLBACK
export RUNTIME_API_TOKEN_FALLBACK

python3 <<'PY'
import json
import os
import shutil
import subprocess
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
environment = os.environ["ENVIRONMENT"]
force = os.environ["FORCE"] == "true"
data = json.loads(os.environ["TF_OUTPUT"])


def val(key: str) -> str:
    raw = data.get(key, {})
    if isinstance(raw, dict):
        raw = raw.get("value")
    if raw is None:
        return ""
    return str(raw)


def render_env(path: Path, assignments: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return
    entries: dict[str, str] = {}
    order: list[str] = []
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key not in entries:
                order.append(key)
            entries[key] = value
    for key, value in assignments:
        if value == "":
            continue
        if key not in entries:
            order.append(key)
        entries[key] = value
    rendered = "\n".join(f"{key}={entries[key]}" for key in order if entries.get(key, "") != "").rstrip() + "\n"
    path.write_text(rendered, encoding="utf-8")


def resolve_entra_scope(client_id: str) -> str:
    if not client_id or shutil.which("az") is None:
        return ""
    result = subprocess.run(
        ["az", "ad", "app", "show", "--id", client_id, "-o", "json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        app = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    identifier_uris = app.get("identifierUris")
    if not isinstance(identifier_uris, list) or not identifier_uris:
        return ""
    scopes = ((app.get("api") or {}).get("oauth2PermissionScopes") or [])
    scope_value = ""
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        value = str(scope.get("value") or "")
        if value == "user_impersonation":
            scope_value = value
            break
        if value and not scope_value:
            scope_value = value
    if not scope_value:
        return ""
    return f"{str(identifier_uris[0]).rstrip('/')}/{scope_value}"


resource_group_name = val("resource_group_name")
aks_resource_group = val("aks_resource_group")
aks_cluster_name = val("aks_cluster_name")
aks_namespace = val("aks_namespace")
aks_api_service_name = val("aks_api_service_name")
aks_api_deployment_name = val("aks_api_deployment_name")
aks_api_service_account_name = val("aks_api_service_account_name")
aks_worker_deployment_name = val("aks_worker_deployment_name")
aks_worker_service_account_name = val("aks_worker_service_account_name")
acr_login_server = val("acr_login_server")
apim_resource_group_name = val("apim_resource_group_name")
apim_name = val("apim_name")
apim_api_id = val("apim_api_id")
apim_api_path = val("apim_api_path")
public_api_base_url = val("public_api_base_url")
database_url = val("postgres_database_url")
entra_tenant_id = val("entra_tenant_id") or os.environ.get("ENTRA_TENANT_ID_FALLBACK", "")
graph_client_id = val("graph_client_id") or os.environ.get("GRAPH_CLIENT_ID_FALLBACK", "")
graph_client_secret = val("graph_client_secret") or os.environ.get("GRAPH_CLIENT_SECRET_FALLBACK", "")
runtime_api_token = val("runtime_api_token") or os.environ.get("RUNTIME_API_TOKEN_FALLBACK", "")
app_service_name = val("app_service_name")
app_service_hostname = val("app_service_hostname")
web_public_url = val("web_public_url") or (f"https://{app_service_hostname}" if app_service_hostname else "")
entra_scope = resolve_entra_scope(graph_client_id)

scripts_env = [
    ("ORCHA_AZ_RESOURCE_GROUP", resource_group_name),
    ("ORCHA_AKS_RESOURCE_GROUP", aks_resource_group),
    ("ORCHA_AKS_CLUSTER_NAME", aks_cluster_name),
    ("ORCHA_AKS_NAMESPACE", aks_namespace),
    ("ORCHA_API_SERVICE_NAME", aks_api_service_name),
    ("ORCHA_API_DEPLOYMENT_NAME", aks_api_deployment_name),
    ("ORCHA_API_SERVICE_ACCOUNT_NAME", aks_api_service_account_name),
    ("ORCHA_WORKER_DEPLOYMENT_NAME", aks_worker_deployment_name),
    ("ORCHA_WORKER_SERVICE_ACCOUNT_NAME", aks_worker_service_account_name),
    ("ORCHA_ACR_LOGIN_SERVER", acr_login_server),
    ("ORCHA_APIM_RESOURCE_GROUP", apim_resource_group_name),
    ("ORCHA_APIM_NAME", apim_name),
    ("ORCHA_APIM_API_ID", apim_api_id),
    ("ORCHA_APIM_API_PATH", apim_api_path),
    ("ORCHA_PUBLIC_API_BASE_URL", public_api_base_url),
    ("ORCHA_KEY_VAULT_NAME", os.environ.get("KEY_VAULT_NAME", "")),
    ("ORCHA_DATABASE_URL", database_url),
    ("ORCHA_ENTRA_TENANT_ID", entra_tenant_id),
    ("ORCHA_GRAPH_CLIENT_ID", graph_client_id),
    ("ORCHA_GRAPH_CLIENT_SECRET", graph_client_secret),
    ("ORCHA_RUNTIME_API_TOKEN", runtime_api_token),
    ("ORCHA_WEB_APP_NAME", app_service_name),
    ("ORCHA_WEB_APP_HOSTNAME", app_service_hostname),
]
api_env = [
    ("AGENT_CORE_DATABASE_URL", database_url),
    ("AGENT_CORE_PUBLIC_API_BASE_URL", public_api_base_url),
    ("AGENT_CORE_API_TOKEN", runtime_api_token),
    ("AGENT_CORE_API_TOKEN_ROLES", "worker"),
    ("AGENT_CORE_ORCHESTRATION_LOOP_ENABLED", "1"),
    ("AGENT_CORE_ENTRA_TENANT_ID", entra_tenant_id),
    ("AGENT_CORE_GRAPH_CLIENT_ID", graph_client_id),
    ("AGENT_CORE_GRAPH_CLIENT_SECRET", graph_client_secret),
    ("AGENT_CORE_GRAPH_TENANT_ID", entra_tenant_id),
]
worker_env = [
    ("AGENT_CORE_API_TOKEN", runtime_api_token),
    ("AGENT_CORE_LIVE_RUNNER_ENABLED", "1"),
]
web_env = [
    ("VITE_API_BASE_URL", public_api_base_url),
    ("VITE_ENTRA_CLIENT_ID", graph_client_id),
    ("VITE_ENTRA_TENANT_ID", entra_tenant_id),
    ("VITE_ENTRA_SCOPE", entra_scope),
    ("VITE_ENTRA_REDIRECT_URI", web_public_url),
    ("VITE_ENTRA_SILENT_REDIRECT_URI", f"{web_public_url.rstrip('/')}/auth/silent.html" if web_public_url else ""),
    ("VITE_AUTH_FLOW", "redirect"),
]

render_env(root / "scripts" / f".env.{environment}", scripts_env)
render_env(root / "api" / f".env.{environment}", api_env)
render_env(root / "worker" / f".env.{environment}", worker_env)
render_env(root / "web" / f".env.{environment}", web_env)
PY

echo "Generated env files for ${ENVIRONMENT}:"
echo "- scripts/.env.${ENVIRONMENT}"
echo "- api/.env.${ENVIRONMENT}"
echo "- worker/.env.${ENVIRONMENT}"
echo "- web/.env.${ENVIRONMENT}"
