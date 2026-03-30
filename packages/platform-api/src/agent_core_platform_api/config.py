from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache


def _split_csv(value: str | None, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    public_api_base_url: str | None
    initial_org_name: str
    initial_org_slug: str
    cors_allow_origins: tuple[str, ...]
    auth_disabled: bool
    dev_user_id: str
    dev_username: str
    dev_roles: tuple[str, ...]
    api_token: str | None
    api_token_roles: tuple[str, ...]
    api_token_user_id: str
    api_token_username: str | None
    jwt_secret: str | None
    jwt_algorithms: tuple[str, ...]
    jwt_audiences: tuple[str, ...]
    jwt_issuers: tuple[str, ...]
    jwt_jwks_url: str | None
    jwt_jwks_path: str | None
    jwt_token_use: str | None
    jwt_cache_seconds: int
    entra_tenant_id: str | None
    role_claims: tuple[str, ...]
    role_mapping: dict[str, str]
    default_role: str
    auth_debug: bool
    crypto_seed: str
    allowed_repo_roots: tuple[str, ...]
    remote_execution_root: str
    runtime_provider: str
    runtime_provider_namespace: str
    orchestration_loop_enabled: bool
    orchestration_tick_interval_seconds: float
    orchestration_max_claims_per_tick: int
    runner_startup_timeout_seconds: int
    runner_heartbeat_timeout_seconds: int
    runner_approval_wait_timeout_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    role_mapping_raw = os.getenv("AGENT_CORE_ROLE_MAPPING", "{}")
    try:
        parsed_role_mapping = json.loads(role_mapping_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AGENT_CORE_ROLE_MAPPING must be valid JSON") from exc
    if not isinstance(parsed_role_mapping, dict):
        raise RuntimeError("AGENT_CORE_ROLE_MAPPING must be a JSON object")

    return Settings(
        app_name=os.getenv("AGENT_CORE_APP_NAME", "Agent Core Starter API"),
        database_url=os.getenv("AGENT_CORE_DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/orcha"),
        public_api_base_url=os.getenv("AGENT_CORE_PUBLIC_API_BASE_URL"),
        initial_org_name=os.getenv("AGENT_CORE_INITIAL_ORG_NAME", "Primary"),
        initial_org_slug=os.getenv("AGENT_CORE_INITIAL_ORG_SLUG", "primary"),
        cors_allow_origins=_split_csv(os.getenv("AGENT_CORE_CORS_ALLOW_ORIGINS")),
        auth_disabled=os.getenv("AGENT_CORE_AUTH_DISABLED", "1") == "1",
        dev_user_id=os.getenv("AGENT_CORE_DEV_USER_ID", "local-dev"),
        dev_username=os.getenv("AGENT_CORE_DEV_USERNAME", "local-dev@example.com"),
        dev_roles=_split_csv(os.getenv("AGENT_CORE_DEV_ROLES"), default=("admin",)),
        api_token=os.getenv("AGENT_CORE_API_TOKEN"),
        api_token_roles=_split_csv(os.getenv("AGENT_CORE_API_TOKEN_ROLES"), default=("worker",)),
        api_token_user_id=os.getenv("AGENT_CORE_API_TOKEN_USER_ID", "orcha-worker"),
        api_token_username=os.getenv("AGENT_CORE_API_TOKEN_USERNAME", "orcha-worker"),
        jwt_secret=os.getenv("AGENT_CORE_JWT_SECRET"),
        jwt_algorithms=_split_csv(os.getenv("AGENT_CORE_JWT_ALGORITHMS"), default=("HS256",)),
        jwt_audiences=_split_csv(
            os.getenv("AGENT_CORE_JWT_AUDIENCE") or os.getenv("AGENT_CORE_ENTRA_AUDIENCE")
        ),
        jwt_issuers=_split_csv(
            os.getenv("AGENT_CORE_JWT_ISSUER") or os.getenv("AGENT_CORE_ENTRA_ISSUER")
        ),
        jwt_jwks_url=os.getenv("AGENT_CORE_JWKS_URL"),
        jwt_jwks_path=os.getenv("AGENT_CORE_JWKS_PATH"),
        jwt_token_use=os.getenv("AGENT_CORE_JWT_TOKEN_USE"),
        jwt_cache_seconds=int(os.getenv("AGENT_CORE_JWKS_CACHE_SECONDS", "3600")),
        entra_tenant_id=os.getenv("AGENT_CORE_ENTRA_TENANT_ID"),
        role_claims=_split_csv(os.getenv("AGENT_CORE_ROLE_CLAIMS"), default=("roles", "groups")),
        role_mapping={str(key): str(value) for key, value in parsed_role_mapping.items()},
        default_role=os.getenv("AGENT_CORE_DEFAULT_ROLE", "viewer"),
        auth_debug=os.getenv("AGENT_CORE_AUTH_DEBUG", "0") == "1",
        crypto_seed=os.getenv("AGENT_CORE_CRYPTO_SEED", "agent-core-local-dev"),
        allowed_repo_roots=_split_csv(
            os.getenv("AGENT_CORE_ALLOWED_REPO_ROOTS") or os.getenv("AGENT_CORE_LOCAL_DEV_ROOT")
        ),
        remote_execution_root=os.getenv("AGENT_CORE_REMOTE_EXECUTION_ROOT", "./artifacts/remote-execution"),
        runtime_provider=os.getenv("AGENT_CORE_RUNTIME_PROVIDER", "aks"),
        runtime_provider_namespace=os.getenv("AGENT_CORE_RUNTIME_PROVIDER_NAMESPACE", "orcha-local"),
        orchestration_loop_enabled=os.getenv("AGENT_CORE_ORCHESTRATION_LOOP_ENABLED", "0") == "1",
        orchestration_tick_interval_seconds=float(os.getenv("AGENT_CORE_ORCHESTRATION_TICK_INTERVAL_SECONDS", "5")),
        orchestration_max_claims_per_tick=int(os.getenv("AGENT_CORE_ORCHESTRATION_MAX_CLAIMS_PER_TICK", "4")),
        runner_startup_timeout_seconds=int(os.getenv("AGENT_CORE_RUNNER_STARTUP_TIMEOUT_SECONDS", "120")),
        runner_heartbeat_timeout_seconds=int(os.getenv("AGENT_CORE_RUNNER_HEARTBEAT_TIMEOUT_SECONDS", "300")),
        runner_approval_wait_timeout_seconds=int(os.getenv("AGENT_CORE_RUNNER_APPROVAL_WAIT_TIMEOUT_SECONDS", "900")),
    )
