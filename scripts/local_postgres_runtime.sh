#!/usr/bin/env bash

agent_core_apply_local_postgres_contract() {
  local fallback_name

  fallback_name="$(printf '%s\n' "${AGENT_CORE_PRODUCT_KEY:-$(agent_core_product_factory_field "product.key" "agent-core")}" \
    | tr '[:upper:]' '[:lower:]' \
    | tr '-' '_' \
    | tr -cd '[:alnum:]_\n' \
    | sed -E 's/_+/_/g; s/^_+//; s/_+$//' \
    | cut -c1-63)"
  if [[ -z "${fallback_name}" ]]; then
    fallback_name="agent_core"
  fi

  export AGENT_CORE_LOCAL_DATABASE_HOST="${AGENT_CORE_LOCAL_DATABASE_HOST:-127.0.0.1}"
  export AGENT_CORE_LOCAL_DATABASE_PORT="${AGENT_CORE_LOCAL_DATABASE_PORT:-5432}"
  export AGENT_CORE_LOCAL_DATABASE_NAME="${AGENT_CORE_LOCAL_DATABASE_NAME:-${fallback_name}}"
  export AGENT_CORE_LOCAL_DATABASE_USER="${AGENT_CORE_LOCAL_DATABASE_USER:-postgres}"
  export AGENT_CORE_LOCAL_DATABASE_PASSWORD="${AGENT_CORE_LOCAL_DATABASE_PASSWORD:-postgres}"
  export AGENT_CORE_LOCAL_DATABASE_URL="${AGENT_CORE_LOCAL_DATABASE_URL:-postgresql+psycopg://${AGENT_CORE_LOCAL_DATABASE_USER}:${AGENT_CORE_LOCAL_DATABASE_PASSWORD}@${AGENT_CORE_LOCAL_DATABASE_HOST}:${AGENT_CORE_LOCAL_DATABASE_PORT}/${AGENT_CORE_LOCAL_DATABASE_NAME}}"
  export AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME="${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME:-agent-core-pg-${AGENT_CORE_WORKTREE_NAMESPACE}}"
  export AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME="${AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME:-agent-core-pg-data-${AGENT_CORE_WORKTREE_NAMESPACE}}"
}

agent_core_require_local_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required for the default local Postgres runtime. Install Docker Desktop or set AGENT_CORE_DATABASE_URL to an existing Postgres instance." >&2
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker is installed but the daemon is unavailable. Start Docker Desktop or set AGENT_CORE_DATABASE_URL to an existing Postgres instance." >&2
    return 1
  fi
}

agent_core_local_postgres_exists() {
  docker container inspect "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" >/dev/null 2>&1
}

agent_core_local_postgres_running() {
  [[ "$(docker container inspect -f '{{.State.Running}}' "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" 2>/dev/null || true)" == "true" ]]
}

agent_core_ensure_local_postgres_database() {
  local exists_output

  exists_output="$(docker exec "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" \
    psql -U "${AGENT_CORE_LOCAL_DATABASE_USER}" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '${AGENT_CORE_LOCAL_DATABASE_NAME}'" 2>/dev/null \
    | tr -d '[:space:]')"
  if [[ "${exists_output}" == "1" ]]; then
    return 0
  fi

  docker exec "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" \
    psql -U "${AGENT_CORE_LOCAL_DATABASE_USER}" -d postgres -v ON_ERROR_STOP=1 -c \
    "CREATE DATABASE \"${AGENT_CORE_LOCAL_DATABASE_NAME}\"" >/dev/null
}

agent_core_wait_for_local_postgres() {
  local timeout_seconds="${AGENT_CORE_LOCAL_DATABASE_START_TIMEOUT_SECONDS:-60}"
  local attempt=0

  echo -n "Waiting for local Postgres"
  while [[ "${attempt}" -lt "${timeout_seconds}" ]]; do
    if docker exec "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" \
      pg_isready -U "${AGENT_CORE_LOCAL_DATABASE_USER}" -d postgres >/dev/null 2>&1; then
      if agent_core_ensure_local_postgres_database >/dev/null 2>&1; then
        if docker exec "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" \
          pg_isready -U "${AGENT_CORE_LOCAL_DATABASE_USER}" -d "${AGENT_CORE_LOCAL_DATABASE_NAME}" >/dev/null 2>&1; then
          echo ""
          return 0
        fi
      fi
    fi
    printf '.'
    sleep 1
    attempt=$((attempt + 1))
  done

  echo ""
  return 1
}

agent_core_start_local_postgres() {
  agent_core_apply_local_postgres_contract
  agent_core_require_local_docker || return 1

  docker volume create "${AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME}" >/dev/null 2>&1 || true

  if agent_core_local_postgres_exists; then
    if ! agent_core_local_postgres_running; then
      docker start "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" >/dev/null
    fi
  else
    docker run --detach \
      --name "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" \
      --publish "${AGENT_CORE_LOCAL_DATABASE_PORT}:5432" \
      --env "POSTGRES_USER=${AGENT_CORE_LOCAL_DATABASE_USER}" \
      --env "POSTGRES_PASSWORD=${AGENT_CORE_LOCAL_DATABASE_PASSWORD}" \
      --env "POSTGRES_DB=${AGENT_CORE_LOCAL_DATABASE_NAME}" \
      --mount "type=volume,src=${AGENT_CORE_LOCAL_DATABASE_VOLUME_NAME},dst=/var/lib/postgresql/data" \
      postgres:16 >/dev/null
  fi

  if ! agent_core_wait_for_local_postgres; then
    echo "Local Postgres did not become ready. Check: docker logs ${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" >&2
    return 1
  fi

  echo "Local Postgres ready at ${AGENT_CORE_LOCAL_DATABASE_HOST}:${AGENT_CORE_LOCAL_DATABASE_PORT}/${AGENT_CORE_LOCAL_DATABASE_NAME}"
}

agent_core_stop_local_postgres() {
  agent_core_apply_local_postgres_contract

  if ! command -v docker >/dev/null 2>&1; then
    echo "[INFO] postgres: docker not installed; skipping local Postgres stop"
    return 0
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "[WARN] postgres: docker daemon unavailable; leaving local Postgres state untouched" >&2
    return 1
  fi
  if ! agent_core_local_postgres_exists; then
    echo "[INFO] postgres: no tracked container for namespace ${AGENT_CORE_WORKTREE_NAMESPACE}"
    return 0
  fi
  if ! agent_core_local_postgres_running; then
    echo "[INFO] postgres: container ${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME} is already stopped"
    return 0
  fi

  docker stop "${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}" >/dev/null
  echo "[OK] postgres: stopped ${AGENT_CORE_LOCAL_DATABASE_CONTAINER_NAME}"
}
