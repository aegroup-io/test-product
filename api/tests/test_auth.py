from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from jose import jwt

from agent_core_platform_api import auth
from agent_core_platform_api.auth import get_current_user
from agent_core_platform_api.config import get_settings


def _request_with_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode("utf-8"))],
        }
    )


def _b64url(value: int) -> str:
    width = (value.bit_length() + 7) // 8
    raw = value.to_bytes(width, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_get_current_user_supports_hmac_bearer_tokens(monkeypatch) -> None:
    auth.JWKS_CACHE["keys"] = None
    auth.JWKS_CACHE["expires_at"] = 0.0
    get_settings.cache_clear()
    monkeypatch.setenv("AGENT_CORE_AUTH_DISABLED", "0")
    monkeypatch.setenv("AGENT_CORE_JWT_SECRET", "super-secret")
    monkeypatch.setenv("AGENT_CORE_JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("AGENT_CORE_JWT_AUDIENCE", "orcha-api")
    monkeypatch.setenv("AGENT_CORE_JWT_ISSUER", "https://issuer.example.com")

    token = jwt.encode(
        {
            "sub": "user-123",
            "preferred_username": "user@example.com",
            "roles": ["admin"],
            "aud": "orcha-api",
            "iss": "https://issuer.example.com",
        },
        "super-secret",
        algorithm="HS256",
    )

    try:
        current_user = get_current_user(_request_with_token(token))
    finally:
        get_settings.cache_clear()

    assert current_user.user_id == "user-123"
    assert current_user.username == "user@example.com"
    assert current_user.roles == {"admin"}


def test_get_current_user_supports_internal_api_token(monkeypatch) -> None:
    auth.JWKS_CACHE["keys"] = None
    auth.JWKS_CACHE["expires_at"] = 0.0
    get_settings.cache_clear()
    monkeypatch.setenv("AGENT_CORE_AUTH_DISABLED", "0")
    monkeypatch.setenv("AGENT_CORE_API_TOKEN", "shared-worker-token")
    monkeypatch.setenv("AGENT_CORE_API_TOKEN_ROLES", "worker")
    monkeypatch.setenv("AGENT_CORE_API_TOKEN_USER_ID", "worker-service")
    monkeypatch.setenv("AGENT_CORE_API_TOKEN_USERNAME", "worker-service")

    try:
        current_user = get_current_user(_request_with_token("shared-worker-token"))
    finally:
        get_settings.cache_clear()

    assert current_user.user_id == "worker-service"
    assert current_user.username == "worker-service"
    assert current_user.roles == {"worker"}


def test_get_current_user_supports_jwks_backed_entra_tokens(monkeypatch) -> None:
    auth.JWKS_CACHE["keys"] = None
    auth.JWKS_CACHE["expires_at"] = 0.0
    get_settings.cache_clear()
    tenant_id = "12cc0497-fc4a-4b20-918f-8bbcb9e9cc69"
    audience = "api://12cc0497-fc4a-4b20-918f-8bbcb9e9cc69/dbt-miner-api-dev"
    issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test-key",
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(public_numbers.n),
                "e": _b64url(public_numbers.e),
            }
        ]
    }

    monkeypatch.setenv("AGENT_CORE_AUTH_DISABLED", "0")
    monkeypatch.setenv("AGENT_CORE_JWT_ALGORITHMS", "RS256")
    monkeypatch.setenv("AGENT_CORE_ENTRA_TENANT_ID", tenant_id)
    monkeypatch.setenv("AGENT_CORE_JWT_AUDIENCE", audience)
    monkeypatch.delenv("AGENT_CORE_JWT_SECRET", raising=False)
    monkeypatch.setattr(auth, "_load_jwks", lambda settings: jwks)

    token = jwt.encode(
        {
            "oid": "entra-user-123",
            "preferred_username": "tyler@example.com",
            "roles": ["admin"],
            "aud": audience,
            "iss": issuer,
            "tid": tenant_id,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    try:
        current_user = get_current_user(_request_with_token(token))
    finally:
        get_settings.cache_clear()

    assert current_user.user_id == "entra-user-123"
    assert current_user.username == "tyler@example.com"
    assert current_user.roles == {"admin"}
