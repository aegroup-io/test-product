import { acquireToken } from "./auth";
import type {
  AIAgent,
  AIModel,
  AIModelTestResponse,
  AIProvider,
  CreateAIAgentRequest,
  CreateAIModelRequest,
  CreateAIProviderRequest,
  CreateOrganizationRequest,
  CreateSecretRequest,
  FeatureFlag,
  OrgMember,
  OrgMemberCreateRequest,
  Organization,
  Permission,
  PlatformSummary,
  RoleFeatureFlagsUpdateRequest,
  RolePermissionsUpdateRequest,
  Role,
  Secret,
  Setting,
  UpdateAIAgentRequest,
  UpdateAIModelRequest,
  UpdateAIProviderRequest,
  UpdateOrganizationRequest,
  UpdateSecretRequest,
  UserSearchResponse,
  UserInfo,
} from "../api/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_STORAGE_KEY = "agentCoreToken";

function getAuthHeader(): HeadersInit {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  retryOn401 = true,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...getAuthHeader(),
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 401 && retryOn401) {
    try {
      const token = await acquireToken();
      if (token) {
        window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
        return apiFetch<T>(path, init, false);
      }
    } catch {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.dispatchEvent(new CustomEvent("agentCoreAuthFailed"));
    }
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  getMe: () => apiFetch<UserInfo>("/me"),
  listOrgs: () => apiFetch<Organization[]>("/orgs"),
  createOrg: (payload: CreateOrganizationRequest) =>
    apiFetch<Organization>("/orgs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateOrg: (orgId: string, payload: UpdateOrganizationRequest) =>
    apiFetch<Organization>(`/orgs/${orgId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  listOrgMembers: (orgId: string, includeInactive = false) =>
    apiFetch<OrgMember[]>(
      `/orgs/${encodeURIComponent(orgId)}/members?include_inactive=${encodeURIComponent(String(includeInactive))}`,
    ),
  addOrgMember: (orgId: string, payload: OrgMemberCreateRequest) =>
    apiFetch<OrgMember>(`/orgs/${encodeURIComponent(orgId)}/members`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  removeOrgMember: (orgId: string, userId: string) =>
    apiFetch<void>(`/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    }),
  setOrgMemberDefault: (orgId: string, userId: string) =>
    apiFetch<OrgMember>(`/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}/default`, {
      method: "POST",
    }),
  setDefaultOrgMember: (orgId: string, userId: string) =>
    api.setOrgMemberDefault(orgId, userId),
  searchUsers: (query: string, limit = 25, nextToken?: string | null) =>
    apiFetch<UserSearchResponse>(
      `/users?query=${encodeURIComponent(query)}&limit=${encodeURIComponent(String(limit))}${
        nextToken ? `&next_token=${encodeURIComponent(nextToken)}` : ""
      }`,
    ),
  getPlatformSummary: () => apiFetch<PlatformSummary>("/platform/summary"),
  listRoles: () => apiFetch<Role[]>("/rbac/roles"),
  listPermissions: () => apiFetch<Permission[]>("/rbac/permissions"),
  listFeatureFlags: () => apiFetch<FeatureFlag[]>("/rbac/feature-flags"),
  updateRolePermissions: (roleId: string, payload: RolePermissionsUpdateRequest) =>
    apiFetch<Role>(`/rbac/roles/${encodeURIComponent(roleId)}/permissions`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  updateRoleFeatureFlags: (roleId: string, payload: RoleFeatureFlagsUpdateRequest) =>
    apiFetch<Role>(`/rbac/roles/${encodeURIComponent(roleId)}/feature-flags`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  listProviders: () => apiFetch<AIProvider[]>("/ai/providers"),
  createProvider: (payload: CreateAIProviderRequest) =>
    apiFetch<AIProvider>("/ai/providers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateProvider: (providerId: string, payload: UpdateAIProviderRequest) =>
    apiFetch<AIProvider>(`/ai/providers/${encodeURIComponent(providerId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  listModels: (providerId?: string) =>
    apiFetch<AIModel[]>(
      providerId
        ? `/ai/models?provider_id=${encodeURIComponent(providerId)}`
        : "/ai/models",
    ),
  createModel: (providerId: string, payload: CreateAIModelRequest) =>
    apiFetch<AIModel>(`/ai/providers/${encodeURIComponent(providerId)}/models`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateModel: (modelId: string, payload: UpdateAIModelRequest) =>
    apiFetch<AIModel>(`/ai/models/${encodeURIComponent(modelId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  testModel: (modelId: string) =>
    apiFetch<AIModelTestResponse>(`/ai/models/${encodeURIComponent(modelId)}/test`, {
      method: "POST",
    }),
  listAgents: () => apiFetch<AIAgent[]>("/ai/agents"),
  createAgent: (payload: CreateAIAgentRequest) =>
    apiFetch<AIAgent>("/ai/agents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAgent: (agentId: string, payload: UpdateAIAgentRequest) =>
    apiFetch<AIAgent>(`/ai/agents/${encodeURIComponent(agentId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  listSecrets: () => apiFetch<Secret[]>("/secrets"),
  createSecret: (payload: CreateSecretRequest) =>
    apiFetch<Secret>("/secrets", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSecret: (secretId: string, payload: UpdateSecretRequest) =>
    apiFetch<Secret>(`/secrets/${encodeURIComponent(secretId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteSecret: (secretId: string) =>
    apiFetch<void>(`/secrets/${encodeURIComponent(secretId)}`, {
      method: "DELETE",
    }),
  listSettings: (scopeType: "platform" | "org" | "user", scopeId: string) =>
    apiFetch<Setting[]>(
      `/settings?scope_type=${encodeURIComponent(scopeType)}&scope_id=${encodeURIComponent(scopeId)}`,
    ),
  upsertSetting: (
    scopeType: "platform" | "org" | "user",
    scopeId: string,
    key: string,
    value: unknown,
  ) =>
    apiFetch<Setting>(`/settings/${scopeType}/${encodeURIComponent(scopeId)}/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    }),
};
