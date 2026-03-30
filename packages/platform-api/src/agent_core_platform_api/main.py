from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent_core_platform_api.ai_agents_routes import router as ai_agents_router
from agent_core_platform_api.ai_registry_routes import router as ai_registry_router
from agent_core_platform_api.bootstrap import ensure_runtime_state
from agent_core_platform_api.component_graph import ComponentGraphService
from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session, get_session_factory, run_database_migrations
from agent_core_platform_api.graph_context import GraphContextService
from agent_core_platform_api.github_integration import (
    GitHubAppAuthError,
    GitHubAppConfigError,
    GitHubWebhookService,
    GitHubWebhookSignatureError,
)
from agent_core_platform_api.github_mirror import GitHubMirrorService
from agent_core_platform_api.lane_recovery import LaneRecoveryService
from agent_core_platform_api.observability import ObservabilityService
from agent_core_platform_api.orchestration_runtime import BackgroundOrchestrationLoop, OrchestrationRuntimeService
from agent_core_platform_api.repos_routes import router as repos_router
from agent_core_platform_api.models import (
    AIAgent,
    AIModel,
    AIProvider,
    ComponentNode,
    FeatureFlag,
    OrchestrationLane,
    OrgMembership,
    Organization,
    Permission,
    Product,
    ProductSeedJob,
    RepositoryBinding,
    Role,
    Secret,
    Setting,
    WebhookDelivery,
)
from agent_core_platform_api.orgs import get_org, list_orgs
from agent_core_platform_api.operator_api import OperatorAPIConflictError, OperatorAPIService, OperatorAPIValidationError
from agent_core_platform_api.product_adoption import ProductAdoptionConflictError, ProductAdoptionService
from agent_core_platform_api.rbac import (
    PERM_ORG_MANAGE,
    PERM_ORG_MEMBERS_MANAGE,
    PERM_ORG_MEMBERS_READ,
    PERM_ORG_READ,
    PERM_PLATFORM_MANAGE,
    PERM_PLATFORM_READ,
    PERM_WORKER_MANAGE,
    DatabaseRBACStore,
    PermissionContext,
    get_permission_context,
)
from agent_core_platform_api.runner_protocol import RunnerHandshake, RunnerProtocolError, RunnerProtocolService, RuntimeEvent
from agent_core_platform_api.product_seeding import ProductSeedService
from agent_core_platform_api.standards_packs import StandardsPackConflictError, StandardsPackService
from agent_core_platform_api.schemas import (
    BaselineResponse,
    FeatureFlagResponse,
    FleetObservabilityResponse,
    GitHubProjectMirrorResponse,
    GraphSliceResponse,
    LaneApproveRequest,
    LaneCancelRequest,
    LaneHumanInputRequest,
    LaneObservabilityResponse,
    LaneResponse,
    LaneRetryRequest,
    OperatorActionRequest,
    OrgMemberCreateRequest,
    OrgMemberResponse,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
    PermissionResponse,
    PlatformSummaryResponse,
    ProductMirrorRefreshRequest,
    ProductRefreshRequest,
    ProductAdoptionRequest,
    ProductAdoptionResponse,
    ProductComponentGraphResponse,
    ProductSummaryResponse,
    ProductSeedJobResponse,
    ProductSeedRequest,
    PullRequestMirrorResponse,
    RoleFeatureFlagsUpdateRequest,
    RolePermissionsUpdateRequest,
    RoleResponse,
    RunnerEventRequest,
    RunnerHandshakeRequest,
    RunnerHeartbeatRequest,
    RunnerLaunchRequestResponse,
    SecretCreateRequest,
    SecretResponse,
    SecretUpdateRequest,
    SettingResponse,
    SettingScopeType,
    SettingUpsertRequest,
    StandardsEvaluationRequest,
    StandardsPackCreateRequest,
    StandardsPackResponse,
    StandardsUpgradeOutcomeRequest,
    StandardsUpgradeRunResponse,
    ProductStandardsOverrideRequest,
    ProductStandardsOverrideResponse,
    UserInfoResponse,
    WebhookDeliveryIntakeResponse,
    WebhookDeliveryResponse,
    WorkItemMirrorResponse,
)
from agent_core_platform_api.secret_crypto import encrypt_secret
from agent_core_platform_api.users_routes import router as users_router


SECRET_KINDS = {
    "api_token",
    "client_secret",
    "shared_secret",
    "signing_key",
    "ai_api_key",
    "git_personal_access_token",
    "databricks_access_token",
    "gcp_service_account_key",
    "github_webhook_secret",
}


logger = logging.getLogger(__name__)


def _cors_allow_origins() -> list[str]:
    settings = get_settings()
    if settings.cors_allow_origins:
        return list(settings.cors_allow_origins)

    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    local_web_origin = os.getenv("AGENT_CORE_LOCAL_WEB_URL", "").strip()
    if local_web_origin and local_web_origin not in origins:
        origins.append(local_web_origin)
    return origins


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_database_migrations()
    session_factory = get_session_factory()
    orchestration_loop: BackgroundOrchestrationLoop | None = None
    with session_factory() as session:
        ensure_runtime_state(session)
        LaneRecoveryService(session).recover_startup_state()
        session.commit()
    if get_settings().orchestration_loop_enabled:
        orchestration_loop = BackgroundOrchestrationLoop(session_factory)
        orchestration_loop.start()
    try:
        yield
    finally:
        if orchestration_loop is not None:
            orchestration_loop.stop()
        with session_factory() as session:
            try:
                summary = LaneRecoveryService(session).cancel_active_lanes_for_shutdown()
                session.commit()
                if summary.cancelled:
                    logger.info("shutdown cleanup cancelled %s active lane(s)", summary.cancelled)
            except Exception:
                session.rollback()
                logger.exception("shutdown cleanup failed")


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ai_registry_router)
app.include_router(ai_agents_router)
app.include_router(users_router)
app.include_router(repos_router)


