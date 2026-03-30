from __future__ import annotations

from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent_core_platform_api.db import get_session
from agent_core_platform_api.models import AIModel, AIProvider, Secret
from agent_core_platform_api.rbac import PERM_AI_MANAGE, PermissionContext, get_permission_context
from agent_core_platform_api.schemas import (
    AIModelCreateRequest,
    AIModelResponse,
    AIModelTestResponse,
    AIModelUpdateRequest,
    AIProviderCreateRequest,
    AIProviderResponse,
    AIProviderUpdateRequest,
)
from agent_core_platform_api.secret_crypto import SecretCryptoError, decrypt_secret


router = APIRouter(prefix="/ai")

VALID_PROVIDER_TYPES = {"anthropic", "azure_openai", "openai"}


def _ensure_ai_manage(permissions: PermissionContext) -> None:
    if not permissions.has(PERM_AI_MANAGE):
        raise HTTPException(status_code=403, detail="AI registry access denied")


def _normalize_provider_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_PROVIDER_TYPES:
        allowed = ", ".join(sorted(VALID_PROVIDER_TYPES))
        raise HTTPException(status_code=422, detail=f"Unsupported provider type. Expected one of: {allowed}")
    return normalized


def _required_str(config: dict[str, Any], key: str, *, provider_type: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise HTTPException(status_code=422, detail=f"Provider '{provider_type}' requires config.{key}")


def _optional_str(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _required_secret_id(
    session: Session,
    config: dict[str, Any],
    key: str,
    *,
    provider_type: str,
) -> str:
    raw = config.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(status_code=422, detail=f"Provider '{provider_type}' requires config.{key}")
    try:
        secret_id = UUID(raw.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid secret id for config.{key}") from exc
    secret = session.get(Secret, secret_id)
    if secret is None:
        raise HTTPException(status_code=422, detail=f"Secret not found for config.{key}")
    if secret.kind != "ai_api_key":
        raise HTTPException(status_code=422, detail="Provider API key secret must be kind 'ai_api_key'")
    return str(secret_id)


def _normalize_provider_config(session: Session, provider_type: str, config: dict[str, Any] | None) -> dict[str, Any]:
    candidate = config if isinstance(config, dict) else {}
    if provider_type == "openai":
        normalized: dict[str, Any] = {
            "api_key_secret_id": _required_secret_id(
                session,
                candidate,
                "api_key_secret_id",
                provider_type=provider_type,
            ),
            "base_url": _optional_str(candidate, "base_url") or "https://api.openai.com/v1",
        }
        organization = _optional_str(candidate, "organization")
        if organization:
            normalized["organization"] = organization
        return normalized

    if provider_type == "azure_openai":
        return {
            "api_key_secret_id": _required_secret_id(
                session,
                candidate,
                "api_key_secret_id",
                provider_type=provider_type,
            ),
            "endpoint": _required_str(candidate, "endpoint", provider_type=provider_type),
            "api_version": _required_str(candidate, "api_version", provider_type=provider_type),
        }

    if provider_type == "anthropic":
        normalized = {
            "api_key_secret_id": _required_secret_id(
                session,
                candidate,
                "api_key_secret_id",
                provider_type=provider_type,
            ),
            "base_url": _optional_str(candidate, "base_url") or "https://api.anthropic.com",
        }
        anthropic_version = _optional_str(candidate, "anthropic_version")
        if anthropic_version:
            normalized["anthropic_version"] = anthropic_version
        return normalized

    raise HTTPException(status_code=422, detail=f"Unsupported provider type '{provider_type}'")


def _provider_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("message")
            if isinstance(detail, dict):
                detail = detail.get("message")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
    except ValueError:
        pass
    text = response.text.strip()
    return text[:240] if text else "Unknown provider error"


def _resolve_model_test_runtime(session: Session, model: AIModel) -> tuple[AIProvider, dict[str, Any], str]:
    provider = session.get(AIProvider, model.provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found for model")
    if not provider.is_active:
        raise HTTPException(status_code=409, detail="Provider is inactive")
    if not model.is_active:
        raise HTTPException(status_code=409, detail="Model is inactive")
    if not model.can_chat:
        raise HTTPException(status_code=422, detail="Model is not chat-capable")

    config = provider.config if isinstance(provider.config, dict) else {}
    raw_secret_id = config.get("api_key_secret_id")
    if not isinstance(raw_secret_id, str) or not raw_secret_id.strip():
        raise HTTPException(status_code=422, detail="Provider config.api_key_secret_id is required")
    try:
        secret_id = UUID(raw_secret_id.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Provider config.api_key_secret_id is invalid") from exc
    secret = session.get(Secret, secret_id)
    if secret is None or secret.kind != "ai_api_key":
        raise HTTPException(status_code=422, detail="Provider API key secret is invalid")
    if not secret.value_ciphertext:
        raise HTTPException(status_code=409, detail="Provider API key secret has no value")
    try:
        api_key = decrypt_secret(secret.value_ciphertext)
    except SecretCryptoError as exc:
        raise HTTPException(status_code=500, detail="Failed to resolve provider API key secret") from exc
    return provider, config, api_key


def _post_openai_chat(url: str, headers: dict[str, str], payload: dict[str, Any]) -> httpx.Response:
    response = httpx.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code == 400 and "max_completion_tokens" in payload:
        detail = _provider_error_detail(response).lower()
        if "max_completion_tokens" in detail and "max_tokens" in detail:
            next_payload = dict(payload)
            next_payload.pop("max_completion_tokens", None)
            next_payload["max_tokens"] = 32
            response = httpx.post(url, headers=headers, json=next_payload, timeout=30)
    return response


@router.get("/providers", response_model=list[AIProviderResponse])
def list_providers(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[AIProviderResponse]:
    _ensure_ai_manage(permissions)
    providers = session.query(AIProvider).order_by(AIProvider.key.asc()).all()
    return [AIProviderResponse.model_validate(provider) for provider in providers]


@router.get("/providers/{provider_id}", response_model=AIProviderResponse)
def get_provider(
    provider_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIProviderResponse:
    _ensure_ai_manage(permissions)
    provider = session.get(AIProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return AIProviderResponse.model_validate(provider)


@router.post("/providers", response_model=AIProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: AIProviderCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIProviderResponse:
    _ensure_ai_manage(permissions)
    provider_type = _normalize_provider_type(payload.type)
    config = _normalize_provider_config(session, provider_type, payload.config)
    provider = AIProvider(
        key=payload.key.strip(),
        type=provider_type,
        name=payload.name.strip(),
        is_active=payload.is_active,
        config=config,
        compliance=payload.compliance,
    )
    session.add(provider)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Provider key already exists") from exc
    session.refresh(provider)
    return AIProviderResponse.model_validate(provider)


@router.patch("/providers/{provider_id}", response_model=AIProviderResponse)
def update_provider(
    provider_id: UUID,
    payload: AIProviderUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIProviderResponse:
    _ensure_ai_manage(permissions)
    provider = session.get(AIProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider_type = _normalize_provider_type(payload.type if payload.type is not None else provider.type)
    config_candidate = payload.config if payload.config is not None else provider.config
    normalized_config = _normalize_provider_config(session, provider_type, config_candidate)
    if payload.key is not None:
        provider.key = payload.key.strip()
    provider.type = provider_type
    if payload.name is not None:
        provider.name = payload.name.strip()
    if payload.is_active is not None:
        provider.is_active = payload.is_active
    provider.config = normalized_config
    if payload.compliance is not None:
        provider.compliance = payload.compliance
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Provider key already exists") from exc
    session.refresh(provider)
    return AIProviderResponse.model_validate(provider)


@router.get("/models", response_model=list[AIModelResponse])
def list_models(
    provider_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[AIModelResponse]:
    _ensure_ai_manage(permissions)
    query = session.query(AIModel)
    if provider_id is not None:
        query = query.filter(AIModel.provider_id == provider_id)
    models = query.order_by(AIModel.key.asc()).all()
    return [AIModelResponse.model_validate(model) for model in models]


@router.get("/models/{model_id}", response_model=AIModelResponse)
def get_model(
    model_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIModelResponse:
    _ensure_ai_manage(permissions)
    model = session.get(AIModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return AIModelResponse.model_validate(model)


@router.post("/models/{model_id}/test", response_model=AIModelTestResponse)
def test_model(
    model_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIModelTestResponse:
    _ensure_ai_manage(permissions)
    model = session.get(AIModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    provider, config, api_key = _resolve_model_test_runtime(session, model)
    provider_model_id = (model.provider_model_id or model.key or "").strip()
    if not provider_model_id:
        raise HTTPException(status_code=422, detail="Model provider_model_id is required")

    provider_type = provider.type.strip().lower()
    message = "Model test successful"
    ok = False

    if provider_type == "openai":
        base_url = str(config.get("base_url") or "").strip() or "https://api.openai.com/v1"
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        organization = config.get("organization")
        if isinstance(organization, str) and organization.strip():
            headers["OpenAI-Organization"] = organization.strip()
        payload = {
            "model": provider_model_id,
            "messages": [{"role": "user", "content": "Reply with: ok"}],
            "max_completion_tokens": 32,
            "temperature": 0,
        }
        response = _post_openai_chat(f"{base_url.rstrip('/')}/chat/completions", headers, payload)
        if response.status_code < 400:
            ok = True
        else:
            message = f"Model test failed ({response.status_code}): {_provider_error_detail(response)}"
    elif provider_type == "azure_openai":
        endpoint = str(config.get("endpoint") or "").strip()
        api_version = str(config.get("api_version") or "").strip()
        if not endpoint or not api_version:
            raise HTTPException(status_code=422, detail="Azure OpenAI provider requires endpoint and api_version")
        headers = {"api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "messages": [{"role": "user", "content": "Reply with: ok"}],
            "max_completion_tokens": 32,
            "temperature": 0,
        }
        deployment = quote(provider_model_id, safe="")
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
        response = httpx.post(url, params={"api-version": api_version}, headers=headers, json=payload, timeout=30)
        if response.status_code == 400 and "max_completion_tokens" in payload:
            detail = _provider_error_detail(response).lower()
            if "max_completion_tokens" in detail and "max_tokens" in detail:
                fallback_payload = dict(payload)
                fallback_payload.pop("max_completion_tokens", None)
                fallback_payload["max_tokens"] = 32
                response = httpx.post(
                    url,
                    params={"api-version": api_version},
                    headers=headers,
                    json=fallback_payload,
                    timeout=30,
                )
        if response.status_code < 400:
            ok = True
        else:
            message = f"Model test failed ({response.status_code}): {_provider_error_detail(response)}"
    elif provider_type == "anthropic":
        base_url = str(config.get("base_url") or "").strip() or "https://api.anthropic.com"
        anthropic_version = str(config.get("anthropic_version") or "").strip() or "2023-06-01"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": anthropic_version,
            "content-type": "application/json",
        }
        payload = {
            "model": provider_model_id,
            "max_tokens": 32,
            "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with: ok"}],
        }
        response = httpx.post(f"{base_url.rstrip('/')}/v1/messages", headers=headers, json=payload, timeout=30)
        if response.status_code < 400:
            ok = True
        else:
            message = f"Model test failed ({response.status_code}): {_provider_error_detail(response)}"
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported provider type '{provider.type}'")

    return AIModelTestResponse(
        ok=ok,
        message=message if not ok else f"{message} ({provider.name} / {model.name})",
        provider_type=provider_type,
        provider_model_id=provider_model_id,
    )


@router.post("/providers/{provider_id}/models", response_model=AIModelResponse, status_code=status.HTTP_201_CREATED)
def create_model(
    provider_id: UUID,
    payload: AIModelCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIModelResponse:
    _ensure_ai_manage(permissions)
    provider = session.get(AIProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    model = AIModel(
        provider_id=provider.provider_id,
        key=payload.key.strip(),
        name=payload.name.strip(),
        provider_model_id=payload.provider_model_id,
        can_embed=payload.can_embed,
        can_rerank=payload.can_rerank,
        can_chat=payload.can_chat,
        can_vision=payload.can_vision,
        can_audio=payload.can_audio,
        default_workload=payload.default_workload,
        is_default=payload.is_default,
        restricted_content_only=payload.restricted_content_only,
        is_active=payload.is_active,
        context_window_tokens=payload.context_window_tokens,
        max_output_tokens=payload.max_output_tokens,
        cost=payload.cost,
        default_params=payload.default_params,
        compliance=payload.compliance,
    )
    session.add(model)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Model key already exists") from exc
    session.refresh(model)
    return AIModelResponse.model_validate(model)


@router.patch("/models/{model_id}", response_model=AIModelResponse)
def update_model(
    model_id: UUID,
    payload: AIModelUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIModelResponse:
    _ensure_ai_manage(permissions)
    model = session.get(AIModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    fields_set = getattr(payload, "model_fields_set", set())
    if payload.key is not None:
        model.key = payload.key.strip()
    if payload.name is not None:
        model.name = payload.name.strip()
    if "provider_model_id" in fields_set:
        model.provider_model_id = payload.provider_model_id
    if payload.can_embed is not None:
        model.can_embed = payload.can_embed
    if payload.can_rerank is not None:
        model.can_rerank = payload.can_rerank
    if payload.can_chat is not None:
        model.can_chat = payload.can_chat
    if payload.can_vision is not None:
        model.can_vision = payload.can_vision
    if payload.can_audio is not None:
        model.can_audio = payload.can_audio
    if "default_workload" in fields_set:
        model.default_workload = payload.default_workload
    if payload.is_default is not None:
        model.is_default = payload.is_default
    if payload.restricted_content_only is not None:
        model.restricted_content_only = payload.restricted_content_only
    if payload.is_active is not None:
        model.is_active = payload.is_active
    if "context_window_tokens" in fields_set:
        model.context_window_tokens = payload.context_window_tokens
    if "max_output_tokens" in fields_set:
        model.max_output_tokens = payload.max_output_tokens
    if payload.cost is not None:
        model.cost = payload.cost
    if payload.default_params is not None:
        model.default_params = payload.default_params
    if payload.compliance is not None:
        model.compliance = payload.compliance
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Model key already exists") from exc
    session.refresh(model)
    return AIModelResponse.model_validate(model)
