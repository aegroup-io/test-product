from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    documentation_visibility: Literal["shared", "isolated"] = "shared"


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, min_length=1)
    documentation_visibility: Literal["shared", "isolated"] | None = None


class OrganizationResponse(BaseModel):
    org_id: UUID
    name: str
    slug: str
    documentation_visibility: Literal["shared", "isolated"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrgMemberCreateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    email: str | None = None
    display_name: str | None = None


class OrgMemberResponse(BaseModel):
    org_id: UUID
    user_id: str
    email: str | None = None
    display_name: str | None = None
    is_active: bool
    is_default: bool
    archived_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    user_id: str
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    status: str | None = None


class UserSearchResponse(BaseModel):
    users: list[UserResponse]
    next_token: str | None = None


class UserLookupRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class UserLookupResponse(BaseModel):
    users: list[UserResponse]


class PermissionResponse(BaseModel):
    permission_id: UUID
    key: str
    description: str
    category: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeatureFlagResponse(BaseModel):
    feature_flag_id: UUID
    key: str
    description: str
    category: str | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RolePermissionsUpdateRequest(BaseModel):
    permission_keys: list[str]


class RoleFeatureFlagsUpdateRequest(BaseModel):
    feature_flag_keys: list[str]


class RoleResponse(BaseModel):
    role_id: UUID
    slug: str
    name: str
    description: str | None = None
    is_system: bool
    permissions: list[PermissionResponse]
    feature_flags: list[FeatureFlagResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIAgentCreateRequest(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    system_prompt: str = Field(min_length=1)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    default_model_id: UUID | None = None
    is_active: bool = True


class AIAgentUpdateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    tool_policy: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    default_model_id: UUID | None = None
    is_active: bool | None = None


class AIAgentResponse(BaseModel):
    agent_id: UUID
    key: str
    name: str
    description: str | None = None
    system_prompt: str
    tool_policy: dict[str, Any]
    output_schema: dict[str, Any]
    default_model_id: UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIProviderCreateRequest(BaseModel):
    key: str = Field(min_length=1)
    type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    is_active: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    compliance: dict[str, Any] = Field(default_factory=dict)


class AIProviderUpdateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=1)
    type: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    config: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None


class AIProviderResponse(BaseModel):
    provider_id: UUID
    key: str
    type: str
    name: str
    is_active: bool
    config: dict[str, Any]
    compliance: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIModelCreateRequest(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    provider_model_id: str | None = None
    can_embed: bool = False
    can_rerank: bool = False
    can_chat: bool = False
    can_vision: bool = False
    can_audio: bool = False
    default_workload: str | None = None
    is_default: bool = False
    restricted_content_only: bool = False
    is_active: bool = True
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    cost: dict[str, Any] = Field(default_factory=dict)
    default_params: dict[str, Any] = Field(default_factory=dict)
    compliance: dict[str, Any] = Field(default_factory=dict)


class AIModelUpdateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    provider_model_id: str | None = None
    can_embed: bool | None = None
    can_rerank: bool | None = None
    can_chat: bool | None = None
    can_vision: bool | None = None
    can_audio: bool | None = None
    default_workload: str | None = None
    is_default: bool | None = None
    restricted_content_only: bool | None = None
    is_active: bool | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    cost: dict[str, Any] | None = None
    default_params: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None


class AIModelResponse(BaseModel):
    model_id: UUID
    provider_id: UUID
    key: str
    name: str
    provider_model_id: str | None = None
    can_embed: bool
    can_rerank: bool
    can_chat: bool
    can_vision: bool
    can_audio: bool
    default_workload: str | None = None
    is_default: bool
    restricted_content_only: bool
    is_active: bool
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    cost: dict[str, Any]
    default_params: dict[str, Any]
    compliance: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIModelTestResponse(BaseModel):
    ok: bool
    message: str
    provider_type: str | None = None
    provider_model_id: str | None = None


SecretKind = Literal[
    "api_token",
    "client_secret",
    "shared_secret",
    "signing_key",
    "ai_api_key",
    "git_personal_access_token",
    "databricks_access_token",
    "gcp_service_account_key",
    "github_webhook_secret",
]
SettingScopeType = Literal["platform", "org", "user"]


class SecretCreateRequest(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: SecretKind
    value: str = Field(min_length=1)
    description: str | None = None


class SecretUpdateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    kind: SecretKind | None = None
    value: str | None = Field(default=None, min_length=1)
    description: str | None = None


class SecretResponse(BaseModel):
    secret_id: UUID
    key: str
    name: str
    kind: SecretKind
    description: str | None = None
    has_value: bool
    created_at: datetime
    updated_at: datetime
    last_rotated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BranchSummary(BaseModel):
    name: str
    head_sha: str
    is_default: bool


class RepoLookupRequest(BaseModel):
    secret_id: UUID
    q: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class RepoLookupPermissions(BaseModel):
    pull: bool | None = None
    push: bool | None = None
    admin: bool | None = None


class RepoLookupItem(BaseModel):
    github_owner: str
    github_repo: str
    full_name: str
    visibility: Literal["public", "private", "internal"] = "private"
    is_private: bool
    is_archived: bool
    default_branch: str
    permissions: RepoLookupPermissions | None = None


class RepoBranchesRequest(BaseModel):
    secret_id: UUID
    github_owner: str = Field(min_length=1)
    github_repo: str = Field(min_length=1)


class RepoCreateRequest(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    github_owner: str = Field(min_length=1)
    github_repo: str = Field(min_length=1)
    visibility: Literal["public", "private", "internal"] = "private"
    default_branch: str = Field(min_length=1)
    git_auth_secret_id: UUID
    org_ids: list[UUID] = Field(min_length=1)


class RepoUpdateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    github_owner: str | None = Field(default=None, min_length=1)
    github_repo: str | None = Field(default=None, min_length=1)
    visibility: Literal["public", "private", "internal"] | None = None
    default_branch: str | None = Field(default=None, min_length=1)
    git_auth_secret_id: UUID | None = None
    org_ids: list[UUID] | None = Field(default=None, min_length=1)


class RepoOrgMappingResponse(BaseModel):
    org_id: UUID
    org_name: str
    active_product_count: int


class RepoResponse(BaseModel):
    repo_id: UUID
    org_id: UUID
    key: str
    name: str
    provider: str
    github_owner: str
    github_repo: str
    visibility: str
    default_branch: str
    clone_url: str
    git_auth_secret_id: UUID
    org_ids: list[UUID]
    org_mappings: list[RepoOrgMappingResponse]
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SettingUpsertRequest(BaseModel):
    value: Any


class SettingResponse(BaseModel):
    setting_id: UUID
    scope_type: SettingScopeType
    scope_id: str
    key: str
    value_json: Any
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserInfoResponse(BaseModel):
    user_id: str
    username: str | None = None
    roles: list[str]
    permissions: list[str]
    feature_flags: list[str]
    org_ids: list[UUID]
    default_org_id: UUID | None = None
    claims: dict[str, Any]


class PlatformSummaryResponse(BaseModel):
    organization_count: int
    provider_count: int
    model_count: int
    agent_count: int
    product_count: int
    repository_binding_count: int
    lane_count: int
    component_node_count: int
    webhook_delivery_count: int
    membership_count: int
    role_count: int
    permission_count: int
    feature_flag_count: int
    secret_count: int
    setting_count: int


class ObservabilityCorrelationResponse(BaseModel):
    org_id: UUID | None = None
    product_id: UUID | None = None
    repo_id: UUID | None = None
    work_item_id: UUID | None = None
    lane_id: UUID | None = None
    agent_session_id: UUID | None = None
    delivery_id: UUID | None = None
    github_delivery_guid: str | None = None
    installation_id: str | None = None


class ObservabilityNotificationResponse(BaseModel):
    notification_type: str
    severity: str
    title: str
    summary: str
    observed_at: datetime | None = None
    target_kind: str
    target_id: str
    source_kind: str
    correlation: ObservabilityCorrelationResponse


class LaneStatusSummaryResponse(BaseModel):
    lane_id: UUID
    product_id: UUID
    work_item_id: UUID
    issue_number: int
    title: str
    state: str
    attempt: int
    retry_due_at: datetime | None = None
    heartbeat_status: str
    summary: str
    updated_at: datetime | None = None


class LaneActivityResponse(BaseModel):
    kind: Literal["session_event", "signal"]
    event_type: str
    summary: str | None = None
    severity: str | None = None
    observed_at: datetime | None = None
    source_kind: str
    correlation: ObservabilityCorrelationResponse
    payload: dict[str, Any] | list | str | int | float | bool | None


class ObservabilityArtifactReferencesResponse(BaseModel):
    workspace_uri: str | None = None
    artifact_uri: str | None = None
    log_uri: str | None = None
    cache_uri: str | None = None


class FleetObservabilityResponse(BaseModel):
    generated_at: datetime
    queue_depth: int
    active_lane_count: int
    retry_backlog_count: int
    dead_letter_backlog_count: int
    mirror_lag_seconds: int | None = None
    stale_heartbeat_count: int
    lane_state_counts: dict[str, int]
    notification_count: int
    notifications: list[ObservabilityNotificationResponse]
    lanes: list[LaneStatusSummaryResponse]


class LaneObservabilityResponse(BaseModel):
    lane: "LaneResponse"
    correlation: ObservabilityCorrelationResponse
    heartbeat_status: str
    summary: str
    last_activity_at: datetime | None = None
    recent_activity: list[LaneActivityResponse]
    notifications: list[ObservabilityNotificationResponse]
    artifact_references: ObservabilityArtifactReferencesResponse


class GraphFreshnessResponse(BaseModel):
    observed_at: datetime | None = None
    status: str
    stale_after_seconds: int


class GraphSignalResponse(BaseModel):
    signal_id: UUID
    signal_type: str
    severity: str | None = None
    value: dict[str, Any] | list | str | int | float | bool | None
    observed_at: datetime | None = None
    source_kind: str


class GraphWorkItemSummaryResponse(BaseModel):
    work_item_id: UUID
    issue_number: int
    title: str
    status: str
    dependency_state: str
    updated_at: datetime | None = None


class GraphPullRequestSummaryResponse(BaseModel):
    pull_request_id: UUID
    number: int
    title: str
    state: str
    review_state: str | None = None
    updated_at: datetime | None = None


class GraphLaneSummaryResponse(BaseModel):
    lane_id: UUID
    work_item_id: UUID
    state: str
    attempt: int
    updated_at: datetime | None = None


class GraphNodeOverlayResponse(BaseModel):
    active_work_items: list[GraphWorkItemSummaryResponse]
    open_pull_requests: list[GraphPullRequestSummaryResponse]
    active_lanes: list[GraphLaneSummaryResponse]
    incidents: list[GraphSignalResponse]
    signals: list[GraphSignalResponse]
    hotspot_score: int
    blocked_dependency_count: int


class GraphNodeResponse(BaseModel):
    component_node_id: UUID
    product_id: UUID
    type: str
    key: str
    name: str
    owner: str | None = None
    version: str | None = None
    status: str | None = None
    source_kind: str
    source_ref: str | None = None
    distance: int
    freshness: GraphFreshnessResponse
    overlay: GraphNodeOverlayResponse


class GraphEdgeResponse(BaseModel):
    component_edge_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    relationship_type: str
    source_kind: str
    confidence: float | None = None
    last_verified_at: datetime | None = None
    freshness: GraphFreshnessResponse
    blocked: bool


class GraphBlockedDependencyResponse(BaseModel):
    component_edge_id: UUID
    from_node_id: UUID
    from_key: str
    to_node_id: UUID
    to_key: str
    relationship_type: str
    reason: str
    cross_product: bool
    observed_at: datetime | None = None


class GraphHotspotResponse(BaseModel):
    component_node_id: UUID
    product_id: UUID
    key: str
    name: str
    type: str
    hotspot_score: int
    active_lane_count: int
    active_work_item_count: int
    observed_at: datetime | None = None


class GraphSliceResponse(BaseModel):
    scope: str
    product_id: UUID
    lane_id: UUID | None = None
    generated_at: datetime
    freshness: GraphFreshnessResponse
    anchor_node_ids: list[UUID]
    depth: int
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    blocked_dependencies: list[GraphBlockedDependencyResponse]
    hotspots: list[GraphHotspotResponse]


class ProductSetupDiagnosticResponse(BaseModel):
    classification: str
    code: str
    message: str
    path: str | None = None


class RepositoryBindingResponse(BaseModel):
    repo_id: UUID
    product_id: UUID
    github_repository_node_id: str | None = None
    owner: str
    name: str
    default_branch: str
    visibility: str
    description: str | None = None
    is_archived: bool
    seed_source: str | None = None
    adoption_state: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductSeedJobSummaryResponse(BaseModel):
    seed_job_id: UUID
    product_id: UUID | None = None
    requested_by: str | None = None
    status: str
    dry_run: bool
    setup_state: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductResponse(BaseModel):
    product_id: UUID
    org_id: UUID
    key: str
    name: str
    description: str | None = None
    status: str
    primary_repo_id: UUID | None = None
    primary_project_id: UUID | None = None
    baseline_channel: str | None = None
    standards_pack_key: str | None = None
    standards_pack_version: str | None = None
    agent_core_version: str | None = None
    execution_profile: str | None = None
    component_root_node_id: UUID | None = None
    manifest_schema_version: int | None = None
    setup_state: str
    setup_diagnostics: list[ProductSetupDiagnosticResponse]
    effective_config: dict[str, Any]
    operator_overrides: dict[str, Any]
    last_config_refresh_at: datetime | None = None
    last_accepted_config_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    latest_seed_job: ProductSeedJobSummaryResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductSeedRequest(BaseModel):
    org_id: UUID
    installation_id: str | None = Field(default=None, min_length=1)
    product_key: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    description: str | None = None
    github_owner: str = Field(min_length=1)
    github_repo: str = Field(min_length=1)
    github_visibility: Literal["private", "internal", "public"] = "private"
    github_default_branch: str = Field(default="dev", min_length=1)
    github_project_node_id: str | None = Field(default=None, min_length=1)
    github_project_number: int | None = Field(default=None, ge=1)
    github_project_title: str | None = Field(default=None, min_length=1)
    status_field: str = Field(default="Status", min_length=1)
    ready_status: str = Field(default="Todo", min_length=1)
    done_status: str = Field(default="Done", min_length=1)
    baseline_channel: str | None = Field(default=None, min_length=1)
    standards_pack: str | None = Field(default=None, min_length=1)
    execution_profile: str | None = Field(default=None, min_length=1)
    max_concurrent_lanes: int | None = Field(default=None, ge=1)
    required_secret_keys: list[str] = Field(default_factory=list)
    dry_run: bool = False

    @model_validator(mode="after")
    def validate_seed_mode(self) -> "ProductSeedRequest":
        if (self.github_project_node_id is None) ^ (self.github_project_number is None):
            raise ValueError("github_project_node_id and github_project_number must be provided together when binding an existing project")
        return self


class ProductSeedJobResponse(BaseModel):
    seed_job_id: UUID
    org_id: UUID
    product_id: UUID | None = None
    requested_by: str | None = None
    status: str
    dry_run: bool
    request_payload: dict[str, Any]
    progress_payload: list[dict[str, Any]]
    error_payload: list[dict[str, Any]]
    audit_payload: list[dict[str, Any]]
    rendered_file_paths: list[str]
    repo_summary: dict[str, Any]
    project_summary: dict[str, Any]
    setup_state: str | None = None
    setup_diagnostics: list[ProductSetupDiagnosticResponse]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    product: ProductResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryResponse(BaseModel):
    delivery_id: UUID
    github_delivery_guid: str
    event_name: str
    installation_id: str | None = None
    received_at: datetime
    processed_at: datetime | None = None
    status: str
    payload_hash: str | None = None
    replay_count: int
    delivery_attempts: int
    error_detail: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryIntakeResponse(WebhookDeliveryResponse):
    duplicate: bool = False


class WorkItemMirrorResponse(BaseModel):
    work_item_id: UUID
    repo_id: UUID
    project_id: UUID | None = None
    github_issue_node_id: str | None = None
    issue_number: int
    title: str
    body: str | None = None
    title_normalized: str | None = None
    body_normalized: str | None = None
    status: str
    status_source: str | None = None
    labels: list[str]
    assignees: list[str]
    dependencies: list[str]
    dependency_state: str
    dependency_details: list[dict[str, Any]]
    priority_hint: str | None = None
    linked_prs: list[str]
    eligibility_flags: list[str]
    handoff_status: str
    requires_repair: bool
    repair_reasons: list[str]
    last_normalized_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PullRequestMirrorResponse(BaseModel):
    pull_request_id: UUID
    repo_id: UUID
    github_pr_node_id: str
    number: int
    title: str
    body: str | None = None
    body_normalized: str | None = None
    state: str
    is_draft: bool
    head_branch: str | None = None
    base_branch: str | None = None
    checks_rollup: dict[str, Any]
    review_state: str | None = None
    merge_state: str | None = None
    linked_work_item_ids: list[str]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class GitHubProjectFieldOptionMirrorResponse(BaseModel):
    project_field_option_id: UUID
    github_project_option_id: str
    name: str
    color: str | None = None
    position: int | None = None

    model_config = ConfigDict(from_attributes=True)


class GitHubProjectFieldMirrorResponse(BaseModel):
    project_field_id: UUID
    github_project_field_node_id: str
    name: str
    data_type: str
    options: list[GitHubProjectFieldOptionMirrorResponse]

    model_config = ConfigDict(from_attributes=True)


class GitHubProjectItemMirrorResponse(BaseModel):
    project_item_id: UUID
    github_project_item_node_id: str
    github_content_node_id: str | None = None
    content_type: str | None = None
    work_item_id: UUID | None = None
    pull_request_id: UUID | None = None
    status_name: str | None = None
    field_values_payload: list[Any]
    last_reconciled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GitHubProjectMirrorResponse(BaseModel):
    project_id: UUID
    product_id: UUID
    github_project_node_id: str | None = None
    number: int
    title: str
    status_field_name: str
    status_options: list[str]
    last_reconciled_at: datetime | None = None
    mirror_version: int
    created_at: datetime
    updated_at: datetime
    fields: list[GitHubProjectFieldMirrorResponse]
    items: list[GitHubProjectItemMirrorResponse]

    model_config = ConfigDict(from_attributes=True)


PermissionLevel = Literal["none", "read", "write", "maintain", "admin"]


class ProductSetupDiagnosticResponse(BaseModel):
    classification: Literal["blocking setup error", "recoverable drift", "advisory warning"]
    code: str
    message: str
    path: str | None = None


class ManagedAssetResponse(BaseModel):
    asset_id: UUID
    path: str
    kind: str
    management_mode: str
    upstream_bundle_version: str | None = None
    drift_status: str | None = None
    last_pr_number: int | None = None
    last_applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RepositoryBindingSummaryResponse(BaseModel):
    repo_id: UUID
    github_repository_node_id: str | None = None
    owner: str
    name: str
    default_branch: str
    visibility: str
    description: str | None = None
    is_archived: bool
    seed_source: str | None = None
    adoption_state: str | None = None
    raw_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GitHubProjectMirrorSummaryResponse(BaseModel):
    project_id: UUID
    github_project_node_id: str | None = None
    number: int
    title: str
    status_field_name: str
    status_options: list[str]
    raw_payload: dict[str, Any]
    mirror_version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductDeliveryPullRequestSummaryResponse(BaseModel):
    github_pr_node_id: str | None = None
    number: int | None = None
    title: str | None = None
    state: str | None = None
    is_draft: bool = False
    review_state: str | None = None
    merge_state: str | None = None
    merged_at: datetime | None = None
    url: str | None = None


class ProductDeliveryWorkItemSummaryResponse(BaseModel):
    work_item_id: UUID
    repo_id: UUID
    repo_owner: str
    repo_name: str
    issue_number: int
    title: str
    status: str
    status_source: str | None = None
    dependency_state: str
    priority_hint: str | None = None
    handoff_status: str
    eligibility_flags: list[str] = Field(default_factory=list)
    mirror_state: str
    requires_repair: bool
    repair_reasons: list[str] = Field(default_factory=list)
    last_normalized_at: datetime | None = None
    updated_at: datetime
    project_status_name: str | None = None
    url: str | None = None
    linked_pull_requests: list[ProductDeliveryPullRequestSummaryResponse] = Field(default_factory=list)


class ProductDeliveryWorkPressureResponse(BaseModel):
    total_open_count: int
    triage_count: int
    ready_count: int
    blocked_count: int
    in_progress_count: int
    in_review_count: int
    done_count: int
    ambiguous_count: int
    stale_count: int


class ProductDeliveryProjectSummaryResponse(BaseModel):
    project_id: UUID
    number: int
    title: str
    status_field_name: str
    item_count: int
    issue_count: int
    pull_request_count: int
    mirror_state: str
    last_reconciled_at: datetime | None = None
    url: str | None = None


class ProductDeliveryCockpitResponse(BaseModel):
    mirror_state: str
    work_pressure: ProductDeliveryWorkPressureResponse
    project: ProductDeliveryProjectSummaryResponse | None = None
    work_items: list[ProductDeliveryWorkItemSummaryResponse] = Field(default_factory=list)
    remaining_work_item_count: int = 0


class ProductResponse(BaseModel):
    product_id: UUID
    org_id: UUID
    key: str
    name: str
    description: str | None = None
    status: str
    baseline_channel: str | None = None
    standards_pack_key: str | None = None
    standards_pack_version: str | None = None
    agent_core_version: str | None = None
    execution_profile: str | None = None
    component_root_node_id: UUID | None = None
    manifest_schema_version: int | None = None
    setup_state: str
    setup_diagnostics: list[ProductSetupDiagnosticResponse]
    effective_config: dict[str, Any]
    operator_overrides: dict[str, Any]
    last_config_refresh_at: datetime | None = None
    last_accepted_config_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    latest_seed_job: ProductSeedJobSummaryResponse | None = None
    primary_repo: RepositoryBindingSummaryResponse | None = None
    primary_project: GitHubProjectMirrorSummaryResponse | None = None
    managed_assets: list[ManagedAssetResponse] = Field(default_factory=list)
    delivery_cockpit: ProductDeliveryCockpitResponse | None = None


class ProductSummaryResponse(ProductResponse):
    pass


class OperatorActionRequest(BaseModel):
    actor_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ProductRefreshRequest(OperatorActionRequest):
    repo_root: str | None = Field(default=None, min_length=1)
    operator_overrides: dict[str, Any] = Field(default_factory=dict)


class ProductMirrorRefreshRequest(OperatorActionRequest):
    pass


class LaneRetryRequest(OperatorActionRequest):
    pass


class LaneCancelRequest(OperatorActionRequest):
    disposition: Literal["terminate", "quarantine"] = "terminate"


class LaneApproveRequest(OperatorActionRequest):
    approval_payload: dict[str, Any] = Field(default_factory=dict)


class LaneHumanInputRequest(OperatorActionRequest):
    input_payload: dict[str, Any] = Field(default_factory=dict)


class RunnerLaunchRequestResponse(BaseModel):
    lane_id: UUID
    agent_session_id: UUID
    lane_metadata: dict[str, Any]
    issue_context: dict[str, Any]
    instruction_bundle: dict[str, Any]
    policy: dict[str, Any]
    artifact_destinations: dict[str, str]
    secret_references: list[str]
    tool_permissions: list[str]
    required_capabilities: list[str]


class RunnerHandshakeRequest(BaseModel):
    runner_session_id: str = Field(min_length=1)
    runner_version: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    environment_identity: str = Field(min_length=1)
    heartbeat_at: datetime | None = None
    thread_id: str | None = None


class RunnerHeartbeatRequest(BaseModel):
    heartbeat_at: datetime | None = None
    thread_id: str | None = None
    turn_id: str | None = None


class RunnerEventRequest(BaseModel):
    event_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime | None = None
    summary: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    token_usage: dict[str, int] | None = None
    tool_name: str | None = None
    tool_status: str | None = None
    error_category: str | None = None


class ProductReferenceResponse(BaseModel):
    product_id: UUID
    key: str
    name: str
    status: str


class LaneWorkItemSummaryResponse(BaseModel):
    work_item_id: UUID
    issue_number: int
    title: str
    status: str
    dependency_state: str
    handoff_status: str
    linked_prs: list[str]
    updated_at: datetime


class ExecutionEnvironmentSummaryResponse(BaseModel):
    execution_environment_id: UUID
    status: str
    runtime_provider: str
    container_image: str | None = None
    container_handle: str | None = None
    workspace_uri: str | None = None
    artifact_uri: str | None = None
    log_uri: str | None = None
    cache_uri: str | None = None
    heartbeat_at: datetime | None = None
    terminated_at: datetime | None = None
    quarantine_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LaneAgentSessionSummaryResponse(BaseModel):
    agent_session_id: UUID
    thread_id: str | None = None
    turn_id: str | None = None
    runner_session_id: str | None = None
    runner_version: str | None = None
    status: str
    capabilities: list[str]
    environment_identity: str | None = None
    last_event: str | None = None
    last_event_at: datetime | None = None
    heartbeat_at: datetime | None = None
    wait_reason: str | None = None
    continuation_summary: dict[str, Any]
    last_error_category: str | None = None
    turn_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_call_count: int
    requires_human_input: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LaneResponse(BaseModel):
    lane_id: UUID
    product_id: UUID
    repo_id: UUID
    work_item_id: UUID
    attempt: int
    state: str
    claimed_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    branch_name: str | None = None
    retry_due_at: datetime | None = None
    handoff_reason: str | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    product: ProductReferenceResponse
    repository: RepositoryBindingSummaryResponse
    work_item: LaneWorkItemSummaryResponse
    execution_environment: ExecutionEnvironmentSummaryResponse | None = None
    agent_session: LaneAgentSessionSummaryResponse | None = None


class BaselineUpgradeRunSummaryResponse(BaseModel):
    standards_upgrade_run_id: UUID
    outcome_kind: str
    outcome_status: str | None = None
    generated_pr_number: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BaselineResponse(BaseModel):
    product_id: UUID
    org_id: UUID
    product_key: str
    product_name: str
    product_status: str
    baseline_channel: str | None = None
    standards_pack_key: str | None = None
    standards_pack_version: str | None = None
    agent_core_version: str | None = None
    setup_state: str
    setup_diagnostics: list[ProductSetupDiagnosticResponse]
    drift_status: str
    managed_asset_counts: dict[str, int]
    managed_assets: list[ManagedAssetResponse]
    latest_run: BaselineUpgradeRunSummaryResponse | None = None
    last_config_refresh_at: datetime | None = None
    last_accepted_config_at: datetime | None = None


class ComponentNodeGraphResponse(BaseModel):
    component_node_id: UUID
    product_id: UUID
    type: str
    key: str
    name: str
    owner: str | None = None
    version: str | None = None
    status: str | None = None
    source_kind: str
    source_ref: str | None = None
    confidence: float | None = None
    confidence_status: Literal["confirmed", "uncertain", "unknown"]
    last_verified_at: datetime | None = None
    freshness_status: Literal["current", "stale", "unknown"]


class ComponentEdgeGraphResponse(BaseModel):
    component_edge_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    relationship: str
    source_kind: str
    source_ref: str | None = None
    confidence: float | None = None
    confidence_status: Literal["confirmed", "uncertain", "unknown"]
    last_verified_at: datetime | None = None
    freshness_status: Literal["current", "stale", "unknown"]
    precedence_state: Literal["effective", "shadowed"]


class ProductComponentGraphResponse(BaseModel):
    product_id: UUID
    component_root_node_id: UUID | None = None
    nodes: list[ComponentNodeGraphResponse]
    edges: list[ComponentEdgeGraphResponse]


class BranchProtectionSnapshotRequest(BaseModel):
    enabled: bool = True
    requires_pull_request: bool = True
    required_approving_review_count: int = Field(default=1, ge=0)
    allows_force_pushes: bool = False
    allows_deletions: bool = False


class RepositoryPermissionSnapshotRequest(BaseModel):
    contents: PermissionLevel = "write"
    pull_requests: PermissionLevel = "write"
    issues: PermissionLevel = "write"
    projects: PermissionLevel = "write"


class ProductAdoptionRepositoryRequest(BaseModel):
    github_repository_node_id: str | None = None
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    default_branch: str = Field(min_length=1)
    visibility: Literal["public", "private", "internal"] = "private"
    description: str | None = None
    is_archived: bool = False
    branch_protection: BranchProtectionSnapshotRequest
    permissions: RepositoryPermissionSnapshotRequest


class ProductAdoptionProjectRequest(BaseModel):
    github_project_node_id: str | None = None
    number: int = Field(ge=1)
    title: str = Field(min_length=1)
    status_field_name: str = Field(min_length=1)
    status_options: list[str] = Field(min_length=1)


class ProductAdoptionRequest(BaseModel):
    org_id: UUID
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    repo_root: str = Field(min_length=1)
    baseline_channel: str = Field(default="stable", min_length=1)
    agent_core_version: str = Field(default="0.1.0", min_length=1)
    execution_profile: str = Field(default="standard-python", min_length=1)
    repository: ProductAdoptionRepositoryRequest
    project: ProductAdoptionProjectRequest
    operator_overrides: dict[str, Any] = Field(default_factory=dict)


class ProductAdoptionResponse(BaseModel):
    dry_run: bool
    product: ProductResponse


class StandardsPackAssetRequest(BaseModel):
    path: str = Field(min_length=1)
    kind: str | None = Field(default=None, min_length=1)
    default_mode: Literal["managed", "section-managed", "advisory", "local"]
    content_text: str
    ownership_metadata: dict[str, Any] = Field(default_factory=dict)


class StandardsPackCreateRequest(BaseModel):
    key: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_bundle: str = Field(min_length=1)
    description: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    assets: list[StandardsPackAssetRequest] = Field(default_factory=list)


class StandardsPackAssetResponse(BaseModel):
    standards_pack_asset_id: UUID
    path: str
    kind: str
    default_mode: str
    content_text: str
    ownership_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StandardsPackResponse(BaseModel):
    standards_pack_id: UUID
    key: str
    channel: str
    version: str
    source_bundle: str
    description: str | None = None
    manifest: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    assets: list[StandardsPackAssetResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProductStandardsOverrideRequest(BaseModel):
    path: str = Field(min_length=1)
    override_mode: Literal["managed", "section-managed", "advisory", "local"] | None = None
    is_deferred: bool = False
    reason: str | None = None
    override_payload: dict[str, Any] = Field(default_factory=dict)


class ProductStandardsOverrideResponse(BaseModel):
    standards_override_id: UUID
    product_id: UUID
    path: str
    override_mode: str | None = None
    is_deferred: bool
    reason: str | None = None
    override_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StandardsEvaluationRequest(BaseModel):
    repo_root: str = Field(min_length=1)
    pack_key: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    version: str = Field(min_length=1)
    installation_id: str | None = Field(default=None, min_length=1)
    materialize_pr: bool = True
    generated_pr_number: int | None = Field(default=None, ge=1)


class StandardsUpgradeOutcomeRequest(BaseModel):
    outcome_status: Literal["accepted", "rejected", "deferred"]
    generated_pr_number: int | None = Field(default=None, ge=1)


class StandardsUpgradeAssetResponse(BaseModel):
    standards_upgrade_asset_id: UUID
    standards_upgrade_run_id: UUID
    path: str
    management_mode: str
    action: str
    drift_status: str
    patch_text: str | None = None
    detail: str | None = None
    metadata_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StandardsFollowUpItemResponse(BaseModel):
    standards_follow_up_item_id: UUID
    standards_upgrade_run_id: UUID
    product_id: UUID
    repo_id: UUID | None = None
    path: str
    title: str
    detail: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StandardsUpgradeRunResponse(BaseModel):
    standards_upgrade_run_id: UUID
    product_id: UUID
    repo_id: UUID | None = None
    standards_pack_id: UUID
    source_bundle: str
    source_version: str
    outcome_kind: str
    outcome_status: str
    generated_pr_number: int | None = None
    pr_title: str | None = None
    pr_body: str | None = None
    summary_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    assets: list[StandardsUpgradeAssetResponse] = Field(default_factory=list)
    follow_up_items: list[StandardsFollowUpItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