def _ensure(permission_context: PermissionContext, permission: str, detail: str) -> None:
    if not permission_context.has(permission):
        raise HTTPException(status_code=403, detail=detail)


def _ensure_rbac_admin(permission_context: PermissionContext) -> None:
    if not permission_context.has(PERM_PLATFORM_MANAGE):
        raise HTTPException(status_code=403, detail="RBAC access denied")


def _resolve_scope_id(scope_type: SettingScopeType, scope_id: str, permission_context: PermissionContext) -> str:
    if scope_type == "user" and scope_id == "me":
        return permission_context.user.user_id
    return scope_id


def _ensure_settings_access(
    permission_context: PermissionContext,
    *,
    scope_type: SettingScopeType,
    scope_id: str,
    write: bool,
) -> str:
    resolved_scope_id = _resolve_scope_id(scope_type, scope_id, permission_context)
    if scope_type == "user" and resolved_scope_id == permission_context.user.user_id:
        return resolved_scope_id
    required_permission = PERM_PLATFORM_MANAGE if write else PERM_PLATFORM_READ
    _ensure(permission_context, required_permission, "Settings access denied")
    return resolved_scope_id


def _raise_operator_error(exc: Exception) -> None:
    detail = str(exc)
    if isinstance(exc, ValueError) and "not found" in detail.lower():
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(exc, (OperatorAPIConflictError, ProductAdoptionConflictError)):
        raise HTTPException(status_code=409, detail=detail) from exc
    if isinstance(exc, OperatorAPIValidationError):
        raise HTTPException(status_code=422, detail=detail) from exc
    raise HTTPException(status_code=400, detail=detail) from exc


def _raise_runner_error(exc: Exception) -> None:
    detail = str(exc)
    if isinstance(exc, ValueError) and "not found" in detail.lower():
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(exc, RunnerProtocolError):
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc
    raise HTTPException(status_code=400, detail=detail) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/github/webhooks", response_model=WebhookDeliveryIntakeResponse, status_code=status.HTTP_202_ACCEPTED)
