from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Iterable

import httpx


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


@dataclass
class GraphUser:
    user_id: str
    username: str | None
    email: str | None
    display_name: str | None
    status: str | None


_token_cache: dict[str, float | str | None] = {
    "token": None,
    "expires_at": 0.0,
}


def _get_graph_config() -> tuple[str, str, str]:
    client_id = os.getenv("AGENT_CORE_GRAPH_CLIENT_ID")
    client_secret = os.getenv("AGENT_CORE_GRAPH_CLIENT_SECRET")
    tenant_id = os.getenv("AGENT_CORE_GRAPH_TENANT_ID") or os.getenv("AGENT_CORE_ENTRA_TENANT_ID")
    if not client_id or not client_secret or not tenant_id:
        raise RuntimeError("Graph client credentials are not configured")
    return client_id, client_secret, tenant_id


def _get_graph_token() -> str:
    cached_token = _token_cache.get("token")
    expires_at = float(_token_cache.get("expires_at") or 0)
    now = time.time()
    if isinstance(cached_token, str) and now < expires_at - 30:
        return cached_token

    client_id, client_secret, tenant_id = _get_graph_config()
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    with httpx.Client(timeout=10) as client:
        response = client.post(token_url, data=data)
        response.raise_for_status()
        payload = response.json()

    access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3600))
    if not access_token:
        raise RuntimeError("Failed to obtain Graph access token")

    _token_cache["token"] = access_token
    _token_cache["expires_at"] = now + expires_in
    return access_token


def _escape_filter(value: str) -> str:
    return value.replace("'", "''")


def _build_user(payload: dict) -> GraphUser:
    user_id = str(payload.get("id") or "")
    display_name = payload.get("displayName")
    email = payload.get("mail")
    username = payload.get("userPrincipalName") or payload.get("mail")
    account_enabled = payload.get("accountEnabled")
    status = "Enabled" if account_enabled is True else "Disabled" if account_enabled is False else None
    return GraphUser(
        user_id=user_id,
        username=username,
        email=email,
        display_name=display_name,
        status=status,
    )


def search_users(
    query: str | None,
    limit: int,
    next_token: str | None,
) -> tuple[list[GraphUser], str | None]:
    token = _get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}

    if next_token:
        url = next_token
        params: dict[str, str] | None = None
    else:
        url = f"{GRAPH_BASE_URL}/users"
        params = {
            "$top": str(limit),
            "$select": "id,displayName,mail,userPrincipalName,accountEnabled",
        }
        if query:
            escaped = _escape_filter(query)
            params["$filter"] = (
                "startswith(displayName,'{value}') or "
                "startswith(userPrincipalName,'{value}') or "
                "startswith(mail,'{value}')"
            ).format(value=escaped)

    with httpx.Client(timeout=10) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()

    users = [_build_user(item) for item in payload.get("value", [])]
    next_link = payload.get("@odata.nextLink")
    return users, next_link


def get_user(user_id: str) -> GraphUser | None:
    token = _get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE_URL}/users/{user_id}"
    params = {"$select": "id,displayName,mail,userPrincipalName,accountEnabled"}
    with httpx.Client(timeout=10) as client:
        response = client.get(url, headers=headers, params=params)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return _build_user(response.json())


def lookup_users(user_ids: Iterable[str]) -> list[GraphUser]:
    results: list[GraphUser] = []
    for user_id in user_ids:
        user = get_user(user_id)
        if user:
            results.append(user)
    return results
