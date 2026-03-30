export interface UserInfo {
  user_id: string;
  username?: string | null;
  roles: string[];
  permissions: string[];
  feature_flags: string[];
  org_ids: string[];
  default_org_id?: string | null;
  claims: Record<string, unknown>;
}

export interface OrganizationResponse {
  org_id: string;
  name: string;
  slug: string;
  documentation_visibility?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SecretResponse {
  secret_id: string;
  key: string;
  name: string;
  kind: string;
  description?: string | null;
  has_value: boolean;
  created_at: string;
  updated_at: string;
  last_rotated_at?: string | null;
}

export interface SecretCreateRequestPayload {
  key: string;
  name: string;
  kind: string;
  value: string;
  description?: string | null;
}

export interface GitRepoBranchResponse {
  name: string;
  head_sha: string;
  is_default: boolean;
}

export interface GitRepoLookupPermissionsResponse {
  pull?: boolean | null;
  push?: boolean | null;
  admin?: boolean | null;
}

export interface GitRepoLookupResultResponse {
  github_owner: string;
  github_repo: string;
  full_name: string;
  visibility: "private" | "internal" | "public";
  is_private: boolean;
  is_archived: boolean;
  default_branch: string;
  permissions?: GitRepoLookupPermissionsResponse | null;
}

export interface GitRepoLookupRequestPayload {
  secret_id: string;
  q?: string | null;
  limit?: number;
}

export interface GitRepoBranchesRequestPayload {
  secret_id: string;
  github_owner: string;
  github_repo: string;
}

export interface GitRepoOrgMappingResponse {
  org_id: string;
  org_name: string;
  active_product_count: number;
}

export interface GitRepoResponse {
  repo_id: string;
  org_id: string;
  key: string;
  name: string;
  provider: string;
  github_owner: string;
  github_repo: string;
  visibility: "private" | "internal" | "public";
  default_branch: string;
  clone_url: string;
  git_auth_secret_id: string;
  org_ids: string[];
  org_mappings: GitRepoOrgMappingResponse[];
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GitRepoCreateRequestPayload {
  key: string;
  name: string;
  github_owner: string;
  github_repo: string;
  visibility: "private" | "internal" | "public";
  default_branch: string;
  git_auth_secret_id: string;
  org_ids: string[];
}

export interface GitRepoUpdateRequestPayload {
  key?: string | null;
  name?: string | null;
  github_owner?: string | null;
  github_repo?: string | null;
  visibility?: "private" | "internal" | "public" | null;
  default_branch?: string | null;
  git_auth_secret_id?: string | null;
  org_ids?: string[] | null;
}

export interface SettingResponse {
  setting_id: string;
  scope_type: "platform" | "org" | "user";
  scope_id: string;
  key: string;
  value_json: unknown;
  created_by?: string | null;
  updated_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductSetupDiagnosticResponse {
  classification: string;
  code: string;
  message: string;
  path?: string | null;
}

export interface ManagedAssetResponse {
  managed_asset_id: string;
  product_id: string;
  path: string;
  kind: string;
  management_mode: string;
  upstream_bundle_version?: string | null;
  drift_status?: string | null;
  last_pr_number?: number | null;
  last_applied_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepositoryBindingSummaryResponse {
  repo_id: string;
  github_repository_node_id?: string | null;
  owner: string;
  name: string;
  default_branch: string;
  visibility: string;
  description?: string | null;
  is_archived: boolean;
  seed_source?: string | null;
  adoption_state?: string | null;
  raw_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface GitHubProjectMirrorSummaryResponse {
  project_id: string;
  github_project_node_id?: string | null;
  number: number;
  title: string;
  status_field_name: string;
  status_options: string[];
  raw_payload: Record<string, unknown>;
  mirror_version: number;
  created_at: string;
  updated_at: string;
}

export interface ProductDeliveryPullRequestSummaryResponse {
  github_pr_node_id?: string | null;
  number?: number | null;
  title?: string | null;
  state?: string | null;
  is_draft: boolean;
  review_state?: string | null;
  merge_state?: string | null;
  merged_at?: string | null;
  url?: string | null;
}

export interface ProductDeliveryWorkItemSummaryResponse {
  work_item_id: string;
  repo_id: string;
  repo_owner: string;
  repo_name: string;
  issue_number: number;
  title: string;
  status: string;
  status_source?: string | null;
  dependency_state: string;
  priority_hint?: string | null;
  handoff_status: string;
  eligibility_flags: string[];
  mirror_state: string;
  requires_repair: boolean;
  repair_reasons: string[];
  last_normalized_at?: string | null;
  updated_at: string;
  project_status_name?: string | null;
  url?: string | null;
  linked_pull_requests: ProductDeliveryPullRequestSummaryResponse[];
}

export interface ProductDeliveryWorkPressureResponse {
  total_open_count: number;
  triage_count: number;
  ready_count: number;
  blocked_count: number;
  in_progress_count: number;
  in_review_count: number;
  done_count: number;
  ambiguous_count: number;
  stale_count: number;
}

export interface ProductDeliveryProjectSummaryResponse {
  project_id: string;
  number: number;
  title: string;
  status_field_name: string;
  item_count: number;
  issue_count: number;
  pull_request_count: number;
  mirror_state: string;
  last_reconciled_at?: string | null;
  url?: string | null;
}

export interface ProductDeliveryCockpitResponse {
  mirror_state: string;
  work_pressure: ProductDeliveryWorkPressureResponse;
  project?: ProductDeliveryProjectSummaryResponse | null;
  work_items: ProductDeliveryWorkItemSummaryResponse[];
  remaining_work_item_count: number;
}

export interface ProductSummaryResponse {
  product_id: string;
  org_id: string;
  key: string;
  name: string;
  description?: string | null;
  status: string;
  baseline_channel?: string | null;
  standards_pack_key?: string | null;
  standards_pack_version?: string | null;
  agent_core_version?: string | null;
  execution_profile?: string | null;
  component_root_node_id?: string | null;
  manifest_schema_version?: number | null;
  setup_state: string;
  setup_diagnostics: ProductSetupDiagnosticResponse[];
  effective_config: Record<string, unknown>;
  operator_overrides: Record<string, unknown>;
  last_config_refresh_at?: string | null;
  last_accepted_config_at?: string | null;
  created_at: string;
  updated_at: string;
  latest_seed_job?: ProductSeedJobSummaryResponse | null;
  primary_repo?: RepositoryBindingSummaryResponse | null;
  primary_project?: GitHubProjectMirrorSummaryResponse | null;
  managed_assets: ManagedAssetResponse[];
  delivery_cockpit?: ProductDeliveryCockpitResponse | null;
}

export interface ProductSeedRequestPayload {
  org_id: string;
  installation_id?: string | null;
  product_key: string;
  product_name: string;
  description?: string | null;
  github_owner: string;
  github_repo: string;
  github_visibility: "private" | "internal" | "public";
  github_default_branch: string;
  github_project_node_id?: string | null;
  github_project_number?: number | null;
  github_project_title?: string | null;
  status_field: string;
  ready_status: string;
  done_status: string;
  baseline_channel?: string | null;
  standards_pack?: string | null;
  execution_profile?: string | null;
  max_concurrent_lanes?: number | null;
  required_secret_keys: string[];
  dry_run: boolean;
}

export interface ProductSeedRepositorySummaryResponse {
  github_repository_node_id: string;
  owner: string;
  name: string;
  default_branch: string;
  visibility: string;
  description?: string | null;
  permissions: Record<string, unknown>;
  branch_protection: Record<string, unknown>;
  raw_payload: Record<string, unknown>;
}

export interface ProductSeedProjectFieldResponse {
  node_id?: string;
  name?: string;
  data_type?: string;
  options?: Array<Record<string, unknown>>;
}

export interface ProductSeedProjectSummaryResponse {
  github_project_node_id: string;
  number: number;
  title: string;
  status_field_name: string;
  status_options: string[];
  fields: ProductSeedProjectFieldResponse[];
  views: string[];
  templates: string[];
  raw_payload: Record<string, unknown>;
}

export interface ProductSeedProgressEntryResponse {
  step: string;
  status: string;
  message: string;
  recorded_at: string;
}

export interface ProductSeedAuditEntryResponse {
  step: string;
  status: string;
  message: string;
  details: Record<string, unknown>;
  recorded_at: string;
}

export interface ProductSeedErrorEntryResponse {
  code: string;
  message: string;
  recorded_at: string;
}

export interface ProductSeedJobSummaryResponse {
  seed_job_id: string;
  product_id?: string | null;
  requested_by?: string | null;
  status: string;
  dry_run: boolean;
  setup_state?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductSeedJobResponse {
  seed_job_id: string;
  org_id: string;
  product_id?: string | null;
  requested_by?: string | null;
  status: string;
  dry_run: boolean;
  request_payload: ProductSeedRequestPayload;
  progress_payload: ProductSeedProgressEntryResponse[];
  error_payload: ProductSeedErrorEntryResponse[];
  audit_payload: ProductSeedAuditEntryResponse[];
  rendered_file_paths: string[];
  repo_summary: ProductSeedRepositorySummaryResponse;
  project_summary: ProductSeedProjectSummaryResponse;
  setup_state?: string | null;
  setup_diagnostics: ProductSetupDiagnosticResponse[];
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
  product?: ProductSummaryResponse | null;
}

export type ProductAdoptionPermissionLevel = "none" | "read" | "write" | "maintain" | "admin";

export interface ProductAdoptionBranchProtectionPayload {
  enabled: boolean;
  requires_pull_request: boolean;
  required_approving_review_count: number;
  allows_force_pushes: boolean;
  allows_deletions: boolean;
}

export interface ProductAdoptionRepositoryPermissionsPayload {
  contents: ProductAdoptionPermissionLevel;
  pull_requests: ProductAdoptionPermissionLevel;
  issues: ProductAdoptionPermissionLevel;
  projects: ProductAdoptionPermissionLevel;
}

export interface ProductAdoptionRepositoryPayload {
  github_repository_node_id?: string | null;
  owner: string;
  name: string;
  default_branch: string;
  visibility: "private" | "internal" | "public";
  description?: string | null;
  is_archived: boolean;
  branch_protection: ProductAdoptionBranchProtectionPayload;
  permissions: ProductAdoptionRepositoryPermissionsPayload;
}

export interface ProductAdoptionProjectPayload {
  github_project_node_id?: string | null;
  number: number;
  title: string;
  status_field_name: string;
  status_options: string[];
}

export interface ProductAdoptionRequestPayload {
  org_id: string;
  key: string;
  name: string;
  description?: string | null;
  repo_root: string;
  baseline_channel: string;
  agent_core_version: string;
  execution_profile: string;
  repository: ProductAdoptionRepositoryPayload;
  project: ProductAdoptionProjectPayload;
  operator_overrides: Record<string, unknown>;
}

export interface ProductAdoptionResponse {
  dry_run: boolean;
  product: ProductSummaryResponse;
}

export interface ProductReferenceResponse {
  product_id: string;
  key: string;
  name: string;
  status: string;
}

export interface LaneWorkItemSummaryResponse {
  work_item_id: string;
  issue_number: number;
  title: string;
  status: string;
  dependency_state: string;
  handoff_status: string;
  linked_prs: string[];
  updated_at: string;
}

export interface ExecutionEnvironmentSummaryResponse {
  execution_environment_id: string;
  status: string;
  runtime_provider: string;
  container_image?: string | null;
  container_handle?: string | null;
  workspace_uri?: string | null;
  artifact_uri?: string | null;
  log_uri?: string | null;
  cache_uri?: string | null;
  heartbeat_at?: string | null;
  terminated_at?: string | null;
  quarantine_reason?: string | null;
}

export interface LaneAgentSessionSummaryResponse {
  agent_session_id: string;
  thread_id?: string | null;
  turn_id?: string | null;
  runner_session_id?: string | null;
  runner_version?: string | null;
  status: string;
  capabilities: string[];
  environment_identity?: string | null;
  last_event?: string | null;
  last_event_at?: string | null;
  heartbeat_at?: string | null;
  wait_reason?: string | null;
  continuation_summary: Record<string, unknown>;
  last_error_category?: string | null;
  turn_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  tool_call_count: number;
  requires_human_input: boolean;
  created_at: string;
  updated_at: string;
}

export interface LaneResponse {
  lane_id: string;
  product_id: string;
  repo_id: string;
  work_item_id: string;
  attempt: number;
  state: string;
  claimed_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  branch_name?: string | null;
  retry_due_at?: string | null;
  handoff_reason?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
  product: ProductReferenceResponse;
  repository: RepositoryBindingSummaryResponse;
  work_item: LaneWorkItemSummaryResponse;
  execution_environment?: ExecutionEnvironmentSummaryResponse | null;
  agent_session?: LaneAgentSessionSummaryResponse | null;
}

export interface ObservabilityCorrelationResponse {
  org_id?: string | null;
  product_id?: string | null;
  repo_id?: string | null;
  work_item_id?: string | null;
  lane_id?: string | null;
  agent_session_id?: string | null;
  delivery_id?: string | null;
  github_delivery_guid?: string | null;
  installation_id?: string | null;
}

export interface ObservabilityNotificationResponse {
  notification_type: string;
  severity: string;
  title: string;
  summary: string;
  observed_at?: string | null;
  target_kind: string;
  target_id: string;
  source_kind: string;
  correlation: ObservabilityCorrelationResponse;
}

export interface LaneStatusSummaryResponse {
  lane_id: string;
  product_id: string;
  work_item_id: string;
  issue_number: number;
  title: string;
  state: string;
  attempt: number;
  retry_due_at?: string | null;
  heartbeat_status: string;
  summary: string;
  updated_at?: string | null;
}

export interface LaneActivityResponse {
  kind: "session_event" | "signal";
  event_type: string;
  summary?: string | null;
  severity?: string | null;
  observed_at?: string | null;
  source_kind: string;
  correlation: ObservabilityCorrelationResponse;
  payload: unknown;
}

export interface ObservabilityArtifactReferencesResponse {
  workspace_uri?: string | null;
  artifact_uri?: string | null;
  log_uri?: string | null;
  cache_uri?: string | null;
}

export interface FleetObservabilityResponse {
  generated_at: string;
  queue_depth: number;
  active_lane_count: number;
  retry_backlog_count: number;
  dead_letter_backlog_count: number;
  mirror_lag_seconds?: number | null;
  stale_heartbeat_count: number;
  lane_state_counts: Record<string, number>;
  notification_count: number;
  notifications: ObservabilityNotificationResponse[];
  lanes: LaneStatusSummaryResponse[];
}

export interface LaneObservabilityResponse {
  lane: LaneResponse;
  correlation: ObservabilityCorrelationResponse;
  heartbeat_status: string;
  summary: string;
  last_activity_at?: string | null;
  recent_activity: LaneActivityResponse[];
  notifications: ObservabilityNotificationResponse[];
  artifact_references: ObservabilityArtifactReferencesResponse;
}

export interface BaselineUpgradeRunSummaryResponse {
  standards_upgrade_run_id: string;
  outcome_kind: string;
  outcome_status?: string | null;
  generated_pr_number?: number | null;
  created_at: string;
  updated_at: string;
}

export interface BaselineResponse {
  product_id: string;
  org_id: string;
  product_key: string;
  product_name: string;
  product_status: string;
  baseline_channel?: string | null;
  standards_pack_key?: string | null;
  standards_pack_version?: string | null;
  agent_core_version?: string | null;
  setup_state: string;
  setup_diagnostics: ProductSetupDiagnosticResponse[];
  drift_status: string;
  managed_asset_counts: Record<string, number>;
  managed_assets: ManagedAssetResponse[];
  latest_run?: BaselineUpgradeRunSummaryResponse | null;
  last_config_refresh_at?: string | null;
  last_accepted_config_at?: string | null;
}

export interface StandardsEvaluationRequestPayload {
  repo_root: string;
  pack_key: string;
  channel: string;
  version: string;
  generated_pr_number?: number | null;
}

export interface StandardsUpgradeOutcomeRequestPayload {
  outcome_status: "accepted" | "rejected" | "deferred";
  generated_pr_number?: number | null;
}

export interface StandardsUpgradeAssetResponse {
  standards_upgrade_asset_id: string;
  standards_upgrade_run_id: string;
  path: string;
  management_mode: string;
  action: string;
  drift_status: string;
  patch_text?: string | null;
  detail?: string | null;
  metadata_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface StandardsFollowUpItemResponse {
  standards_follow_up_item_id: string;
  standards_upgrade_run_id: string;
  product_id: string;
  repo_id?: string | null;
  path: string;
  title: string;
  detail: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface StandardsUpgradeRunResponse {
  standards_upgrade_run_id: string;
  product_id: string;
  repo_id?: string | null;
  standards_pack_id: string;
  source_bundle: string;
  source_version: string;
  outcome_kind: string;
  outcome_status: string;
  generated_pr_number?: number | null;
  pr_title?: string | null;
  pr_body?: string | null;
  summary_payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  assets: StandardsUpgradeAssetResponse[];
  follow_up_items: StandardsFollowUpItemResponse[];
}

export interface GraphFreshnessResponse {
  observed_at?: string | null;
  status: string;
  stale_after_seconds: number;
}

export interface GraphSignalResponse {
  signal_id: string;
  signal_type: string;
  severity?: string | null;
  value: unknown;
  observed_at?: string | null;
  source_kind: string;
}

export interface GraphWorkItemSummaryResponse {
  work_item_id: string;
  issue_number: number;
  title: string;
  status: string;
  dependency_state: string;
  updated_at?: string | null;
}

export interface GraphPullRequestSummaryResponse {
  pull_request_id: string;
  number: number;
  title: string;
  state: string;
  review_state?: string | null;
  updated_at?: string | null;
}

export interface GraphLaneSummaryResponse {
  lane_id: string;
  work_item_id: string;
  state: string;
  attempt: number;
  updated_at?: string | null;
}

export interface GraphNodeOverlayResponse {
  active_work_items: GraphWorkItemSummaryResponse[];
  open_pull_requests: GraphPullRequestSummaryResponse[];
  active_lanes: GraphLaneSummaryResponse[];
  incidents: GraphSignalResponse[];
  signals: GraphSignalResponse[];
  hotspot_score: number;
  blocked_dependency_count: number;
}

export interface GraphNodeResponse {
  component_node_id: string;
  product_id: string;
  type: string;
  key: string;
  name: string;
  owner?: string | null;
  version?: string | null;
  status?: string | null;
  source_kind: string;
  source_ref?: string | null;
  distance: number;
  freshness: GraphFreshnessResponse;
  overlay: GraphNodeOverlayResponse;
}

export interface GraphEdgeResponse {
  component_edge_id: string;
  from_node_id: string;
  to_node_id: string;
  relationship_type: string;
  source_kind: string;
  confidence?: number | null;
  last_verified_at?: string | null;
  freshness: GraphFreshnessResponse;
  blocked: boolean;
}

export interface GraphBlockedDependencyResponse {
  component_edge_id: string;
  from_node_id: string;
  from_key: string;
  to_node_id: string;
  to_key: string;
  relationship_type: string;
  reason: string;
  cross_product: boolean;
  observed_at?: string | null;
}

export interface GraphHotspotResponse {
  component_node_id: string;
  product_id: string;
  key: string;
  name: string;
  type: string;
  hotspot_score: number;
  active_lane_count: number;
  active_work_item_count: number;
  observed_at?: string | null;
}

export interface GraphSliceResponse {
  scope: string;
  product_id: string;
  lane_id?: string | null;
  generated_at: string;
  freshness: GraphFreshnessResponse;
  anchor_node_ids: string[];
  depth: number;
  nodes: GraphNodeResponse[];
  edges: GraphEdgeResponse[];
  blocked_dependencies: GraphBlockedDependencyResponse[];
  hotspots: GraphHotspotResponse[];
}

export interface OperatorActionRequest {
  actor_id: string;
  reason: string;
}

export interface ProductRefreshRequest extends OperatorActionRequest {
  repo_root?: string;
  operator_overrides: Record<string, unknown>;
}

export interface ProductMirrorRefreshRequest extends OperatorActionRequest {}

export interface LaneCancelRequest extends OperatorActionRequest {
  disposition: "terminate" | "quarantine";
}

export interface LaneApproveRequest extends OperatorActionRequest {
  approval_payload: Record<string, unknown>;
}

export interface LaneHumanInputRequest extends OperatorActionRequest {
  input_payload: Record<string, unknown>;
}
