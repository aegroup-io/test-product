import { acquireToken } from "./auth";
import type {
  BaselineResponse,
  FleetObservabilityResponse,
  GitRepoBranchResponse,
  GitRepoBranchesRequestPayload,
  GitRepoCreateRequestPayload,
  GitRepoLookupRequestPayload,
  GitRepoLookupResultResponse,
  GitRepoResponse,
  GitRepoUpdateRequestPayload,
  LaneObservabilityResponse,
  LaneApproveRequest,
  LaneCancelRequest,
  LaneHumanInputRequest,
  LaneResponse,
  OrganizationResponse,
  OperatorActionRequest,
  ProductAdoptionRequestPayload,
  ProductAdoptionResponse,
  ProductMirrorRefreshRequest,
  ProductRefreshRequest,
  ProductSeedJobResponse,
  ProductSeedRequestPayload,
  ProductSummaryResponse,
  SecretCreateRequestPayload,
  SecretResponse,
  SettingResponse,
  StandardsEvaluationRequestPayload,
  StandardsUpgradeOutcomeRequestPayload,
  StandardsUpgradeRunResponse,
  UserInfo,
  GraphSliceResponse,
} from "./operator-types";

function deriveLocalApiBase() {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:7100";
  }
  const current = new URL(window.location.origin);
  const currentPort = Number(current.port || (current.protocol === "https:" ? "443" : "80"));
  if (Number.isNaN(currentPort)) {
    return "http://127.0.0.1:7100";
  }
  if (currentPort >= 5100 && currentPort < 6100) {
    current.port = String(currentPort + 2000);
    return current.origin;
  }
  return "http://127.0.0.1:7100";
}

export const operatorApiBase = import.meta.env.VITE_API_BASE_URL ?? deriveLocalApiBase();
const TOKEN_STORAGE_KEY = "agentCoreToken";

export class OperatorApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "OperatorApiError";
    this.status = status;
  }
}

