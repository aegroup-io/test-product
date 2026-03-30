from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, Request, status
from jose import JWTError, jwk, jwt

from agent_core_platform_api.config import Settings, get_settings


JWKS_CACHE: dict[str, Any] = {"keys": None, "expires_at": 0.0}
LOGGER = logging.getLogger("uvicorn.error")

ROLE_ALIASES = {
    "administrator": "admin",
    "admin": "admin",
    "analyst": "analyst",
    "org_admin": "org_admin",
    "organization_admin": "org_admin",
    "developer": "analyst",
    "dev": "analyst",
    "viewer": "viewer",
}


@dataclass(frozen=True)
class UserContext:
    user_id: str
    username: str | None
    roles: set[str]
    claims: dict[str, Any]


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower().replace("-", "_").replace(" ", "_")
    return ROLE_ALIASES.get(normalized, normalized)


def _normalized_issuers(settings: Settings) -> tuple[str, ...]:
    issuers = list(settings.jwt_issuers)
    if settings.entra_tenant_id:
        defaults = [
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
            f"https://sts.windows.net/{settings.entra_tenant_id}/",
        ]
        for issuer in defaults:
            if issuer not in issuers:
                issuers.append(issuer)
    return tuple(issuers)


def _jwks_url(settings: Settings) -> str | None:
    if settings.jwt_jwks_url:
        return settings.jwt_jwks_url
    if settings.entra_tenant_id:
        return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/discovery/v2.0/keys"
    return None


def _parse_roles(claims: dict[str, Any]) -> set[str]:
    settings = get_settings()
    roles: set[str] = set()
    for claim in settings.role_claims:
        value = claims.get(claim)
        if isinstance(value, str):
            roles.add(_normalize_role(value))
        elif isinstance(value, list):
            roles.update(_normalize_role(str(item)) for item in value if str(item).strip())
    if settings.role_mapping:
        roles = {_normalize_role(settings.role_mapping.get(role, role)) for role in roles}
    if settings.default_role and not roles:
        roles.add(_normalize_role(settings.default_role))
    return roles


def _build_user_context(claims: dict[str, Any]) -> UserContext:
    user_id = str(
        claims.get("oid")
        or claims.get("sub")
        or claims.get("user_id")
        or claims.get("preferred_username")
        or claims.get("upn")
        or "unknown"
    )
    username = (
        claims.get("name")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("unique_name")
        or claims.get("email")
    )
    return UserContext(
        user_id=user_id,
        username=str(username) if username else None,
        roles=_parse_roles(claims),
        claims=claims,
    )


def _shared_api_token_user(settings: Settings) -> UserContext | None:
    token = settings.api_token.strip() if settings.api_token else ""
    if not token:
        return None
    return UserContext(
        user_id=settings.api_token_user_id,
        username=settings.api_token_username,
        roles={_normalize_role(role) for role in settings.api_token_roles if role.strip()},
        claims={"mode": "api-token"},
    )


def _load_jwks(settings: Settings) -> dict[str, Any]:
    now = time.time()
    if JWKS_CACHE["keys"] and JWKS_CACHE["expires_at"] > now:
        return JWKS_CACHE["keys"]

    if settings.jwt_jwks_path:
        data = json.loads(Path(settings.jwt_jwks_path).read_text(encoding="utf-8"))
    else:
        jwks_url = _jwks_url(settings)
        if not jwks_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT issuer or JWKS URL must be configured",
            )
        response = httpx.get(jwks_url, timeout=5)
        response.raise_for_status()
        data = response.json()

    JWKS_CACHE["keys"] = data
    JWKS_CACHE["expires_at"] = now + settings.jwt_cache_seconds
    return data


def _get_signing_key(token: str, settings: Settings):
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
    except Exception as exc:  # pragma: no cover - jose can raise non-JWTError values here
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc

    algorithm = header.get("alg")
    if algorithm not in settings.jwt_algorithms:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token algorithm")

    if isinstance(algorithm, str) and algorithm.startswith("HS"):
        if not settings.jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AGENT_CORE_JWT_SECRET must be configured for HMAC bearer tokens",
            )
        return settings.jwt_secret

    jwks = _load_jwks(settings)
    keys = jwks.get("keys", [])
    key_id = header.get("kid")
    jwk_data = None
    if key_id:
        jwk_data = next((key for key in keys if key.get("kid") == key_id), None)
    elif len(keys) == 1:
        jwk_data = keys[0]

    if not jwk_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signing key not found")

    key = jwk.construct(jwk_data, algorithm)
    return key.to_pem().decode("utf-8")


def _decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    key = _get_signing_key(token, settings)
    audiences = settings.jwt_audiences
    issuers = _normalized_issuers(settings)
    audience_for_decode = audiences[0] if len(audiences) == 1 else None

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=list(settings.jwt_algorithms),
            audience=audience_for_decode,
            issuer=None,
            options={"verify_aud": bool(audience_for_decode), "verify_iss": False},
        )
    except JWTError as exc:
        if settings.auth_debug:
            try:
                unverified = jwt.get_unverified_claims(token)
                LOGGER.warning(
                    "JWT validation failed: %s (aud=%s iss=%s tid=%s)",
                    exc,
                    unverified.get("aud"),
                    unverified.get("iss"),
                    unverified.get("tid"),
                )
            except Exception:
                LOGGER.warning("JWT validation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc

    if audiences:
        claim_aud = claims.get("aud")
        if isinstance(claim_aud, list):
            aud_values = {str(value) for value in claim_aud}
        elif claim_aud is not None:
            aud_values = {str(claim_aud)}
        else:
            aud_values = set()
        if not aud_values.intersection(audiences):
            if settings.auth_debug:
                LOGGER.warning("JWT audience mismatch: %s not in %s", aud_values, audiences)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token audience")

    if issuers:
        claim_issuer = str(claims.get("iss", "")).rstrip("/")
        normalized_issuers = {issuer.rstrip("/") for issuer in issuers}
        if claim_issuer not in normalized_issuers:
            if settings.auth_debug:
                LOGGER.warning("JWT issuer mismatch: %s not in %s", claim_issuer, normalized_issuers)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")

    if settings.jwt_token_use and claims.get("token_use") != settings.jwt_token_use:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token use")

    if settings.entra_tenant_id and claims.get("tid") != settings.entra_tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid tenant")

    user = _build_user_context(claims)
    if settings.auth_debug:
        LOGGER.info(
            "JWT roles parsed=%s claim_roles=%s claim_groups=%s claim_scp=%s claim_aud=%s claim_iss=%s",
            sorted(user.roles),
            claims.get("roles"),
            claims.get("groups"),
            claims.get("scp"),
            claims.get("aud"),
            claims.get("iss"),
        )
    return claims


def get_current_user(request: Request) -> UserContext:
    settings = get_settings()
    if settings.auth_disabled:
        return UserContext(
            user_id=settings.dev_user_id,
            username=settings.dev_username,
            roles={_normalize_role(role) for role in settings.dev_roles},
            claims={"mode": "local-dev"},
        )

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    shared_api_user = _shared_api_token_user(settings)
    if shared_api_user is not None and token == (settings.api_token or "").strip():
        return shared_api_user
    return _build_user_context(_decode_token(token))
