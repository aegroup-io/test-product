from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent_core_platform_api.db import get_session
from agent_core_platform_api.models import AIAgent
from agent_core_platform_api.rbac import PERM_AI_MANAGE, PermissionContext, get_permission_context
from agent_core_platform_api.schemas import AIAgentCreateRequest, AIAgentResponse, AIAgentUpdateRequest


router = APIRouter(prefix="/ai")


def _ensure_ai_manage(permissions: PermissionContext) -> None:
    if not permissions.has(PERM_AI_MANAGE):
        raise HTTPException(status_code=403, detail="AI agent access denied")


@router.get("/agents", response_model=list[AIAgentResponse])
def list_agents(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[AIAgentResponse]:
    _ensure_ai_manage(permissions)
    agents = session.query(AIAgent).order_by(AIAgent.key.asc()).all()
    return [AIAgentResponse.model_validate(agent) for agent in agents]


@router.get("/agents/{agent_id}", response_model=AIAgentResponse)
def get_agent(
    agent_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIAgentResponse:
    _ensure_ai_manage(permissions)
    agent = session.get(AIAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AIAgentResponse.model_validate(agent)


@router.post("/agents", response_model=AIAgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AIAgentCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIAgentResponse:
    _ensure_ai_manage(permissions)
    agent = AIAgent(
        key=payload.key.strip(),
        name=payload.name.strip(),
        description=payload.description,
        system_prompt=payload.system_prompt,
        tool_policy=payload.tool_policy,
        output_schema=payload.output_schema,
        default_model_id=payload.default_model_id,
        is_active=payload.is_active,
    )
    session.add(agent)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Agent key already exists") from exc
    session.refresh(agent)
    return AIAgentResponse.model_validate(agent)


@router.patch("/agents/{agent_id}", response_model=AIAgentResponse)
def update_agent(
    agent_id: UUID,
    payload: AIAgentUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> AIAgentResponse:
    _ensure_ai_manage(permissions)
    agent = session.get(AIAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    fields_set = getattr(payload, "model_fields_set", set())
    if payload.key is not None:
        agent.key = payload.key.strip()
    if payload.name is not None:
        agent.name = payload.name.strip()
    if "description" in fields_set:
        agent.description = payload.description
    if payload.system_prompt is not None:
        agent.system_prompt = payload.system_prompt
    if payload.tool_policy is not None:
        agent.tool_policy = payload.tool_policy
    if payload.output_schema is not None:
        agent.output_schema = payload.output_schema
    if "default_model_id" in fields_set:
        agent.default_model_id = payload.default_model_id
    if payload.is_active is not None:
        agent.is_active = payload.is_active
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Agent key already exists") from exc
    session.refresh(agent)
    return AIAgentResponse.model_validate(agent)
