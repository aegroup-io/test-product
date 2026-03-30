from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_core_platform_api import rbac
from agent_core_platform_api.graph_users import GraphUser, get_user, lookup_users, search_users
from agent_core_platform_api.schemas import (
    UserLookupRequest,
    UserLookupResponse,
    UserResponse,
    UserSearchResponse,
)


router = APIRouter()


def _require_user_admin(permissions: rbac.PermissionContext) -> None:
    if not permissions.has("org.members.manage"):
        raise HTTPException(status_code=403, detail="User lookup not permitted")


def _to_response(user: GraphUser) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
    )


def _handle_graph_error(err: Exception) -> HTTPException:
    detail = "User lookup failed. Ensure Microsoft Graph credentials are configured."
    return HTTPException(status_code=503, detail=detail)


@router.get("/users", response_model=UserSearchResponse)
def search_users_route(
    query: str | None = Query(default=None, alias="query"),
    limit: int = Query(default=25, ge=1, le=60),
    next_token: str | None = Query(default=None, alias="next_token"),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> UserSearchResponse:
    _require_user_admin(permissions)
    try:
        users, pagination_token = search_users(query=query, limit=limit, next_token=next_token)
    except Exception as err:  # noqa: BLE001
        raise _handle_graph_error(err) from err
    return UserSearchResponse(
        users=[_to_response(user) for user in users],
        next_token=pagination_token,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user_detail(
    user_id: str,
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> UserResponse:
    _require_user_admin(permissions)
    try:
        user = get_user(user_id=user_id)
    except Exception as err:  # noqa: BLE001
        raise _handle_graph_error(err) from err
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_response(user)


@router.post("/users/lookup", response_model=UserLookupResponse)
def lookup_users_route(
    payload: UserLookupRequest,
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> UserLookupResponse:
    _require_user_admin(permissions)
    try:
        users = lookup_users(payload.user_ids)
    except Exception as err:  # noqa: BLE001
        raise _handle_graph_error(err) from err
    return UserLookupResponse(users=[_to_response(user) for user in users])
