export interface Organization {
  org_id: string;
  name: string;
  slug: string;
  documentation_visibility: "shared" | "isolated";
  created_at: string;
  updated_at: string;
}

export interface CreateOrganizationRequest {
  name: string;
  slug: string;
  documentation_visibility: "shared" | "isolated";
}

export interface UpdateOrganizationRequest {
  name?: string;
  slug?: string;
  documentation_visibility?: "shared" | "isolated";
}

export interface OrgMember {
  org_id: string;
  user_id: string;
  email?: string | null;
  display_name?: string | null;
  is_active: boolean;
  is_default: boolean;
  archived_at?: string | null;
  created_at: string;
}

export interface OrgMemberCreateRequest {
  user_id: string;
  email?: string | null;
  display_name?: string | null;
}

export type CreateOrgMemberRequest = OrgMemberCreateRequest;

export interface UserResponse {
  user_id: string;
  username?: string | null;
  email?: string | null;
  display_name?: string | null;
  status?: string | null;
}

export interface UserSearchResponse {
  users: UserResponse[];
  next_token?: string | null;
}

export interface Permission {
  permission_id: string;
  key: string;
  description: string;
  category?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeatureFlag {
  feature_flag_id: string;
  key: string;
  description: string;
  category?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface Role {
  role_id: string;
  slug: string;
  name: string;
  description?: string | null;
  is_system: boolean;
  permissions: Permission[];
  feature_flags: FeatureFlag[];
  created_at: string;
  updated_at: string;
}

export interface RolePermissionsUpdateRequest {
  permission_keys: string[];
}

export interface RoleFeatureFlagsUpdateRequest {
  feature_flag_keys: string[];
}

export interface AIAgent {
  agent_id: string;
  key: string;
  name: string;
  description?: string | null;
  system_prompt: string;
  tool_policy: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  default_model_id?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateAIAgentRequest {
  key: string;
  name: string;
  description?: string | null;
  system_prompt: string;
  tool_policy?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  default_model_id?: string | null;
  is_active?: boolean;
}

export interface UpdateAIAgentRequest {
  key?: string;
  name?: string;
  description?: string | null;
  system_prompt?: string;
  tool_policy?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  default_model_id?: string | null;
  is_active?: boolean;
}

export interface AIProvider {
  provider_id: string;
  key: string;
  type: string;
  name: string;
  is_active: boolean;
  config: Record<string, unknown>;
  compliance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateAIProviderRequest {
  key: string;
  type: string;
  name: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
}

export interface UpdateAIProviderRequest {
  key?: string;
  type?: string;
  name?: string;
  is_active?: boolean;
  config?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
}

export interface AIModel {
  model_id: string;
  provider_id: string;
  key: string;
  name: string;
  provider_model_id?: string | null;
  can_embed: boolean;
  can_rerank: boolean;
  can_chat: boolean;
  can_vision: boolean;
  can_audio: boolean;
  default_workload?: string | null;
  is_default: boolean;
  restricted_content_only: boolean;
  is_active: boolean;
  context_window_tokens?: number | null;
  max_output_tokens?: number | null;
  cost: Record<string, unknown>;
  default_params: Record<string, unknown>;
  compliance: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CreateAIModelRequest {
  key: string;
  name: string;
  provider_model_id?: string | null;
  can_embed?: boolean;
  can_rerank?: boolean;
  can_chat?: boolean;
  can_vision?: boolean;
  can_audio?: boolean;
  default_workload?: string | null;
  is_default?: boolean;
  restricted_content_only?: boolean;
  is_active?: boolean;
  context_window_tokens?: number | null;
  max_output_tokens?: number | null;
  cost?: Record<string, unknown>;
  default_params?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
}

export interface UpdateAIModelRequest {
  key?: string;
  name?: string;
  provider_model_id?: string | null;
  can_embed?: boolean;
  can_rerank?: boolean;
  can_chat?: boolean;
  can_vision?: boolean;
  can_audio?: boolean;
  default_workload?: string | null;
  is_default?: boolean;
  restricted_content_only?: boolean;
  is_active?: boolean;
  context_window_tokens?: number | null;
  max_output_tokens?: number | null;
  cost?: Record<string, unknown>;
  default_params?: Record<string, unknown>;
  compliance?: Record<string, unknown>;
}

export interface AIModelTestResponse {
  ok: boolean;
  message: string;
  provider_type?: string | null;
  provider_model_id?: string | null;
}

export interface Secret {
  secret_id: string;
  key: string;
  name: string;
  kind:
    | "api_token"
    | "client_secret"
    | "shared_secret"
    | "signing_key"
    | "ai_api_key"
    | "git_personal_access_token"
    | "databricks_access_token"
    | "gcp_service_account_key"
    | "github_webhook_secret";
  description?: string | null;
  has_value: boolean;
  created_at: string;
  updated_at: string;
  last_rotated_at?: string | null;
}

export interface CreateSecretRequest {
  key: string;
  name: string;
  kind: Secret["kind"];
  value: string;
  description?: string | null;
}

export interface UpdateSecretRequest {
  key?: string;
  name?: string;
  kind?: Secret["kind"];
  value?: string;
  description?: string | null;
}

export interface Setting {
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

export interface PlatformSummary {
  organization_count: number;
  provider_count: number;
  model_count: number;
  agent_count: number;
  product_count: number;
  repository_binding_count: number;
  lane_count: number;
  component_node_count: number;
  webhook_delivery_count: number;
  membership_count: number;
  role_count: number;
  permission_count: number;
  feature_flag_count: number;
  secret_count: number;
  setting_count: number;
}