async def intake_github_webhook(
    request: Request,
    session: Session = Depends(get_session),
) -> WebhookDeliveryIntakeResponse:
    body = await request.body()
    service = GitHubWebhookService(session)
    try:
        result = service.intake(headers=request.headers, body=body)
        session.commit()
    except IntegrityError:
        session.rollback()
        github_delivery_guid = request.headers.get("X-GitHub-Delivery") or request.headers.get("x-github-delivery")
        if not github_delivery_guid:
            raise HTTPException(status_code=500, detail="Concurrent delivery recovery failed without a delivery GUID.")
        try:
            result = GitHubWebhookService(session).recover_duplicate(
                github_delivery_guid=github_delivery_guid,
                body=body,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GitHubWebhookSignatureError as exc:
        session.rollback()
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GitHubAppConfigError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = WebhookDeliveryResponse.model_validate(result.delivery).model_dump()
    payload["duplicate"] = result.duplicate
    return WebhookDeliveryIntakeResponse.model_validate(payload)


@app.get("/github/webhooks/{delivery_id}", response_model=WebhookDeliveryResponse)
def get_github_webhook_delivery(
    delivery_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> WebhookDeliveryResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Webhook delivery access denied")
    delivery = session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    return WebhookDeliveryResponse.model_validate(delivery)


@app.post("/github/webhooks/{delivery_id}/replay", response_model=WebhookDeliveryResponse)
def replay_github_webhook_delivery(
    delivery_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> WebhookDeliveryResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Webhook replay access denied")
    service = GitHubWebhookService(session)
    try:
        delivery = service.replay(delivery_id)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WebhookDeliveryResponse.model_validate(delivery)


@app.get("/github/mirror/work-items/{github_issue_node_id}", response_model=WorkItemMirrorResponse)
def get_mirrored_work_item(
    github_issue_node_id: str,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> WorkItemMirrorResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "GitHub mirror access denied")
    work_item = GitHubMirrorService(session).get_work_item_by_node_id(github_issue_node_id)
    if work_item is None:
        raise HTTPException(status_code=404, detail="Mirrored work item not found")
    return WorkItemMirrorResponse.model_validate(work_item)


@app.post("/github/mirror/work-items/{github_issue_node_id}/repair", response_model=WorkItemMirrorResponse)
def repair_mirrored_work_item(
    github_issue_node_id: str,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> WorkItemMirrorResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "GitHub repair access denied")
    service = GitHubMirrorService(session)
    try:
        work_item = service.repair_issue(
            github_issue_node_id=github_issue_node_id,
        )
        session.commit()
    except (GitHubAppAuthError, GitHubAppConfigError) as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WorkItemMirrorResponse.model_validate(work_item)


@app.get("/github/mirror/pull-requests/{github_pr_node_id}", response_model=PullRequestMirrorResponse)
def get_mirrored_pull_request(
    github_pr_node_id: str,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> PullRequestMirrorResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "GitHub mirror access denied")
    pull_request = GitHubMirrorService(session).get_pull_request_by_node_id(github_pr_node_id)
    if pull_request is None:
        raise HTTPException(status_code=404, detail="Mirrored pull request not found")
    return PullRequestMirrorResponse.model_validate(pull_request)


@app.post("/github/mirror/pull-requests/{github_pr_node_id}/repair", response_model=PullRequestMirrorResponse)
def repair_mirrored_pull_request(
    github_pr_node_id: str,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> PullRequestMirrorResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "GitHub repair access denied")
    service = GitHubMirrorService(session)
    try:
        pull_request = service.repair_pull_request(
            github_pr_node_id=github_pr_node_id,
        )
        session.commit()
    except GitHubAppAuthError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PullRequestMirrorResponse.model_validate(pull_request)


@app.get("/github/mirror/projects/{github_project_node_id}", response_model=GitHubProjectMirrorResponse)
def get_mirrored_project(
    github_project_node_id: str,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> GitHubProjectMirrorResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "GitHub mirror access denied")
    project = GitHubMirrorService(session).get_project_by_node_id(github_project_node_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Mirrored project not found")
    return GitHubProjectMirrorResponse.model_validate(project)


@app.post("/github/mirror/projects/{github_project_node_id}/repair", response_model=GitHubProjectMirrorResponse)
def repair_mirrored_project(
    github_project_node_id: str,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> GitHubProjectMirrorResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "GitHub repair access denied")
    service = GitHubMirrorService(session)
    try:
        project = service.repair_project(
            github_project_node_id=github_project_node_id,
        )
        session.commit()
    except GitHubAppAuthError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    project = service.get_project_by_node_id(github_project_node_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Mirrored project not found after repair")
    return GitHubProjectMirrorResponse.model_validate(project)


@app.get("/me", response_model=UserInfoResponse)
def get_me(
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> UserInfoResponse:
    memberships = (
        session.query(OrgMembership)
        .filter(
            OrgMembership.user_id == permissions.user.user_id,
            OrgMembership.is_active.is_(True),
        )
        .all()
    )
    org_ids = [membership.org_id for membership in memberships]
    default_org_id = next((membership.org_id for membership in memberships if membership.is_default), None)
    if default_org_id is None and len(org_ids) == 1:
        default_org_id = org_ids[0]
    return UserInfoResponse(
        user_id=permissions.user.user_id,
        username=permissions.user.username,
        roles=permissions.roles,
        permissions=sorted(permissions.permissions),
        feature_flags=sorted(permissions.feature_flags),
        org_ids=org_ids,
        default_org_id=default_org_id,
        claims=permissions.user.claims,
    )


@app.get("/platform/summary", response_model=PlatformSummaryResponse)
def get_platform_summary(
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> PlatformSummaryResponse:
    _ensure(permissions, PERM_ORG_READ, "Platform summary access denied")
    return PlatformSummaryResponse(
        organization_count=session.query(Organization).count(),
        provider_count=session.query(AIProvider).count(),
        model_count=session.query(AIModel).count(),
        agent_count=session.query(AIAgent).count(),
        product_count=session.query(Product).count(),
        repository_binding_count=session.query(RepositoryBinding).count(),
        lane_count=session.query(OrchestrationLane).count(),
        component_node_count=session.query(ComponentNode).count(),
        webhook_delivery_count=session.query(WebhookDelivery).count(),
        membership_count=session.query(OrgMembership).filter(OrgMembership.is_active.is_(True)).count(),
        role_count=session.query(Role).count(),
        permission_count=session.query(Permission).count(),
        feature_flag_count=session.query(FeatureFlag).count(),
        secret_count=session.query(Secret).count(),
        setting_count=session.query(Setting).count(),
    )


@app.get("/v1/products", response_model=list[ProductSummaryResponse])
def list_v1_products(
    org_id: UUID | None = None,
    status: str | None = None,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> list[ProductSummaryResponse]:
    _ensure(permissions, PERM_ORG_READ, "Product access denied")
    return OperatorAPIService(session).list_products(org_id=org_id, status=status)


@app.get("/v1/products/{product_id}", response_model=ProductSummaryResponse)
def get_v1_product(
    product_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSummaryResponse:
    _ensure(permissions, PERM_ORG_READ, "Product access denied")
    try:
        return OperatorAPIService(session).get_product(product_id)
    except ValueError as exc:
        _raise_operator_error(exc)


@app.post("/v1/products", response_model=ProductSummaryResponse, status_code=status.HTTP_201_CREATED)
def create_v1_product(
    payload: ProductAdoptionRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSummaryResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product creation denied")
    try:
        return OperatorAPIService(session).create_product(payload)
    except (ProductAdoptionConflictError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/products/{product_id}/pause", response_model=ProductSummaryResponse)
def pause_v1_product(
    product_id: UUID,
    payload: OperatorActionRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSummaryResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product pause denied")
    try:
        response = OperatorAPIService(session).pause_product(product_id, actor_id=payload.actor_id, reason=payload.reason)
        session.commit()
        return response
    except GitHubAppAuthError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/products/{product_id}/resume", response_model=ProductSummaryResponse)
def resume_v1_product(
    product_id: UUID,
    payload: OperatorActionRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSummaryResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product resume denied")
    try:
        response = OperatorAPIService(session).resume_product(product_id, actor_id=payload.actor_id, reason=payload.reason)
        session.commit()
        return response
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/products/{product_id}/refresh", response_model=ProductSummaryResponse)
def refresh_v1_product(
    product_id: UUID,
    payload: ProductRefreshRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSummaryResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product refresh denied")
    try:
        response = OperatorAPIService(session).refresh_product(
            product_id,
            actor_id=payload.actor_id,
            reason=payload.reason,
            repo_root=payload.repo_root,
            operator_overrides=payload.operator_overrides,
        )
        session.commit()
        return response
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/products/{product_id}/refresh-mirror", response_model=ProductSummaryResponse)
def refresh_v1_product_mirror(
    product_id: UUID,
    payload: ProductMirrorRefreshRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSummaryResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product mirror refresh denied")
    try:
        response = OperatorAPIService(session).refresh_product_mirror(
            product_id,
            actor_id=payload.actor_id,
            reason=payload.reason,
        )
        session.commit()
        return response
    except GitHubAppAuthError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.get("/v1/lanes", response_model=list[LaneResponse])
def list_v1_lanes(
    product_id: UUID | None = None,
    status: str | None = None,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> list[LaneResponse]:
    _ensure(permissions, PERM_PLATFORM_READ, "Lane access denied")
    return OperatorAPIService(session).list_lanes(product_id=product_id, status=status)


@app.get("/v1/lanes/{lane_id}", response_model=LaneResponse)
def get_v1_lane(
    lane_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Lane access denied")
    try:
        return OperatorAPIService(session).get_lane(lane_id)
    except ValueError as exc:
        _raise_operator_error(exc)


@app.get("/v1/observability/summary", response_model=FleetObservabilityResponse)
def get_v1_observability_summary(
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> FleetObservabilityResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Observability access denied")
    return ObservabilityService(session).get_fleet_observability()


@app.get("/v1/observability/lanes/{lane_id}", response_model=LaneObservabilityResponse)
def get_v1_lane_observability(
    lane_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneObservabilityResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Observability access denied")
    try:
        return ObservabilityService(session).get_lane_observability(lane_id)
    except ValueError as exc:
        _raise_operator_error(exc)


@app.post("/v1/lanes/{lane_id}/retry", response_model=LaneResponse)
def retry_v1_lane(
    lane_id: UUID,
    payload: LaneRetryRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Lane retry denied")
    try:
        response = OperatorAPIService(session).retry_lane(lane_id, actor_id=payload.actor_id, reason=payload.reason)
        session.commit()
        return response
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/lanes/{lane_id}/cancel", response_model=LaneResponse)
def cancel_v1_lane(
    lane_id: UUID,
    payload: LaneCancelRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Lane cancellation denied")
    try:
        response = OperatorAPIService(session).cancel_lane(
            lane_id,
            actor_id=payload.actor_id,
            reason=payload.reason,
            disposition=payload.disposition,
        )
        session.commit()
        return response
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/lanes/{lane_id}/approve", response_model=LaneResponse)
def approve_v1_lane(
    lane_id: UUID,
    payload: LaneApproveRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Lane approval denied")
    try:
        response = OperatorAPIService(session).approve_lane(
            lane_id,
            actor_id=payload.actor_id,
            reason=payload.reason,
            approval_payload=payload.approval_payload,
        )
        session.commit()
        return response
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.post("/v1/lanes/{lane_id}/human-input", response_model=LaneResponse)
def submit_v1_lane_human_input(
    lane_id: UUID,
    payload: LaneHumanInputRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Lane human-input denied")
    try:
        response = OperatorAPIService(session).submit_human_input(
            lane_id,
            actor_id=payload.actor_id,
            reason=payload.reason,
            input_payload=payload.input_payload,
        )
        session.commit()
        return response
    except (OperatorAPIConflictError, OperatorAPIValidationError, ValueError) as exc:
        session.rollback()
        _raise_operator_error(exc)


@app.get("/v1/runner/launches/next", response_model=RunnerLaunchRequestResponse)
def get_v1_next_runner_launch(
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> RunnerLaunchRequestResponse | Response:
    _ensure(permissions, PERM_WORKER_MANAGE, "Runner launch access denied")
    launch = OrchestrationRuntimeService(session).peek_next_launch()
    if launch is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return RunnerLaunchRequestResponse.model_validate(
        {
            "lane_id": launch.lane_id,
            "agent_session_id": launch.agent_session_id,
            "lane_metadata": launch.lane_metadata,
            "issue_context": launch.issue_context,
            "instruction_bundle": launch.instruction_bundle,
            "policy": launch.policy,
            "artifact_destinations": launch.artifact_destinations,
            "secret_references": launch.secret_references,
            "tool_permissions": launch.tool_permissions,
            "required_capabilities": launch.required_capabilities,
        }
    )


@app.post("/v1/runner/lanes/{lane_id}/handshake", response_model=LaneResponse)
def post_v1_runner_handshake(
    lane_id: UUID,
    payload: RunnerHandshakeRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_WORKER_MANAGE, "Runner handshake denied")
    try:
        RunnerProtocolService(session).record_handshake(
            lane_id,
            RunnerHandshake(
                runner_session_id=payload.runner_session_id,
                runner_version=payload.runner_version,
                capabilities=payload.capabilities,
                environment_identity=payload.environment_identity,
                heartbeat_at=payload.heartbeat_at,
                thread_id=payload.thread_id,
            ),
        )
        response = OperatorAPIService(session).get_lane(lane_id)
        session.commit()
        return response
    except (RunnerProtocolError, ValueError) as exc:
        session.rollback()
        _raise_runner_error(exc)


@app.post("/v1/runner/lanes/{lane_id}/heartbeat", response_model=LaneResponse)
def post_v1_runner_heartbeat(
    lane_id: UUID,
    payload: RunnerHeartbeatRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_WORKER_MANAGE, "Runner heartbeat denied")
    try:
        RunnerProtocolService(session).record_heartbeat(
            lane_id,
            heartbeat_at=payload.heartbeat_at,
            thread_id=payload.thread_id,
            turn_id=payload.turn_id,
        )
        response = OperatorAPIService(session).get_lane(lane_id)
        session.commit()
        return response
    except (RunnerProtocolError, ValueError) as exc:
        session.rollback()
        _raise_runner_error(exc)


@app.post("/v1/runner/lanes/{lane_id}/events", response_model=LaneResponse)
def post_v1_runner_event(
    lane_id: UUID,
    payload: RunnerEventRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> LaneResponse:
    _ensure(permissions, PERM_WORKER_MANAGE, "Runner event ingestion denied")
    try:
        RunnerProtocolService(session).record_event(
            lane_id,
            RuntimeEvent(
                event_type=payload.event_type,
                payload=payload.payload,
                observed_at=payload.observed_at or datetime.now(timezone.utc),
                summary=payload.summary,
                thread_id=payload.thread_id,
                turn_id=payload.turn_id,
                token_usage=payload.token_usage,
                tool_name=payload.tool_name,
                tool_status=payload.tool_status,
                error_category=payload.error_category,
            ),
        )
        response = OperatorAPIService(session).get_lane(lane_id)
        session.commit()
        return response
    except (RunnerProtocolError, ValueError) as exc:
        session.rollback()
        _raise_runner_error(exc)


@app.get("/v1/baselines", response_model=list[BaselineResponse])
def list_v1_baselines(
    org_id: UUID | None = None,
    drift_status: str | None = None,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> list[BaselineResponse]:
    _ensure(permissions, PERM_ORG_READ, "Baseline access denied")
    return OperatorAPIService(session).list_baselines(org_id=org_id, drift_status=drift_status)


@app.get("/v1/baselines/{product_id}", response_model=BaselineResponse)
def get_v1_baseline(
    product_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> BaselineResponse:
    _ensure(permissions, PERM_ORG_READ, "Baseline access denied")
    try:
        return OperatorAPIService(session).get_baseline(product_id)
    except ValueError as exc:
        _raise_operator_error(exc)


@app.get("/v1/graph/products/{product_id}", response_model=GraphSliceResponse)
def get_v1_product_graph(
    product_id: UUID,
    depth: int = Query(default=3, ge=0, le=6),
    component_key: list[str] | None = Query(default=None),
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> GraphSliceResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Graph slice access denied")
    service = GraphContextService(session)
    try:
        payload = service.build_product_slice(product_id, depth=depth, component_keys=component_key or None)
    except ValueError as exc:
        session.rollback()
        _raise_operator_error(exc)
    return GraphSliceResponse.model_validate(payload)


@app.post("/v1/webhooks/{delivery_id}/replay", response_model=WebhookDeliveryResponse)
def replay_v1_webhook_delivery(
    delivery_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> WebhookDeliveryResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Webhook replay access denied")
    service = GitHubWebhookService(session)
    try:
        delivery = service.replay(delivery_id)
        session.commit()
    except ValueError as exc:
        session.rollback()
        _raise_operator_error(exc)
    return WebhookDeliveryResponse.model_validate(delivery)


@app.get("/graph/products/{product_id}/slice", response_model=GraphSliceResponse)
def get_product_graph_slice(
    product_id: UUID,
    depth: int = Query(default=3, ge=0, le=6),
    component_key: list[str] | None = Query(default=None),
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> GraphSliceResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Graph slice access denied")
    service = GraphContextService(session)
    try:
        payload = service.build_product_slice(
            product_id,
            depth=depth,
            component_keys=component_key or None,
        )
    except ValueError as exc:
        session.rollback()
        detail = str(exc)
        raise HTTPException(status_code=404 if "not found" in detail.lower() else 400, detail=detail) from exc
    return GraphSliceResponse.model_validate(payload)


@app.get("/graph/lanes/{lane_id}/slice", response_model=GraphSliceResponse)
def get_lane_graph_slice(
    lane_id: UUID,
    depth: int = Query(default=3, ge=0, le=6),
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> GraphSliceResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Graph slice access denied")
    service = GraphContextService(session)
    try:
        payload = service.build_lane_slice(lane_id, depth=depth)
    except ValueError as exc:
        session.rollback()
        detail = str(exc)
        raise HTTPException(status_code=404 if "not found" in detail.lower() else 400, detail=detail) from exc
    return GraphSliceResponse.model_validate(payload)


@app.post("/products/seed", response_model=ProductSeedJobResponse, status_code=status.HTTP_201_CREATED)
def seed_product_repository(
    payload: ProductSeedRequest,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSeedJobResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Product seed access denied")
    try:
        job = ProductSeedService(session).seed_product(payload, requested_by=permissions.user.user_id)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProductSeedJobResponse.model_validate(job)


@app.get("/products/seed-jobs/{seed_job_id}", response_model=ProductSeedJobResponse)
def get_product_seed_job(
    seed_job_id: UUID,
    permissions: PermissionContext = Depends(get_permission_context),
    session: Session = Depends(get_session),
) -> ProductSeedJobResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Product seed access denied")
    job = session.get(ProductSeedJob, seed_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Product seed job not found")
    return ProductSeedJobResponse.model_validate(job)


@app.post("/products/adoptions/dry-run", response_model=ProductAdoptionResponse)
def dry_run_product_adoption(
    payload: ProductAdoptionRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> ProductAdoptionResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product adoption not permitted")
    service = ProductAdoptionService(session)
    try:
        return service.adopt_product(payload, dry_run=True)
    except ProductAdoptionConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/products/adoptions", response_model=ProductAdoptionResponse, status_code=status.HTTP_201_CREATED)
def adopt_product(
    payload: ProductAdoptionRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> ProductAdoptionResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Product adoption not permitted")
    service = ProductAdoptionService(session)
    try:
        return service.adopt_product(payload, dry_run=False)
    except ProductAdoptionConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/products/{product_id}/graph", response_model=ProductComponentGraphResponse)
def get_product_component_graph(
    product_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> ProductComponentGraphResponse:
    _ensure(permissions, PERM_ORG_READ, "Product graph access denied")
    try:
        payload = ComponentGraphService(session).build_product_graph(product_id=product_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProductComponentGraphResponse.model_validate(payload)


@app.post("/standards-packs", response_model=StandardsPackResponse, status_code=status.HTTP_201_CREATED)
def create_standards_pack(
    payload: StandardsPackCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> StandardsPackResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Standards pack creation denied")
    service = StandardsPackService(session)
    try:
        pack = service.create_pack(
            key=payload.key,
            channel=payload.channel,
            version=payload.version,
            source_bundle=payload.source_bundle,
            description=payload.description,
            manifest=payload.manifest,
            assets=[item.model_dump(mode="python") for item in payload.assets],
        )
        session.commit()
    except StandardsPackConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Standards pack conflicts with existing persisted state") from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StandardsPackResponse.model_validate(pack)


@app.post("/products/{product_id}/standards/overrides", response_model=ProductStandardsOverrideResponse)
def upsert_product_standards_override(
    product_id: UUID,
    payload: ProductStandardsOverrideRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> ProductStandardsOverrideResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Standards override update denied")
    service = StandardsPackService(session)
    try:
        override = service.upsert_override(
            product_id=product_id,
            path=payload.path,
            override_mode=payload.override_mode,
            is_deferred=payload.is_deferred,
            reason=payload.reason,
            override_payload=payload.override_payload,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProductStandardsOverrideResponse.model_validate(override)


@app.post("/products/{product_id}/standards/evaluations", response_model=StandardsUpgradeRunResponse)
def evaluate_product_standards(
    product_id: UUID,
    payload: StandardsEvaluationRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> StandardsUpgradeRunResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Standards evaluation denied")
    service = StandardsPackService(session)
    try:
        run = service.evaluate_product(
            product_id=product_id,
            repo_root=Path(payload.repo_root),
            pack_key=payload.pack_key,
            channel=payload.channel,
            version=payload.version,
            installation_id=payload.installation_id,
            materialize_pr=payload.materialize_pr,
            generated_pr_number=payload.generated_pr_number,
        )
        session.commit()
    except GitHubAppConfigError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GitHubAppAuthError as exc:
        session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StandardsUpgradeRunResponse.model_validate(run)


@app.get("/products/{product_id}/standards/runs", response_model=list[StandardsUpgradeRunResponse])
def list_product_standards_runs(
    product_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[StandardsUpgradeRunResponse]:
    _ensure(permissions, PERM_ORG_READ, "Standards run access denied")
    runs = StandardsPackService(session).list_runs(product_id=product_id)
    return [StandardsUpgradeRunResponse.model_validate(item) for item in runs]


@app.post("/standards/runs/{standards_upgrade_run_id}/outcome", response_model=StandardsUpgradeRunResponse)
def record_standards_run_outcome(
    standards_upgrade_run_id: UUID,
    payload: StandardsUpgradeOutcomeRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> StandardsUpgradeRunResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Standards run outcome denied")
    service = StandardsPackService(session)
    try:
        run = service.record_outcome(
            standards_upgrade_run_id=standards_upgrade_run_id,
            outcome_status=payload.outcome_status,
            generated_pr_number=payload.generated_pr_number,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StandardsUpgradeRunResponse.model_validate(run)


@app.get("/orgs", response_model=list[OrganizationResponse])
def list_organizations(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[OrganizationResponse]:
    _ensure(permissions, PERM_ORG_READ, "Organization access denied")
    return [OrganizationResponse.model_validate(org) for org in list_orgs(session)]


@app.post("/orgs", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> OrganizationResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Organization creation not permitted")
    has_default = (
        session.query(OrgMembership)
        .filter(
            OrgMembership.user_id == permissions.user.user_id,
            OrgMembership.is_active.is_(True),
            OrgMembership.is_default.is_(True),
        )
        .first()
        is not None
    )
    org = Organization(
        name=payload.name.strip(),
        slug=payload.slug.strip(),
        documentation_visibility=payload.documentation_visibility,
    )
    session.add(org)
    session.flush()
    session.add(
        OrgMembership(
            org_id=org.org_id,
            user_id=permissions.user.user_id,
            email=permissions.user.username,
            display_name=permissions.user.username or permissions.user.user_id,
            is_active=True,
            is_default=not has_default,
        )
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Organization slug already exists") from exc
    session.refresh(org)
    return OrganizationResponse.model_validate(org)


@app.patch("/orgs/{org_id}", response_model=OrganizationResponse)
def update_organization(
    org_id: UUID,
    payload: OrganizationUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> OrganizationResponse:
    _ensure(permissions, PERM_ORG_MANAGE, "Organization updates not permitted")
    org = get_org(session, org_id=org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if payload.name is not None:
        org.name = payload.name.strip()
    if payload.slug is not None:
        org.slug = payload.slug.strip()
    if payload.documentation_visibility is not None:
        org.documentation_visibility = payload.documentation_visibility
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Organization slug already exists") from exc
    session.refresh(org)
    return OrganizationResponse.model_validate(org)


@app.get("/orgs/{org_id}/members", response_model=list[OrgMemberResponse])
def list_org_members(
    org_id: UUID,
    include_inactive: bool = Query(False),
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[OrgMemberResponse]:
    _ensure(permissions, PERM_ORG_MEMBERS_READ, "Organization member access denied")
    if get_org(session, org_id=org_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    query = session.query(OrgMembership).filter(OrgMembership.org_id == org_id)
    if not include_inactive:
        query = query.filter(OrgMembership.is_active.is_(True))
    members = query.order_by(OrgMembership.is_default.desc(), OrgMembership.created_at.asc()).all()
    return [OrgMemberResponse.model_validate(member) for member in members]


@app.post("/orgs/{org_id}/members", response_model=OrgMemberResponse, status_code=status.HTTP_201_CREATED)
def add_org_member(
    org_id: UUID,
    payload: OrgMemberCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> OrgMemberResponse:
    _ensure(permissions, PERM_ORG_MEMBERS_MANAGE, "Organization membership updates not permitted")
    if get_org(session, org_id=org_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    member = (
        session.query(OrgMembership)
        .filter(OrgMembership.org_id == org_id, OrgMembership.user_id == payload.user_id)
        .first()
    )
    has_default = (
        session.query(OrgMembership)
        .filter(
            OrgMembership.user_id == payload.user_id,
            OrgMembership.is_active.is_(True),
            OrgMembership.is_default.is_(True),
        )
        .first()
        is not None
    )
    if member is None:
        member = OrgMembership(
            org_id=org_id,
            user_id=payload.user_id,
            email=payload.email,
            display_name=payload.display_name,
            is_active=True,
            is_default=not has_default,
        )
        session.add(member)
    elif member.is_active:
        raise HTTPException(status_code=409, detail="Member already exists")
    else:
        member.email = payload.email
        member.display_name = payload.display_name
        member.is_active = True
        member.archived_at = None
        if not has_default:
            member.is_default = True
    session.commit()
    session.refresh(member)
    return OrgMemberResponse.model_validate(member)


@app.delete("/orgs/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_org_member(
    org_id: UUID,
    user_id: str,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> None:
    _ensure(permissions, PERM_ORG_MEMBERS_MANAGE, "Organization membership updates not permitted")
    if get_org(session, org_id=org_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    member = (
        session.query(OrgMembership)
        .filter(OrgMembership.org_id == org_id, OrgMembership.user_id == user_id)
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    member.is_active = False
    member.is_default = False
    member.archived_at = datetime.now(timezone.utc)
    session.commit()
    return None


@app.post("/orgs/{org_id}/members/{user_id}/default", response_model=OrgMemberResponse)
def set_default_org_member(
    org_id: UUID,
    user_id: str,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> OrgMemberResponse:
    _ensure(permissions, PERM_ORG_MEMBERS_MANAGE, "Default org update not permitted")
    if get_org(session, org_id=org_id) is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    member = (
        session.query(OrgMembership)
        .filter(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
            OrgMembership.is_active.is_(True),
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    session.query(OrgMembership).filter(
        OrgMembership.user_id == user_id,
        OrgMembership.is_active.is_(True),
    ).update({"is_default": False})
    member.is_default = True
    session.commit()
    session.refresh(member)
    return OrgMemberResponse.model_validate(member)


@app.get("/rbac/permissions", response_model=list[PermissionResponse])
def list_permissions(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[PermissionResponse]:
    _ensure(permissions, PERM_PLATFORM_READ, "RBAC access denied")
    store = DatabaseRBACStore()
    return [PermissionResponse.model_validate(permission) for permission in store.list_permissions(session)]


@app.get("/rbac/feature-flags", response_model=list[FeatureFlagResponse])
def list_feature_flags(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[FeatureFlagResponse]:
    _ensure(permissions, PERM_PLATFORM_READ, "RBAC access denied")
    store = DatabaseRBACStore()
    return [FeatureFlagResponse.model_validate(feature_flag) for feature_flag in store.list_feature_flags(session)]


@app.get("/rbac/roles", response_model=list[RoleResponse])
def list_roles(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[RoleResponse]:
    _ensure(permissions, PERM_PLATFORM_READ, "RBAC access denied")
    store = DatabaseRBACStore()
    return [RoleResponse.model_validate(role) for role in store.list_roles(session)]


@app.put("/rbac/roles/{role_id}/permissions", response_model=RoleResponse)
def update_role_permissions(
    role_id: UUID,
    payload: RolePermissionsUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> RoleResponse:
    _ensure_rbac_admin(permissions)
    store = DatabaseRBACStore()
    role = store.get_role(session, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        updated = store.set_role_permissions(session, role=role, permission_keys=payload.permission_keys)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unknown permission keys") from exc
    return RoleResponse.model_validate(updated)


@app.put("/rbac/roles/{role_id}/feature-flags", response_model=RoleResponse)
def update_role_feature_flags(
    role_id: UUID,
    payload: RoleFeatureFlagsUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> RoleResponse:
    _ensure_rbac_admin(permissions)
    store = DatabaseRBACStore()
    role = store.get_role(session, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    try:
        updated = store.set_role_feature_flags(session, role=role, feature_flag_keys=payload.feature_flag_keys)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unknown feature flag keys") from exc
    return RoleResponse.model_validate(updated)


@app.get("/secrets", response_model=list[SecretResponse])
def list_secrets(
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[SecretResponse]:
    _ensure(permissions, PERM_PLATFORM_READ, "Secret access denied")
    secrets = session.query(Secret).order_by(Secret.key.asc()).all()
    return [SecretResponse.model_validate(secret) for secret in secrets]


@app.get("/secrets/{secret_id}", response_model=SecretResponse)
def get_secret(
    secret_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> SecretResponse:
    _ensure(permissions, PERM_PLATFORM_READ, "Secret access denied")
    secret = session.get(Secret, secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    return SecretResponse.model_validate(secret)


@app.post("/secrets", response_model=SecretResponse, status_code=status.HTTP_201_CREATED)
def create_secret(
    payload: SecretCreateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> SecretResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Secret updates not permitted")
    if payload.kind not in SECRET_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported secret kind")
    secret = Secret(
        key=payload.key.strip(),
        name=payload.name.strip(),
        kind=payload.kind,
        description=payload.description,
        value_ciphertext=encrypt_secret(payload.value),
        last_rotated_at=datetime.now(timezone.utc),
    )
    session.add(secret)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Secret key already exists") from exc
    session.refresh(secret)
    return SecretResponse.model_validate(secret)


@app.patch("/secrets/{secret_id}", response_model=SecretResponse)
def update_secret(
    secret_id: UUID,
    payload: SecretUpdateRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> SecretResponse:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Secret updates not permitted")
    secret = session.get(Secret, secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    if payload.kind is not None and payload.kind not in SECRET_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported secret kind")
    if payload.key is not None:
        secret.key = payload.key.strip()
    if payload.name is not None:
        secret.name = payload.name.strip()
    if payload.kind is not None:
        secret.kind = payload.kind
    if payload.description is not None:
        secret.description = payload.description
    if payload.value is not None:
        secret.value_ciphertext = encrypt_secret(payload.value)
        secret.last_rotated_at = datetime.now(timezone.utc)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Secret key already exists") from exc
    session.refresh(secret)
    return SecretResponse.model_validate(secret)


@app.delete("/secrets/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_secret(
    secret_id: UUID,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> None:
    _ensure(permissions, PERM_PLATFORM_MANAGE, "Secret updates not permitted")
    secret = session.get(Secret, secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    session.delete(secret)
    session.commit()
    return None


@app.get("/settings", response_model=list[SettingResponse])
def list_settings(
    scope_type: SettingScopeType,
    scope_id: str,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> list[SettingResponse]:
    resolved_scope_id = _ensure_settings_access(
        permissions,
        scope_type=scope_type,
        scope_id=scope_id,
        write=False,
    )
    settings = (
        session.query(Setting)
        .filter(Setting.scope_type == scope_type, Setting.scope_id == resolved_scope_id)
        .order_by(Setting.key.asc())
        .all()
    )
    return [SettingResponse.model_validate(setting) for setting in settings]


@app.put("/settings/{scope_type}/{scope_id}/{key}", response_model=SettingResponse)
def upsert_setting(
    scope_type: SettingScopeType,
    scope_id: str,
    key: str,
    payload: SettingUpsertRequest,
    session: Session = Depends(get_session),
    permissions: PermissionContext = Depends(get_permission_context),
) -> SettingResponse:
    resolved_scope_id = _ensure_settings_access(
        permissions,
        scope_type=scope_type,
        scope_id=scope_id,
        write=True,
    )
    setting = (
        session.query(Setting)
        .filter(
            Setting.scope_type == scope_type,
            Setting.scope_id == resolved_scope_id,
            Setting.key == key,
        )
        .first()
    )
    if setting is None:
        setting = Setting(
            scope_type=scope_type,
            scope_id=resolved_scope_id,
            key=key,
            value_json=payload.value,
            created_by=permissions.user.user_id,
            updated_by=permissions.user.user_id,
        )
        session.add(setting)
    else:
        setting.value_json = payload.value
        setting.updated_by = permissions.user.user_id
    session.commit()
    session.refresh(setting)
    return SettingResponse.model_validate(setting)