function getAuthHeader(): HeadersInit {
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

async function operatorFetch<T>(
  path: string,
  init: RequestInit = {},
  retryOn401 = true,
): Promise<T> {
  const response = await fetch(`${operatorApiBase}${path}`, {
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
        return operatorFetch<T>(path, init, false);
      }
    } catch {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.dispatchEvent(new CustomEvent("agentCoreAuthFailed"));
    }
  }

  if (!response.ok) {
    const text = await response.text();
    throw new OperatorApiError(text || `Operator API request failed: ${response.status}`, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const operatorApi = {
  getMe: () => operatorFetch<UserInfo>("/me"),
  listOrganizations: () => operatorFetch<OrganizationResponse[]>("/orgs"),
  listSecrets: () => operatorFetch<SecretResponse[]>("/secrets"),
  createSecret: (payload: SecretCreateRequestPayload) =>
    operatorFetch<SecretResponse>("/secrets", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listSettings: (scopeType: "platform" | "org" | "user", scopeId: string) =>
    operatorFetch<SettingResponse[]>(
      `/settings?scope_type=${encodeURIComponent(scopeType)}&scope_id=${encodeURIComponent(scopeId)}`,
    ),
  upsertSetting: (
    scopeType: "platform" | "org" | "user",
    scopeId: string,
    key: string,
    value: unknown,
  ) =>
    operatorFetch<SettingResponse>(
      `/settings/${scopeType}/${encodeURIComponent(scopeId)}/${encodeURIComponent(key)}`,
      {
        method: "PUT",
        body: JSON.stringify({ value }),
      },
    ),
  listOrgRepos: (orgId: string, q?: string) =>
    operatorFetch<GitRepoResponse[]>(
      `/orgs/${encodeURIComponent(orgId)}/repos${q?.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
    ),
  createRepo: (orgId: string, payload: GitRepoCreateRequestPayload) =>
    operatorFetch<GitRepoResponse>(`/orgs/${encodeURIComponent(orgId)}/repos`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateRepo: (repoId: string, payload: GitRepoUpdateRequestPayload) =>
    operatorFetch<GitRepoResponse>(`/repos/${encodeURIComponent(repoId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteRepo: (repoId: string) =>
    operatorFetch<void>(`/repos/${encodeURIComponent(repoId)}`, {
      method: "DELETE",
    }),
  lookupGithubRepos: (orgId: string, payload: GitRepoLookupRequestPayload) =>
    operatorFetch<GitRepoLookupResultResponse[]>(
      `/orgs/${encodeURIComponent(orgId)}/github/repos/lookup`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  listGithubRepoBranches: (orgId: string, payload: GitRepoBranchesRequestPayload) =>
    operatorFetch<GitRepoBranchResponse[]>(
      `/orgs/${encodeURIComponent(orgId)}/github/repos/branches`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  listProducts: () => operatorFetch<ProductSummaryResponse[]>("/v1/products"),
  dryRunProductAdoption: (payload: ProductAdoptionRequestPayload) =>
    operatorFetch<ProductAdoptionResponse>("/products/adoptions/dry-run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  adoptProduct: (payload: ProductAdoptionRequestPayload) =>
    operatorFetch<ProductAdoptionResponse>("/products/adoptions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  seedProduct: (payload: ProductSeedRequestPayload) =>
    operatorFetch<ProductSeedJobResponse>("/products/seed", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getProductSeedJob: (seedJobId: string) =>
    operatorFetch<ProductSeedJobResponse>(`/products/seed-jobs/${encodeURIComponent(seedJobId)}`),
  pauseProduct: (productId: string, payload: OperatorActionRequest) =>
    operatorFetch<ProductSummaryResponse>(`/v1/products/${encodeURIComponent(productId)}/pause`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resumeProduct: (productId: string, payload: OperatorActionRequest) =>
    operatorFetch<ProductSummaryResponse>(`/v1/products/${encodeURIComponent(productId)}/resume`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  refreshProduct: (productId: string, payload: ProductRefreshRequest) =>
    operatorFetch<ProductSummaryResponse>(`/v1/products/${encodeURIComponent(productId)}/refresh`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  refreshProductMirror: (productId: string, payload: ProductMirrorRefreshRequest) =>
    operatorFetch<ProductSummaryResponse>(`/v1/products/${encodeURIComponent(productId)}/refresh-mirror`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getFleetObservabilitySummary: () =>
    operatorFetch<FleetObservabilityResponse>("/v1/observability/summary"),
  listLanes: () => operatorFetch<LaneResponse[]>("/v1/lanes"),
  getLaneObservability: (laneId: string) =>
    operatorFetch<LaneObservabilityResponse>(`/v1/observability/lanes/${encodeURIComponent(laneId)}`),
  retryLane: (laneId: string, payload: OperatorActionRequest) =>
    operatorFetch<LaneResponse>(`/v1/lanes/${encodeURIComponent(laneId)}/retry`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelLane: (laneId: string, payload: LaneCancelRequest) =>
    operatorFetch<LaneResponse>(`/v1/lanes/${encodeURIComponent(laneId)}/cancel`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  approveLane: (laneId: string, payload: LaneApproveRequest) =>
    operatorFetch<LaneResponse>(`/v1/lanes/${encodeURIComponent(laneId)}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitHumanInput: (laneId: string, payload: LaneHumanInputRequest) =>
    operatorFetch<LaneResponse>(`/v1/lanes/${encodeURIComponent(laneId)}/human-input`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listBaselines: () => operatorFetch<BaselineResponse[]>("/v1/baselines"),
  evaluateProductStandards: (productId: string, payload: StandardsEvaluationRequestPayload) =>
    operatorFetch<StandardsUpgradeRunResponse>(
      `/products/${encodeURIComponent(productId)}/standards/evaluations`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  listProductStandardsRuns: (productId: string) =>
    operatorFetch<StandardsUpgradeRunResponse[]>(
      `/products/${encodeURIComponent(productId)}/standards/runs`,
    ),
  recordStandardsRunOutcome: (
    standardsUpgradeRunId: string,
    payload: StandardsUpgradeOutcomeRequestPayload,
  ) =>
    operatorFetch<StandardsUpgradeRunResponse>(
      `/standards/runs/${encodeURIComponent(standardsUpgradeRunId)}/outcome`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  getGraph: (productId: string) =>
    operatorFetch<GraphSliceResponse>(`/v1/graph/products/${encodeURIComponent(productId)}`),
};
