import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  ExternalLink,
  GitBranch,
  Grid2x2,
  Loader2,
  Monitor,
  Moon,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Shield,
  ShieldAlert,
  Sparkles,
  Sun,
  TriangleAlert,
  Waypoints,
  Workflow,
  Wrench,
} from "lucide-react";
import {
  type ButtonHTMLAttributes,
  Fragment,
  type ReactNode,
  forwardRef,
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useState,
} from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";

import {
  AgentCoreShellApp,
  type ShellSettingsExtension,
  type ThemePreference,
  useTheme,
} from "@aegroup/agent-core-web-shell";

import { productBranding } from "./product-branding";
import { operatorApi } from "./operator-api";
import { acquireToken, getAccountLabel, initAuth, isAuthConfigured, login, logout } from "./auth";
import {
  PRODUCT_DEFAULTS_SETTING_KEY,
  SELECTED_ORG_STORAGE_KEY,
  buildProductOnboardingDefaultsRecord,
  buildProductOnboardingDefaultsValue,
  createErroredProductOnboardingDefaultsRecord,
  createUnloadedProductOnboardingDefaultsRecord,
  normalizeOnboardingSecretKeys,
  type ProductOnboardingDefaults,
  type ProductOnboardingDefaultsRecord,
} from "./onboarding-defaults";
import type {
  BaselineResponse,
  FleetObservabilityResponse,
  GitRepoResponse,
  GraphSliceResponse,
  LaneObservabilityResponse,
  LaneResponse,
  LaneStatusSummaryResponse,
  ObservabilityNotificationResponse,
  ProductAdoptionPermissionLevel,
  ProductAdoptionRequestPayload,
  ProductAdoptionResponse,
  OrganizationResponse,
  ProductSeedJobResponse,
  ProductSeedRequestPayload,
  ProductSummaryResponse,
  SecretResponse,
  StandardsUpgradeRunResponse,
  UserInfo,
} from "./operator-types";
import WorkspaceOnboardingDefaultsPage from "./settings/WorkspaceOnboardingDefaultsPage";
import GitRepositoriesPage from "./settings/GitRepositoriesPage";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  CardContent,
  CardDescription,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
  FormField,
  Input,
  LoginPrompt,
  Select,
  Textarea,
  UserMenu,
} from "./ui";

const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === "1";
const REFRESH_REPO_ROOT_HINT = import.meta.env.VITE_OPERATOR_REPO_ROOT_HINT ?? "";
const AUTH_TOKEN_STORAGE_KEY = "agentCoreToken";
const COMPACT_ACTION_BUTTON_CLASS = "w-full max-w-[200px] justify-start";
const PAUSE_BUTTON_CLASS =
  "border border-amber-500/60 bg-amber-300 text-zinc-950 hover:bg-amber-200 disabled:!opacity-100 disabled:!bg-amber-300 disabled:!text-zinc-950";
const RESUME_BUTTON_CLASS =
  "border border-emerald-600/40 bg-emerald-600 text-white hover:bg-emerald-500 disabled:!opacity-100 disabled:!bg-emerald-600 disabled:!text-white";

type DashboardState = {
  products: ProductSummaryResponse[];
  lanes: LaneResponse[];
  baselines: BaselineResponse[];
  observability: FleetObservabilityResponse | null;
};

type BreadcrumbItem = {
  label: string;
  to?: string;
};

type OnboardingDefaultsByOrg = Record<string, ProductOnboardingDefaultsRecord>;

type ProductAction =
  | { kind: "pause"; productId: string; reason: string; actorId: string }
  | { kind: "resume"; productId: string; reason: string; actorId: string }
  | { kind: "refresh"; productId: string; reason: string; actorId: string; repoRoot?: string }
  | { kind: "refresh-mirror"; productId: string; reason: string; actorId: string };

type LaneAction =
  | { kind: "approve"; laneId: string; reason: string; actorId: string; note: string }
  | { kind: "human-input"; laneId: string; reason: string; actorId: string; note: string }
  | { kind: "cancel"; laneId: string; reason: string; actorId: string; disposition: "terminate" | "quarantine" }
  | { kind: "retry"; laneId: string; reason: string; actorId: string };

type ProductSeedProjectMode = "create" | "bind-existing";
type ProductSeedBaselineMode = "stable" | "candidate" | "custom";

type ProductSeedDraft = {
  orgId: string;
  productKey: string;
  productName: string;
  description: string;
  githubOwner: string;
  githubRepo: string;
  githubVisibility: "private" | "internal" | "public";
  githubDefaultBranch: string;
  projectMode: ProductSeedProjectMode;
  githubProjectNodeId: string;
  githubProjectNumber: string;
  githubProjectTitle: string;
  statusField: string;
  readyStatus: string;
  doneStatus: string;
  baselineMode: ProductSeedBaselineMode;
  customBaselineChannel: string;
  standardsPack: string;
  executionProfile: string;
  maxConcurrentLanes: string;
  requiredSecretKeys: string[];
};

type ProductSeedDraftState = {
  seedDraft?: ProductSeedDraft;
};

type ProductSeedFieldErrors = Partial<Record<
  | "orgId"
  | "productKey"
  | "productName"
  | "githubRepoProfile"
  | "githubOwner"
  | "githubRepo"
  | "githubDefaultBranch"
  | "githubProjectNodeId"
  | "githubProjectNumber"
  | "githubProjectTitle"
  | "statusField"
  | "readyStatus"
  | "doneStatus"
  | "baselineChannel"
  | "standardsPack"
  | "executionProfile"
  | "maxConcurrentLanes"
  | "requiredSecretKeys",
  string
>>;

type ProductSeedValidation = {
  previewErrors: string[];
  liveErrors: string[];
  previewFieldErrors: ProductSeedFieldErrors;
  liveFieldErrors: ProductSeedFieldErrors;
  missingSecretKeys: string[];
};

type ProductSeedJobRouteState = ProductSeedDraftState & {
  seedJob?: ProductSeedJobResponse;
};

type ProductAdoptionBaselineMode = "stable" | "candidate" | "custom";

type ProductAdoptionDraft = {
  orgId: string;
  key: string;
  name: string;
  description: string;
  repoRoot: string;
  baselineMode: ProductAdoptionBaselineMode;
  customBaselineChannel: string;
  agentCoreVersion: string;
  executionProfile: string;
  githubRepositoryNodeId: string;
  repositoryOwner: string;
  repositoryName: string;
  repositoryDefaultBranch: string;
  repositoryVisibility: "private" | "internal" | "public";
  repositoryDescription: string;
  repositoryArchived: boolean;
  branchProtectionEnabled: boolean;
  branchProtectionRequiresPullRequest: boolean;
  branchProtectionApprovals: string;
  branchProtectionAllowsForcePushes: boolean;
  branchProtectionAllowsDeletions: boolean;
  projectNodeId: string;
  projectNumber: string;
  projectTitle: string;
  statusFieldName: string;
  statusOptionsText: string;
  contentsPermission: ProductAdoptionPermissionLevel;
  pullRequestsPermission: ProductAdoptionPermissionLevel;
  issuesPermission: ProductAdoptionPermissionLevel;
  projectsPermission: ProductAdoptionPermissionLevel;
};

type ProductAdoptionDraftState = {
  adoptionDraft?: ProductAdoptionDraft;
};

type ProductAdoptionFieldErrors = Partial<Record<
  | "orgId"
  | "key"
  | "name"
  | "repoRoot"
  | "baselineChannel"
  | "agentCoreVersion"
  | "executionProfile"
  | "repositoryOwner"
  | "repositoryName"
  | "repositoryDefaultBranch"
  | "projectNumber"
  | "projectTitle"
  | "statusFieldName"
  | "statusOptions",
  string
>>;

type ProductAdoptionValidation = {
  previewErrors: string[];
  previewFieldErrors: ProductAdoptionFieldErrors;
};

type ProductAdoptionRouteState = ProductAdoptionDraftState & {
  adoptionResult?: ProductAdoptionResponse;
};

type ProductAdoptionPermissionField =
  | "contentsPermission"
  | "pullRequestsPermission"
  | "issuesPermission"
  | "projectsPermission";

type ProductAdoptionBranchProtectionSnapshot = {
  enabled?: boolean;
  requires_pull_request?: boolean;
  required_approving_review_count?: number;
  allows_force_pushes?: boolean;
  allows_deletions?: boolean;
};

type ProductAdoptionPermissionsSnapshot = {
  contents?: string;
  pull_requests?: string;
  issues?: string;
  projects?: string;
};

type ProductOnboardingActivity = {
  kind: "seed" | "adoption";
  productId: string;
  productName: string;
  title: string;
  description: string;
  target: string;
  actionLabel: string;
  status: string;
  updatedAt?: string | null;
};

type SetupDiagnostic = ProductSummaryResponse["setup_diagnostics"][number];
type ManagedAssetRecord = ProductSummaryResponse["managed_assets"][number];
type DeliveryCockpitRecord = NonNullable<ProductSummaryResponse["delivery_cockpit"]>;
type DeliveryWorkItemRecord = DeliveryCockpitRecord["work_items"][number];
type DeliveryPullRequestRecord = DeliveryWorkItemRecord["linked_pull_requests"][number];
type StandardsRunRecord = StandardsUpgradeRunResponse;
type StandardsOutcomeDecision = "accepted" | "rejected" | "deferred";
type FleetObservabilityRecord = FleetObservabilityResponse;
type LaneObservabilityRecord = LaneObservabilityResponse;
type LaneStatusSummaryRecord = LaneStatusSummaryResponse;
type ObservabilityNotificationRecord = ObservabilityNotificationResponse;

type GuidedRemediationAction = {
  key: string;
  label: string;
  description: string;
  to: string;
  variant?: "primary" | "outline";
};

type ProductDeliveryNextStep = {
  title: string;
  description: string;
  status: ActivationReadinessStatus;
  actionLabel: string;
  to?: string;
  href?: string | null;
};

type ActivationReadinessStatus = "ready" | "follow-up" | "blocking";

type ActivationReadinessItem = {
  key: string;
  label: string;
  description: string;
  status: ActivationReadinessStatus;
};

const ADOPTION_PERMISSION_LEVEL_OPTIONS: ProductAdoptionPermissionLevel[] = [
  "none",
  "read",
  "write",
  "maintain",
  "admin",
];

const ADOPTION_PERMISSION_FIELDS: Array<{
  label: string;
  field: ProductAdoptionPermissionField;
}> = [
  { label: "Contents", field: "contentsPermission" },
  { label: "Pull requests", field: "pullRequestsPermission" },
  { label: "Issues", field: "issuesPermission" },
  { label: "Projects", field: "projectsPermission" },
];

const STANDARDS_UPDATE_ACTIONS = new Set(["create-file", "update-file", "refresh-sections"]);
const STANDARDS_REVIEWABLE_STATUSES = new Set(["reviewable", "conflict"]);

function statusTone(status: string) {
  switch (status) {
    case "Active":
    case "Running":
    case "Succeeded":
    case "DryRun":
    case "completed":
    case "succeeded":
    case "current":
    case "ready":
    case "healthy":
      return "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
    case "Paused":
    case "AwaitingApproval":
    case "AwaitingGitHub":
    case "Queued":
    case "Claimed":
    case "Draft":
    case "Blocked":
    case "blocked":
    case "advisory":
    case "reviewable":
    case "advisory-drift":
    case "update-available":
    case "deferred":
    case "warning":
    case "waiting":
      return "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300";
    case "Cancelled":
    case "Failed":
    case "FailedTerminal":
    case "failed":
    case "drift":
    case "setup-needed":
    case "ambiguous":
    case "conflict":
    case "rejected":
    case "error":
    case "stale":
      return "border-rose-500/30 bg-rose-500/12 text-rose-700 dark:text-rose-300";
    case "accepted":
    case "advisory-reviewed":
    case "noop":
      return "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
    default:
      return "border-border bg-secondary text-secondary-foreground";
  }
}

function humanize(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }
  return value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return count === 1 ? singular : plural;
}

function displayOrgLabel(value: string | null | undefined) {
  if (!value) {
    return "Standard";
  }
  return humanize(value);
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatRelativeTime(value: string | null | undefined) {
  if (!value) {
    return "No signal yet";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units = [
    { unit: "day", seconds: 60 * 60 * 24 },
    { unit: "hour", seconds: 60 * 60 },
    { unit: "minute", seconds: 60 },
  ] as const;
  for (const item of units) {
    if (Math.abs(seconds) >= item.seconds || item.unit === "minute") {
      return formatter.format(Math.round(seconds / item.seconds), item.unit);
    }
  }
  return formatter.format(seconds, "second");
}

function formatDurationSeconds(value: number | null | undefined) {
  if (value == null) {
    return "Current";
  }
  if (value < 60) {
    return `${value}s`;
  }
  if (value < 60 * 60) {
    const minutes = Math.floor(value / 60);
    const seconds = value % 60;
    return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  const hours = Math.floor(value / (60 * 60));
  const minutes = Math.floor((value % (60 * 60)) / 60);
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function resolveRecentTimestamp(value: string | null | undefined) {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatStandardsOutcomeKind(value: string | null | undefined) {
  switch ((value ?? "").toLowerCase()) {
    case "upgrade-pr":
      return "Upgrade PR";
    case "no-op":
      return "No changes";
    default:
      return humanize(value);
  }
}

function describeStandardsRunStatus(
  run:
    | Pick<StandardsRunRecord, "outcome_kind" | "outcome_status" | "generated_pr_number">
    | Pick<NonNullable<BaselineResponse["latest_run"]>, "outcome_kind" | "outcome_status" | "generated_pr_number">
    | null
    | undefined,
) {
  if (!run) {
    return "No standards evaluation has been recorded yet.";
  }
  const kind = formatStandardsOutcomeKind(run.outcome_kind).toLowerCase();
  const prLabel = run.generated_pr_number ? ` on PR #${run.generated_pr_number}` : "";
  switch ((run.outcome_status ?? "").toLowerCase()) {
    case "current":
      return "Current after the latest standards evaluation.";
    case "reviewable":
      return `Reviewable ${kind}${prLabel} is ready for operator review.`;
    case "conflict":
      return `Conflicts blocked the latest ${kind}; operator follow-up is required.`;
    case "accepted":
      return `Operator accepted the latest ${kind}${prLabel}.`;
    case "rejected":
      return `Operator rejected the latest ${kind}${prLabel}.`;
    case "deferred":
      return `Operator deferred the latest ${kind}${prLabel}.`;
    default:
      return `${formatStandardsOutcomeKind(run.outcome_kind)} is ${humanize(run.outcome_status ?? "unknown").toLowerCase()}.`;
  }
}

function parseOptionalPositiveIntegerField(value: string, fieldLabel: string) {
  const normalized = value.trim();
  if (!normalized) {
    return { value: null, error: null };
  }
  const parsed = Number(normalized);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return { value: null, error: `${fieldLabel} must be a positive integer.` };
  }
  return { value: parsed, error: null };
}

function sortStandardsRuns(runs: StandardsRunRecord[]) {
  return [...runs].sort(
    (left, right) =>
      resolveRecentTimestamp(right.updated_at ?? right.created_at) -
      resolveRecentTimestamp(left.updated_at ?? left.created_at),
  );
}

function mergeStandardsRun(currentRuns: StandardsRunRecord[], nextRun: StandardsRunRecord) {
  return sortStandardsRuns([
    nextRun,
    ...currentRuns.filter((run) => run.standards_upgrade_run_id !== nextRun.standards_upgrade_run_id),
  ]);
}

function countStandardsRunUpdates(run: StandardsRunRecord) {
  return run.assets.filter((asset) => STANDARDS_UPDATE_ACTIONS.has(asset.action)).length;
}

function countStandardsRunAdvisories(run: StandardsRunRecord) {
  return run.assets.filter((asset) => asset.action === "advisory-drift" || asset.action === "deferred").length;
}

function countStandardsRunConflicts(run: StandardsRunRecord) {
  return run.assets.filter((asset) => asset.action === "conflict").length;
}

function canRecordStandardsOutcome(run: StandardsRunRecord) {
  return run.outcome_kind !== "no-op" && STANDARDS_REVIEWABLE_STATUSES.has((run.outcome_status ?? "").toLowerCase());
}

function resolveProductOnboardingActivity(product: ProductSummaryResponse): ProductOnboardingActivity | null {
  const latestSeedJob = product.latest_seed_job;
  if (latestSeedJob?.seed_job_id) {
    const setupState = latestSeedJob.setup_state ?? product.setup_state;
    const hasBlockers =
      setupState === "setup-needed" || latestSeedJob.status === "Blocked" || latestSeedJob.status === "Failed";
    return {
      kind: "seed",
      productId: product.product_id,
      productName: product.name,
      title: "Seed onboarding result",
      description: hasBlockers
        ? `${product.name} finished seeding with blockers or failures that still need review.`
        : `${product.name} has a durable seed result with progress, audit detail, and rendered files.`,
      target: `/products/seed/jobs/${latestSeedJob.seed_job_id}`,
      actionLabel: "Open onboarding result",
      status: latestSeedJob.status,
      updatedAt: latestSeedJob.finished_at ?? latestSeedJob.updated_at,
    };
  }

  const seedSource = product.primary_repo?.seed_source ?? "";
  const adoptionState = product.primary_repo?.adoption_state ?? "";
  const isAdoption =
    seedSource === "github-adoption" || ["adopting", "adopted", "setup-needed"].includes(adoptionState);
  if (!isAdoption) {
    return null;
  }

  const hasBlockers = product.setup_state === "setup-needed";
  return {
    kind: "adoption",
    productId: product.product_id,
    productName: product.name,
    title: "Adoption onboarding result",
    description: hasBlockers
      ? `${product.name} still has adoption blockers visible from onboarding.`
      : `${product.name} can be resumed from the persisted adoption result surface.`,
    target: `/products/adopt/review/${product.product_id}`,
    actionLabel: "Open adoption result",
    status: hasBlockers ? product.setup_state : product.status,
    updatedAt: product.last_config_refresh_at ?? product.updated_at,
  };
}

function collectOnboardingActivities(products: ProductSummaryResponse[]) {
  return products
    .map((product) => resolveProductOnboardingActivity(product))
    .filter((activity): activity is ProductOnboardingActivity => activity !== null)
    .sort((left, right) => resolveRecentTimestamp(right.updatedAt) - resolveRecentTimestamp(left.updatedAt));
}

function isTerminalLaneState(state: string) {
  return ["Cancelled", "FailedTerminal", "HandedOff"].includes(state);
}

function resolveLaneHeartbeatStatus(
  lane: LaneResponse,
  summary?: LaneStatusSummaryRecord | null,
) {
  if (summary?.heartbeat_status) {
    return summary.heartbeat_status;
  }
  if (lane.finished_at || isTerminalLaneState(lane.state)) {
    return "terminal";
  }
  if (lane.state === "AwaitingApproval" || lane.state === "AwaitingGitHub") {
    return "waiting";
  }
  if (lane.state === "Running") {
    if (lane.agent_session?.heartbeat_at || lane.agent_session?.last_event_at || lane.execution_environment?.heartbeat_at) {
      return "healthy";
    }
    return "unknown";
  }
  return "active";
}

function describeLaneRuntimeHealth(
  lane: LaneResponse,
  summary?: LaneStatusSummaryRecord | null,
) {
  const heartbeatStatus = resolveLaneHeartbeatStatus(lane, summary);
  const fragments = [`Heartbeat ${humanize(heartbeatStatus).toLowerCase()}`];
  fragments.push(
    lane.agent_session?.status
      ? `Session ${humanize(lane.agent_session.status).toLowerCase()}`
      : "No session attached",
  );
  fragments.push(
    lane.execution_environment?.status
      ? `Environment ${humanize(lane.execution_environment.status).toLowerCase()}`
      : "No environment attached",
  );
  return fragments.join(" • ");
}

function describeProductRuntimeSummary(
  activeLanes: LaneResponse[],
  laneSummariesById: Map<string, LaneStatusSummaryRecord>,
) {
  if (!activeLanes.length) {
    return "No active runtime lanes.";
  }
  const staleCount = activeLanes.filter(
    (lane) => resolveLaneHeartbeatStatus(lane, laneSummariesById.get(lane.lane_id)) === "stale",
  ).length;
  if (staleCount) {
    return `${staleCount} stale ${pluralize(staleCount, "runner heartbeat")}.`;
  }
  const waitingCount = activeLanes.filter(
    (lane) => lane.state === "AwaitingApproval" || lane.state === "AwaitingGitHub",
  ).length;
  if (waitingCount) {
    return `${waitingCount} ${pluralize(waitingCount, "lane")} waiting on operator input.`;
  }
  const healthyCount = activeLanes.filter(
    (lane) => resolveLaneHeartbeatStatus(lane, laneSummariesById.get(lane.lane_id)) === "healthy",
  ).length;
  if (healthyCount) {
    return `${healthyCount} ${pluralize(healthyCount, "lane")} currently report healthy runner signals.`;
  }
  return "Runtime health is attached to the active lane set.";
}

function describeLane(lane: LaneResponse) {
  if (lane.state === "AwaitingApproval") {
    return lane.agent_session?.wait_reason ?? "Waiting on operator approval.";
  }
  if (lane.state === "AwaitingGitHub") {
    return lane.agent_session?.wait_reason ?? "Waiting on human input.";
  }
  if (lane.state === "Running") {
    return lane.execution_environment?.workspace_uri
      ? "Runner is active with an attached workspace."
      : "Runner is active and streaming work.";
  }
  if (lane.state === "FailedTerminal") {
    return lane.last_error ?? "Execution failed and may need a retry decision.";
  }
  if (lane.state === "Cancelled") {
    return "Execution was cancelled by an operator or recovery policy.";
  }
  if (lane.state === "Claimed") {
    return "Lane is claimed and waiting for environment readiness.";
  }
  return `Lane is ${humanize(lane.state).toLowerCase()}.`;
}

function computeFleetStats(products: ProductSummaryResponse[], lanes: LaneResponse[], baselines: BaselineResponse[]) {
  return {
    products: products.length,
    activeProducts: products.filter((item) => item.status === "Active").length,
    setupWarnings: products.filter((item) => item.setup_state === "setup-needed").length,
    activeLanes: lanes.filter((item) => !["Cancelled", "FailedTerminal", "HandedOff"].includes(item.state)).length,
    waitingLanes: lanes.filter((item) => item.state === "AwaitingApproval" || item.state === "AwaitingGitHub").length,
    driftedBaselines: baselines.filter((item) => item.drift_status === "drift").length,
  };
}

function countWaitingLaneStates(laneStateCounts: Record<string, number>) {
  return (laneStateCounts.AwaitingApproval ?? 0) + (laneStateCounts.AwaitingGitHub ?? 0);
}

function countHighPriorityNotifications(notifications: ObservabilityNotificationRecord[]) {
  return notifications.filter((notification) => notification.severity === "error").length;
}

function isRuntimeNotification(notification: ObservabilityNotificationRecord) {
  return notification.notification_type !== "baseline-upgrade-failed";
}

function resolveObservabilityNotificationTarget(notification: ObservabilityNotificationRecord) {
  const laneId = notification.correlation.lane_id;
  const productId = notification.correlation.product_id;
  if (notification.notification_type === "baseline-upgrade-failed" && productId) {
    return {
      to: `/baselines/${productId}`,
      label: "Open baseline",
    };
  }
  if (notification.target_kind === "lane" && (laneId || notification.target_id)) {
    return {
      to: `/lanes/${laneId ?? notification.target_id}`,
      label: "Open lane",
    };
  }
  if (productId) {
    return {
      to: `/products/${productId}`,
      label: "Open product",
    };
  }
  if (laneId) {
    return {
      to: `/lanes/${laneId}`,
      label: "Open lane",
    };
  }
  return null;
}

function buttonLinkClassName(variant: "primary" | "outline" = "primary") {
  return variant === "outline"
    ? "inline-flex items-center justify-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
    : "inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90";
}

function ActionLink({
  to,
  href,
  label,
  variant = "primary",
}: {
  to?: string;
  href?: string | null;
  label: string;
  variant?: "primary" | "outline";
}) {
  if (to) {
    return (
      <Link to={to} className={buttonLinkClassName(variant)}>
        {label}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={buttonLinkClassName(variant)}>
        {label}
        <ExternalLink className="size-4" />
      </a>
    );
  }
  return null;
}

function resolvePrimaryDeliveryPullRequest(item: DeliveryWorkItemRecord): DeliveryPullRequestRecord | null {
  return item.linked_pull_requests.find((pullRequest) => pullRequest.number != null) ?? item.linked_pull_requests[0] ?? null;
}

function resolveDeliveryRepairSummary(reasons: string[]) {
  if (!reasons.length) {
    return "GitHub source of record needs review before the mirrored state is trustworthy.";
  }
  const visibleReasons = reasons.slice(0, 2).map((reason) => humanize(reason.replace(/\./g, " ")));
  return reasons.length > 2 ? `${visibleReasons.join(", ")}, and ${reasons.length - 2} more.` : `${visibleReasons.join(", ")}.`;
}

function buildDeliveryLaneByWorkItemId(lanes: LaneResponse[]) {
  const sortedLanes = [...lanes].sort((left, right) => {
    const rank = (lane: LaneResponse) => {
      if (lane.state === "AwaitingApproval") {
        return 0;
      }
      if (lane.state === "AwaitingGitHub") {
        return 1;
      }
      if (!isTerminalLaneState(lane.state)) {
        return 2;
      }
      return 3;
    };
    return rank(left) - rank(right) || resolveRecentTimestamp(right.updated_at) - resolveRecentTimestamp(left.updated_at);
  });

  const laneByWorkItemId = new Map<string, LaneResponse>();
  sortedLanes.forEach((lane) => {
    if (!laneByWorkItemId.has(lane.work_item_id)) {
      laneByWorkItemId.set(lane.work_item_id, lane);
    }
  });
  return laneByWorkItemId;
}

function sortDeliveryWorkItemsForDisplay(
  items: DeliveryWorkItemRecord[],
  laneByWorkItemId: Map<string, LaneResponse>,
) {
  const rank = (item: DeliveryWorkItemRecord) => {
    const lane = laneByWorkItemId.get(item.work_item_id);
    if (lane?.state === "AwaitingApproval") {
      return 0;
    }
    if (lane?.state === "AwaitingGitHub") {
      return 1;
    }
    if (lane && !isTerminalLaneState(lane.state)) {
      return 2;
    }
    if (item.handoff_status === "in_review" || item.handoff_status === "merged") {
      return 3;
    }
    if (item.mirror_state === "ambiguous") {
      return 4;
    }
    if (item.mirror_state === "stale") {
      return 5;
    }
    if (item.status === "Ready") {
      return 6;
    }
    if (item.status === "Blocked") {
      return 7;
    }
    return 8;
  };

  return [...items].sort(
    (left, right) =>
      rank(left) - rank(right) || resolveRecentTimestamp(right.updated_at) - resolveRecentTimestamp(left.updated_at),
  );
}

function resolveDeliveryWorkItemSummary({
  item,
  lane,
  laneSummary,
}: {
  item: DeliveryWorkItemRecord;
  lane: LaneResponse | null;
  laneSummary?: LaneStatusSummaryRecord | null;
}) {
  const primaryPullRequest = resolvePrimaryDeliveryPullRequest(item);
  if (lane) {
    if (lane.state === "AwaitingApproval" || lane.state === "AwaitingGitHub") {
      return lane.agent_session?.wait_reason ?? describeLane(lane);
    }
    return `${describeLane(lane)} ${describeLaneRuntimeHealth(lane, laneSummary)}`;
  }
  if (item.requires_repair) {
    return `Mirror needs review: ${resolveDeliveryRepairSummary(item.repair_reasons)}`;
  }
  if (primaryPullRequest?.number && item.handoff_status === "in_review") {
    return `Handed off on PR #${primaryPullRequest.number}; GitHub review is the source of record from here.`;
  }
  if (primaryPullRequest?.number && item.handoff_status === "merged") {
    return `PR #${primaryPullRequest.number} merged; closeout still lives in GitHub until the issue mirror catches up.`;
  }
  if (item.status === "Ready") {
    return "Ready backlog item with no active lane yet. Scheduler-owned dispatch should claim it next.";
  }
  if (item.status === "Blocked") {
    return item.dependency_state === "ambiguous"
      ? "Dependency state is ambiguous and still needs GitHub confirmation."
      : "Dependency or backlog state still blocks build work.";
  }
  if (item.status === "In Progress") {
    return "GitHub still shows active build work, but no current lane is attached on this route.";
  }
  if (item.status === "Triage") {
    return "This item is still waiting on backlog clarification before it is safe to build.";
  }
  return `${humanize(item.status)} remains the mirrored source-of-record status.`;
}

function resolveProductDeliveryNextStep({
  product,
  cockpit,
  lanes,
  remediationActions,
  onboardingActivity,
}: {
  product: ProductSummaryResponse;
  cockpit: DeliveryCockpitRecord | null;
  lanes: LaneResponse[];
  remediationActions: GuidedRemediationAction[];
  onboardingActivity: ProductOnboardingActivity | null;
}): ProductDeliveryNextStep {
  const activeLanes = lanes
    .filter((lane) => !isTerminalLaneState(lane.state))
    .sort((left, right) => resolveRecentTimestamp(right.updated_at) - resolveRecentTimestamp(left.updated_at));
  const blockingCount = computeDiagnosticBuckets(product.setup_diagnostics).blocking.length || 1;
  const waitingLane =
    activeLanes.find((lane) => lane.state === "AwaitingApproval") ??
    activeLanes.find((lane) => lane.state === "AwaitingGitHub");
  const reviewItem = cockpit?.work_items.find(
    (item) => item.handoff_status === "in_review" || item.handoff_status === "merged",
  );
  const ambiguousItem = cockpit?.work_items.find((item) => item.mirror_state !== "current");
  const activeLane = activeLanes[0] ?? null;
  const readyItem = cockpit?.work_items.find((item) => item.status === "Ready") ?? null;
  const primaryRemediation = remediationActions.find((action) => action.variant === "primary") ?? remediationActions[0] ?? null;

  if (product.setup_state === "setup-needed") {
    return {
      title: "Resolve setup blockers before the first build",
      description: `${blockingCount} ${pluralize(blockingCount, "blocking diagnostic")} still prevent a safe active-build posture for this product.`,
      status: "blocking",
      actionLabel: primaryRemediation?.label ?? onboardingActivity?.actionLabel ?? "Review blockers",
      to: primaryRemediation?.to ?? onboardingActivity?.target,
    };
  }

  if (waitingLane) {
    return {
      title: waitingLane.state === "AwaitingApproval" ? "Review waiting approval" : "Provide waiting human input",
      description: `Issue #${waitingLane.work_item.issue_number} is paused on lane state ${humanize(waitingLane.state).toLowerCase()}.`,
      status: "follow-up",
      actionLabel: "Open waiting lane",
      to: `/lanes/${waitingLane.lane_id}`,
    };
  }

  if (reviewItem) {
    const primaryPullRequest = resolvePrimaryDeliveryPullRequest(reviewItem);
    return {
      title: reviewItem.handoff_status === "merged" ? "Close the merged handoff loop" : "Follow work into review",
      description: primaryPullRequest?.number
        ? `Issue #${reviewItem.issue_number} is now tracked through PR #${primaryPullRequest.number} in GitHub.`
        : `Issue #${reviewItem.issue_number} has review-state handoff visible in the mirror.`,
      status: "follow-up",
      actionLabel: primaryPullRequest?.number ? `Open PR #${primaryPullRequest.number}` : `Open issue #${reviewItem.issue_number}`,
      href: primaryPullRequest?.url ?? reviewItem.url,
    };
  }

  if (ambiguousItem) {
    return {
      title: ambiguousItem.mirror_state === "stale" ? "Re-check stale mirrored work" : "Review ambiguous mirrored work",
      description:
        ambiguousItem.mirror_state === "stale"
          ? `Issue #${ambiguousItem.issue_number} has not been normalized recently enough to treat the mirror as current.`
          : `Issue #${ambiguousItem.issue_number} still carries repair-needed or ambiguous delivery state.`,
      status: "follow-up",
      actionLabel: `Open issue #${ambiguousItem.issue_number}`,
      href: ambiguousItem.url,
    };
  }

  if (activeLane) {
    return {
      title: "Follow active lane execution",
      description: `Issue #${activeLane.work_item.issue_number} is currently ${humanize(activeLane.state).toLowerCase()} on this product.`,
      status: "ready",
      actionLabel: "Open active lane",
      to: `/lanes/${activeLane.lane_id}`,
    };
  }

  if (readyItem) {
    return {
      title: "Track the first ready build item",
      description: `Issue #${readyItem.issue_number} is ready in the mirror, but no lane has claimed it yet. Scheduler-owned dispatch should pick it up from here.`,
      status: "ready",
      actionLabel: `Open issue #${readyItem.issue_number}`,
      href: readyItem.url,
    };
  }

  if (cockpit?.project?.url) {
    return {
      title: "Review GitHub project delivery state",
      description: `No active lane is attached yet. GitHub Project #${cockpit.project.number} remains the source of record for the next build step.`,
      status: "follow-up",
      actionLabel: "Open GitHub project",
      href: cockpit.project.url,
    };
  }

  if (onboardingActivity) {
    return {
      title: "Return to the onboarding handoff",
      description: "No delivery mirror is attached yet, so the last onboarding result remains the best starting point.",
      status: "follow-up",
      actionLabel: onboardingActivity.actionLabel,
      to: onboardingActivity.target,
    };
  }

  return {
    title: "Watch delivery activity come online",
    description: "No active lanes or mirrored work items are attached yet. Delivery context will appear here after GitHub backlog and lane state are mirrored.",
    status: "follow-up",
    actionLabel: "Open Products",
    to: "/products",
  };
}

function PageHeader({
  eyebrow,
  title,
  description,
  action,
  breadcrumbs,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
}) {
  return (
    <div
      className={[
        "flex flex-col gap-4 lg:flex-row lg:justify-between",
        breadcrumbs?.length ? "lg:items-start" : "lg:items-end",
      ].join(" ")}
    >
      <div className={breadcrumbs?.length ? "space-y-3" : "space-y-2"}>
        {breadcrumbs?.length ? (
          <nav aria-label="Breadcrumb">
            <ol className="flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
              {breadcrumbs.map((item, index) => (
                <Fragment key={`${item.label}:${item.to ?? index}`}>
                  {index ? <li className="text-zinc-400">/</li> : null}
                  <li>
                    {item.to ? (
                      <Link to={item.to} className="underline text-zinc-700 dark:text-zinc-300">
                        {item.label}
                      </Link>
                    ) : (
                      <span
                        aria-current={index === breadcrumbs.length - 1 ? "page" : undefined}
                        className={
                          index === breadcrumbs.length - 1
                            ? "font-medium text-zinc-900 dark:text-zinc-100"
                            : "text-zinc-700 dark:text-zinc-300"
                        }
                      >
                        {item.label}
                      </span>
                    )}
                  </li>
                </Fragment>
              ))}
            </ol>
          </nav>
        ) : null}
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-primary/80">{eyebrow}</p>
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
      {action ? <div className="flex flex-wrap items-center gap-3">{action}</div> : null}
    </div>
  );
}

function SurfaceEntryCard({
  eyebrow,
  title,
  description,
  icon,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  icon: ReactNode;
  action: ReactNode;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader className="space-y-3">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            {icon}
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              {eyebrow}
            </p>
            <CardTitle className="text-foreground">{title}</CardTitle>
          </div>
        </div>
        <CardDescription className="text-muted-foreground">{description}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        {action}
      </CardContent>
    </Card>
  );
}

function MetricCard({
  icon,
  label,
  value,
  helper,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  helper: string;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader className="space-y-3 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            {icon}
          </div>
          <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</span>
        </div>
        <div>
          <CardTitle className="text-3xl text-foreground">{value}</CardTitle>
          <CardDescription className="pt-1 text-muted-foreground">{helper}</CardDescription>
        </div>
      </CardHeader>
    </Card>
  );
}

function EmptyState({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Card className="border-dashed shadow-none">
      <CardContent className="flex flex-col items-start gap-2 py-8">
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
        {children}
        {action ? <div className="flex flex-wrap gap-2 pt-2">{action}</div> : null}
      </CardContent>
    </Card>
  );
}

function OnboardingActivityPanel({
  title,
  description,
  activities,
  emptyTitle,
  emptyDescription,
  limit = 4,
}: {
  title: string;
  description: string;
  activities: ProductOnboardingActivity[];
  emptyTitle: string;
  emptyDescription: string;
  limit?: number;
}) {
  const visibleActivities = activities.slice(0, limit);

  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-foreground">{title}</CardTitle>
        <CardDescription className="text-muted-foreground">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {visibleActivities.length ? (
          visibleActivities.map((activity) => (
            <Link
              key={`${activity.kind}:${activity.productId}`}
              to={activity.target}
              className="block rounded-3xl border border-border/70 bg-muted/30 p-4 transition hover:border-primary/30"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-foreground">{activity.productName}</p>
                    <Badge className="border-border bg-secondary text-secondary-foreground">
                      {humanize(activity.kind)}
                    </Badge>
                    <Badge className={statusTone(activity.status)}>{humanize(activity.status)}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{activity.description}</p>
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    {activity.title} • {formatRelativeTime(activity.updatedAt)}
                  </p>
                </div>
                <div className="flex items-center gap-2 text-sm text-primary">
                  {activity.actionLabel}
                  <ArrowRight className="mt-0.5 size-4" />
                </div>
              </div>
            </Link>
          ))
        ) : (
          <EmptyState title={emptyTitle} description={emptyDescription} />
        )}
      </CardContent>
    </Card>
  );
}

function ObservabilityNotificationList({
  notifications,
  emptyTitle,
  emptyDescription,
  limit = 5,
}: {
  notifications: ObservabilityNotificationRecord[];
  emptyTitle: string;
  emptyDescription: string;
  limit?: number;
}) {
  const visibleNotifications = notifications.slice(0, limit);

  if (!visibleNotifications.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <>
      {visibleNotifications.map((notification) => {
        const target = resolveObservabilityNotificationTarget(notification);
        const content = (
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">{notification.title}</p>
                <Badge className={statusTone(notification.severity)}>{humanize(notification.severity)}</Badge>
                <Badge className="border-border bg-secondary text-secondary-foreground">
                  {humanize(notification.target_kind)}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">{notification.summary}</p>
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                {humanize(notification.notification_type)} • {formatRelativeTime(notification.observed_at)}
              </p>
            </div>
            {target ? (
              <div className="flex items-center gap-2 text-sm text-primary">
                {target.label}
                <ArrowRight className="mt-0.5 size-4" />
              </div>
            ) : null}
          </div>
        );

        return target ? (
          <Link
            key={`${notification.notification_type}:${notification.target_id}:${notification.observed_at ?? "unknown"}`}
            to={target.to}
            className="block rounded-3xl border border-border/70 bg-muted/30 p-4 transition hover:border-primary/30"
          >
            {content}
          </Link>
        ) : (
          <div
            key={`${notification.notification_type}:${notification.target_id}:${notification.observed_at ?? "unknown"}`}
            className="rounded-3xl border border-border/70 bg-muted/30 p-4"
          >
            {content}
          </div>
        );
      })}
    </>
  );
}

function ProductDeliveryCockpitCard({
  product,
  cockpit,
  lanes,
  laneSummariesById,
  onboardingActivity,
  remediationActions,
  actorId,
  actionBusy,
  onProductAction,
}: {
  product: ProductSummaryResponse;
  cockpit: DeliveryCockpitRecord | null;
  lanes: LaneResponse[];
  laneSummariesById: Map<string, LaneStatusSummaryRecord>;
  onboardingActivity: ProductOnboardingActivity | null;
  remediationActions: GuidedRemediationAction[];
  actorId: string;
  actionBusy: string | null;
  onProductAction: (action: ProductAction) => Promise<void>;
}) {
  const laneByWorkItemId = buildDeliveryLaneByWorkItemId(lanes);
  const workItems = sortDeliveryWorkItemsForDisplay(cockpit?.work_items ?? [], laneByWorkItemId);
  const nextStep = resolveProductDeliveryNextStep({
    product,
    cockpit,
    lanes,
    remediationActions,
    onboardingActivity,
  });
  const project = cockpit?.project ?? null;
  const workPressure = cockpit?.work_pressure ?? {
    total_open_count: 0,
    triage_count: 0,
    ready_count: 0,
    blocked_count: 0,
    in_progress_count: 0,
    in_review_count: 0,
    done_count: 0,
    ambiguous_count: 0,
    stale_count: 0,
  };
  const activeLaneCount = lanes.filter((lane) => !isTerminalLaneState(lane.state)).length;
  const mirrorFollowUpCount = workPressure.ambiguous_count + workPressure.stale_count;

  return (
    <Card className="shadow-none">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-foreground">Delivery cockpit</CardTitle>
          {cockpit ? <Badge className={statusTone(cockpit.mirror_state)}>{humanize(cockpit.mirror_state)}</Badge> : null}
        </div>
        <CardDescription className="text-muted-foreground">
          GitHub project state, mirrored build pressure, lane handoff, and the next operator decision stay together here while GitHub remains the planning system of record.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className={`rounded-3xl border p-4 ${resolveReadinessTone(nextStep.status)}`}>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-1">
              <p className="font-medium text-foreground">{nextStep.title}</p>
              <p className="text-sm">{nextStep.description}</p>
            </div>
            <ActionLink to={nextStep.to} href={nextStep.href} label={nextStep.actionLabel} />
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Open work</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{workPressure.total_open_count}</p>
            <p className="pt-1 text-sm text-muted-foreground">
              {workPressure.triage_count} triage • {workPressure.blocked_count} blocked
            </p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Ready now</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{workPressure.ready_count}</p>
            <p className="pt-1 text-sm text-muted-foreground">
              Ready backlog stays visible even before a lane is claimed.
            </p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">In review</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{workPressure.in_review_count}</p>
            <p className="pt-1 text-sm text-muted-foreground">
              Pull-request handoff remains in GitHub, not inside a second Orcha planner.
            </p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Active lanes</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{activeLaneCount}</p>
            <p className="pt-1 text-sm text-muted-foreground">
              {mirrorFollowUpCount
                ? `${mirrorFollowUpCount} mirrored ${pluralize(mirrorFollowUpCount, "item")} still need ambiguity or freshness review.`
                : "No mirrored freshness or ambiguity follow-up is currently surfaced."}
            </p>
          </div>
        </div>

        <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">GitHub project mirror</p>
                {project ? <Badge className={statusTone(project.mirror_state)}>{humanize(project.mirror_state)}</Badge> : null}
              </div>
              <p className="text-sm text-muted-foreground">
                GitHub project state is summarized here, but GitHub still owns backlog authoring and project management.
              </p>
            </div>
            {project ? <ActionLink href={project.url} label="Open GitHub project" variant="outline" /> : null}
          </div>

          {project ? (
            <div className="grid gap-3 pt-4 md:grid-cols-3">
              <div className="rounded-2xl border border-border/70 bg-background/80 p-3">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Project</p>
                <p className="pt-1 font-medium text-foreground">
                  #{project.number} {project.title}
                </p>
                <p className="pt-1 text-sm text-muted-foreground">{project.status_field_name} is the mirrored planning field.</p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/80 p-3">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Mirrored items</p>
                <p className="pt-1 font-medium text-foreground">{project.item_count}</p>
                <p className="pt-1 text-sm text-muted-foreground">
                  {project.issue_count} issues • {project.pull_request_count} PRs
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/80 p-3">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Last reconciled</p>
                <p className="pt-1 font-medium text-foreground">{formatRelativeTime(project.last_reconciled_at)}</p>
                <p className="pt-1 text-sm text-muted-foreground">
                  Mirror freshness is shown, not assumed, when operators review delivery state.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className={`mt-3 ${COMPACT_ACTION_BUTTON_CLASS}`}
                  onClick={() =>
                    void onProductAction({
                      kind: "refresh-mirror",
                      productId: product.product_id,
                      actorId,
                      reason: "Refresh product mirror from delivery cockpit.",
                    })
                  }
                  disabled={actionBusy === `product:refresh-mirror:${product.product_id}`}
                >
                  {actionBusy === `product:refresh-mirror:${product.product_id}` ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RefreshCw className="size-4" />
                  )}
                  Refresh mirror
                </Button>
              </div>
            </div>
          ) : (
            <div className="pt-4">
              <EmptyState
                title="No GitHub project mirror is attached."
                description="Issue and PR mirrors can still show delivery context, but the backlog source-of-record remains outside Orcha until a project is bound."
                action={
                  onboardingActivity ? (
                    <ActionLink to={onboardingActivity.target} label={onboardingActivity.actionLabel} variant="outline" />
                  ) : undefined
                }
              />
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-medium text-foreground">Tracked build work</p>
              <p className="pt-1 text-sm text-muted-foreground">
                Operators can move from mirrored issue state to the active lane or external GitHub handoff without leaving product detail.
              </p>
            </div>
            {cockpit?.remaining_work_item_count ? (
              <Badge className="border-border bg-secondary text-secondary-foreground">
                +{cockpit.remaining_work_item_count} more in GitHub
              </Badge>
            ) : null}
          </div>

          {workItems.length ? (
            workItems.map((item) => {
              const lane = laneByWorkItemId.get(item.work_item_id) ?? null;
              const laneSummary = lane ? laneSummariesById.get(lane.lane_id) ?? null : null;
              const primaryPullRequest = resolvePrimaryDeliveryPullRequest(item);
              return (
                <div key={item.work_item_id} className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-foreground">
                          #{item.issue_number} {item.title}
                        </p>
                        <Badge className={statusTone(item.status)}>{humanize(item.status)}</Badge>
                        {item.handoff_status !== "none" ? (
                          <Badge className={statusTone(item.handoff_status)}>{humanize(item.handoff_status)}</Badge>
                        ) : null}
                        {item.dependency_state !== "clear" ? (
                          <Badge className={statusTone(item.dependency_state)}>{humanize(item.dependency_state)}</Badge>
                        ) : null}
                        {item.mirror_state !== "current" ? (
                          <Badge className={statusTone(item.mirror_state)}>{humanize(item.mirror_state)}</Badge>
                        ) : null}
                        {lane ? <Badge className={statusTone(lane.state)}>{humanize(lane.state)}</Badge> : null}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {resolveDeliveryWorkItemSummary({ item, lane, laneSummary })}
                      </p>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        {item.repo_owner}/{item.repo_name}
                        {item.project_status_name ? ` • GitHub Project ${item.project_status_name}` : ""}
                        {item.status_source ? ` • Source ${humanize(item.status_source)}` : ""}
                        • normalized {formatRelativeTime(item.last_normalized_at)}
                        • updated {formatRelativeTime(item.updated_at)}
                      </p>
                      {item.requires_repair ? (
                        <p className="text-sm text-rose-700 dark:text-rose-200">
                          Mirror ambiguity: {resolveDeliveryRepairSummary(item.repair_reasons)}
                        </p>
                      ) : null}
                      {primaryPullRequest?.number ? (
                        <p className="text-sm text-muted-foreground">
                          PR #{primaryPullRequest.number}
                          {primaryPullRequest.title ? ` • ${primaryPullRequest.title}` : ""}
                          {primaryPullRequest.review_state ? ` • ${humanize(primaryPullRequest.review_state)}` : ""}
                          {primaryPullRequest.merge_state ? ` • ${humanize(primaryPullRequest.merge_state)}` : ""}
                        </p>
                      ) : null}
                    </div>

                    <div className="flex flex-wrap gap-2 xl:justify-end">
                      {lane ? <ActionLink to={`/lanes/${lane.lane_id}`} label="Open lane" variant="outline" /> : null}
                      <ActionLink href={item.url} label={`Issue #${item.issue_number}`} variant="outline" />
                      {primaryPullRequest?.number ? (
                        <ActionLink href={primaryPullRequest.url} label={`PR #${primaryPullRequest.number}`} />
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <EmptyState
              title="No mirrored build work is attached yet."
              description={
                project
                  ? "The product is bound to GitHub, but no open issue or PR mirror is currently active on this route. Use the project link and next-step guidance above instead of waiting on a blank lane list."
                  : "Delivery context will appear here after GitHub issues, PRs, or lanes are mirrored for this product."
              }
              action={
                project ? (
                  <ActionLink href={project.url} label="Open GitHub project" variant="outline" />
                ) : onboardingActivity ? (
                  <ActionLink to={onboardingActivity.target} label={onboardingActivity.actionLabel} variant="outline" />
                ) : undefined
              }
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ContractRefreshPanel({
  productId,
  actorId,
  actionBusy,
  onProductAction,
  defaultRepoRoot,
  defaultRefreshReason,
  allowRemoteRefresh = false,
  title = "Refresh contract",
  description = "Run the durable refresh path after you clear repo, settings, or secret blockers so the latest setup state is recorded.",
  buttonLabel = "Refresh contract",
  buttonClassName = COMPACT_ACTION_BUTTON_CLASS,
  onAfterRefresh,
}: {
  productId: string;
  actorId: string;
  actionBusy: string | null;
  onProductAction: (action: ProductAction) => Promise<void>;
  defaultRepoRoot: string;
  defaultRefreshReason: string;
  allowRemoteRefresh?: boolean;
  title?: string;
  description?: string;
  buttonLabel?: string;
  buttonClassName?: string;
  onAfterRefresh?: () => Promise<void>;
}) {
  const [repoRoot, setRepoRoot] = useState(defaultRepoRoot.trim() || REFRESH_REPO_ROOT_HINT);
  const [refreshReason, setRefreshReason] = useState(defaultRefreshReason);
  const repoRootInputId = `contract-refresh-repo-root-${productId}`;
  const refreshReasonInputId = `contract-refresh-reason-${productId}`;

  useEffect(() => {
    setRepoRoot(defaultRepoRoot.trim() || REFRESH_REPO_ROOT_HINT);
  }, [defaultRepoRoot]);

  useEffect(() => {
    setRefreshReason(defaultRefreshReason);
  }, [defaultRefreshReason]);

  const normalizedRepoRoot = repoRoot.trim();
  const canRefresh = Boolean(normalizedRepoRoot) || allowRemoteRefresh;

  async function refreshContract() {
    if (!canRefresh) {
      return;
    }
    await onProductAction({
      kind: "refresh",
      productId,
      actorId,
      reason: refreshReason.trim() || defaultRefreshReason,
      repoRoot: normalizedRepoRoot || undefined,
    });
    if (onAfterRefresh) {
      await onAfterRefresh();
    }
  }

  return (
    <div className="space-y-2 rounded-3xl border border-border/70 bg-muted/30 p-4">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="text-sm text-muted-foreground">{description}</p>
      <FormField
        label={allowRemoteRefresh ? "Repo root override" : "Repo root"}
        htmlFor={repoRootInputId}
        description={
          allowRemoteRefresh && !defaultRepoRoot.trim()
            ? "Leave this blank to refresh from the bound GitHub repository."
            : undefined
        }
      >
        <Input
          id={repoRootInputId}
          value={repoRoot}
          onChange={(event) => setRepoRoot(event.target.value)}
          placeholder={allowRemoteRefresh ? "/path/to/product/repo (optional)" : "/path/to/product/repo"}
          className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
        />
      </FormField>
      <FormField label="Refresh reason" htmlFor={refreshReasonInputId}>
        <Input
          id={refreshReasonInputId}
          value={refreshReason}
          onChange={(event) => setRefreshReason(event.target.value)}
          className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
        />
      </FormField>
      <Button
        type="button"
        onClick={() => void refreshContract()}
        disabled={!canRefresh || actionBusy === `product:refresh:${productId}`}
        className={`${buttonClassName} bg-primary text-primary-foreground hover:bg-primary/90`}
      >
        {actionBusy === `product:refresh:${productId}` ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <RefreshCw className="size-4" />
        )}
        {buttonLabel}
      </Button>
    </div>
  );
}

function MirrorRefreshPanel({
  productId,
  actorId,
  actionBusy,
  onProductAction,
  defaultReason,
  title = "Refresh mirror",
  description = "Backfill GitHub issues and project state into Orcha, and re-check webhook delivery so future issue changes arrive automatically.",
  buttonLabel = "Refresh mirror",
  buttonClassName = COMPACT_ACTION_BUTTON_CLASS,
}: {
  productId: string;
  actorId: string;
  actionBusy: string | null;
  onProductAction: (action: ProductAction) => Promise<void>;
  defaultReason: string;
  title?: string;
  description?: string;
  buttonLabel?: string;
  buttonClassName?: string;
}) {
  return (
    <div className="space-y-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
      <div className="space-y-1">
        <p className="font-medium text-foreground">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Button
        type="button"
        className={buttonClassName}
        onClick={() =>
          void onProductAction({
            kind: "refresh-mirror",
            productId,
            actorId,
            reason: defaultReason,
          })
        }
        disabled={actionBusy === `product:refresh-mirror:${productId}`}
      >
        {actionBusy === `product:refresh-mirror:${productId}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
        {buttonLabel}
      </Button>
    </div>
  );
}

function OnboardingFollowUpCard({
  product,
  actorId,
  actionBusy,
  onProductAction,
  defaultRepoRoot,
  defaultRefreshReason,
  buttonClassName,
  onAfterRefresh,
}: {
  product: ProductSummaryResponse;
  actorId: string;
  actionBusy: string | null;
  onProductAction: (action: ProductAction) => Promise<void>;
  defaultRepoRoot: string;
  defaultRefreshReason: string;
  buttonClassName?: string;
  onAfterRefresh?: () => Promise<void>;
}) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle>Direct next steps</CardTitle>
        <CardDescription>
          Open the product, review baselines, go to settings, or rerun contract validation without leaving the onboarding result route.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Link
          to={`/products/${product.product_id}`}
          className={buttonLinkClassName(product.setup_state === "setup-needed" ? "outline" : "primary")}
        >
          {product.setup_state === "setup-needed" ? "Open product blockers" : "Open product"}
        </Link>
        <Link to={`/baselines/${product.product_id}`} className={buttonLinkClassName("outline")}>
          Review baselines
        </Link>
        <Link to="/settings/orgs" className={buttonLinkClassName("outline")}>
          Open settings
        </Link>
        <ContractRefreshPanel
          productId={product.product_id}
          actorId={actorId}
          actionBusy={actionBusy}
          onProductAction={onProductAction}
          defaultRepoRoot={defaultRepoRoot}
          defaultRefreshReason={defaultRefreshReason}
          allowRemoteRefresh={Boolean(product.primary_repo)}
          title="Rerun contract refresh"
          description="Use the tracked repo root to refresh setup diagnostics after you clear onboarding blockers."
          buttonLabel="Rerun contract refresh"
          buttonClassName={buttonClassName ?? COMPACT_ACTION_BUTTON_CLASS}
          onAfterRefresh={onAfterRefresh}
        />
      </CardContent>
    </Card>
  );
}

function ActivationReadinessCard({
  title = "Activation readiness",
  description,
  setupState,
  diagnostics,
  managedAssets,
  lastConfigRefreshAt,
}: {
  title?: string;
  description: string;
  setupState: string;
  diagnostics: SetupDiagnostic[];
  managedAssets: ManagedAssetRecord[];
  lastConfigRefreshAt?: string | null;
}) {
  const diagnosticBuckets = computeDiagnosticBuckets(diagnostics);
  const readinessItems = buildActivationReadinessItems({
    setupState,
    diagnostics,
    managedAssets,
    lastConfigRefreshAt,
  });
  const blockingCount = diagnosticBuckets.blocking.length;
  const managedAssetFollowUp = countManagedAssetFollowUp(managedAssets);
  const advisoryCount = diagnosticBuckets.advisory.length + diagnosticBuckets.other.length;
  const isBlocked = setupState === "setup-needed" || blockingCount > 0;
  const summaryTone = isBlocked
    ? resolveReadinessTone("blocking")
    : managedAssetFollowUp || advisoryCount
      ? resolveReadinessTone("follow-up")
      : resolveReadinessTone("ready");
  const summaryTitle = isBlocked ? "Lane work is still blocked" : "Blocking setup is clear";
  const summaryDescription = isBlocked
    ? `${blockingCount || 1} ${pluralize(blockingCount || 1, "blocking diagnostic")} still need remediation before lane work should resume. Drift and advisory findings stay visible as separate follow-up.`
    : managedAssetFollowUp || advisoryCount
      ? "Blocking setup is clear. Remaining managed asset drift and advisory findings stay visible as follow-up only."
      : "Blocking setup is clear and the latest refresh shows no remaining drift or advisory follow-up.";

  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-foreground">{title}</CardTitle>
        <CardDescription className="text-muted-foreground">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className={`rounded-3xl border p-4 ${summaryTone}`}>
          <p className="font-medium text-foreground">{summaryTitle}</p>
          <p className="pt-1 text-sm">{summaryDescription}</p>
        </div>
        <div className="space-y-3">
          {readinessItems.map((item) => (
            <div key={item.key} className="flex items-start gap-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
              <div className={`mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-2xl border ${resolveReadinessTone(item.status)}`}>
                {item.status === "ready" ? (
                  <CheckCircle2 className="size-4" />
                ) : item.status === "blocking" ? (
                  <TriangleAlert className="size-4" />
                ) : (
                  <CircleHelp className="size-4" />
                )}
              </div>
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-foreground">{item.label}</p>
                  <Badge className={resolveReadinessTone(item.status)}>{humanize(item.status)}</Badge>
                </div>
                <p className="text-sm text-muted-foreground">{item.description}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function GuidedRemediationCard({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions: GuidedRemediationAction[];
}) {
  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-foreground">{title}</CardTitle>
        <CardDescription className="text-muted-foreground">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {actions.map((action) => (
          <Link
            key={action.key}
            to={action.to}
            className={`block rounded-3xl border p-4 transition hover:border-primary/30 ${
              action.variant === "primary"
                ? "border-primary/20 bg-primary/5"
                : "border-border/70 bg-muted/30"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <p className="font-medium text-foreground">{action.label}</p>
                <p className="text-sm text-muted-foreground">{action.description}</p>
              </div>
              <ArrowRight className="mt-1 size-4 shrink-0 text-primary" />
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

function SetupFindingsCard({
  title,
  description,
  diagnostics,
}: {
  title: string;
  description: string;
  diagnostics: SetupDiagnostic[];
}) {
  const diagnosticBuckets = computeDiagnosticBuckets(diagnostics);
  const metricCards = [
    { key: "blocking", label: "Blocking", count: diagnosticBuckets.blocking.length, tone: "border-rose-500/20 bg-rose-500/8" },
    { key: "drift", label: "Drift", count: diagnosticBuckets.drift.length, tone: "border-amber-500/20 bg-amber-500/8" },
    { key: "advisory", label: "Advisory", count: diagnosticBuckets.advisory.length, tone: "border-border/70 bg-muted/30" },
  ];

  if (diagnosticBuckets.other.length) {
    metricCards.push({
      key: "other",
      label: "Other",
      count: diagnosticBuckets.other.length,
      tone: "border-border/70 bg-muted/30",
    });
  }

  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-foreground">{title}</CardTitle>
        <CardDescription className="text-muted-foreground">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className={`grid gap-3 ${metricCards.length > 3 ? "md:grid-cols-4" : "md:grid-cols-3"}`}>
          {metricCards.map((item) => (
            <div key={item.key} className={`rounded-2xl border p-3 ${item.tone}`}>
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{item.label}</p>
              <p className="pt-1 text-2xl font-semibold text-foreground">{item.count}</p>
            </div>
          ))}
        </div>
        {diagnostics.length ? (
          [
            {
              title: "Blocking setup errors",
              entries: diagnosticBuckets.blocking,
              description: "Blocking setup errors keep the product out of a safe activation posture until they are resolved.",
            },
            {
              title: "Recoverable drift",
              entries: diagnosticBuckets.drift,
              description: "Recoverable findings stay visible as follow-up work instead of being collapsed into setup blockers.",
            },
            {
              title: "Advisory warnings",
              entries: diagnosticBuckets.advisory,
              description: "Advisory findings remain operator-visible, but they are not hard activation blockers.",
            },
            {
              title: "Other findings",
              entries: diagnosticBuckets.other,
              description: "Unexpected classifications remain visible so operators can still act on the full diagnostic set.",
            },
          ]
            .filter((section) => section.entries.length || section.title !== "Other findings")
            .map((section) => (
              <div key={section.title} className="space-y-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
                <div>
                  <p className="font-medium text-foreground">{section.title}</p>
                  <p className="pt-1 text-sm text-muted-foreground">{section.description}</p>
                </div>
                {section.entries.length ? (
                  section.entries.map((diagnostic) => (
                    <div key={`${diagnostic.code}:${diagnostic.message}`} className="rounded-2xl border border-border/70 bg-background px-4 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge className={diagnosticTone(diagnostic.classification)}>
                          {humanize(diagnostic.classification)}
                        </Badge>
                        <p className="font-medium text-foreground">{diagnostic.code}</p>
                      </div>
                      <p className="pt-2 text-sm text-muted-foreground">{diagnostic.message}</p>
                      {diagnostic.path ? (
                        <p className="pt-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                          {diagnostic.path}
                        </p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">None reported.</p>
                )}
              </div>
            ))
        ) : (
          <EmptyState
            title="No setup diagnostics were recorded."
            description="The latest contract refresh did not produce setup diagnostics for this surface."
          />
        )}
      </CardContent>
    </Card>
  );
}

function StandardsRunAssetCard({
  asset,
}: {
  asset: StandardsRunRecord["assets"][number];
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background px-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-foreground">{asset.path}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={statusTone(asset.action)}>{humanize(asset.action)}</Badge>
          <Badge className={statusTone(asset.drift_status)}>{humanize(asset.drift_status)}</Badge>
        </div>
      </div>
      <p className="pt-2 text-sm text-muted-foreground">
        {humanize(asset.management_mode)}
        {asset.detail ? ` • ${asset.detail}` : ""}
      </p>
      {asset.patch_text ? (
        <details className="mt-3 rounded-2xl border border-border/70 bg-muted/30 px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium text-foreground">Patch preview</summary>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs text-muted-foreground">
            {asset.patch_text}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function StandardsWorkspaceCard({
  baseline,
  runs,
  selectedRun,
  selectedRunId,
  loading,
  error,
  notice,
  actionBusy,
  evaluationRepoRoot,
  evaluationPrNumber,
  outcomePrNumber,
  onSelectRun,
  onEvaluateRepoRootChange,
  onEvaluationPrNumberChange,
  onOutcomePrNumberChange,
  onEvaluate,
  onSubmitOutcome,
}: {
  baseline: BaselineResponse;
  runs: StandardsRunRecord[];
  selectedRun: StandardsRunRecord | null;
  selectedRunId: string | null;
  loading: boolean;
  error: string | null;
  notice: string | null;
  actionBusy: string | null;
  evaluationRepoRoot: string;
  evaluationPrNumber: string;
  outcomePrNumber: string;
  onSelectRun: (runId: string) => void;
  onEvaluateRepoRootChange: (value: string) => void;
  onEvaluationPrNumberChange: (value: string) => void;
  onOutcomePrNumberChange: (value: string) => void;
  onEvaluate: () => Promise<void>;
  onSubmitOutcome: (decision: StandardsOutcomeDecision) => Promise<void>;
}) {
  const latestRun = runs[0] ?? baseline.latest_run ?? null;
  const managedAssetFollowUp = countManagedAssetFollowUp(baseline.managed_assets);
  const canSubmitOutcome = selectedRun ? canRecordStandardsOutcome(selectedRun) : false;
  const evaluationRepoRootId = `standards-eval-repo-root-${baseline.product_id}`;
  const evaluationPrNumberId = `standards-eval-pr-number-${baseline.product_id}`;
  const outcomePrNumberId = `standards-outcome-pr-number-${baseline.product_id}`;

  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-foreground">Standards workspace</CardTitle>
        <CardDescription className="text-muted-foreground">
          Start standards evaluations, review recent run state, and record operator outcomes without leaving baseline detail.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Channel</p>
            <p className="pt-1 text-sm font-medium text-foreground">{baseline.baseline_channel ?? "Unknown"}</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Standards Pack</p>
            <p className="pt-1 text-sm font-medium text-foreground">
              {baseline.standards_pack_key ?? "Unknown"} {baseline.standards_pack_version ?? ""}
            </p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Agent Core</p>
            <p className="pt-1 text-sm font-medium text-foreground">{baseline.agent_core_version ?? "Unknown"}</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Managed Follow-up</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{managedAssetFollowUp}</p>
          </div>
        </div>

        <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-foreground">Latest standards outcome</p>
            {latestRun ? (
              <>
                <Badge className="border-border bg-secondary text-secondary-foreground">
                  {formatStandardsOutcomeKind(latestRun.outcome_kind)}
                </Badge>
                <Badge className={statusTone(latestRun.outcome_status ?? "unknown")}>
                  {humanize(latestRun.outcome_status ?? "unknown")}
                </Badge>
              </>
            ) : null}
          </div>
          <p className="pt-2 text-sm text-muted-foreground">{describeStandardsRunStatus(latestRun)}</p>
        </div>

        {notice ? (
          <div className="rounded-3xl border border-emerald-500/25 bg-emerald-500/10 p-4 text-sm text-emerald-700 dark:text-emerald-300">
            {notice}
          </div>
        ) : null}
        {error ? (
          <div className="rounded-3xl border border-rose-500/25 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
            {error}
          </div>
        ) : null}

        <div className="space-y-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
          <div>
            <p className="font-medium text-foreground">Start standards evaluation</p>
            <p className="pt-1 text-sm text-muted-foreground">
              Evaluate the tracked repository against the current baseline channel and approved standards pack.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <FormField label="Local repo root" htmlFor={evaluationRepoRootId} required>
              <Input
                id={evaluationRepoRootId}
                value={evaluationRepoRoot}
                onChange={(event) => onEvaluateRepoRootChange(event.target.value)}
                placeholder="/path/to/product/repo"
                className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
              />
            </FormField>
            <FormField label="Generated PR Number" htmlFor={evaluationPrNumberId}>
              <Input
                id={evaluationPrNumberId}
                value={evaluationPrNumber}
                onChange={(event) => onEvaluationPrNumberChange(event.target.value)}
                inputMode="numeric"
                placeholder="Optional"
                className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
              />
            </FormField>
          </div>
          <Button
            type="button"
            onClick={() => void onEvaluate()}
            disabled={
              !evaluationRepoRoot.trim() ||
              !baseline.baseline_channel ||
              !baseline.standards_pack_key ||
              !baseline.standards_pack_version ||
              actionBusy === "evaluate"
            }
            className="w-full bg-primary text-primary-foreground hover:bg-primary/90 sm:w-[200px]"
          >
            {actionBusy === "evaluate" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            Start standards evaluation
          </Button>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium text-foreground">Recent runs</p>
              <p className="text-sm text-muted-foreground">
                Review the latest run state before recording an operator outcome.
              </p>
            </div>
            {loading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : null}
          </div>
          {runs.length ? (
            runs.map((run) => (
              <button
                key={run.standards_upgrade_run_id}
                type="button"
                onClick={() => onSelectRun(run.standards_upgrade_run_id)}
                className={`w-full rounded-3xl border p-4 text-left transition hover:border-primary/30 ${
                  selectedRunId === run.standards_upgrade_run_id
                    ? "border-primary/30 bg-primary/5"
                    : "border-border/70 bg-muted/30"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-foreground">{formatDateTime(run.created_at)}</p>
                      <Badge className="border-border bg-secondary text-secondary-foreground">
                        {formatStandardsOutcomeKind(run.outcome_kind)}
                      </Badge>
                      <Badge className={statusTone(run.outcome_status)}>{humanize(run.outcome_status)}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{describeStandardsRunStatus(run)}</p>
                    <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      {formatRelativeTime(run.updated_at)} • {countStandardsRunUpdates(run)} updates • {countStandardsRunConflicts(run)} conflicts • {run.follow_up_items.length} follow-up {pluralize(run.follow_up_items.length, "item")}
                    </p>
                  </div>
                  <ArrowRight className="mt-1 size-4 shrink-0 text-primary" />
                </div>
              </button>
            ))
          ) : (
            <EmptyState
              title="No standards evaluations are recorded yet."
              description="Start the first evaluation from the tracked repo root to populate run history, diffs, and operator review state."
            />
          )}
        </div>

        {selectedRun ? (
          <div className="space-y-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
            <div>
              <p className="font-medium text-foreground">Operator outcome</p>
              <p className="pt-1 text-sm text-muted-foreground">
                {canSubmitOutcome
                  ? "Record whether the current standards run should be accepted, rejected, or deferred. Managed asset posture and follow-up item status will update after submission."
                  : (selectedRun.outcome_status ?? "").toLowerCase() === "current"
                    ? "This run is already current. No operator outcome is required."
                    : `Operator outcome is already recorded as ${humanize(selectedRun.outcome_status).toLowerCase()}.`}
              </p>
            </div>
            {canSubmitOutcome ? (
              <>
                <FormField label="Generated PR Number" htmlFor={outcomePrNumberId}>
                  <Input
                    id={outcomePrNumberId}
                    value={outcomePrNumber}
                    onChange={(event) => onOutcomePrNumberChange(event.target.value)}
                    inputMode="numeric"
                    placeholder="Optional"
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </FormField>
                <div className="grid gap-2 md:grid-cols-3">
                  <Button
                    type="button"
                    variant="success"
                    onClick={() => void onSubmitOutcome("accepted")}
                    disabled={Boolean(actionBusy) && actionBusy !== "outcome:accepted"}
                  >
                    {actionBusy === "outcome:accepted" ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                    Accept run
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void onSubmitOutcome("deferred")}
                    disabled={Boolean(actionBusy) && actionBusy !== "outcome:deferred"}
                    className="border border-amber-400/40 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300"
                  >
                    {actionBusy === "outcome:deferred" ? <Loader2 className="size-4 animate-spin" /> : <Clock3 className="size-4" />}
                    Defer run
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void onSubmitOutcome("rejected")}
                    disabled={Boolean(actionBusy) && actionBusy !== "outcome:rejected"}
                    className="bg-rose-400 text-zinc-950 hover:bg-rose-300"
                  >
                    {actionBusy === "outcome:rejected" ? <Loader2 className="size-4 animate-spin" /> : <AlertTriangle className="size-4" />}
                    Reject run
                  </Button>
                </div>
              </>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function StandardsRunDetailsCard({
  baseline,
  run,
}: {
  baseline: BaselineResponse;
  run: StandardsRunRecord | null;
}) {
  if (!run) {
    return (
      <Card className="shadow-none">
        <CardHeader>
          <CardTitle className="text-foreground">Standards run detail</CardTitle>
          <CardDescription className="text-muted-foreground">
            Asset-level changes, conflicts, and follow-up items appear here after the first evaluation completes.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No standards run is selected."
            description="Start or select a standards evaluation from the workspace to inspect diffs and follow-up items."
          />
        </CardContent>
      </Card>
    );
  }

  const updateAssets = run.assets.filter((asset) => STANDARDS_UPDATE_ACTIONS.has(asset.action));
  const advisoryAssets = run.assets.filter((asset) => asset.action === "advisory-drift" || asset.action === "deferred");
  const conflictAssets = run.assets.filter((asset) => asset.action === "conflict");
  const passiveAssetCount = run.assets.length - updateAssets.length - advisoryAssets.length - conflictAssets.length;

  return (
    <Card className="shadow-none">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-foreground">Standards run detail</CardTitle>
          <Badge className="border-border bg-secondary text-secondary-foreground">
            {formatStandardsOutcomeKind(run.outcome_kind)}
          </Badge>
          <Badge className={statusTone(run.outcome_status)}>{humanize(run.outcome_status)}</Badge>
        </div>
        <CardDescription className="text-muted-foreground">
          Selected standards evaluation with asset-level drift, follow-up items, and operator review context.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Managed Updates</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{countStandardsRunUpdates(run)}</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Advisory Drift</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{countStandardsRunAdvisories(run)}</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Conflicts</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{countStandardsRunConflicts(run)}</p>
          </div>
          <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Follow-up Items</p>
            <p className="pt-1 text-2xl font-semibold text-foreground">{run.follow_up_items.length}</p>
          </div>
        </div>

        <div className="rounded-3xl border border-border/70 bg-muted/30 px-4 py-1">
          <InfoLine label="Source bundle" value={run.source_bundle} />
          <InfoLine label="Pack version" value={`${baseline.standards_pack_key ?? "Unknown"} ${run.source_version}`} />
          <InfoLine label="Channel" value={baseline.baseline_channel ?? "Unknown"} />
          <InfoLine label="Generated PR" value={run.generated_pr_number ? `#${run.generated_pr_number}` : "Not linked"} />
          <InfoLine label="Created" value={formatDateTime(run.created_at)} />
          <InfoLine label="Updated" value={formatRelativeTime(run.updated_at)} />
        </div>

        {(run.pr_title || run.pr_body) ? (
          <div className="space-y-2 rounded-3xl border border-border/70 bg-muted/30 p-4">
            <p className="font-medium text-foreground">Suggested PR context</p>
            <p className="text-sm text-muted-foreground">{run.pr_title ?? "No PR title recorded."}</p>
            {run.pr_body ? (
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border/70 bg-background px-4 py-4 text-xs text-muted-foreground">
                {run.pr_body}
              </pre>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
          <div>
            <p className="font-medium text-foreground">Follow-up review</p>
            <p className="pt-1 text-sm text-muted-foreground">
              Conflicts and operator follow-up items stay separate from blocking setup diagnostics.
            </p>
          </div>
          {run.follow_up_items.length ? (
            run.follow_up_items.map((item) => (
              <div key={item.standards_follow_up_item_id} className="rounded-2xl border border-border/70 bg-background px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-foreground">{item.title}</p>
                  <Badge className={statusTone(item.status)}>{humanize(item.status)}</Badge>
                </div>
                <p className="pt-2 text-sm text-muted-foreground">{item.detail}</p>
                <p className="pt-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">{item.path}</p>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">No follow-up items were generated for this standards run.</p>
          )}
        </div>

        {[
          {
            title: "Managed updates",
            description: "Assets that would create files, refresh managed sections, or update fully managed content.",
            assets: updateAssets,
          },
          {
            title: "Advisory drift",
            description: "Divergence that remains visible to operators without being treated as blocking setup.",
            assets: advisoryAssets,
          },
          {
            title: "Conflicts",
            description: "Assets that could not be reconciled cleanly and require operator follow-up.",
            assets: conflictAssets,
          },
        ]
          .filter((section) => section.assets.length)
          .map((section) => (
            <div key={section.title} className="space-y-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
              <div>
                <p className="font-medium text-foreground">{section.title}</p>
                <p className="pt-1 text-sm text-muted-foreground">{section.description}</p>
              </div>
              {section.assets.map((asset) => (
                <StandardsRunAssetCard key={asset.standards_upgrade_asset_id} asset={asset} />
              ))}
            </div>
          ))}

        {passiveAssetCount ? (
          <p className="text-sm text-muted-foreground">
            {passiveAssetCount} additional {pluralize(passiveAssetCount, "asset")} were already current or local-only in this run.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function InfoLine({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/60 py-3 text-sm last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right text-foreground">{value}</span>
    </div>
  );
}

function diagnosticTone(classification: string | null | undefined) {
  const normalized = classification?.toLowerCase() ?? "";
  if (normalized.includes("blocking")) {
    return "border-rose-500/30 bg-rose-500/12 text-rose-700 dark:text-rose-300";
  }
  if (normalized.includes("advisory") || normalized.includes("recoverable")) {
    return "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300";
  }
  return "border-border bg-secondary text-secondary-foreground";
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
}

function normalizeSecretKeys(keys: string[]) {
  return normalizeOnboardingSecretKeys(keys);
}

function resolveSeedOrgLabel(orgId: string, organizations: OrganizationResponse[]) {
  return organizations.find((org) => org.org_id === orgId)?.name ?? displayOrgLabel(orgId);
}

function resolveDefaultSeedGithubOwner(
  orgId: string,
  organizations: OrganizationResponse[],
  products: ProductSummaryResponse[],
) {
  const matchingProduct = products.find((product) => product.org_id === orgId && product.primary_repo?.owner);
  if (matchingProduct?.primary_repo?.owner) {
    return matchingProduct.primary_repo.owner;
  }
  const matchingOrg = organizations.find((org) => org.org_id === orgId);
  if (matchingOrg?.slug) {
    return matchingOrg.slug;
  }
  return products.find((product) => product.primary_repo?.owner)?.primary_repo?.owner ?? "";
}

function shouldRefreshDefaultGithubOwner(
  owner: string,
  orgId: string,
  organizations: OrganizationResponse[],
) {
  const normalizedOwner = owner.trim();
  const orgSlug = organizations.find((org) => org.org_id === orgId)?.slug ?? "";
  return !normalizedOwner || normalizedOwner === orgSlug;
}

function resolveOrgOnboardingDefaultsRecord(
  orgId: string | null | undefined,
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg,
) {
  if (!orgId) {
    return createUnloadedProductOnboardingDefaultsRecord();
  }
  return onboardingDefaultsByOrg[orgId] ?? createUnloadedProductOnboardingDefaultsRecord();
}

function organizationExists(orgId: string | null | undefined, organizations: OrganizationResponse[]) {
  return Boolean(orgId) && organizations.some((org) => org.org_id === orgId);
}

function readLegacyGithubInstallationId(defaultsRecord: ProductOnboardingDefaultsRecord) {
  const githubValue = defaultsRecord.rawValue.github;
  if (!githubValue || typeof githubValue !== "object" || Array.isArray(githubValue)) {
    return null;
  }
  const installationId = (githubValue as Record<string, unknown>).installation_id;
  return typeof installationId === "string" && installationId.trim()
    ? installationId.trim()
    : null;
}

function resolveOnboardingBaselineDraftValues(channel: string) {
  const normalizedChannel = channel.trim() || "stable";
  if (normalizedChannel === "stable" || normalizedChannel === "candidate") {
    return {
      baselineMode: normalizedChannel as ProductSeedBaselineMode,
      customBaselineChannel: "",
    };
  }
  return {
    baselineMode: "custom" as ProductSeedBaselineMode,
    customBaselineChannel: normalizedChannel,
  };
}

function buildOnboardingStatusOptionsText(defaults: ProductOnboardingDefaults) {
  return Array.from(
    new Set(
      [defaults.github.readyStatus.trim(), "In Progress", defaults.github.doneStatus.trim()].filter(Boolean),
    ),
  ).join(", ");
}

function applySeedOnboardingDefaults(
  draft: ProductSeedDraft,
  defaultsRecord: ProductOnboardingDefaultsRecord,
) {
  const defaults = defaultsRecord.defaults;
  const baselineDefaults = resolveOnboardingBaselineDraftValues(defaults.baseline.channel);
  return {
    ...draft,
    statusField: defaults.github.statusField,
    readyStatus: defaults.github.readyStatus,
    doneStatus: defaults.github.doneStatus,
    baselineMode: baselineDefaults.baselineMode,
    customBaselineChannel: baselineDefaults.customBaselineChannel,
    executionProfile: defaults.execution.profile,
    requiredSecretKeys: normalizeSecretKeys(defaults.activation.requiredSecretKeys),
  } satisfies ProductSeedDraft;
}

function applyAdoptionOnboardingDefaults(
  draft: ProductAdoptionDraft,
  defaultsRecord: ProductOnboardingDefaultsRecord,
) {
  const defaults = defaultsRecord.defaults;
  const baselineDefaults = resolveOnboardingBaselineDraftValues(defaults.baseline.channel);
  return {
    ...draft,
    baselineMode: baselineDefaults.baselineMode,
    customBaselineChannel: baselineDefaults.customBaselineChannel,
    executionProfile: defaults.execution.profile,
    statusFieldName: defaults.github.statusField,
    statusOptionsText: buildOnboardingStatusOptionsText(defaults),
  } satisfies ProductAdoptionDraft;
}

function createProductSeedDraft({
  user,
  organizations,
  products,
  onboardingDefaultsByOrg,
  seedDraft,
}: {
  user: UserInfo;
  organizations: OrganizationResponse[];
  products: ProductSummaryResponse[];
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg;
  seedDraft?: ProductSeedDraft;
}) {
  if (seedDraft) {
    return {
      ...seedDraft,
      requiredSecretKeys: normalizeSecretKeys(seedDraft.requiredSecretKeys),
    };
  }
  const orgId = user.default_org_id ?? organizations[0]?.org_id ?? user.org_ids[0] ?? "";
  const defaultsRecord = resolveOrgOnboardingDefaultsRecord(orgId, onboardingDefaultsByOrg);
  const baselineDefaults = resolveOnboardingBaselineDraftValues(defaultsRecord.defaults.baseline.channel);
  return {
    orgId,
    productKey: "",
    productName: "",
    description: "",
    githubOwner: resolveDefaultSeedGithubOwner(orgId, organizations, products),
    githubRepo: "",
    githubVisibility: "private",
    githubDefaultBranch: "dev",
    projectMode: "create",
    githubProjectNodeId: "",
    githubProjectNumber: "",
    githubProjectTitle: "",
    statusField: defaultsRecord.defaults.github.statusField,
    readyStatus: defaultsRecord.defaults.github.readyStatus,
    doneStatus: defaultsRecord.defaults.github.doneStatus,
    baselineMode: baselineDefaults.baselineMode,
    customBaselineChannel: baselineDefaults.customBaselineChannel,
    standardsPack: "default",
    executionProfile: defaultsRecord.defaults.execution.profile,
    maxConcurrentLanes: "4",
    requiredSecretKeys: normalizeSecretKeys(defaultsRecord.defaults.activation.requiredSecretKeys),
  } satisfies ProductSeedDraft;
}

function applySeedNameDefaults(draft: ProductSeedDraft, productName: string) {
  const previousSlug = slugify(draft.productName);
  const nextSlug = slugify(productName);
  const nextProjectTitle =
    !draft.githubProjectTitle.trim() || draft.githubProjectTitle === draft.productName
      ? productName
      : draft.githubProjectTitle;
  return {
    ...draft,
    productName,
    productKey: !draft.productKey.trim() || draft.productKey === previousSlug ? nextSlug : draft.productKey,
    githubProjectTitle: nextProjectTitle,
  };
}

function productSeedDraftFromPayload(payload: ProductSeedRequestPayload): ProductSeedDraft {
  const baselineChannel = (payload.baseline_channel ?? "stable").trim() || "stable";
  const baselineMode: ProductSeedBaselineMode =
    baselineChannel === "stable" || baselineChannel === "candidate" ? baselineChannel : "custom";
  return {
    orgId: payload.org_id,
    productKey: payload.product_key,
    productName: payload.product_name,
    description: payload.description ?? "",
    githubOwner: payload.github_owner,
    githubRepo: payload.github_repo,
    githubVisibility: payload.github_visibility,
    githubDefaultBranch: payload.github_default_branch,
    projectMode: payload.github_project_node_id && payload.github_project_number ? "bind-existing" : "create",
    githubProjectNodeId: payload.github_project_node_id ?? "",
    githubProjectNumber: payload.github_project_number ? String(payload.github_project_number) : "",
    githubProjectTitle: payload.github_project_title ?? payload.product_name,
    statusField: payload.status_field,
    readyStatus: payload.ready_status,
    doneStatus: payload.done_status,
    baselineMode,
    customBaselineChannel: baselineMode === "custom" ? baselineChannel : "",
    standardsPack: payload.standards_pack ?? "default",
    executionProfile: payload.execution_profile ?? "standard-python",
    maxConcurrentLanes: payload.max_concurrent_lanes ? String(payload.max_concurrent_lanes) : "4",
    requiredSecretKeys: normalizeSecretKeys(payload.required_secret_keys),
  };
}

function normalizeSeedJobSummaryStrings(value: unknown) {
  return Array.isArray(value)
    ? value
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter(Boolean)
    : [];
}

function normalizeSeedJobProjectFields(value: unknown) {
  return Array.isArray(value)
    ? value.filter(
        (item): item is { name?: string } =>
          Boolean(item) && typeof item === "object" && !Array.isArray(item),
      )
    : [];
}

function resolveBaselineChannel(draft: ProductSeedDraft) {
  return draft.baselineMode === "custom" ? draft.customBaselineChannel.trim() : draft.baselineMode;
}

function matchesSeedWorkspaceRepo(
  repo: GitRepoResponse,
  draft: Pick<ProductSeedDraft, "githubOwner" | "githubRepo" | "githubVisibility" | "githubDefaultBranch">,
) {
  return (
    repo.github_owner.trim().toLowerCase() === draft.githubOwner.trim().toLowerCase() &&
    repo.github_repo.trim().toLowerCase() === draft.githubRepo.trim().toLowerCase() &&
    repo.visibility === draft.githubVisibility &&
    repo.default_branch.trim().toLowerCase() === draft.githubDefaultBranch.trim().toLowerCase()
  );
}

function findMatchingSeedWorkspaceRepo(
  repos: GitRepoResponse[] | undefined,
  draft: Pick<ProductSeedDraft, "githubOwner" | "githubRepo" | "githubVisibility" | "githubDefaultBranch">,
) {
  return repos?.find((repo) => matchesSeedWorkspaceRepo(repo, draft)) ?? null;
}

function buildProductSeedPayload(
  draft: ProductSeedDraft,
  dryRun: boolean,
  options: {
    legacyInstallationId?: string | null;
  } = {},
): ProductSeedRequestPayload {
  const projectTitle = (draft.githubProjectTitle.trim() || draft.productName.trim()) || null;
  const projectNumber = Number(draft.githubProjectNumber);
  const maxConcurrentLanes = Number(draft.maxConcurrentLanes);
  return {
    org_id: draft.orgId,
    installation_id: options.legacyInstallationId?.trim() || null,
    product_key: draft.productKey.trim(),
    product_name: draft.productName.trim(),
    description: draft.description.trim() || null,
    github_owner: draft.githubOwner.trim(),
    github_repo: draft.githubRepo.trim(),
    github_visibility: draft.githubVisibility,
    github_default_branch: draft.githubDefaultBranch.trim(),
    github_project_node_id:
      draft.projectMode === "bind-existing" ? draft.githubProjectNodeId.trim() || null : null,
    github_project_number:
      draft.projectMode === "bind-existing" && Number.isInteger(projectNumber) ? projectNumber : null,
    github_project_title: draft.projectMode === "create" ? projectTitle : null,
    status_field: draft.statusField.trim(),
    ready_status: draft.readyStatus.trim(),
    done_status: draft.doneStatus.trim(),
    baseline_channel: resolveBaselineChannel(draft) || null,
    standards_pack: draft.standardsPack.trim() || null,
    execution_profile: draft.executionProfile.trim() || null,
    max_concurrent_lanes:
      draft.maxConcurrentLanes.trim() && Number.isInteger(maxConcurrentLanes) ? maxConcurrentLanes : null,
    required_secret_keys: normalizeSecretKeys(draft.requiredSecretKeys),
    dry_run: dryRun,
  };
}

function buildProductSeedValidation(
  draft: ProductSeedDraft,
  secrets: SecretResponse[],
  options: {
    secretInventoryAvailable: boolean;
    repoInventory?: GitRepoResponse[];
    repoInventoryLoaded?: boolean;
    repoInventoryFailed?: boolean;
  },
): ProductSeedValidation {
  const previewErrors: string[] = [];
  const liveErrors: string[] = [];
  const previewFieldErrors: ProductSeedFieldErrors = {};
  const liveFieldErrors: ProductSeedFieldErrors = {};
  const missingSecretKeys: string[] = [];

  function addError(
    scope: "preview" | "live" | "both",
    field: keyof ProductSeedFieldErrors | null,
    message: string,
  ) {
    if (scope === "preview" || scope === "both") {
      previewErrors.push(message);
      if (field && !previewFieldErrors[field]) {
        previewFieldErrors[field] = message;
      }
    }
    if (scope === "live" || scope === "both") {
      liveErrors.push(message);
      if (field && !liveFieldErrors[field]) {
        liveFieldErrors[field] = message;
      }
    }
  }

  const productKey = draft.productKey.trim();
  const productName = draft.productName.trim();
  const githubOwner = draft.githubOwner.trim();
  const githubRepo = draft.githubRepo.trim();
  const githubDefaultBranch = draft.githubDefaultBranch.trim();
  const repoInventory = options.repoInventory ?? [];
  const useRepoInventoryValidation =
    options.repoInventory !== undefined ||
    options.repoInventoryLoaded !== undefined ||
    options.repoInventoryFailed !== undefined;
  const selectedRepo = findMatchingSeedWorkspaceRepo(repoInventory, draft);
  const statusField = draft.statusField.trim();
  const readyStatus = draft.readyStatus.trim();
  const doneStatus = draft.doneStatus.trim();
  const baselineChannel = resolveBaselineChannel(draft);
  const standardsPack = draft.standardsPack.trim();
  const executionProfile = draft.executionProfile.trim();
  const maxConcurrentLanes = draft.maxConcurrentLanes.trim();
  const requiredSecretKeys = normalizeSecretKeys(draft.requiredSecretKeys);

  if (!draft.orgId.trim()) {
    addError("both", "orgId", "Choose the owning organization before continuing.");
  }
  if (!productName) {
    addError("both", "productName", "Provide the product name that should appear in the control plane.");
  }
  if (!productKey) {
    addError("both", "productKey", "Provide a stable product key before previewing the baseline.");
  } else if (/\s/.test(productKey)) {
    addError("both", "productKey", "Product key cannot contain spaces.");
  }
  if (useRepoInventoryValidation) {
    if (options.repoInventoryFailed) {
      addError(
        "both",
        "githubRepoProfile",
        "Connected Git repository settings could not be loaded. Reload the page or review Settings > Git Repositories.",
      );
    } else if (!options.repoInventoryLoaded) {
      addError("both", "githubRepoProfile", "Connected Git repository settings are still loading.");
    } else if (repoInventory.length === 0) {
      addError(
        "both",
        "githubRepoProfile",
        "Connect a Git repository in Settings > Git Repositories before seeding a product.",
      );
    } else if (!selectedRepo) {
      addError("both", "githubRepoProfile", "Choose a connected Git repository profile before continuing.");
    }
  }

  if (!useRepoInventoryValidation || selectedRepo) {
    if (!githubOwner) {
      addError("both", "githubOwner", "Choose the GitHub owner that will receive the new repository.");
    } else if (/\s/.test(githubOwner)) {
      addError("both", "githubOwner", "GitHub owner cannot contain spaces.");
    }
    if (!githubRepo) {
      addError("both", "githubRepo", "Provide the GitHub repository name that Orcha should create.");
    } else if (/\s/.test(githubRepo)) {
      addError("both", "githubRepo", "GitHub repository name cannot contain spaces.");
    }
    if (!githubDefaultBranch) {
      addError("both", "githubDefaultBranch", "Choose the protected default branch for the seeded repo.");
    } else if (/\s/.test(githubDefaultBranch)) {
      addError("both", "githubDefaultBranch", "Default branch cannot contain spaces.");
    }
  }
  if (draft.projectMode === "create") {
    if (!(draft.githubProjectTitle.trim() || productName)) {
      addError("both", "githubProjectTitle", "Name the primary GitHub Project that will be created.");
    }
  } else {
    if (!draft.githubProjectNodeId.trim()) {
      addError("both", "githubProjectNodeId", "Existing project binding requires the GitHub Project node id.");
    }
    const projectNumber = Number(draft.githubProjectNumber);
    if (!draft.githubProjectNumber.trim() || !Number.isInteger(projectNumber) || projectNumber < 1) {
      addError("both", "githubProjectNumber", "Existing project binding requires a valid project number.");
    }
  }
  if (!statusField) {
    addError("both", "statusField", "Provide the status field name used by the primary project.");
  }
  if (!readyStatus) {
    addError("both", "readyStatus", "Provide the ready status option that new work starts in.");
  }
  if (!doneStatus) {
    addError("both", "doneStatus", "Provide the done status option used for completed work.");
  }
  if (!baselineChannel) {
    addError("both", "baselineChannel", "Choose the baseline channel that should seed the repo.");
  } else if (/\s/.test(baselineChannel)) {
    addError("both", "baselineChannel", "Baseline channel cannot contain spaces.");
  }
  if (!standardsPack) {
    addError("both", "standardsPack", "Choose the standards pack that should be declared in product.yaml.");
  }
  if (!executionProfile) {
    addError("both", "executionProfile", "Choose an execution profile before continuing.");
  } else if (executionProfile !== "standard-python") {
    addError("both", "executionProfile", "Only the standard-python execution profile is supported today.");
  }
  if (maxConcurrentLanes) {
    const parsedMax = Number(maxConcurrentLanes);
    if (!Number.isInteger(parsedMax) || parsedMax < 1 || parsedMax > 6) {
      addError("both", "maxConcurrentLanes", "Max concurrent lanes must be an integer between 1 and 6.");
    }
  }

  if (requiredSecretKeys.length) {
    if (!options.secretInventoryAvailable) {
      addError(
        "live",
        "requiredSecretKeys",
        "Secret inventory is unavailable, so live seeding cannot validate the required secret inputs yet.",
      );
    } else {
      const secretLookup = new Map(secrets.map((secret) => [secret.key, secret]));
      for (const secretKey of requiredSecretKeys) {
        const secret = secretLookup.get(secretKey);
        if (!secret?.has_value) {
          missingSecretKeys.push(secretKey);
        }
      }
      if (missingSecretKeys.length) {
        addError(
          "live",
          "requiredSecretKeys",
          missingSecretKeys.length === 1
            ? `Required secret is missing or has no value: ${missingSecretKeys[0]}.`
            : `Required secrets are missing or have no value: ${missingSecretKeys.join(", ")}.`,
        );
      }
    }
  }

  return {
    previewErrors,
    liveErrors,
    previewFieldErrors,
    liveFieldErrors,
    missingSecretKeys,
  };
}

function buildAuditDetailsSummary(details: Record<string, unknown>) {
  return Object.entries(details)
    .flatMap(([key, value]) => {
      if (value == null || value === "") {
        return [];
      }
      if (Array.isArray(value)) {
        return value.length ? `${humanize(key)}: ${value.join(", ")}` : [];
      }
      if (typeof value === "object") {
        const count = Object.keys(value as Record<string, unknown>).length;
        return count ? `${humanize(key)}: ${count} fields` : [];
      }
      return `${humanize(key)}: ${String(value)}`;
    })
    .slice(0, 3)
    .join(" • ");
}

function normalizeSeedSubmissionErrorMessage(message: string) {
  if (message.includes("installation_id is required unless dry_run is true")) {
    return "The API process is still enforcing the deprecated GitHub App installation requirement. Restart or redeploy the API on the current commit, or temporarily restore a legacy installation id in Settings > Workspace.";
  }
  if (message.includes("Organization not found:")) {
    return "This seed request references an organization that no longer exists in the current local environment. Open Edit seed request, choose an active org, and create a new dry-run preview before promoting it to live.";
  }
  return message;
}

function createProductAdoptionDraft({
  user,
  organizations,
  products,
  onboardingDefaultsByOrg,
  adoptionDraft,
}: {
  user: UserInfo;
  organizations: OrganizationResponse[];
  products: ProductSummaryResponse[];
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg;
  adoptionDraft?: ProductAdoptionDraft;
}) {
  if (adoptionDraft) {
    return {
      ...adoptionDraft,
      branchProtectionApprovals: adoptionDraft.branchProtectionApprovals || "1",
      statusOptionsText: adoptionDraft.statusOptionsText || "Todo, In Progress, Done",
    };
  }
  const orgId = user.default_org_id ?? organizations[0]?.org_id ?? user.org_ids[0] ?? "";
  const defaultsRecord = resolveOrgOnboardingDefaultsRecord(orgId, onboardingDefaultsByOrg);
  const baselineDefaults = resolveOnboardingBaselineDraftValues(defaultsRecord.defaults.baseline.channel);
  return {
    orgId,
    key: "",
    name: "",
    description: "",
    repoRoot: REFRESH_REPO_ROOT_HINT,
    baselineMode: baselineDefaults.baselineMode,
    customBaselineChannel: baselineDefaults.customBaselineChannel,
    agentCoreVersion: "0.1.0",
    executionProfile: defaultsRecord.defaults.execution.profile,
    githubRepositoryNodeId: "",
    repositoryOwner: resolveDefaultSeedGithubOwner(orgId, organizations, products),
    repositoryName: "",
    repositoryDefaultBranch: "dev",
    repositoryVisibility: "private",
    repositoryDescription: "",
    repositoryArchived: false,
    branchProtectionEnabled: true,
    branchProtectionRequiresPullRequest: true,
    branchProtectionApprovals: "1",
    branchProtectionAllowsForcePushes: false,
    branchProtectionAllowsDeletions: false,
    projectNodeId: "",
    projectNumber: "1",
    projectTitle: "",
    statusFieldName: defaultsRecord.defaults.github.statusField,
    statusOptionsText: buildOnboardingStatusOptionsText(defaultsRecord.defaults),
    contentsPermission: "write",
    pullRequestsPermission: "write",
    issuesPermission: "write",
    projectsPermission: "write",
  } satisfies ProductAdoptionDraft;
}

function applyAdoptionRepositoryNameDefaults(draft: ProductAdoptionDraft, repositoryName: string) {
  const previousSlug = slugify(draft.repositoryName);
  const nextSlug = slugify(repositoryName);
  const nextNameCandidate = humanize(repositoryName);
  return {
    ...draft,
    repositoryName,
    key: !draft.key.trim() || draft.key === previousSlug ? nextSlug : draft.key,
    name:
      !draft.name.trim() || draft.name === humanize(draft.repositoryName)
        ? nextNameCandidate
        : draft.name,
    projectTitle:
      !draft.projectTitle.trim() ||
      draft.projectTitle === draft.name ||
      draft.projectTitle === humanize(draft.repositoryName)
        ? nextNameCandidate
        : draft.projectTitle,
  };
}

function applyAdoptionProductNameDefaults(draft: ProductAdoptionDraft, name: string) {
  const previousSlug = slugify(draft.name);
  const nextSlug = slugify(name);
  return {
    ...draft,
    name,
    key: !draft.key.trim() || draft.key === previousSlug ? nextSlug : draft.key,
    projectTitle:
      !draft.projectTitle.trim() || draft.projectTitle === draft.name ? name : draft.projectTitle,
  };
}

function parseStatusOptions(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function resolveAdoptionBaselineChannel(draft: ProductAdoptionDraft) {
  return draft.baselineMode === "custom" ? draft.customBaselineChannel.trim() : draft.baselineMode;
}

function buildProductAdoptionPayload(draft: ProductAdoptionDraft): ProductAdoptionRequestPayload {
  const approvals = Number(draft.branchProtectionApprovals);
  const projectNumber = Number(draft.projectNumber);
  return {
    org_id: draft.orgId,
    key: draft.key.trim(),
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    repo_root: draft.repoRoot.trim(),
    baseline_channel: resolveAdoptionBaselineChannel(draft) || "stable",
    agent_core_version: draft.agentCoreVersion.trim(),
    execution_profile: draft.executionProfile.trim(),
    repository: {
      github_repository_node_id: draft.githubRepositoryNodeId.trim() || null,
      owner: draft.repositoryOwner.trim(),
      name: draft.repositoryName.trim(),
      default_branch: draft.repositoryDefaultBranch.trim(),
      visibility: draft.repositoryVisibility,
      description: draft.repositoryDescription.trim() || null,
      is_archived: draft.repositoryArchived,
      branch_protection: {
        enabled: draft.branchProtectionEnabled,
        requires_pull_request: draft.branchProtectionRequiresPullRequest,
        required_approving_review_count: Number.isInteger(approvals) ? approvals : 0,
        allows_force_pushes: draft.branchProtectionAllowsForcePushes,
        allows_deletions: draft.branchProtectionAllowsDeletions,
      },
      permissions: {
        contents: draft.contentsPermission,
        pull_requests: draft.pullRequestsPermission,
        issues: draft.issuesPermission,
        projects: draft.projectsPermission,
      },
    },
    project: {
      github_project_node_id: draft.projectNodeId.trim() || null,
      number: Number.isInteger(projectNumber) ? projectNumber : 1,
      title: draft.projectTitle.trim(),
      status_field_name: draft.statusFieldName.trim(),
      status_options: parseStatusOptions(draft.statusOptionsText),
    },
    operator_overrides: {},
  };
}

function buildProductAdoptionValidation(
  draft: ProductAdoptionDraft,
  products: ProductSummaryResponse[],
): ProductAdoptionValidation {
  const previewErrors: string[] = [];
  const previewFieldErrors: ProductAdoptionFieldErrors = {};

  function addError(field: keyof ProductAdoptionFieldErrors | null, message: string) {
    previewErrors.push(message);
    if (field && !previewFieldErrors[field]) {
      previewFieldErrors[field] = message;
    }
  }

  const key = draft.key.trim();
  const name = draft.name.trim();
  const repoRoot = draft.repoRoot.trim();
  const baselineChannel = resolveAdoptionBaselineChannel(draft);
  const agentCoreVersion = draft.agentCoreVersion.trim();
  const executionProfile = draft.executionProfile.trim();
  const repositoryOwner = draft.repositoryOwner.trim();
  const repositoryName = draft.repositoryName.trim();
  const repositoryDefaultBranch = draft.repositoryDefaultBranch.trim();
  const projectNumber = Number(draft.projectNumber);
  const projectTitle = draft.projectTitle.trim();
  const statusFieldName = draft.statusFieldName.trim();
  const statusOptions = parseStatusOptions(draft.statusOptionsText);

  if (!draft.orgId.trim()) {
    addError("orgId", "Choose the owning organization before running adoption preview.");
  }
  if (!key) {
    addError("key", "Provide the product key that Orcha should register for this repository.");
  } else if (/\s/.test(key)) {
    addError("key", "Product key cannot contain spaces.");
  } else if (products.some((product) => product.org_id === draft.orgId && product.key === key)) {
    addError("key", "A product with this key is already registered in the selected organization.");
  }
  if (!name) {
    addError("name", "Provide the product name that should appear in the operator surfaces.");
  }
  if (!repoRoot) {
    addError("repoRoot", "Provide the local repository root that Orcha should validate.");
  }
  if (!baselineChannel) {
    addError("baselineChannel", "Choose the baseline channel that should be associated with the adopted repo.");
  } else if (/\s/.test(baselineChannel)) {
    addError("baselineChannel", "Baseline channel cannot contain spaces.");
  }
  if (!agentCoreVersion) {
    addError("agentCoreVersion", "Provide the agent-core version that should be recorded for this adoption.");
  }
  if (!executionProfile) {
    addError("executionProfile", "Choose an execution profile before continuing.");
  } else if (executionProfile !== "standard-python") {
    addError("executionProfile", "Only the standard-python execution profile is supported today.");
  }
  if (!repositoryOwner) {
    addError("repositoryOwner", "Provide the GitHub owner for the repository being adopted.");
  } else if (/\s/.test(repositoryOwner)) {
    addError("repositoryOwner", "GitHub owner cannot contain spaces.");
  }
  if (!repositoryName) {
    addError("repositoryName", "Provide the GitHub repository name being adopted.");
  } else if (/\s/.test(repositoryName)) {
    addError("repositoryName", "GitHub repository name cannot contain spaces.");
  } else if (
    products.some(
      (product) =>
        product.primary_repo?.owner === repositoryOwner && product.primary_repo?.name === repositoryName,
    )
  ) {
    addError("repositoryName", "This repository is already bound to an existing product.");
  }
  if (!repositoryDefaultBranch) {
    addError("repositoryDefaultBranch", "Provide the repository default branch snapshot for adoption.");
  } else if (/\s/.test(repositoryDefaultBranch)) {
    addError("repositoryDefaultBranch", "Default branch cannot contain spaces.");
  }
  if (!draft.projectNumber.trim() || !Number.isInteger(projectNumber) || projectNumber < 1) {
    addError("projectNumber", "Provide a valid primary project number.");
  }
  if (!projectTitle) {
    addError("projectTitle", "Provide the primary project title that should be mirrored.");
  }
  if (!statusFieldName) {
    addError("statusFieldName", "Provide the project status field name for the adoption snapshot.");
  }
  if (!statusOptions.length) {
    addError("statusOptions", "Provide at least one project status option for the adoption snapshot.");
  }

  return {
    previewErrors,
    previewFieldErrors,
  };
}

function computeDiagnosticBuckets(diagnostics: SetupDiagnostic[]) {
  return diagnostics.reduce(
    (buckets, item) => {
      const classification = item.classification.toLowerCase();
      if (classification.includes("blocking")) {
        buckets.blocking.push(item);
      } else if (classification.includes("recoverable") || classification.includes("drift")) {
        buckets.drift.push(item);
      } else if (classification.includes("advisory")) {
        buckets.advisory.push(item);
      } else {
        buckets.other.push(item);
      }
      return buckets;
    },
    {
      blocking: [] as SetupDiagnostic[],
      drift: [] as SetupDiagnostic[],
      advisory: [] as SetupDiagnostic[],
      other: [] as SetupDiagnostic[],
    },
  );
}

function computeManagedAssetCounts(managedAssets: ManagedAssetRecord[]) {
  return managedAssets.reduce<Record<string, number>>((counts, asset) => {
    const key = asset.drift_status ?? "unknown";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

function countManagedAssetFollowUp(managedAssets: ManagedAssetRecord[]) {
  return managedAssets.filter((asset) => asset.drift_status && asset.drift_status !== "current").length;
}

function resolveReadinessTone(status: ActivationReadinessStatus) {
  switch (status) {
    case "blocking":
      return "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300";
    case "follow-up":
      return "border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    default:
      return "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
}

function buildActivationReadinessItems({
  setupState,
  diagnostics,
  managedAssets,
  lastConfigRefreshAt,
}: {
  setupState: string;
  diagnostics: SetupDiagnostic[];
  managedAssets: ManagedAssetRecord[];
  lastConfigRefreshAt?: string | null;
}) {
  const diagnosticBuckets = computeDiagnosticBuckets(diagnostics);
  const managedAssetFollowUp = countManagedAssetFollowUp(managedAssets);
  const advisoryCount = diagnosticBuckets.advisory.length + diagnosticBuckets.other.length;
  const blockingCount = diagnosticBuckets.blocking.length;

  return [
    {
      key: "blocking",
      label: "Blocking setup errors",
      description:
        setupState === "setup-needed" || blockingCount
          ? `${blockingCount || 1} ${pluralize(blockingCount || 1, "blocking diagnostic")} still keep lane work paused.`
          : "No blocking setup errors are preventing activation.",
      status: setupState === "setup-needed" || blockingCount ? "blocking" : "ready",
    },
    {
      key: "managed-assets",
      label: "Managed asset drift",
      description: managedAssetFollowUp
        ? `${managedAssetFollowUp} ${pluralize(managedAssetFollowUp, "managed asset")} still need follow-up. This remains separate from activation blockers.`
        : "Managed asset posture is current.",
      status: managedAssetFollowUp ? "follow-up" : "ready",
    },
    {
      key: "advisory",
      label: "Advisory findings",
      description: advisoryCount
        ? `${advisoryCount} ${pluralize(advisoryCount, "advisory finding")} remain visible, but they are not hard activation blockers.`
        : "No advisory findings are pending review.",
      status: advisoryCount ? "follow-up" : "ready",
    },
    {
      key: "refresh",
      label: "Latest contract refresh",
      description: lastConfigRefreshAt
        ? `Last refreshed ${formatRelativeTime(lastConfigRefreshAt)}. Rerun refresh after remediation to confirm the latest setup state.`
        : "No refresh has been recorded yet. Run contract refresh after remediation to confirm setup state.",
      status: lastConfigRefreshAt ? "ready" : "follow-up",
    },
  ] satisfies ActivationReadinessItem[];
}

function collectGuidedRemediationActions({
  productId,
  diagnostics,
  managedAssets,
  onboardingActivity,
  includeProductLink = false,
  includeBaselineLink = false,
}: {
  productId: string;
  diagnostics: SetupDiagnostic[];
  managedAssets: ManagedAssetRecord[];
  onboardingActivity: ProductOnboardingActivity | null;
  includeProductLink?: boolean;
  includeBaselineLink?: boolean;
}) {
  const actions: GuidedRemediationAction[] = [];
  const diagnosticCodes = diagnostics.map((item) => item.code.toLowerCase());
  const hasSecretFinding = diagnosticCodes.some((code) => code.startsWith("secret."));
  const hasSettingsFinding = diagnosticCodes.some((code) => code.startsWith("settings."));
  const hasBaselineFollowUp =
    diagnosticCodes.some((code) => code.startsWith("asset.")) || managedAssets.some((asset) => asset.drift_status && asset.drift_status !== "current");

  function addAction(action: GuidedRemediationAction) {
    if (!actions.some((item) => item.key === action.key)) {
      actions.push(action);
    }
  }

  if (includeProductLink) {
    addAction({
      key: "product",
      label: "Open product blockers",
      description: "Use the product surface to review setup state, baseline posture, and the latest refresh outcome together.",
      to: `/products/${productId}`,
      variant: "primary",
    });
  }

  if (hasSecretFinding) {
    addAction({
      key: "secrets",
      label: "Open secrets",
      description: "Provide or rotate required secret values before running another contract refresh.",
      to: "/settings/secrets",
      variant: includeProductLink ? "outline" : "primary",
    });
  }

  if (hasSettingsFinding) {
    addAction({
      key: "settings",
      label: "Review workspace defaults",
      description: "Resolve invalid or missing onboarding defaults before running another contract refresh.",
      to: "/settings/workspace",
      variant: "outline",
    });
  }

  if (includeBaselineLink && hasBaselineFollowUp) {
    addAction({
      key: "baselines",
      label: "Review baselines",
      description: "Inspect managed asset drift separately from activation blockers and confirm what is still out of policy.",
      to: `/baselines/${productId}`,
      variant: "outline",
    });
  }

  if (onboardingActivity) {
    addAction({
      key: "onboarding",
      label: onboardingActivity.kind === "seed" ? "Reopen seed result" : "Reopen adoption result",
      description:
        onboardingActivity.kind === "seed"
          ? "Return to the durable seed result to inspect rendered files, audit detail, and setup snapshots."
          : "Return to the persisted adoption result to inspect the repo and project snapshots used during onboarding.",
      to: onboardingActivity.target,
      variant: "outline",
    });
  }

  if (!actions.length) {
    addAction({
      key: "settings-fallback",
      label: includeProductLink ? "Open settings" : "Open product",
      description: includeProductLink
        ? "Review shared settings or secrets before rerunning contract validation."
        : "Open the product surface before rerunning contract validation.",
      to: includeProductLink ? "/settings/workspace" : `/products/${productId}`,
      variant: includeProductLink ? "outline" : "primary",
    });
  }

  return actions;
}

function WorkspaceDefaultsCard({
  defaultsRecord,
  title = "Workspace defaults",
  description,
  actionLabel = "Review workspace defaults",
}: {
  defaultsRecord: ProductOnboardingDefaultsRecord;
  title?: string;
  description: string;
  actionLabel?: string;
}) {
  const defaults = defaultsRecord.defaults;
  const baselineSummary = defaults.baseline.channel.trim() || "stable";
  const requiredSecretSummary = defaults.activation.requiredSecretKeys.length
    ? defaults.activation.requiredSecretKeys.join(", ")
    : "No additional org-level secret requirements";
  const auditActor = defaultsRecord.setting?.updated_by ?? defaultsRecord.setting?.created_by ?? "Not recorded";
  const auditTimestamp = defaultsRecord.setting?.updated_at ?? defaultsRecord.setting?.created_at ?? null;

  return (
    <Card className="shadow-none">
      <CardHeader>
        <CardTitle className="text-foreground">{title}</CardTitle>
        <CardDescription className="text-muted-foreground">{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <InfoLine label="GitHub auth source" value="Settings > Git Repositories" />
        <InfoLine
          label="Project field mapping"
          value={`${defaults.github.statusField} • ${buildOnboardingStatusOptionsText(defaults)}`}
        />
        <InfoLine
          label="Baseline and execution"
          value={`${baselineSummary} • ${defaults.execution.profile}`}
        />
        <InfoLine label="Required secrets" value={requiredSecretSummary} />
        <InfoLine label="Last updated by" value={auditActor} />
        <InfoLine label="Last updated at" value={formatDateTime(auditTimestamp)} />
        {defaultsRecord.error ? (
          <p className="pt-3 text-sm text-amber-700 dark:text-amber-300">{defaultsRecord.error}</p>
        ) : null}
        <p className="pt-3 text-sm text-muted-foreground">
          Workspace defaults keep project, baseline, execution, and secret policy aligned. PAT-backed
          GitHub access stays in Settings &gt; Git Repositories.
        </p>
        <div className="pt-3">
          <Link to="/settings/workspace" className={buttonLinkClassName("outline")}>
            {actionLabel}
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function SeedField({
  label,
  htmlFor,
  hint,
  error,
  required = false,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <FormField
      label={label}
      htmlFor={htmlFor}
      description={hint}
      error={error}
      required={required}
    >
      {children}
    </FormField>
  );
}

function SeedReadinessBlock({
  title,
  description,
  errors,
  readyMessage,
}: {
  title: string;
  description: string;
  errors: string[];
  readyMessage: string;
}) {
  return (
    <div
      className={`rounded-3xl border p-4 ${
        errors.length
          ? "border-amber-400/25 bg-amber-500/10"
          : "border-emerald-400/25 bg-emerald-500/10"
      }`}
    >
      <p className="font-medium text-foreground">{title}</p>
      <p className="pt-1 text-sm text-muted-foreground">{description}</p>
      {errors.length ? (
        <ul className="list-disc space-y-2 pl-5 pt-3 text-sm text-amber-700 dark:text-amber-300">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : (
        <p className="pt-3 text-sm text-emerald-700 dark:text-emerald-300">{readyMessage}</p>
      )}
    </div>
  );
}

const HeaderIconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string }
>(({ label, className, children, type = "button", ...props }, ref) => {
  return (
    <button
      ref={ref}
      type={type}
      className={[
        "rounded-md p-2 text-zinc-600 transition-colors hover:bg-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:ring-offset-2 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:focus:ring-zinc-100",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  );
});

HeaderIconButton.displayName = "HeaderIconButton";

function SettingsSidebar() {
  const items = [
    { to: "/settings/orgs", label: "Organizations", icon: Building2 },
    { to: "/settings/access", label: "Roles & Permissions", icon: Shield },
    { to: "/settings/workspace", label: "Workspace", icon: Wrench },
  ];

  return (
    <aside className="w-full shrink-0 border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900 lg:w-64 lg:border-r lg:border-b-0">
      <div className="border-b border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Settings
        </h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          System Configuration
        </p>
      </div>
      <nav className="space-y-1 p-4">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                [
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100",
                ].join(" ")
              }
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}

function ShellScaffold({
  user,
  organizations,
  accountLabel,
  loading,
  authConfigured,
  onLogin,
  onLogout,
  children,
}: {
  user: UserInfo;
  organizations: OrganizationResponse[];
  accountLabel: string | null;
  loading: boolean;
  authConfigured: boolean;
  onLogin: () => Promise<void>;
  onLogout: () => Promise<void>;
  children: ReactNode;
}) {
  const location = useLocation();
  const { preference, resolvedDark, setPreference } = useTheme();
  const isSettings = location.pathname.startsWith("/settings");
  const orgOptions = organizations.length
    ? organizations
        .filter((org) => user.org_ids.includes(org.org_id) || org.org_id === user.default_org_id)
        .map((org) => ({ org_id: org.org_id, label: org.name }))
    : Array.from(
        new Set([user.default_org_id, ...user.org_ids].filter((value): value is string => Boolean(value))),
      ).map((orgId) => ({ org_id: orgId, label: displayOrgLabel(orgId) }));
  const preferredOrgId = user.default_org_id ?? orgOptions[0]?.org_id ?? "standard";
  const [selectedOrgId, setSelectedOrgId] = useState(() => {
    if (typeof window === "undefined") {
      return preferredOrgId;
    }
    return window.localStorage.getItem(SELECTED_ORG_STORAGE_KEY) ?? preferredOrgId;
  });
  const selectedOrgLabel =
    orgOptions.find((org) => org.org_id === selectedOrgId)?.label ?? displayOrgLabel(selectedOrgId);

  useEffect(() => {
    setSelectedOrgId((current) => {
      const nextOrgId = orgOptions.some((org) => org.org_id === current) ? current : preferredOrgId;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(SELECTED_ORG_STORAGE_KEY, nextOrgId);
      }
      return nextOrgId;
    });
  }, [preferredOrgId, orgOptions.map((org) => org.org_id).join("|")]);

  useEffect(() => {
    if (typeof window !== "undefined" && selectedOrgId) {
      window.localStorage.setItem(SELECTED_ORG_STORAGE_KEY, selectedOrgId);
    }
  }, [selectedOrgId]);

  const navItems = [
    { to: "/", label: "Fleet", end: true, forceActive: false },
    { to: "/products", label: "Products", end: false, forceActive: false },
    { to: "/baselines", label: "Baselines", end: false, forceActive: false },
    { to: "/settings/orgs", label: "Settings", end: false, forceActive: isSettings },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 w-full border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="container mx-auto flex flex-col gap-3 px-4 py-3 lg:h-[68px] lg:flex-row lg:items-center lg:justify-between lg:px-6 lg:py-0">
          <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-center">
            <Link to="/" className="flex min-w-0 items-center">
              <img
                src={resolvedDark ? (productBranding.logoDarkSrc ?? "/logo-dark.svg") : (productBranding.logoLightSrc ?? "/logo-light.svg")}
                alt={productBranding.title ?? "Orcha"}
                className="h-10 w-auto shrink-0"
              />
            </Link>
            <div className="hidden h-6 w-px bg-zinc-200 dark:bg-zinc-800 lg:block" />
            <div className="flex flex-wrap items-center gap-1">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    disabled={orgOptions.length === 0}
                    className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:cursor-default disabled:opacity-70 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    <Building2 className="h-4 w-4" />
                    <span>{selectedOrgLabel}</span>
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="min-w-[180px]">
                  {orgOptions.map((org) => (
                    <DropdownMenuItem
                      key={org.org_id}
                      onClick={() => setSelectedOrgId(org.org_id)}
                      className={
                        selectedOrgId === org.org_id
                          ? "cursor-pointer bg-zinc-100 dark:bg-zinc-800"
                          : "cursor-pointer"
                      }
                    >
                      {org.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              <nav className="flex items-center gap-1">
                {navItems.map((item) => {
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) =>
                        [
                          "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                          (item.forceActive || isActive)
                            ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                            : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100",
                        ].join(" ")
                      }
                    >
                      {item.label}
                    </NavLink>
                  );
                })}
              </nav>
            </div>
          </div>
          <div className="flex items-center gap-4 self-end lg:self-auto">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <HeaderIconButton label="Theme">
                  {preference === "dark" ? (
                    <Moon className="h-5 w-5" />
                  ) : preference === "light" ? (
                    <Sun className="h-5 w-5" />
                  ) : (
                    <Monitor className="h-5 w-5" />
                  )}
                </HeaderIconButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuRadioGroup
                  value={preference}
                  onValueChange={(value) => setPreference(value as ThemePreference)}
                >
                  <DropdownMenuRadioItem value="light" className="cursor-pointer">
                    <Sun className="h-4 w-4" />
                    Light
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="dark" className="cursor-pointer">
                    <Moon className="h-4 w-4" />
                    Dark
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="system" className="cursor-pointer">
                    <Monitor className="h-4 w-4" />
                    System
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
            <HeaderIconButton
              label="Help"
              onClick={() => {
                window.open("/docs", "_blank", "noopener,noreferrer");
              }}
            >
              <CircleHelp className="h-5 w-5" />
            </HeaderIconButton>
            {loading ? (
              <div className="px-2 text-sm text-zinc-500 dark:text-zinc-400">Loading...</div>
            ) : null}
            {!loading ? (
              <UserMenu
                label={accountLabel ?? user.username ?? user.user_id}
                email={user.username}
                roles={user.roles}
                themePreference={preference}
                onThemeChange={(value) => setPreference(value as ThemePreference)}
                authDisabled={!authConfigured}
                onLogin={onLogin}
                onLogout={onLogout}
              />
            ) : null}
          </div>
        </div>
      </header>
      {isSettings ? (
        <div className="bg-zinc-50 dark:bg-zinc-950 lg:min-h-[calc(100vh-68px)]">{children}</div>
      ) : (
        <main className="container mx-auto px-4 py-6 lg:px-6">{children}</main>
      )}
    </div>
  );
}

function SettingsOrganizationsPage({
  user,
}: {
  user: UserInfo;
}) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = deferredSearch.trim().toLowerCase();
  const orgs = Array.from(
    new Set([user.default_org_id, ...user.org_ids].filter((value): value is string => Boolean(value))),
  );
  const filteredOrgs = query
    ? orgs.filter((orgId) => {
        const label = displayOrgLabel(orgId).toLowerCase();
        return label.includes(query) || orgId.toLowerCase().includes(query);
      })
    : orgs;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Settings"
        title="Organizations"
        description="Settings keeps organization context and access review in the same shared workspace used by the rest of the shell."
        action={
          <div className="w-full max-w-sm">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search organizations..."
            />
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.15fr,0.85fr]">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Accessible organizations</CardTitle>
            <CardDescription>
              The operator identity can switch between these organizations from the header control.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {filteredOrgs.length ? (
              filteredOrgs.map((orgId) => (
                <div
                  key={orgId}
                  className="rounded-3xl border border-border/70 bg-background px-4 py-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-foreground">{displayOrgLabel(orgId)}</p>
                    {user.default_org_id === orgId ? (
                      <Badge className="border-border bg-secondary text-secondary-foreground">
                        Default
                      </Badge>
                    ) : null}
                  </div>
                  <p className="pt-2 text-sm text-muted-foreground">
                    Org id: {orgId}
                  </p>
                </div>
              ))
            ) : (
              <EmptyState
                title="No organizations match the current query."
                description="Try a broader organization name or id."
              />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Current context</CardTitle>
              <CardDescription>
                The header selector defaults to the account’s standard organization.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine
                label="Default org"
                value={displayOrgLabel(user.default_org_id ?? user.org_ids[0])}
              />
              <InfoLine label="Accessible orgs" value={orgs.length || 0} />
              <InfoLine
                label="Header behavior"
                value="Use the org control next to the logo"
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>What changed</CardTitle>
              <CardDescription>
                This restores the standard organization review surface instead of a one-off placeholder page.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>The org label in the header is now visible again.</p>
              <p>The settings workspace mirrors the shared shell structure.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function SettingsAccessPage({
  user,
}: {
  user: UserInfo;
}) {
  const identityLabel = user.username ?? user.user_id;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Settings"
        title="Roles & Permissions"
        description="Settings keeps identity, roles, and permissions readable in the same left-rail workspace used across the shell."
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Identity</CardTitle>
            <CardDescription>
              Current operator account and default context.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            <InfoLine label="Display name" value={identityLabel} />
            <InfoLine label="User id" value={user.user_id} />
            <InfoLine
              label="Default org"
              value={displayOrgLabel(user.default_org_id ?? user.org_ids[0])}
            />
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Roles</CardTitle>
            <CardDescription>
              Role claims attached to the current operator account.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {user.roles.length ? (
              user.roles.map((role) => (
                <Badge
                  key={role}
                  className="border-border bg-secondary text-secondary-foreground"
                >
                  {role}
                </Badge>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No explicit roles reported.</p>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Permissions</CardTitle>
            <CardDescription>
              Effective permissions from the operator API identity.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {user.permissions.length ? (
              user.permissions.map((permission) => (
                <div
                  key={permission}
                  className="rounded-2xl border border-border/70 bg-background px-3 py-2 text-sm text-foreground"
                >
                  {permission}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No explicit permissions reported.</p>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Feature flags</CardTitle>
            <CardDescription>
              Optional shell features attached to the current account.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {user.feature_flags.length ? (
              user.feature_flags.map((flag) => (
                <div
                  key={flag}
                  className="rounded-2xl border border-border/70 bg-background px-3 py-2 text-sm text-foreground"
                >
                  {flag}
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No feature flags reported.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SettingsWorkspacePage({
  user,
}: {
  user: UserInfo;
}) {
  const { preference, setPreference } = useTheme();
  const themeOptions: Array<{ label: string; value: ThemePreference; icon: typeof Sun }> = [
    { label: "Light", value: "light", icon: Sun },
    { label: "Dark", value: "dark", icon: Moon },
    { label: "System", value: "system", icon: Monitor },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Settings"
        title="Workspace"
        description="Settings keeps theme, help, and account controls in the same shared workspace patterns used across the shell."
      />

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Theme</CardTitle>
            <CardDescription>
              The top-right theme control and this workspace stay in sync.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {themeOptions.map((option) => {
              const Icon = option.icon;
              const isActive = preference === option.value;
              return (
                <Button
                  key={option.value}
                  type="button"
                  variant="outline"
                  className={
                    isActive
                      ? "w-full justify-start border-primary/30 bg-primary/10 text-foreground"
                      : "w-full justify-start"
                  }
                  onClick={() => setPreference(option.value)}
                >
                  <Icon className="size-4" />
                  {option.label}
                </Button>
              );
            })}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Help &amp; docs</CardTitle>
            <CardDescription>
              Documentation stays attached to the shared-shell help affordance.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              The help button in the header opens the docs workspace in a new tab.
            </p>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
            >
              Open docs
            </a>
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Account</CardTitle>
            <CardDescription>
              User controls stay in the standard top-right menu instead of a product-local pill.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            <InfoLine label="User" value={user.username ?? user.user_id} />
            <InfoLine
              label="Org"
              value={displayOrgLabel(user.default_org_id ?? user.org_ids[0])}
            />
            <InfoLine label="Roles" value={user.roles.length || 0} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FleetPage({
  products,
  lanes,
  baselines,
  observability,
}: DashboardState) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = deferredSearch.trim().toLowerCase();
  const hasQuery = query.length > 0;
  const laneSummariesById = new Map((observability?.lanes ?? []).map((item) => [item.lane_id, item]));
  const filteredProducts = query
    ? products.filter(
        (item) =>
          item.name.toLowerCase().includes(query) ||
          item.key.toLowerCase().includes(query) ||
          item.primary_repo?.name.toLowerCase().includes(query),
      )
    : products;
  const filteredLanes = query
    ? lanes.filter(
        (item) =>
          item.work_item.title.toLowerCase().includes(query) ||
          item.product.name.toLowerCase().includes(query) ||
          String(item.work_item.issue_number).includes(query),
      )
    : lanes;
  const stats = computeFleetStats(products, lanes, baselines);
  const setupWarningProduct = products.find((item) => item.setup_state === "setup-needed");
  const driftedBaseline = baselines.find((item) => item.drift_status === "drift");
  const runtimeNotifications = (observability?.notifications ?? []).filter(isRuntimeNotification);
  const highPriorityCount = countHighPriorityNotifications(runtimeNotifications);
  const waitingLane = lanes.find(
    (item) => item.state === "AwaitingApproval" || item.state === "AwaitingGitHub",
  );
  const waitingDecisionCount = observability
    ? countWaitingLaneStates(observability.lane_state_counts)
    : stats.waitingLanes;
  const reviewBlockersTarget = setupWarningProduct
    ? `/products/${setupWarningProduct.product_id}`
    : waitingLane
      ? `/lanes/${waitingLane.lane_id}`
      : driftedBaseline
        ? `/baselines/${driftedBaseline.product_id}`
        : "/products";
  const blockerActionLabel = setupWarningProduct
    ? "Review setup blockers"
    : waitingLane
      ? "Review waiting lane"
      : driftedBaseline
      ? "Review drift detail"
      : "Open Products";
  const driftTarget = driftedBaseline ? `/baselines/${driftedBaseline.product_id}` : "/baselines";
  const runtimeFocusTarget = runtimeNotifications
    .map((notification) => resolveObservabilityNotificationTarget(notification))
    .find((target): target is NonNullable<ReturnType<typeof resolveObservabilityNotificationTarget>> => target !== null);
  const runtimeEntryTarget = runtimeFocusTarget
    ?? (waitingLane
      ? {
          to: `/lanes/${waitingLane.lane_id}`,
          label: "Open lane",
        }
      : {
          to: "/products",
          label: "Open Products",
        });
  const onboardingActivities = collectOnboardingActivities(products);
  const visibleLanes = filteredLanes.slice(0, 6);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Fleet"
        title="Dashboard and triage"
        description="Fleet is the cross-product dashboard for bring-up blockers, live runner and lane health, GitHub delivery lag, and standards drift. Start onboarding in Products, then return here to separate setup-needed blockers from runtime issues once work starts moving."
        action={
          <div className="flex w-full flex-col gap-2 lg:w-auto lg:items-end">
            <div className="flex flex-wrap gap-2">
              <Link to="/products" className={buttonLinkClassName()}>
                Open Products
              </Link>
              <Link to={reviewBlockersTarget} className={buttonLinkClassName("outline")}>
                Review blockers
              </Link>
            </div>
            <div className="w-full max-w-sm">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search products, issues, or repos"
              />
            </div>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={<Boxes className="size-5" />}
          label="Products"
          value={stats.products}
          helper={`${stats.activeProducts} active, ${stats.setupWarnings} need setup`}
        />
        <MetricCard
          icon={<AlertTriangle className="size-5" />}
          label="Blockers"
          value={stats.setupWarnings}
          helper="Products still blocked by onboarding or contract diagnostics"
        />
        <MetricCard
          icon={<ShieldAlert className="size-5" />}
          label="Drift"
          value={stats.driftedBaselines}
          helper="Baselines with direct managed asset drift"
        />
        <MetricCard
          icon={<Waypoints className="size-5" />}
          label="Repos"
          value={products.filter((item) => item.primary_repo).length}
          helper="Products bound to a primary repository"
        />
      </div>

      {observability ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <MetricCard
            icon={<Waypoints className="size-5" />}
            label="Queue depth"
            value={observability.queue_depth}
            helper={`${observability.active_lane_count} active lanes in the live queue`}
          />
          <MetricCard
            icon={<Workflow className="size-5" />}
            label="Waiting"
            value={waitingDecisionCount}
            helper="Approvals or human-input lanes paused on an operator"
          />
          <MetricCard
            icon={<RefreshCw className="size-5" />}
            label="Retry backlog"
            value={observability.retry_backlog_count}
            helper="Lanes currently scheduled for retry handling"
          />
          <MetricCard
            icon={<AlertTriangle className="size-5" />}
            label="Dead letters"
            value={observability.dead_letter_backlog_count}
            helper="Webhook deliveries that have fallen into the dead-letter queue"
          />
          <MetricCard
            icon={<Clock3 className="size-5" />}
            label="Mirror lag"
            value={formatDurationSeconds(observability.mirror_lag_seconds)}
            helper={
              observability.mirror_lag_seconds == null
                ? "GitHub delivery mirrors are current"
                : `${observability.mirror_lag_seconds}s on the oldest unprocessed delivery`
            }
          />
          <MetricCard
            icon={<Monitor className="size-5" />}
            label="Priority alerts"
            value={highPriorityCount}
            helper={`${observability.stale_heartbeat_count} stale heartbeats, ${observability.notification_count} total notifications`}
          />
        </div>
      ) : (
        <EmptyState
          title="Observability summary is unavailable."
          description="Fleet can still show setup blockers and product posture, but queue depth, heartbeat health, and GitHub delivery lag are not currently attached."
        />
      )}

      <Card className="shadow-none">
        <CardContent className="flex items-start gap-3 py-5">
          <Monitor className="mt-0.5 size-5 text-primary" />
          <div className="space-y-1">
            <p className="font-medium text-foreground">Setup blockers and runtime health are rendered separately.</p>
            <p className="text-sm text-muted-foreground">
              `setup-needed` still means onboarding or contract diagnostics are blocking activation. Fleet observability tracks lane, runner, and GitHub delivery health after bring-up starts so operators do not confuse runtime incidents with product setup work.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SurfaceEntryCard
          eyebrow="Products"
          title="Start onboarding in Products"
          description="Products is the operator home for seeding a new repo from the approved baseline, adopting an existing repository, and then opening product-level workflows."
          icon={<Boxes className="size-5" />}
          action={
            <Link to="/products" className={buttonLinkClassName()}>
              Open Products
            </Link>
          }
        />
        <SurfaceEntryCard
          eyebrow="Blockers"
          title="Resolve onboarding blockers"
          description={
            setupWarningProduct
              ? `${setupWarningProduct.name} is currently setup-needed. Use product detail to inspect diagnostics, refresh contract state, and decide when the product can resume.`
              : waitingLane
                ? `${waitingLane.product.name} currently has work waiting on an operator decision. Fleet links directly into the lane or product surface that needs attention.`
                : "When setup diagnostics or queued approvals block bring-up, Fleet sends operators straight to the product or lane surface that needs attention."
          }
          icon={<AlertTriangle className="size-5" />}
          action={
            <Link to={reviewBlockersTarget} className={buttonLinkClassName("outline")}>
              {blockerActionLabel}
            </Link>
          }
        />
        <SurfaceEntryCard
          eyebrow="Runtime"
          title="Review runtime health"
          description={
            runtimeNotifications.length
              ? `${runtimeNotifications[0].title}. ${runtimeNotifications[0].summary}`
              : "Runner heartbeat health, retry pressure, and GitHub delivery lag stay visible here once products start running live work."
          }
          icon={<Monitor className="size-5" />}
          action={
            <Link to={runtimeEntryTarget.to} className={buttonLinkClassName("outline")}>
              {runtimeEntryTarget.label}
            </Link>
          }
        />
        <SurfaceEntryCard
          eyebrow="Baselines"
          title="Review standards drift"
          description={
            driftedBaseline
              ? `${driftedBaseline.product_name} currently reports managed-asset drift. Baselines is where standards posture and follow-up state stay visible.`
              : "Use Baselines when you need standards posture, managed-asset counts, and drift follow-up for registered products."
          }
          icon={<ShieldAlert className="size-5" />}
          action={
            <Link to={driftTarget} className={buttonLinkClassName("outline")}>
              {driftedBaseline ? "Review standards drift" : "Open Baselines"}
            </Link>
          }
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.35fr,1fr]">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="text-foreground">Product fleet</CardTitle>
            <CardDescription className="text-muted-foreground">
              Each row opens the product surface where setup blockers, baseline posture, and lane context come together.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {products.length ? (
              filteredProducts.length ? (
                filteredProducts.map((product) => {
                  const baseline = baselines.find((item) => item.product_id === product.product_id);
                  const productLanes = lanes.filter(
                    (item) =>
                      item.product_id === product.product_id &&
                      !["Cancelled", "FailedTerminal", "HandedOff"].includes(item.state),
                  );
                  return (
                    <Link
                      key={product.product_id}
                      to={`/products/${product.product_id}`}
                      className="group block rounded-3xl border border-border/70 bg-muted/30 p-4 transition hover:border-primary/30 hover:bg-accent/60"
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <h2 className="text-lg font-semibold text-foreground">{product.name}</h2>
                            <Badge className={statusTone(product.status)}>{humanize(product.status)}</Badge>
                            <Badge className={statusTone(product.setup_state)}>{humanize(product.setup_state)}</Badge>
                            {baseline ? (
                              <Badge className={statusTone(baseline.drift_status)}>{humanize(baseline.drift_status)}</Badge>
                            ) : null}
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {product.description ?? "No product description provided."}
                          </p>
                          <div className="flex flex-wrap gap-5 text-sm text-muted-foreground">
                            <span>
                              {product.primary_repo
                                ? `${product.primary_repo.owner}/${product.primary_repo.name}`
                                : "Repository pending"}
                            </span>
                            <span>{productLanes.length} active lanes</span>
                            <span>{describeProductRuntimeSummary(productLanes, laneSummariesById)}</span>
                            <span>Config refreshed {formatRelativeTime(product.last_config_refresh_at)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-sm text-primary">
                          Open product
                          <ArrowRight className="size-4 transition group-hover:translate-x-1" />
                        </div>
                      </div>
                    </Link>
                  );
                })
              ) : (
                <EmptyState
                  title="No products match the current fleet query."
                  description="Try a broader product key, repository name, or issue number."
                />
              )
            ) : (
              <EmptyState
                title="No products are onboarded yet."
                description="Open Products to seed a new repo from the approved baseline or adopt an existing repository into Orcha."
                action={
                  <Link to="/products" className={buttonLinkClassName()}>
                    Open Products
                  </Link>
                }
              />
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Runtime and delivery health</CardTitle>
              <CardDescription className="text-muted-foreground">
                These alerts cover active lanes, runner heartbeat degradation, retries, and GitHub delivery health. They do not replace setup-needed onboarding blockers.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ObservabilityNotificationList
                notifications={runtimeNotifications}
                emptyTitle="No runtime or delivery alerts are currently active."
                emptyDescription="Setup blockers still live on Products and Baselines, while Fleet will populate this feed once lane or delivery health begins to degrade."
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Decision queue</CardTitle>
              <CardDescription className="text-muted-foreground">
                Waiting approval and human-input lanes stay in Fleet so operators can triage bring-up without guessing where decisions belong. Session and environment health stay attached to each lane row.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {visibleLanes.length ? (
                visibleLanes.map((lane) => {
                  const laneSummary = laneSummariesById.get(lane.lane_id);
                  const heartbeatStatus = resolveLaneHeartbeatStatus(lane, laneSummary);
                  return (
                    <Link
                      key={lane.lane_id}
                      to={`/lanes/${lane.lane_id}`}
                      className="block rounded-3xl border border-border/70 bg-muted/30 p-4 transition hover:border-primary/30"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-foreground">
                              #{lane.work_item.issue_number} {lane.work_item.title}
                            </p>
                            <Badge className={statusTone(lane.state)}>{humanize(lane.state)}</Badge>
                            <Badge className={statusTone(heartbeatStatus)}>{humanize(heartbeatStatus)}</Badge>
                            {lane.agent_session ? (
                              <Badge className="border-border bg-secondary text-secondary-foreground">
                                {humanize(lane.agent_session.status)}
                              </Badge>
                            ) : null}
                            {lane.execution_environment ? (
                              <Badge className="border-border bg-secondary text-secondary-foreground">
                                {humanize(lane.execution_environment.status)}
                              </Badge>
                            ) : null}
                          </div>
                          <p className="text-sm text-muted-foreground">{laneSummary?.summary ?? describeLane(lane)}</p>
                          <p className="text-sm text-muted-foreground">
                            {describeLaneRuntimeHealth(lane, laneSummary)}
                          </p>
                          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                            {lane.product.name} • attempt {lane.attempt} • session {formatRelativeTime(lane.agent_session?.heartbeat_at ?? lane.agent_session?.last_event_at ?? null)} • env {formatRelativeTime(lane.execution_environment?.heartbeat_at ?? null)}
                          </p>
                        </div>
                        <ArrowRight className="mt-1 size-4 text-muted-foreground" />
                      </div>
                    </Link>
                  );
                })
              ) : (
                <EmptyState
                  title={hasQuery ? "No lanes match the current fleet query." : "No lanes need operator attention right now."}
                  description={
                    hasQuery
                      ? "Try a broader product key, issue number, or lane title."
                      : "Approval and human-input lanes will appear here after products are onboarded and active work reaches an operator decision point."
                  }
                  action={
                    !hasQuery ? (
                      <Link
                        to={setupWarningProduct ? `/products/${setupWarningProduct.product_id}` : "/products"}
                        className={buttonLinkClassName("outline")}
                      >
                        {setupWarningProduct ? "Review setup blockers" : "Open Products"}
                      </Link>
                    ) : undefined
                  }
                />
              )}
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Baseline watch</CardTitle>
              <CardDescription className="text-muted-foreground">
                Standards posture and managed-asset drift stay visible alongside the products operators own.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {baselines.length ? (
                baselines.slice(0, 5).map((baseline) => (
                  <Link
                    key={baseline.product_id}
                    to={`/baselines/${baseline.product_id}`}
                    className="flex items-center justify-between rounded-3xl border border-border/70 bg-muted/30 px-4 py-3 transition hover:border-primary/30"
                  >
                    <div>
                      <p className="font-medium text-foreground">{baseline.product_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {baseline.standards_pack_key ?? "No pack"} {baseline.standards_pack_version ?? ""}
                      </p>
                    </div>
                    <Badge className={statusTone(baseline.drift_status)}>{humanize(baseline.drift_status)}</Badge>
                  </Link>
                ))
              ) : (
                <EmptyState
                  title="No baseline posture is available yet."
                  description="Baseline summaries appear after Products seeds or adopts a repo and Orcha evaluates managed assets against the approved standards pack."
                  action={
                    <Link to="/products" className={buttonLinkClassName("outline")}>
                      Open Products
                    </Link>
                  }
                />
              )}
            </CardContent>
          </Card>

          <OnboardingActivityPanel
            title="Onboarding activity"
            description="Seed and adoption work stays inspectable from Fleet so operators can return to in-flight or recently completed bring-up without guessing which route owns the details."
            activities={onboardingActivities}
            emptyTitle="No onboarding activity is linked yet."
            emptyDescription="Seed and adoption results will appear here once Products records durable onboarding work."
          />
        </div>
      </div>
    </div>
  );
}

function ProductsPage({
  products,
  lanes,
  baselines,
}: DashboardState) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = deferredSearch.trim().toLowerCase();
  const hasQuery = query.length > 0;
  const filteredProducts = query
    ? products.filter(
        (product) =>
          product.name.toLowerCase().includes(query) ||
          product.key.toLowerCase().includes(query) ||
          product.primary_repo?.name.toLowerCase().includes(query) ||
          product.primary_repo?.owner.toLowerCase().includes(query),
      )
    : products;
  const firstProduct = products[0] ?? null;
  const setupWarningProduct = products.find((product) => product.setup_state === "setup-needed");
  const onboardingActivities = collectOnboardingActivities(products);
  const leadOnboardingActivity = onboardingActivities[0] ?? null;
  const productWorkflowTarget = setupWarningProduct
    ? `/products/${setupWarningProduct.product_id}`
    : firstProduct
      ? `/products/${firstProduct.product_id}`
      : "/products";
  const entryGridClassName = leadOnboardingActivity
    ? products.length
      ? "xl:grid-cols-4"
      : "xl:grid-cols-3"
    : products.length
      ? "xl:grid-cols-3"
      : "xl:grid-cols-2";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Products"
        title="Seed, adopt, and operate products"
        description="Products is the onboarding home. Start here to seed a repo from the approved agent-core baseline, adopt an existing repository, or open a product to clear setup blockers and manage day-two workflows."
        action={
          <div className="flex w-full flex-col gap-2 lg:w-auto lg:items-end">
            <div className="flex flex-wrap gap-2">
              <Link to="/products/seed" className={buttonLinkClassName()}>
                Seed a product
              </Link>
              <Link to="/products/adopt" className={buttonLinkClassName("outline")}>
                Adopt a repo
              </Link>
            </div>
            {products.length ? (
              <div className="w-full max-w-sm">
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search products or repositories"
                />
              </div>
            ) : null}
          </div>
        }
      />

      <div className={`grid gap-4 ${entryGridClassName}`}>
        <SurfaceEntryCard
          eyebrow="Seed"
          title="Create a repo from the approved baseline"
          description="Use seeding when the repository does not exist yet and Orcha should render the approved baseline bundle before registration."
          icon={<Sparkles className="size-5" />}
          action={
            <Link to="/products/seed" className={buttonLinkClassName()}>
              Open seed flow
            </Link>
          }
        />
        <SurfaceEntryCard
          eyebrow="Adopt"
          title="Bring an existing repo under Orcha"
          description="Use adoption when the repository already exists and Orcha needs to validate the default branch, register bindings, and surface setup diagnostics."
          icon={<Waypoints className="size-5" />}
          action={
            <Link to="/products/adopt" className={buttonLinkClassName("outline")}>
              Open adoption flow
            </Link>
          }
        />
        {leadOnboardingActivity ? (
          <SurfaceEntryCard
            eyebrow="Onboarding"
            title="Resume onboarding work"
            description="Return to the latest seed or adoption result without hunting through product detail first."
            icon={<Clock3 className="size-5" />}
            action={
              <Link to={leadOnboardingActivity.target} className={buttonLinkClassName("outline")}>
                {leadOnboardingActivity.actionLabel}
              </Link>
            }
          />
        ) : null}
        {products.length ? (
          <SurfaceEntryCard
            eyebrow="Operate"
            title="Open product workflows"
            description="Product detail is where setup diagnostics, lane activity, baseline posture, and graph linkouts come together once a product exists."
            icon={<Workflow className="size-5" />}
            action={
              <Link to={productWorkflowTarget} className={buttonLinkClassName("outline")}>
                {setupWarningProduct ? "Review setup blockers" : "Open first product"}
              </Link>
            }
          />
        ) : null}
      </div>

      {onboardingActivities.length ? (
        <OnboardingActivityPanel
          title="Recent onboarding activity"
          description="Seed jobs and adoption results stay reachable from Products after navigation, refresh, or re-login."
          activities={onboardingActivities}
          emptyTitle="No onboarding activity is available."
          emptyDescription="Seed or adopt a product first to create a durable onboarding route."
          limit={3}
        />
      ) : null}

      {!products.length ? (
        <div className="grid gap-4 xl:grid-cols-[1.1fr,0.9fr]">
          <EmptyState
            title="No products are registered yet."
            description="Start here to seed a new repo from the approved baseline or adopt an existing repository. Product detail routes appear after the first registration."
            action={
              <>
                <Link
                  to="/products/seed"
                  className={buttonLinkClassName()}
                >
                  Seed a product
                </Link>
                <Link
                  to="/products/adopt"
                  className={buttonLinkClassName("outline")}
                >
                  Adopt a repo
                </Link>
              </>
            }
          />
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>What appears here after onboarding</CardTitle>
              <CardDescription>
                Products becomes the directory for registered product surfaces and operator workflows once bring-up has started.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Product detail" value="Setup diagnostics, refresh, and pause or resume actions" />
              <InfoLine label="Baseline posture" value="Direct links into managed-asset drift and standards runs" />
              <InfoLine label="Graph context" value="Bounded dependency slice for the selected product" />
            </CardContent>
          </Card>
        </div>
      ) : filteredProducts.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {filteredProducts.map((product) => {
            const laneCount = lanes.filter((item) => item.product_id === product.product_id).length;
            const baseline = baselines.find((item) => item.product_id === product.product_id);
            const onboardingActivity = resolveProductOnboardingActivity(product);
            return (
              <Card key={product.product_id} className="shadow-none">
                <CardHeader className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-foreground">{product.name}</CardTitle>
                    <Badge className={statusTone(product.status)}>{humanize(product.status)}</Badge>
                    <Badge className={statusTone(product.setup_state)}>{humanize(product.setup_state)}</Badge>
                  </div>
                  <CardDescription className="text-muted-foreground">
                    {product.primary_repo
                      ? `${product.primary_repo.owner}/${product.primary_repo.name}`
                      : "No primary repository bound yet"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">{product.description ?? "No product description provided."}</p>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Lanes</p>
                      <p className="pt-1 text-2xl font-semibold text-foreground">{laneCount}</p>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Standards Posture</p>
                      <p className="pt-1 text-sm font-medium text-foreground">{baseline ? humanize(baseline.drift_status) : "No evaluation yet"}</p>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Config Refresh</p>
                      <p className="pt-1 text-sm font-medium text-foreground">{formatRelativeTime(product.last_config_refresh_at)}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link
                      to={`/products/${product.product_id}`}
                      className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
                    >
                      Open product
                    </Link>
                    <Link
                      to={`/graphs/products/${product.product_id}`}
                      className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
                    >
                      Open graph
                    </Link>
                    {onboardingActivity ? (
                      <Link
                        to={onboardingActivity.target}
                        className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
                      >
                        {onboardingActivity.actionLabel}
                      </Link>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="No products match the current query."
          description={hasQuery ? "Try a broader product name, key, or repository." : "Products will appear here after the first seed or adoption completes."}
        />
      )}
    </div>
  );
}

function ProductSeedPage({
  user,
  organizations,
  products,
  onboardingDefaultsByOrg,
  onRefreshDashboard,
}: {
  user: UserInfo;
  organizations: OrganizationResponse[];
  products: ProductSummaryResponse[];
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg;
  onRefreshDashboard: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as ProductSeedDraftState | null) ?? null;
  const [draft, setDraft] = useState(() =>
    createProductSeedDraft({
      user,
      organizations,
      products,
      onboardingDefaultsByOrg,
      seedDraft: locationState?.seedDraft,
    }),
  );
  const [secrets, setSecrets] = useState<SecretResponse[]>([]);
  const [secretSelection, setSecretSelection] = useState("");
  const [attemptedMode, setAttemptedMode] = useState<"preview" | "live" | null>(null);
  const [submittingMode, setSubmittingMode] = useState<"preview" | "live" | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [isLoadingSecrets, setIsLoadingSecrets] = useState(true);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [orgRepos, setOrgRepos] = useState<GitRepoResponse[]>([]);
  const [isLoadingOrgRepos, setIsLoadingOrgRepos] = useState(true);
  const [orgReposError, setOrgReposError] = useState<string | null>(null);

  const loadSecrets = useEffectEvent(async () => {
    setIsLoadingSecrets(true);
    setSecretsError(null);
    try {
      setSecrets(await operatorApi.listSecrets());
    } catch (loadError) {
      setSecrets([]);
      setSecretsError(loadError instanceof Error ? loadError.message : "Failed to load secret inventory.");
    } finally {
      setIsLoadingSecrets(false);
    }
  });

  const loadOrgRepos = useEffectEvent(async (orgId: string) => {
    setIsLoadingOrgRepos(true);
    setOrgReposError(null);
    try {
      setOrgRepos(await operatorApi.listOrgRepos(orgId));
    } catch (loadError) {
      setOrgRepos([]);
      setOrgReposError(loadError instanceof Error ? loadError.message : "Failed to load connected repositories.");
    } finally {
      setIsLoadingOrgRepos(false);
    }
  });

  useEffect(() => {
    void loadSecrets();
  }, []);

  useEffect(() => {
    if (!draft.orgId.trim()) {
      setOrgRepos([]);
      setOrgReposError(null);
      setIsLoadingOrgRepos(false);
      return;
    }
    void loadOrgRepos(draft.orgId);
  }, [draft.orgId]);

  useEffect(() => {
    if (locationState?.seedDraft) {
      setDraft(
        createProductSeedDraft({
          user,
          organizations,
          products,
          onboardingDefaultsByOrg,
          seedDraft: locationState.seedDraft,
        }),
      );
      setAttemptedMode(null);
      setSubmissionError(null);
      setSecretSelection("");
    }
  }, [location.key]);

  useEffect(() => {
    setDraft((current) => {
      const preferredOrgId = user.default_org_id ?? organizations[0]?.org_id ?? user.org_ids[0] ?? current.orgId;
      const hasOrg =
        !current.orgId.trim() || organizations.length === 0 || organizations.some((org) => org.org_id === current.orgId);
      const nextOrgId = hasOrg ? current.orgId || preferredOrgId : preferredOrgId;
      const defaultOwner = resolveDefaultSeedGithubOwner(nextOrgId, organizations, products);
      const shouldRefreshOwner = shouldRefreshDefaultGithubOwner(current.githubOwner, nextOrgId, organizations);
      if (nextOrgId === current.orgId && (!shouldRefreshOwner || current.githubOwner === defaultOwner)) {
        return current;
      }
      const nextDraft = {
        ...current,
        orgId: nextOrgId,
        githubOwner: shouldRefreshOwner ? defaultOwner : current.githubOwner,
      };
      return nextOrgId !== current.orgId
        ? applySeedOnboardingDefaults(
            nextDraft,
            resolveOrgOnboardingDefaultsRecord(nextOrgId, onboardingDefaultsByOrg),
          )
        : nextDraft;
    });
  }, [
    user.default_org_id,
    user.org_ids.join("|"),
    organizations.map((org) => `${org.org_id}:${org.slug}`).join("|"),
    products.map((product) => `${product.org_id}:${product.primary_repo?.owner ?? ""}`).join("|"),
    Object.keys(onboardingDefaultsByOrg).join("|"),
  ]);

  const onboardingDefaultsRecord = resolveOrgOnboardingDefaultsRecord(draft.orgId, onboardingDefaultsByOrg);
  const legacyInstallationId = readLegacyGithubInstallationId(onboardingDefaultsRecord);
  const selectedSeedRepo = findMatchingSeedWorkspaceRepo(orgRepos, draft);
  const validation = buildProductSeedValidation(draft, secrets, {
    secretInventoryAvailable: !isLoadingSecrets && !secretsError,
    repoInventory: orgRepos,
    repoInventoryLoaded: !isLoadingOrgRepos,
    repoInventoryFailed: Boolean(orgReposError),
  });
  const activeFieldErrors =
    attemptedMode === "live" ? validation.liveFieldErrors : validation.previewFieldErrors;
  const selectedSecretKeys = normalizeSecretKeys(draft.requiredSecretKeys);
  const availableSecrets = secrets.filter((secret) => !selectedSecretKeys.includes(secret.key));
  const baselineChannel = resolveBaselineChannel(draft);
  const selectedOrgLabel = resolveSeedOrgLabel(draft.orgId, organizations);
  const previewProjectTitle = draft.githubProjectTitle.trim() || draft.productName.trim() || "Will use the product name";
  const projectSummary =
    draft.projectMode === "create"
      ? `Create ${previewProjectTitle}`
      : `${draft.githubProjectNodeId.trim() || "Bind existing project"}${
          draft.githubProjectNumber.trim() ? ` (#${draft.githubProjectNumber.trim()})` : ""
        }`;
  const attemptErrors =
    attemptedMode === "live" ? validation.liveErrors : attemptedMode === "preview" ? validation.previewErrors : [];

  function fieldError(field: keyof ProductSeedFieldErrors) {
    return attemptedMode ? activeFieldErrors[field] : undefined;
  }

  function updateDraft(updater: (current: ProductSeedDraft) => ProductSeedDraft) {
    setSubmissionError(null);
    setDraft((current) => updater(current));
  }

  function handleOrgChange(nextOrgId: string) {
    updateDraft((current) => {
      return applySeedOnboardingDefaults(
        {
          ...current,
          orgId: nextOrgId,
          githubOwner: "",
          githubRepo: "",
          githubVisibility: "private",
          githubDefaultBranch: "dev",
        },
        resolveOrgOnboardingDefaultsRecord(nextOrgId, onboardingDefaultsByOrg),
      );
    });
  }

  function toggleSecret(secretKey: string) {
    updateDraft((current) => {
      const nextKeys = current.requiredSecretKeys.includes(secretKey)
        ? current.requiredSecretKeys.filter((item) => item !== secretKey)
        : [...current.requiredSecretKeys, secretKey];
      return {
        ...current,
        requiredSecretKeys: normalizeSecretKeys(nextKeys),
      };
    });
  }

  function addSelectedSecret(secretKey: string) {
    const normalized = secretKey.trim();
    if (!normalized) {
      return;
    }
    updateDraft((current) => ({
      ...current,
      requiredSecretKeys: normalizeSecretKeys([...current.requiredSecretKeys, normalized]),
    }));
    setSecretSelection("");
  }

  async function submitSeed(mode: "preview" | "live") {
    setAttemptedMode(mode);
    setSubmissionError(null);
    const errors = mode === "preview" ? validation.previewErrors : validation.liveErrors;
    if (errors.length) {
      return;
    }
    setSubmittingMode(mode);
    try {
      const job = await operatorApi.seedProduct(
        buildProductSeedPayload(draft, mode === "preview", {
          legacyInstallationId,
        }),
      );
      if (mode === "live") {
        await onRefreshDashboard();
      }
      navigate(`/products/seed/jobs/${job.seed_job_id}`, {
        state: {
          seedJob: job,
          seedDraft: productSeedDraftFromPayload(job.request_payload),
        } satisfies ProductSeedJobRouteState,
      });
    } catch (submitError) {
      setSubmissionError(
        submitError instanceof Error
          ? normalizeSeedSubmissionErrorMessage(submitError.message)
          : "Product seeding failed.",
      );
    } finally {
      setSubmittingMode(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Products"
        title="Seed a new product"
        description="Collect the approved seed request, inspect the dry-run preview, and only submit the live repo mutation once repository, project, and secret guardrails are clear."
        breadcrumbs={[
          { label: "Products", to: "/products" },
          { label: "Seed request" },
        ]}
        action={
          <div className="flex flex-wrap gap-2">
            <Link to="/products" className={buttonLinkClassName("outline")}>
              Back to Products
            </Link>
            <Link to="/" className={buttonLinkClassName("outline")}>
              Open Fleet
            </Link>
          </div>
        }
      />

      {submissionError ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Seed request was not accepted</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">{submissionError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Identity and repo target</CardTitle>
              <CardDescription>
                Establish the control-plane identity first, then choose the saved GitHub repository profile Orcha should use for the seed target.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <SeedField
                  label="Owning org"
                  htmlFor="seed-org"
                  hint="The product record will be created under this organization."
                  error={fieldError("orgId")}
                  required
                >
                  <Select
                    id="seed-org"
                    value={draft.orgId}
                    onChange={(event) => handleOrgChange(event.target.value)}
                    aria-invalid={Boolean(fieldError("orgId"))}
                    className="border-input bg-background/90 text-foreground"
                  >
                    {[draft.orgId, ...organizations.map((org) => org.org_id)]
                      .filter((value, index, values) => Boolean(value) && values.indexOf(value) === index)
                      .map((orgId) => (
                        <option key={orgId} value={orgId}>
                          {resolveSeedOrgLabel(orgId, organizations)}
                        </option>
                      ))}
                  </Select>
                </SeedField>
                <SeedField
                  label="Product name"
                  htmlFor="seed-product-name"
                  hint="Shown in Products, Fleet, and onboarding state surfaces."
                  error={fieldError("productName")}
                  required
                >
                  <Input
                    id="seed-product-name"
                    value={draft.productName}
                    onChange={(event) => updateDraft((current) => applySeedNameDefaults(current, event.target.value))}
                    placeholder="Atlas"
                    aria-invalid={Boolean(fieldError("productName"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Product key"
                  htmlFor="seed-product-key"
                  hint="Used in the product contract and component graph."
                  error={fieldError("productKey")}
                  required
                >
                  <Input
                    id="seed-product-key"
                    value={draft.productKey}
                    onChange={(event) => updateDraft((current) => ({ ...current, productKey: event.target.value }))}
                    placeholder="atlas"
                    aria-invalid={Boolean(fieldError("productKey"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Description"
                  htmlFor="seed-description"
                  hint="Optional description that will be written into product.yaml."
                >
                  <Textarea
                    id="seed-description"
                    value={draft.description}
                    onChange={(event) => updateDraft((current) => ({ ...current, description: event.target.value }))}
                    placeholder="Operator-ready control plane"
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                    rows={4}
                  />
                </SeedField>
                <div>
                  <SeedField
                    label="Connected repository"
                    htmlFor="seed-connected-repo"
                    hint="Uses the owner, repo, visibility, and default branch from Settings > Git Repositories."
                    error={fieldError("githubRepoProfile")}
                    required
                  >
                    <Select
                      id="seed-connected-repo"
                      value={selectedSeedRepo?.repo_id ?? ""}
                      onChange={(event) => {
                        const nextRepo = orgRepos.find((repo) => repo.repo_id === event.target.value) ?? null;
                        updateDraft((current) => ({
                          ...current,
                          githubOwner: nextRepo?.github_owner ?? "",
                          githubRepo: nextRepo?.github_repo ?? "",
                          githubVisibility: nextRepo?.visibility ?? "private",
                          githubDefaultBranch: nextRepo?.default_branch ?? "dev",
                        }));
                      }}
                      disabled={isLoadingOrgRepos || orgRepos.length === 0}
                      aria-invalid={Boolean(fieldError("githubRepoProfile"))}
                      className="border-input bg-background/90 text-foreground"
                    >
                      <option value="">
                        {isLoadingOrgRepos
                          ? "Loading connected repositories..."
                          : orgRepos.length === 0
                            ? "No connected repositories configured"
                            : "Select a connected repository"}
                      </option>
                      {orgRepos.map((repo) => (
                        <option key={repo.repo_id} value={repo.repo_id}>
                          {repo.github_owner}/{repo.github_repo} • {humanize(repo.visibility)} • {repo.default_branch}
                        </option>
                      ))}
                    </Select>
                  </SeedField>
                  {orgReposError ? (
                    <p role="alert" className="pt-2 text-sm text-rose-700 dark:text-rose-300">
                      {orgReposError}
                    </p>
                  ) : null}
                  {!isLoadingOrgRepos && !orgReposError && orgRepos.length === 0 ? (
                    <p className="pt-2 text-sm text-muted-foreground">
                      Add a connected repo in{" "}
                      <Link to="/settings/git-repos" className="font-medium text-foreground underline underline-offset-4">
                        Settings &gt; Git Repositories
                      </Link>{" "}
                      before running a seed.
                    </p>
                  ) : null}
                </div>
                {selectedSeedRepo ? (
                  <div className="md:col-span-2 rounded-xl border border-border/70 bg-muted/20 px-4 py-1">
                    <InfoLine label="GitHub owner" value={selectedSeedRepo.github_owner} />
                    <InfoLine label="GitHub repo" value={selectedSeedRepo.github_repo} />
                    <InfoLine label="Visibility" value={humanize(selectedSeedRepo.visibility)} />
                    <InfoLine label="Default branch" value={selectedSeedRepo.default_branch} />
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Project binding</CardTitle>
              <CardDescription>
                Choose whether seeding should create the primary GitHub Project or bind the product to an existing one.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <SeedField
                  label="Project mode"
                  htmlFor="seed-project-mode"
                  hint="The preview mirrors the same project shape that live seeding will validate."
                >
                  <Select
                    id="seed-project-mode"
                    value={draft.projectMode}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        projectMode: event.target.value as ProductSeedProjectMode,
                      }))
                    }
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="create">Create a new project</option>
                    <option value="bind-existing">Bind an existing project</option>
                  </Select>
                </SeedField>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {draft.projectMode === "create" ? (
                  <SeedField
                    label="Project title"
                    htmlFor="seed-project-title"
                    hint="Defaults to the product name unless you override it."
                    error={fieldError("githubProjectTitle")}
                    required
                  >
                    <Input
                      id="seed-project-title"
                      value={draft.githubProjectTitle}
                      onChange={(event) =>
                        updateDraft((current) => ({ ...current, githubProjectTitle: event.target.value }))
                      }
                      placeholder="Atlas"
                      aria-invalid={Boolean(fieldError("githubProjectTitle"))}
                      className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                    />
                  </SeedField>
                ) : (
                  <>
                    <SeedField
                      label="Project node id"
                      htmlFor="seed-project-node-id"
                      hint="Required when binding to an existing Project V2."
                      error={fieldError("githubProjectNodeId")}
                      required
                    >
                      <Input
                        id="seed-project-node-id"
                        value={draft.githubProjectNodeId}
                        onChange={(event) =>
                          updateDraft((current) => ({ ...current, githubProjectNodeId: event.target.value }))
                        }
                        placeholder="PVT_kwDOB..."
                        aria-invalid={Boolean(fieldError("githubProjectNodeId"))}
                        className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                      />
                    </SeedField>
                    <SeedField
                      label="Project number"
                      htmlFor="seed-project-number"
                      hint="Shown in the repo sidebar and onboarding summary."
                      error={fieldError("githubProjectNumber")}
                      required
                    >
                      <Input
                        id="seed-project-number"
                        value={draft.githubProjectNumber}
                        onChange={(event) =>
                          updateDraft((current) => ({ ...current, githubProjectNumber: event.target.value }))
                        }
                        inputMode="numeric"
                        placeholder="7"
                        aria-invalid={Boolean(fieldError("githubProjectNumber"))}
                        className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                      />
                    </SeedField>
                  </>
                )}
                <SeedField
                  label="Status field"
                  htmlFor="seed-status-field"
                  hint="Live preflight verifies that the primary project exposes this field."
                  error={fieldError("statusField")}
                  required
                >
                  <Input
                    id="seed-status-field"
                    value={draft.statusField}
                    onChange={(event) => updateDraft((current) => ({ ...current, statusField: event.target.value }))}
                    placeholder="Status"
                    aria-invalid={Boolean(fieldError("statusField"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Ready status"
                  htmlFor="seed-ready-status"
                  hint="New work lands here after seeding."
                  error={fieldError("readyStatus")}
                  required
                >
                  <Input
                    id="seed-ready-status"
                    value={draft.readyStatus}
                    onChange={(event) => updateDraft((current) => ({ ...current, readyStatus: event.target.value }))}
                    placeholder="Todo"
                    aria-invalid={Boolean(fieldError("readyStatus"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Done status"
                  htmlFor="seed-done-status"
                  hint="Live preflight also expects an In Progress option between ready and done."
                  error={fieldError("doneStatus")}
                  required
                >
                  <Input
                    id="seed-done-status"
                    value={draft.doneStatus}
                    onChange={(event) => updateDraft((current) => ({ ...current, doneStatus: event.target.value }))}
                    placeholder="Done"
                    aria-invalid={Boolean(fieldError("doneStatus"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Standards and activation</CardTitle>
              <CardDescription>
                Live seeding is blocked until the connected repository profile, execution profile, and required secret inputs are compatible with the approved baseline.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <SeedField
                  label="Baseline preset"
                  htmlFor="seed-baseline-mode"
                  hint="Use stable or candidate unless this product needs a promoted channel."
                  error={fieldError("baselineChannel")}
                  required
                >
                  <Select
                    id="seed-baseline-mode"
                    value={draft.baselineMode}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        baselineMode: event.target.value as ProductSeedBaselineMode,
                      }))
                    }
                    aria-invalid={Boolean(fieldError("baselineChannel"))}
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="stable">Stable</option>
                    <option value="candidate">Candidate</option>
                    <option value="custom">Custom channel</option>
                  </Select>
                </SeedField>
                {draft.baselineMode === "custom" ? (
                  <SeedField
                    label="Custom baseline channel"
                    htmlFor="seed-custom-baseline"
                    hint="Keep this aligned with the promoted standards channel."
                    error={fieldError("baselineChannel")}
                    required
                  >
                    <Input
                      id="seed-custom-baseline"
                      value={draft.customBaselineChannel}
                      onChange={(event) =>
                        updateDraft((current) => ({ ...current, customBaselineChannel: event.target.value }))
                      }
                      placeholder="release-2026-q1"
                      aria-invalid={Boolean(fieldError("baselineChannel"))}
                      className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                    />
                  </SeedField>
                ) : null}
                <SeedField
                  label="Standards pack"
                  htmlFor="seed-standards-pack"
                  hint="Written into the seeded product contract."
                  error={fieldError("standardsPack")}
                  required
                >
                  <Input
                    id="seed-standards-pack"
                    value={draft.standardsPack}
                    onChange={(event) => updateDraft((current) => ({ ...current, standardsPack: event.target.value }))}
                    placeholder="default"
                    aria-invalid={Boolean(fieldError("standardsPack"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Execution profile"
                  htmlFor="seed-execution-profile"
                  hint="Only supported profiles can clear activation preflight."
                  error={fieldError("executionProfile")}
                  required
                >
                  <Select
                    id="seed-execution-profile"
                    value={draft.executionProfile}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, executionProfile: event.target.value }))
                    }
                    aria-invalid={Boolean(fieldError("executionProfile"))}
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="standard-python">standard-python</option>
                  </Select>
                </SeedField>
                <SeedField
                  label="Max concurrent lanes"
                  htmlFor="seed-max-lanes"
                  hint="The standard-python profile currently supports up to 6 lanes."
                  error={fieldError("maxConcurrentLanes")}
                >
                  <Input
                    id="seed-max-lanes"
                    value={draft.maxConcurrentLanes}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, maxConcurrentLanes: event.target.value }))
                    }
                    inputMode="numeric"
                    placeholder="4"
                    aria-invalid={Boolean(fieldError("maxConcurrentLanes"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
              </div>

              <div className="space-y-4 rounded-3xl border border-border/70 bg-muted/30 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-foreground">Required secret inputs</p>
                    <p className="text-sm text-muted-foreground">
                      Select existing secrets from the shared inventory. Create new secrets in Settings and reference them here.
                    </p>
                  </div>
                  <Badge className="border-border bg-secondary text-secondary-foreground">
                    {selectedSecretKeys.length} selected
                  </Badge>
                </div>
                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr),auto] md:items-end">
                  <SeedField
                    label="Add required secret"
                    htmlFor="seed-required-secret"
                    hint="This list comes from Settings > Secrets. The seed form only references those records by key."
                  >
                    <Select
                      id="seed-required-secret"
                      value={secretSelection}
                      onChange={(event) => setSecretSelection(event.target.value)}
                      disabled={isLoadingSecrets || availableSecrets.length === 0}
                      className="border-input bg-background/90 text-foreground"
                    >
                      <option value="">
                        {isLoadingSecrets
                          ? "Loading secret inventory..."
                          : availableSecrets.length === 0
                            ? "No additional secrets available"
                            : "Select a secret"}
                      </option>
                      {availableSecrets.map((secret) => (
                        <option key={secret.secret_id} value={secret.key}>
                          {secret.name} • {secret.key} • {secret.has_value ? "Value ready" : "Missing value"}
                        </option>
                      ))}
                    </Select>
                  </SeedField>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => addSelectedSecret(secretSelection)}
                      disabled={!secretSelection.trim()}
                    >
                      Add secret
                    </Button>
                    <Link to="/settings/secrets" className={buttonLinkClassName("outline")}>
                      Add new secret
                    </Link>
                  </div>
                </div>
                {isLoadingSecrets ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Loading secret inventory…
                  </div>
                ) : null}
                {!isLoadingSecrets && !secrets.length ? (
                  <EmptyState
                    title="No secrets are registered yet."
                    description="Create secrets in Settings before adding them to the activation policy."
                  />
                ) : null}
                {selectedSecretKeys.length ? (
                  <div className="flex flex-wrap gap-2">
                    {selectedSecretKeys.map((secretKey) => {
                      const secret = secrets.find((item) => item.key === secretKey);
                      return (
                        <button
                          key={secretKey}
                          type="button"
                          onClick={() => toggleSecret(secretKey)}
                          className="inline-flex items-center gap-2 rounded-full border border-input bg-background px-3 py-1.5 text-sm text-foreground transition hover:bg-accent hover:text-accent-foreground"
                        >
                          <span>{secretKey}</span>
                          <Badge className={secret?.has_value ? statusTone("ready") : statusTone("setup-needed")}>
                            {secret ? (secret.has_value ? "Ready" : "Missing value") : "Not in inventory"}
                          </Badge>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No additional secret keys are required beyond the standard-python defaults.
                  </p>
                )}
                {secretsError ? (
                  <p className="text-sm text-amber-700 dark:text-amber-300">{secretsError}</p>
                ) : null}
                {fieldError("requiredSecretKeys") ? (
                  <p role="alert" className="text-sm text-rose-700 dark:text-rose-300">
                    {fieldError("requiredSecretKeys")}
                  </p>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <WorkspaceDefaultsCard
            defaultsRecord={onboardingDefaultsRecord}
            description="Seed starts from the org-scoped onboarding defaults saved in Settings so project mapping, baseline policy, and required secrets do not need to be retyped."
          />

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Seed summary</CardTitle>
              <CardDescription>
                Confirm the repo, project, branch, and standards choices before you preview or mutate anything.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Owning org" value={selectedOrgLabel} />
              <InfoLine
                label="Repository"
                value={`${draft.githubOwner.trim() || "owner"}/${draft.githubRepo.trim() || "repo"}`}
              />
              <InfoLine label="Visibility" value={humanize(draft.githubVisibility)} />
              <InfoLine label="Project" value={projectSummary} />
              <InfoLine label="Default branch" value={draft.githubDefaultBranch.trim() || "Not set"} />
              <InfoLine
                label="Standards"
                value={`${baselineChannel || "Choose a channel"} • ${draft.standardsPack.trim() || "Choose a pack"}`}
              />
              <InfoLine
                label="Runtime"
                value={`${draft.executionProfile.trim() || "Choose a profile"} • ${draft.maxConcurrentLanes.trim() || "default"} lanes`}
              />
              <InfoLine
                label="Required secrets"
                value={selectedSecretKeys.length ? selectedSecretKeys.join(", ") : "None"}
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Submission readiness</CardTitle>
              <CardDescription>
                Preview and live submission share the same contract inputs, but live seeding adds repository-auth and secret checks.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <SeedReadinessBlock
                title="Dry-run preview"
                description="Renders the approved bundle, records the intended repo and project shape, and does not mutate GitHub."
                errors={validation.previewErrors}
                readyMessage="Preview is ready. Orcha can render the seed bundle and record the onboarding summary."
              />
              <SeedReadinessBlock
                title="Live seed"
                description="Creates or binds the real GitHub targets, registers the product, and runs activation preflight."
                errors={validation.liveErrors}
                readyMessage="Live seed is ready. Installation, project binding, execution profile, and required secret inputs all pass local validation."
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Submit the seed request</CardTitle>
              <CardDescription>
                Dry-run is the default inspection path. Live submission should follow once the preview and guardrails look correct.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {attemptedMode && attemptErrors.length ? (
                <div className="rounded-3xl border border-rose-400/25 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
                  Fix the highlighted seed inputs before continuing.
                </div>
              ) : null}
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                <Button
                  type="button"
                  onClick={() => void submitSeed("preview")}
                  disabled={submittingMode !== null}
                  className="w-full sm:min-w-[240px] sm:w-auto"
                >
                  {submittingMode === "preview" ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Sparkles className="size-4" />
                  )}
                  Run dry-run preview
                </Button>
                <Button
                  type="button"
                  variant="success"
                  onClick={() => void submitSeed("live")}
                  disabled={submittingMode !== null}
                  className="w-full sm:min-w-[240px] sm:w-auto"
                >
                  {submittingMode === "live" ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <ArrowRight className="size-4" />
                  )}
                  Submit live seed
                </Button>
              </div>
              <p className="text-sm text-muted-foreground">
                Live submission stays on the dedicated onboarding result surface instead of dropping you back into the generic product list.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ProductSeedJobPage({
  organizations,
  onboardingDefaultsByOrg,
  actorId,
  actionBusy,
  onRefreshDashboard,
  onProductAction,
}: {
  organizations: OrganizationResponse[];
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg;
  actorId: string;
  actionBusy: string | null;
  onRefreshDashboard: () => Promise<void>;
  onProductAction: (action: ProductAction) => Promise<void>;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { seedJobId = "" } = useParams();
  const locationState = (location.state as ProductSeedJobRouteState | null) ?? null;
  const [job, setJob] = useState<ProductSeedJobResponse | null>(() =>
    locationState?.seedJob?.seed_job_id === seedJobId ? locationState.seedJob : null,
  );
  const [isLoadingJob, setIsLoadingJob] = useState(job === null);
  const [isRefreshingJob, setIsRefreshingJob] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [secrets, setSecrets] = useState<SecretResponse[]>([]);
  const [isLoadingSecrets, setIsLoadingSecrets] = useState(true);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [isSubmittingLive, setIsSubmittingLive] = useState(false);
  const [attemptedLive, setAttemptedLive] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  const loadSeedJob = useEffectEvent(async (refreshOnly = false) => {
    if (!seedJobId) {
      return;
    }
    if (refreshOnly) {
      setIsRefreshingJob(true);
    } else {
      setIsLoadingJob(true);
    }
    setJobError(null);
    try {
      setJob(await operatorApi.getProductSeedJob(seedJobId));
    } catch (loadError) {
      setJobError(loadError instanceof Error ? loadError.message : "Failed to load the seed job.");
    } finally {
      setIsLoadingJob(false);
      setIsRefreshingJob(false);
    }
  });

  const loadSecrets = useEffectEvent(async () => {
    setIsLoadingSecrets(true);
    setSecretsError(null);
    try {
      setSecrets(await operatorApi.listSecrets());
    } catch (loadError) {
      setSecrets([]);
      setSecretsError(loadError instanceof Error ? loadError.message : "Failed to load secret inventory.");
    } finally {
      setIsLoadingSecrets(false);
    }
  });

  useEffect(() => {
    if (locationState?.seedJob?.seed_job_id === seedJobId) {
      setJob(locationState.seedJob);
      setIsLoadingJob(false);
      void loadSeedJob(true);
      return;
    }
    setJob(null);
    void loadSeedJob(false);
  }, [seedJobId, location.key]);

  useEffect(() => {
    void loadSecrets();
  }, []);

  useEffect(() => {
    if (job && !job.dry_run && job.product_id) {
      void onRefreshDashboard();
    }
  }, [job?.seed_job_id, job?.dry_run, job?.product_id]);

  const seedDraft = job ? productSeedDraftFromPayload(job.request_payload) : null;
  const validation = seedDraft
    ? buildProductSeedValidation(seedDraft, secrets, {
        secretInventoryAvailable: !isLoadingSecrets && !secretsError,
      })
    : null;
  const previewOrgMissing = Boolean(job?.dry_run && !organizationExists(job.org_id, organizations));
  const previewRefreshFailed = Boolean(job?.dry_run && jobError);
  const livePromotionBlockedReason = previewRefreshFailed
    ? "This preview could not be reloaded from the API. Recreate the dry-run preview before promoting it to a live seed."
    : previewOrgMissing
      ? "This preview targets an organization that no longer exists in the current local environment. Open Edit seed request, choose an active org, and create a new dry-run preview before promoting it to live."
      : null;
  const selectedOrgLabel = job ? resolveSeedOrgLabel(job.org_id, organizations) : "Unknown";
  const workspaceDefaults = job
    ? resolveOrgOnboardingDefaultsRecord(job.org_id, onboardingDefaultsByOrg)
    : createUnloadedProductOnboardingDefaultsRecord();
  const legacyInstallationId = readLegacyGithubInstallationId(workspaceDefaults);
  const productLinkLabel = job?.product?.name ?? job?.request_payload.product_name ?? "Product";
  const title = job?.dry_run ? "Review seed preview" : "Review onboarding result";
  const seedJobBreadcrumbs = job?.dry_run
    ? [
        { label: "Products", to: "/products" },
        { label: "Seed request", to: "/products/seed" },
        { label: "Preview" },
      ]
    : job?.product_id
      ? [
          { label: "Products", to: "/products" },
          { label: productLinkLabel, to: `/products/${job.product_id}` },
          { label: "Seed result" },
        ]
      : [
          { label: "Products", to: "/products" },
          { label: "Seed result" },
        ];

  async function submitLiveSeed() {
    if (!job || !validation) {
      return;
    }
    if (livePromotionBlockedReason) {
      setLiveError(livePromotionBlockedReason);
      return;
    }
    setAttemptedLive(true);
    setLiveError(null);
    if (validation.liveErrors.length) {
      return;
    }
    setIsSubmittingLive(true);
    try {
      const liveJob = await operatorApi.seedProduct({
        ...job.request_payload,
        installation_id: job.request_payload.installation_id ?? legacyInstallationId ?? null,
        dry_run: false,
      });
      await onRefreshDashboard();
      navigate(`/products/seed/jobs/${liveJob.seed_job_id}`, {
        replace: true,
        state: {
          seedJob: liveJob,
          seedDraft: productSeedDraftFromPayload(liveJob.request_payload),
        } satisfies ProductSeedJobRouteState,
      });
    } catch (submitError) {
      setLiveError(
        submitError instanceof Error
          ? normalizeSeedSubmissionErrorMessage(submitError.message)
          : "Live seed failed.",
      );
    } finally {
      setIsSubmittingLive(false);
    }
  }

  if (isLoadingJob && !job) {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Products"
          title="Load seed job"
          description="Orcha is loading the durable seed job so you can review the onboarding state."
          breadcrumbs={[
            { label: "Products", to: "/products" },
            { label: "Seed result" },
          ]}
          action={
            <Link to="/products" className={buttonLinkClassName("outline")}>
              Back to Products
            </Link>
          }
        />
        <Card className="shadow-none">
          <CardContent className="flex items-center gap-3 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading seed job…
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!job) {
    return (
      <EmptyState
        title="Seed job not found."
        description={jobError ?? "The requested seed job could not be resolved from the operator API."}
        action={
          <Link to="/products" className={buttonLinkClassName()}>
            Back to Products
          </Link>
        }
      />
    );
  }

  const repoOwner = job.repo_summary.owner ?? job.request_payload.github_owner;
  const repoName = job.repo_summary.name ?? job.request_payload.github_repo;
  const repoDefaultBranch = job.repo_summary.default_branch ?? job.request_payload.github_default_branch;
  const repoVisibility = job.repo_summary.visibility ?? job.request_payload.github_visibility;
  const repoDescription = job.repo_summary.description ?? job.request_payload.description ?? "No description";
  const projectTitle = job.project_summary.title ?? job.request_payload.github_project_title ?? job.request_payload.product_name;
  const projectNumber = typeof job.project_summary.number === "number" ? job.project_summary.number : null;
  const projectStatusField = job.project_summary.status_field_name ?? job.request_payload.status_field;
  const projectStatusOptions = normalizeSeedJobSummaryStrings(job.project_summary.status_options);
  const projectFieldNames = normalizeSeedJobProjectFields(job.project_summary.fields)
    .map((field) => (typeof field.name === "string" ? field.name.trim() : ""))
    .filter(Boolean);
  const projectViews = normalizeSeedJobSummaryStrings(job.project_summary.views);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Products"
        title={title}
        description={`${job.request_payload.product_name} • ${repoOwner}/${repoName}`}
        breadcrumbs={seedJobBreadcrumbs}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={statusTone(job.status)}>{humanize(job.status)}</Badge>
            <Button type="button" variant="outline" onClick={() => void loadSeedJob(true)} disabled={isRefreshingJob}>
              {isRefreshingJob ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
              Refresh job
            </Button>
          </div>
        }
      />

      {jobError ? (
        <Card className="border-amber-200 bg-amber-50 shadow-none dark:border-amber-900/60 dark:bg-amber-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-amber-600 dark:text-amber-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">The job surface is showing the last known payload</p>
              <p className="text-sm text-amber-700 dark:text-amber-200">{jobError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {liveError ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Live seed did not complete</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">{liveError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job.error_payload.length ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardHeader>
            <CardTitle>Durable workflow errors</CardTitle>
            <CardDescription>
              The seed job recorded these failures even if the route refreshes later.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {job.error_payload.map((entry) => (
              <div key={`${entry.code}:${entry.recorded_at}`} className="rounded-3xl border border-rose-400/25 bg-rose-500/10 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={statusTone("Failed")}>{entry.code}</Badge>
                  <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                    {formatDateTime(entry.recorded_at)}
                  </span>
                </div>
                <p className="pt-2 text-sm text-rose-700 dark:text-rose-200">{entry.message}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Onboarding summary</CardTitle>
              <CardDescription>
                This route keeps the durable seed outcome visible instead of sending you back to a generic list page.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Owning org" value={selectedOrgLabel} />
              <InfoLine label="Mode" value={job.dry_run ? "Dry-run preview" : "Live seed"} />
              <InfoLine label="Repository" value={`${repoOwner}/${repoName}`} />
              <InfoLine label="Default branch" value={repoDefaultBranch} />
              <InfoLine label="Project" value={projectNumber !== null ? `${projectTitle} (#${projectNumber})` : projectTitle} />
              <InfoLine
                label="Standards"
                value={`${job.request_payload.baseline_channel ?? "stable"} • ${job.request_payload.standards_pack ?? "default"}`}
              />
              <InfoLine label="Setup state" value={humanize(job.setup_state ?? "ready")} />
              <InfoLine label="Requested by" value={job.requested_by ?? "Unknown"} />
              <InfoLine label="Finished" value={formatDateTime(job.finished_at ?? job.updated_at)} />
              {!job.dry_run && job.product_id ? (
                <InfoLine
                  label="Product route"
                  value={
                    <Link className="text-primary hover:text-foreground" to={`/products/${job.product_id}`}>
                      {productLinkLabel}
                    </Link>
                  }
                />
              ) : null}
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Setup diagnostics</CardTitle>
              <CardDescription>
                Activation blockers and advisory findings are preserved on the seed job alongside the product record.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {job.setup_diagnostics.length ? (
                job.setup_diagnostics.map((diagnostic) => (
                  <div
                    key={`${diagnostic.code}:${diagnostic.message}`}
                    className="rounded-3xl border border-border/70 bg-muted/30 p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge className={diagnosticTone(diagnostic.classification)}>
                        {humanize(diagnostic.classification)}
                      </Badge>
                      <p className="font-medium text-foreground">{diagnostic.code}</p>
                    </div>
                    <p className="pt-2 text-sm text-muted-foreground">{diagnostic.message}</p>
                    {diagnostic.path ? (
                      <p className="pt-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        {diagnostic.path}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <EmptyState
                  title="No setup diagnostics were recorded."
                  description="This job did not surface any contract, branch-protection, or secret blockers."
                />
              )}
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Progress and audit trail</CardTitle>
              <CardDescription>
                Dry-run and live seed both append durable progress entries so the onboarding path is reviewable after the request completes.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {job.progress_payload.length ? (
                <div className="space-y-3">
                  {job.progress_payload.map((entry) => (
                    <div key={`${entry.step}:${entry.recorded_at}`} className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge className={statusTone(entry.status)}>{humanize(entry.status)}</Badge>
                        <p className="font-medium text-foreground">{humanize(entry.step)}</p>
                        <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                          {formatDateTime(entry.recorded_at)}
                        </span>
                      </div>
                      <p className="pt-2 text-sm text-muted-foreground">{entry.message}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No progress entries were recorded."
                  description="The seed job did not append any step-level progress messages."
                />
              )}
              {job.audit_payload.length ? (
                <div className="space-y-3">
                  {job.audit_payload.map((entry) => (
                    <div key={`${entry.step}:${entry.recorded_at}`} className="rounded-3xl border border-border/70 bg-background px-4 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge className={statusTone(entry.status)}>{humanize(entry.status)}</Badge>
                        <p className="font-medium text-foreground">{entry.message}</p>
                      </div>
                      <p className="pt-2 text-sm text-muted-foreground">
                        {humanize(entry.step)} • {formatDateTime(entry.recorded_at)}
                      </p>
                      {buildAuditDetailsSummary(entry.details) ? (
                        <p className="pt-2 text-sm text-muted-foreground">{buildAuditDetailsSummary(entry.details)}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {job.dry_run && validation ? (
            <Card className="shadow-none">
              <CardHeader>
                <CardTitle>Promote preview to live seed</CardTitle>
                <CardDescription>
                  Use the durable preview output to confirm the GitHub target, then run the real seed when the remaining live checks are clear.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <SeedReadinessBlock
                  title="Live guardrails"
                  description="Live seed requires a connected Git repository profile plus any selected secret keys with stored values."
                  errors={validation.liveErrors}
                  readyMessage="The preview request can be promoted directly into a live seed."
                />
                {attemptedLive && validation.liveErrors.length ? (
                  <div className="rounded-3xl border border-rose-400/25 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
                    Fix the remaining live blockers before promoting this preview.
                  </div>
                ) : null}
                {secretsError ? (
                  <p className="text-sm text-amber-700 dark:text-amber-300">{secretsError}</p>
                ) : null}
                {livePromotionBlockedReason ? (
                  <div className="rounded-3xl border border-amber-400/25 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
                    {livePromotionBlockedReason}
                  </div>
                ) : null}
                <div className="flex flex-col items-start gap-3">
                  <Button
                    type="button"
                    variant="success"
                    onClick={() => void submitLiveSeed()}
                    disabled={isSubmittingLive || Boolean(livePromotionBlockedReason)}
                    className="w-full sm:w-[200px]"
                  >
                    {isSubmittingLive ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
                    Run live seed
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full sm:w-[200px]"
                    onClick={() =>
                      navigate("/products/seed", {
                        state: {
                          seedDraft: productSeedDraftFromPayload(job.request_payload),
                        } satisfies ProductSeedDraftState,
                      })
                    }
                  >
                    Edit seed request
                  </Button>
                </div>
                {isSubmittingLive ? (
                  <div className="rounded-3xl border border-emerald-400/25 bg-emerald-500/10 p-4 text-sm text-emerald-900 dark:text-emerald-100">
                    <div className="flex items-center gap-2 font-medium text-foreground">
                      <Loader2 className="size-4 animate-spin" />
                      Live seed is running
                    </div>
                    <p className="pt-2 text-muted-foreground">
                      Expected phases: repository prep, project prep, baseline file writes, then activation checks. The route
                      will switch to the durable onboarding result as soon as the API call returns.
                    </p>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : job.product ? (
            <OnboardingFollowUpCard
              product={job.product}
              actorId={actorId}
              actionBusy={actionBusy}
              onProductAction={onProductAction}
              defaultRepoRoot={REFRESH_REPO_ROOT_HINT}
          defaultRefreshReason="Refresh seeded product contract from the onboarding result."
          buttonClassName={COMPACT_ACTION_BUTTON_CLASS}
          onAfterRefresh={async () => {
            await loadSeedJob(true);
          }}
        />
          ) : (
            <Card className="shadow-none">
              <CardHeader>
                <CardTitle>Next operator action</CardTitle>
                <CardDescription>
                  Continue directly into Products or Fleet when the seed job does not yet have a persisted product summary attached.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Link to="/products" className={buttonLinkClassName("outline")}>
                  Back to Products
                </Link>
                <Link to="/" className={buttonLinkClassName("outline")}>
                  Open Fleet
                </Link>
              </CardContent>
            </Card>
          )}

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>GitHub target shape</CardTitle>
              <CardDescription>
                The job records the exact repo and project summaries used during preview or live preflight.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Repo visibility" value={humanize(repoVisibility)} />
              <InfoLine label="Repo description" value={repoDescription} />
              <InfoLine label="Project title" value={projectTitle} />
              <InfoLine label="Status field" value={projectStatusField} />
              <InfoLine label="Status options" value={projectStatusOptions.length ? projectStatusOptions.join(", ") : "No status options recorded"} />
              <InfoLine
                label="Project fields"
                value={projectFieldNames.join(", ") || "No fields recorded"}
              />
              <InfoLine
                label="Views"
                value={projectViews.length ? projectViews.join(", ") : "No views recorded"}
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Rendered bundle</CardTitle>
              <CardDescription>
                Dry-run and live seed both keep the rendered file list for review.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-foreground">Rendered files</p>
                  <Badge className="border-border bg-secondary text-secondary-foreground">
                    {job.rendered_file_paths.length}
                  </Badge>
                </div>
                {job.rendered_file_paths.length ? (
                  <div className="mt-3 max-h-72 space-y-2 overflow-auto pr-1">
                    {job.rendered_file_paths.map((path) => (
                      <div key={path} className="rounded-2xl border border-border/70 bg-background px-3 py-2 text-sm text-foreground">
                        {path}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="pt-3 text-sm text-muted-foreground">No rendered file paths were recorded.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ProductAdoptionPage({
  user,
  organizations,
  products,
  onboardingDefaultsByOrg,
}: {
  user: UserInfo;
  organizations: OrganizationResponse[];
  products: ProductSummaryResponse[];
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as ProductAdoptionDraftState | null) ?? null;
  const [draft, setDraft] = useState(() =>
    createProductAdoptionDraft({
      user,
      organizations,
      products,
      onboardingDefaultsByOrg,
      adoptionDraft: locationState?.adoptionDraft,
    }),
  );
  const [attemptedPreview, setAttemptedPreview] = useState(false);
  const [submittingPreview, setSubmittingPreview] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  useEffect(() => {
    if (locationState?.adoptionDraft) {
      setDraft(
        createProductAdoptionDraft({
          user,
          organizations,
          products,
          onboardingDefaultsByOrg,
          adoptionDraft: locationState.adoptionDraft,
        }),
      );
      setAttemptedPreview(false);
      setSubmissionError(null);
    }
  }, [location.key]);

  useEffect(() => {
    setDraft((current) => {
      const preferredOrgId = user.default_org_id ?? organizations[0]?.org_id ?? user.org_ids[0] ?? current.orgId;
      const hasOrg =
        !current.orgId.trim() || organizations.length === 0 || organizations.some((org) => org.org_id === current.orgId);
      const nextOrgId = hasOrg ? current.orgId || preferredOrgId : preferredOrgId;
      const defaultOwner = resolveDefaultSeedGithubOwner(nextOrgId, organizations, products);
      const shouldRefreshOwner = shouldRefreshDefaultGithubOwner(current.repositoryOwner, nextOrgId, organizations);
      if (nextOrgId === current.orgId && (!shouldRefreshOwner || current.repositoryOwner === defaultOwner)) {
        return current;
      }
      const nextDraft = {
        ...current,
        orgId: nextOrgId,
        repositoryOwner: shouldRefreshOwner ? defaultOwner : current.repositoryOwner,
      };
      return nextOrgId !== current.orgId
        ? applyAdoptionOnboardingDefaults(
            nextDraft,
            resolveOrgOnboardingDefaultsRecord(nextOrgId, onboardingDefaultsByOrg),
          )
        : nextDraft;
    });
  }, [
    user.default_org_id,
    user.org_ids.join("|"),
    organizations.map((org) => `${org.org_id}:${org.slug}`).join("|"),
    products.map((product) => `${product.org_id}:${product.primary_repo?.owner ?? ""}`).join("|"),
    Object.keys(onboardingDefaultsByOrg).join("|"),
  ]);

  const onboardingDefaultsRecord = resolveOrgOnboardingDefaultsRecord(draft.orgId, onboardingDefaultsByOrg);
  const validation = buildProductAdoptionValidation(draft, products);
  const activeFieldErrors = attemptedPreview ? validation.previewFieldErrors : {};
  const baselineChannel = resolveAdoptionBaselineChannel(draft);
  const selectedOrgLabel = resolveSeedOrgLabel(draft.orgId, organizations);
  const statusOptions = parseStatusOptions(draft.statusOptionsText);

  function fieldError(field: keyof ProductAdoptionFieldErrors) {
    return attemptedPreview ? activeFieldErrors[field] : undefined;
  }

  function updateDraft(updater: (current: ProductAdoptionDraft) => ProductAdoptionDraft) {
    setSubmissionError(null);
    setDraft((current) => updater(current));
  }

  function handleOrgChange(nextOrgId: string) {
    updateDraft((current) => {
      const previousDefaultOwner = resolveDefaultSeedGithubOwner(current.orgId, organizations, products);
      const nextDefaultOwner = resolveDefaultSeedGithubOwner(nextOrgId, organizations, products);
      return applyAdoptionOnboardingDefaults(
        {
          ...current,
          orgId: nextOrgId,
          repositoryOwner:
            !current.repositoryOwner.trim() || current.repositoryOwner === previousDefaultOwner
              ? nextDefaultOwner
              : current.repositoryOwner,
        },
        resolveOrgOnboardingDefaultsRecord(nextOrgId, onboardingDefaultsByOrg),
      );
    });
  }

  async function submitPreview() {
    setAttemptedPreview(true);
    setSubmissionError(null);
    if (validation.previewErrors.length) {
      return;
    }
    setSubmittingPreview(true);
    try {
      const adoptionResult = await operatorApi.dryRunProductAdoption(buildProductAdoptionPayload(draft));
      navigate("/products/adopt/review", {
        state: {
          adoptionDraft: draft,
          adoptionResult,
        } satisfies ProductAdoptionRouteState,
      });
    } catch (submitError) {
      setSubmissionError(submitError instanceof Error ? submitError.message : "Adoption preview failed.");
    } finally {
      setSubmittingPreview(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Products"
        title="Adopt an existing repo"
        description="Capture the repo and project snapshot, run the dry-run contract check first, and only promote the adoption after the preview makes the next setup step clear."
        breadcrumbs={[
          { label: "Products", to: "/products" },
          { label: "Adoption request" },
        ]}
        action={
          <div className="flex flex-wrap gap-2">
            <Link to="/products" className={buttonLinkClassName("outline")}>
              Back to Products
            </Link>
            <Link to="/" className={buttonLinkClassName("outline")}>
              Open Fleet
            </Link>
          </div>
        }
      />

      {submissionError ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Adoption preview was not accepted</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">{submissionError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Identity and local repo context</CardTitle>
              <CardDescription>
                Bind the product identity to the repository root that the adoption dry run should validate.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <SeedField
                  label="Owning org"
                  htmlFor="adopt-org"
                  hint="The adopted product will be registered under this organization."
                  error={fieldError("orgId")}
                  required
                >
                  <Select
                    id="adopt-org"
                    value={draft.orgId}
                    onChange={(event) => handleOrgChange(event.target.value)}
                    aria-invalid={Boolean(fieldError("orgId"))}
                    className="border-input bg-background/90 text-foreground"
                  >
                    {[draft.orgId, ...organizations.map((org) => org.org_id)]
                      .filter((value, index, values) => Boolean(value) && values.indexOf(value) === index)
                      .map((orgId) => (
                        <option key={orgId} value={orgId}>
                          {resolveSeedOrgLabel(orgId, organizations)}
                        </option>
                      ))}
                  </Select>
                </SeedField>
                <SeedField
                  label="Local repo root"
                  htmlFor="adopt-repo-root"
                  hint="Dry-run and live adoption both validate this repository path on the operator host."
                  error={fieldError("repoRoot")}
                  required
                >
                  <Input
                    id="adopt-repo-root"
                    value={draft.repoRoot}
                    onChange={(event) => updateDraft((current) => ({ ...current, repoRoot: event.target.value }))}
                    placeholder="/path/to/existing/repo"
                    aria-invalid={Boolean(fieldError("repoRoot"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Product name"
                  htmlFor="adopt-product-name"
                  hint="Shown in Products, Fleet, and follow-up surfaces after adoption."
                  error={fieldError("name")}
                  required
                >
                  <Input
                    id="adopt-product-name"
                    value={draft.name}
                    onChange={(event) =>
                      updateDraft((current) => applyAdoptionProductNameDefaults(current, event.target.value))
                    }
                    placeholder="Atlas"
                    aria-invalid={Boolean(fieldError("name"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Product key"
                  htmlFor="adopt-product-key"
                  hint="Must be unique within the selected organization."
                  error={fieldError("key")}
                  required
                >
                  <Input
                    id="adopt-product-key"
                    value={draft.key}
                    onChange={(event) => updateDraft((current) => ({ ...current, key: event.target.value }))}
                    placeholder="atlas"
                    aria-invalid={Boolean(fieldError("key"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Description"
                  htmlFor="adopt-description"
                  hint="Optional product description recorded on adoption."
                >
                  <Textarea
                    id="adopt-description"
                    value={draft.description}
                    onChange={(event) => updateDraft((current) => ({ ...current, description: event.target.value }))}
                    placeholder="GitHub-native orchestration control plane"
                    rows={4}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Repository and project snapshot</CardTitle>
              <CardDescription>
                The dry run uses this GitHub posture snapshot to classify setup blockers, drift, and advisory follow-up.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <SeedField
                  label="Repository node id"
                  htmlFor="adopt-repo-node-id"
                  hint="Optional, but helps keep adoption bindings precise."
                >
                  <Input
                    id="adopt-repo-node-id"
                    value={draft.githubRepositoryNodeId}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, githubRepositoryNodeId: event.target.value }))
                    }
                    placeholder="R_kgDOB..."
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="GitHub owner"
                  htmlFor="adopt-repo-owner"
                  hint="The owner that already hosts the repository."
                  error={fieldError("repositoryOwner")}
                  required
                >
                  <Input
                    id="adopt-repo-owner"
                    value={draft.repositoryOwner}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, repositoryOwner: event.target.value }))
                    }
                    placeholder="aegroup-io"
                    aria-invalid={Boolean(fieldError("repositoryOwner"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Repository name"
                  htmlFor="adopt-repo-name"
                  hint="Used for both uniqueness checks and product-safe default suggestions."
                  error={fieldError("repositoryName")}
                  required
                >
                  <Input
                    id="adopt-repo-name"
                    value={draft.repositoryName}
                    onChange={(event) =>
                      updateDraft((current) => applyAdoptionRepositoryNameDefaults(current, event.target.value))
                    }
                    placeholder="atlas"
                    aria-invalid={Boolean(fieldError("repositoryName"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Default branch"
                  htmlFor="adopt-default-branch"
                  hint="Adoption records the current protection posture for this branch."
                  error={fieldError("repositoryDefaultBranch")}
                  required
                >
                  <Input
                    id="adopt-default-branch"
                    value={draft.repositoryDefaultBranch}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, repositoryDefaultBranch: event.target.value }))
                    }
                    placeholder="dev"
                    aria-invalid={Boolean(fieldError("repositoryDefaultBranch"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Visibility"
                  htmlFor="adopt-repo-visibility"
                  hint="Snapshot the current repo visibility as part of the adoption review."
                >
                  <Select
                    id="adopt-repo-visibility"
                    value={draft.repositoryVisibility}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        repositoryVisibility: event.target.value as ProductAdoptionDraft["repositoryVisibility"],
                      }))
                    }
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="private">Private</option>
                    <option value="internal">Internal</option>
                    <option value="public">Public</option>
                  </Select>
                </SeedField>
                <SeedField
                  label="Repository description"
                  htmlFor="adopt-repo-description"
                  hint="Optional repo description captured alongside the binding."
                >
                  <Textarea
                    id="adopt-repo-description"
                    value={draft.repositoryDescription}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, repositoryDescription: event.target.value }))
                    }
                    placeholder="Existing product repository"
                    rows={4}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Archived"
                  htmlFor="adopt-repo-archived"
                  hint="Archived repositories stay blocked in setup-needed even if the contract otherwise parses cleanly."
                >
                  <Select
                    id="adopt-repo-archived"
                    value={draft.repositoryArchived ? "true" : "false"}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        repositoryArchived: event.target.value === "true",
                      }))
                    }
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="false">No</option>
                    <option value="true">Yes</option>
                  </Select>
                </SeedField>
                <SeedField
                  label="Project node id"
                  htmlFor="adopt-project-node-id"
                  hint="Optional, but recommended when the GitHub Project is already mirrored elsewhere."
                >
                  <Input
                    id="adopt-project-node-id"
                    value={draft.projectNodeId}
                    onChange={(event) => updateDraft((current) => ({ ...current, projectNodeId: event.target.value }))}
                    placeholder="PVT_kwDOB..."
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Project number"
                  htmlFor="adopt-project-number"
                  hint="The primary GitHub Project number that Orcha should mirror."
                  error={fieldError("projectNumber")}
                  required
                >
                  <Input
                    id="adopt-project-number"
                    value={draft.projectNumber}
                    onChange={(event) => updateDraft((current) => ({ ...current, projectNumber: event.target.value }))}
                    inputMode="numeric"
                    placeholder="4"
                    aria-invalid={Boolean(fieldError("projectNumber"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Project title"
                  htmlFor="adopt-project-title"
                  hint="Defaults toward the product name so the review surface stays readable."
                  error={fieldError("projectTitle")}
                  required
                >
                  <Input
                    id="adopt-project-title"
                    value={draft.projectTitle}
                    onChange={(event) => updateDraft((current) => ({ ...current, projectTitle: event.target.value }))}
                    placeholder="Atlas"
                    aria-invalid={Boolean(fieldError("projectTitle"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Status field"
                  htmlFor="adopt-status-field"
                  hint="Compared against the repo contract during adoption refresh."
                  error={fieldError("statusFieldName")}
                  required
                >
                  <Input
                    id="adopt-status-field"
                    value={draft.statusFieldName}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, statusFieldName: event.target.value }))
                    }
                    placeholder="Status"
                    aria-invalid={Boolean(fieldError("statusFieldName"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Status options"
                  htmlFor="adopt-status-options"
                  hint="Comma or newline separated. The contract typically expects Todo, In Progress, and Done."
                  error={fieldError("statusOptions")}
                  required
                >
                  <Textarea
                    id="adopt-status-options"
                    value={draft.statusOptionsText}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, statusOptionsText: event.target.value }))
                    }
                    placeholder="Todo, In Progress, Done"
                    rows={4}
                    aria-invalid={Boolean(fieldError("statusOptions"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Baseline and GitHub posture</CardTitle>
              <CardDescription>
                Adoption uses explicit branch-protection and permission snapshots so setup-needed outcomes never arrive as a surprise.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <SeedField
                  label="Baseline preset"
                  htmlFor="adopt-baseline-mode"
                  hint="Use stable unless this repository is already aligned to a promoted channel."
                  error={fieldError("baselineChannel")}
                  required
                >
                  <Select
                    id="adopt-baseline-mode"
                    value={draft.baselineMode}
                    onChange={(event) =>
                      updateDraft((current) => ({
                        ...current,
                        baselineMode: event.target.value as ProductAdoptionBaselineMode,
                      }))
                    }
                    aria-invalid={Boolean(fieldError("baselineChannel"))}
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="stable">Stable</option>
                    <option value="candidate">Candidate</option>
                    <option value="custom">Custom channel</option>
                  </Select>
                </SeedField>
                {draft.baselineMode === "custom" ? (
                  <SeedField
                    label="Custom baseline channel"
                    htmlFor="adopt-custom-baseline"
                    hint="Keep this aligned with the standards pack already applied to the repository."
                    error={fieldError("baselineChannel")}
                    required
                  >
                    <Input
                      id="adopt-custom-baseline"
                      value={draft.customBaselineChannel}
                      onChange={(event) =>
                        updateDraft((current) => ({ ...current, customBaselineChannel: event.target.value }))
                      }
                      placeholder="release-2026-q1"
                      aria-invalid={Boolean(fieldError("baselineChannel"))}
                      className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                    />
                  </SeedField>
                ) : null}
                <SeedField
                  label="Agent-core version"
                  htmlFor="adopt-agent-core-version"
                  hint="Recorded on the product so the adopted repo stays traceable to the current baseline family."
                  error={fieldError("agentCoreVersion")}
                  required
                >
                  <Input
                    id="adopt-agent-core-version"
                    value={draft.agentCoreVersion}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, agentCoreVersion: event.target.value }))
                    }
                    placeholder="0.1.0"
                    aria-invalid={Boolean(fieldError("agentCoreVersion"))}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </SeedField>
                <SeedField
                  label="Execution profile"
                  htmlFor="adopt-execution-profile"
                  hint="Adoption records the profile that future dispatch and validation should expect."
                  error={fieldError("executionProfile")}
                  required
                >
                  <Select
                    id="adopt-execution-profile"
                    value={draft.executionProfile}
                    onChange={(event) =>
                      updateDraft((current) => ({ ...current, executionProfile: event.target.value }))
                    }
                    aria-invalid={Boolean(fieldError("executionProfile"))}
                    className="border-input bg-background/90 text-foreground"
                  >
                    <option value="standard-python">standard-python</option>
                  </Select>
                </SeedField>
              </div>

              <div className="space-y-4 rounded-3xl border border-border/70 bg-muted/30 p-4">
                <div>
                  <p className="font-medium text-foreground">Branch protection snapshot</p>
                  <p className="text-sm text-muted-foreground">
                    Preview uses these inputs to show whether the repo can enter adoption safely or remain setup-needed.
                  </p>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <SeedField label="Protection enabled" htmlFor="adopt-protection-enabled">
                    <Select
                      id="adopt-protection-enabled"
                      value={draft.branchProtectionEnabled ? "true" : "false"}
                      onChange={(event) =>
                        updateDraft((current) => ({
                          ...current,
                          branchProtectionEnabled: event.target.value === "true",
                        }))
                      }
                      className="border-input bg-background/90 text-foreground"
                    >
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </Select>
                  </SeedField>
                  <SeedField label="Pull requests required" htmlFor="adopt-protection-pr-required">
                    <Select
                      id="adopt-protection-pr-required"
                      value={draft.branchProtectionRequiresPullRequest ? "true" : "false"}
                      onChange={(event) =>
                        updateDraft((current) => ({
                          ...current,
                          branchProtectionRequiresPullRequest: event.target.value === "true",
                        }))
                      }
                      className="border-input bg-background/90 text-foreground"
                    >
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </Select>
                  </SeedField>
                  <SeedField label="Approving reviews" htmlFor="adopt-protection-approvals">
                    <Input
                      id="adopt-protection-approvals"
                      value={draft.branchProtectionApprovals}
                      onChange={(event) =>
                        updateDraft((current) => ({ ...current, branchProtectionApprovals: event.target.value }))
                      }
                      inputMode="numeric"
                      placeholder="1"
                      className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                    />
                  </SeedField>
                  <SeedField label="Force pushes allowed" htmlFor="adopt-protection-force-push">
                    <Select
                      id="adopt-protection-force-push"
                      value={draft.branchProtectionAllowsForcePushes ? "true" : "false"}
                      onChange={(event) =>
                        updateDraft((current) => ({
                          ...current,
                          branchProtectionAllowsForcePushes: event.target.value === "true",
                        }))
                      }
                      className="border-input bg-background/90 text-foreground"
                    >
                      <option value="false">No</option>
                      <option value="true">Yes</option>
                    </Select>
                  </SeedField>
                  <SeedField label="Deletions allowed" htmlFor="adopt-protection-deletions">
                    <Select
                      id="adopt-protection-deletions"
                      value={draft.branchProtectionAllowsDeletions ? "true" : "false"}
                      onChange={(event) =>
                        updateDraft((current) => ({
                          ...current,
                          branchProtectionAllowsDeletions: event.target.value === "true",
                        }))
                      }
                      className="border-input bg-background/90 text-foreground"
                    >
                      <option value="false">No</option>
                      <option value="true">Yes</option>
                    </Select>
                  </SeedField>
                </div>
              </div>

              <div className="space-y-4 rounded-3xl border border-border/70 bg-muted/30 p-4">
                <div>
                  <p className="font-medium text-foreground">GitHub permission snapshot</p>
                  <p className="text-sm text-muted-foreground">
                    Product-safe defaults assume write access for the repo, pull requests, issues, and projects.
                  </p>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  {ADOPTION_PERMISSION_FIELDS.map(({ label, field }) => (
                    <SeedField key={field} label={label} htmlFor={`adopt-permission-${field}`}>
                      <Select
                        id={`adopt-permission-${field}`}
                        value={draft[field]}
                        onChange={(event) =>
                          updateDraft((current) => ({
                            ...current,
                            [field]: event.target.value as ProductAdoptionPermissionLevel,
                          }))
                        }
                        className="border-input bg-background/90 text-foreground"
                      >
                        {ADOPTION_PERMISSION_LEVEL_OPTIONS.map((value) => (
                          <option key={value} value={value}>
                            {humanize(value)}
                          </option>
                        ))}
                      </Select>
                    </SeedField>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <WorkspaceDefaultsCard
            defaultsRecord={onboardingDefaultsRecord}
            description="Adoption starts from the same org defaults used by seeding so baseline, execution, and project-field expectations stay aligned."
          />

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Adoption summary</CardTitle>
              <CardDescription>
                Keep the repo, project, baseline, and execution context visible before you ask the backend to validate anything.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Owning org" value={selectedOrgLabel} />
              <InfoLine
                label="Repository"
                value={`${draft.repositoryOwner.trim() || "owner"}/${draft.repositoryName.trim() || "repo"}`}
              />
              <InfoLine label="Repo root" value={draft.repoRoot.trim() || "Not set"} />
              <InfoLine label="Project" value={`${draft.projectTitle.trim() || "Project"} (#${draft.projectNumber.trim() || "?"})`} />
              <InfoLine label="Status field" value={draft.statusFieldName.trim() || "Not set"} />
              <InfoLine label="Status options" value={statusOptions.length ? statusOptions.join(", ") : "None"} />
              <InfoLine label="Baseline" value={`${baselineChannel || "Choose a channel"} • ${draft.agentCoreVersion.trim() || "version?"}`} />
              <InfoLine label="Execution" value={draft.executionProfile.trim() || "Choose a profile"} />
              <InfoLine
                label="Branch protection"
                value={
                  draft.branchProtectionEnabled
                    ? `${draft.branchProtectionRequiresPullRequest ? "PRs required" : "Direct merges allowed"} • ${draft.branchProtectionApprovals.trim() || "0"} review(s)`
                    : "Protection disabled"
                }
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Dry-run readiness</CardTitle>
              <CardDescription>
                The preview validates the current contract and GitHub snapshot before you decide whether live adoption is acceptable.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <SeedReadinessBlock
                title="Preview request"
                description="Dry-run adoption validates the repo contract and classifies blocking setup errors, recoverable drift, and advisory warnings without persisting the product."
                errors={validation.previewErrors}
                readyMessage="Preview is ready. Run the dry-run adoption to inspect compatibility and follow-up work."
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Run adoption preview</CardTitle>
              <CardDescription>
                Live adoption is only available from the preview surface so operators always review the diagnostics first.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {attemptedPreview && validation.previewErrors.length ? (
                <div className="rounded-3xl border border-rose-400/25 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-300">
                  Fix the highlighted adoption inputs before running the preview.
                </div>
              ) : null}
              <Button
                type="button"
                onClick={() => void submitPreview()}
                disabled={submittingPreview}
                className="w-full bg-primary text-primary-foreground hover:bg-primary/90"
              >
                {submittingPreview ? <Loader2 className="size-4 animate-spin" /> : <Waypoints className="size-4" />}
                Run dry-run adoption
              </Button>
              <p className="text-sm text-muted-foreground">
                The preview route keeps setup-needed blockers, drift, and advisory findings visible before any product record is committed.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ProductAdoptionReviewPage({
  organizations,
  products,
  actorId,
  actionBusy,
  onRefreshDashboard,
  onProductAction,
}: {
  organizations: OrganizationResponse[];
  products: ProductSummaryResponse[];
  actorId: string;
  actionBusy: string | null;
  onRefreshDashboard: () => Promise<void>;
  onProductAction: (action: ProductAction) => Promise<void>;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { productId = "" } = useParams();
  const locationState = (location.state as ProductAdoptionRouteState | null) ?? null;
  const fallbackProduct = productId ? products.find((product) => product.product_id === productId) ?? null : null;
  const persistedResult = fallbackProduct ? { dry_run: false, product: fallbackProduct } : null;
  const adoptionResult = productId ? persistedResult ?? locationState?.adoptionResult ?? null : locationState?.adoptionResult ?? null;
  const draft = locationState?.adoptionDraft ?? null;
  const [isSubmittingLive, setIsSubmittingLive] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  if (!adoptionResult) {
    return (
      <EmptyState
        title="Adoption review is unavailable."
        description="Run the dry-run adoption again from Products to review the repo compatibility and decide whether to persist the product."
        action={
          <Link to="/products/adopt" className={buttonLinkClassName()}>
            Open adoption flow
          </Link>
        }
      />
    );
  }

  const product = adoptionResult.product;
  const repo = product.primary_repo;
  const project = product.primary_project;
  const diagnosticBuckets = computeDiagnosticBuckets(product.setup_diagnostics);
  const managedAssetCounts = computeManagedAssetCounts(product.managed_assets);
  const hasBlockingDiagnostics = diagnosticBuckets.blocking.length > 0;
  const branchProtectionSnapshot =
    typeof repo?.raw_payload?.default_branch_protection === "object" && repo?.raw_payload?.default_branch_protection
      ? (repo.raw_payload.default_branch_protection as ProductAdoptionBranchProtectionSnapshot)
      : null;
  const permissionsSnapshot =
    typeof repo?.raw_payload?.orcha_permissions === "object" && repo?.raw_payload?.orcha_permissions
      ? (repo.raw_payload.orcha_permissions as ProductAdoptionPermissionsSnapshot)
      : null;
  const adoptionBreadcrumbs = adoptionResult.dry_run
    ? [
        { label: "Products", to: "/products" },
        { label: "Adoption request", to: "/products/adopt" },
        { label: "Preview" },
      ]
    : [
        { label: "Products", to: "/products" },
        { label: product.name, to: `/products/${product.product_id}` },
        { label: "Adoption result" },
      ];

  async function proceedLiveAdoption() {
    if (!draft) {
      return;
    }
    setLiveError(null);
    setIsSubmittingLive(true);
    try {
      const liveResult = await operatorApi.adoptProduct(buildProductAdoptionPayload(draft));
      await onRefreshDashboard();
      navigate(`/products/adopt/review/${liveResult.product.product_id}`, {
        replace: true,
        state: {
          adoptionDraft: draft,
          adoptionResult: liveResult,
        } satisfies ProductAdoptionRouteState,
      });
    } catch (submitError) {
      setLiveError(submitError instanceof Error ? submitError.message : "Live adoption failed.");
    } finally {
      setIsSubmittingLive(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Products"
        title={adoptionResult.dry_run ? "Review adoption preview" : "Review onboarding result"}
        description={`${product.name} • ${repo ? `${repo.owner}/${repo.name}` : "Repository snapshot unavailable"}`}
        breadcrumbs={adoptionBreadcrumbs}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={statusTone(product.status)}>{humanize(product.status)}</Badge>
            <Badge className={statusTone(product.setup_state)}>{humanize(product.setup_state)}</Badge>
          </div>
        }
      />

      {!locationState?.adoptionResult && fallbackProduct ? (
        <Card className="border-amber-200 bg-amber-50 shadow-none dark:border-amber-900/60 dark:bg-amber-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-amber-600 dark:text-amber-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Showing persisted product context only</p>
              <p className="text-sm text-amber-700 dark:text-amber-200">
                The preview request was not preserved across refresh, so this route is using the current product summary from the dashboard.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {liveError ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Live adoption did not complete</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">{liveError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Onboarding summary</CardTitle>
              <CardDescription>
                Repo, project, baseline, and execution-profile context stay visible throughout preview and live adoption.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Owning org" value={resolveSeedOrgLabel(product.org_id, organizations)} />
              <InfoLine label="Mode" value={adoptionResult.dry_run ? "Dry-run preview" : "Live adoption"} />
              <InfoLine label="Repository" value={repo ? `${repo.owner}/${repo.name}` : "Not bound"} />
              <InfoLine label="Repo root" value={draft?.repoRoot ?? "Preview request not available"} />
              <InfoLine label="Default branch" value={repo?.default_branch ?? "Unknown"} />
              <InfoLine label="Project" value={project ? `${project.title} (#${project.number})` : "Not mirrored"} />
              <InfoLine label="Status field" value={project?.status_field_name ?? "Unknown"} />
              <InfoLine label="Status options" value={project?.status_options.join(", ") ?? "Unknown"} />
              <InfoLine label="Baseline channel" value={product.baseline_channel ?? "Unknown"} />
              <InfoLine label="Execution profile" value={product.execution_profile ?? "Unknown"} />
              <InfoLine label="Setup state" value={humanize(product.setup_state)} />
            </CardContent>
          </Card>

          <SetupFindingsCard
            title="Compatibility results"
            description="Blocking setup errors, recoverable drift, and advisory warnings are rendered separately so operators can judge the adoption outcome clearly."
            diagnostics={product.setup_diagnostics}
          />

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Managed asset posture</CardTitle>
              <CardDescription>
                Adoption surfaces baseline drift explicitly instead of trying to remediate it inline.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Assets</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{product.managed_assets.length}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Current</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{managedAssetCounts.current ?? 0}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Follow-up</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">
                    {product.managed_assets.length - (managedAssetCounts.current ?? 0)}
                  </p>
                </div>
              </div>
              {product.managed_assets.length ? (
                <div className="space-y-2">
                  {product.managed_assets.slice(0, 8).map((asset) => (
                    <div key={asset.managed_asset_id} className="rounded-2xl border border-border/70 bg-background px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-foreground">{asset.path}</p>
                        <Badge className={statusTone(asset.drift_status ?? "current")}>
                          {humanize(asset.drift_status ?? "current")}
                        </Badge>
                      </div>
                      <p className="pt-1 text-sm text-muted-foreground">{humanize(asset.management_mode)} • {humanize(asset.kind)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No managed assets were recorded on this adoption response.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {adoptionResult.dry_run ? (
            <Card className="shadow-none">
              <CardHeader>
                <CardTitle>Next adoption action</CardTitle>
                <CardDescription>
                  {hasBlockingDiagnostics
                    ? "Blocking setup errors stay visible here. Live adoption will register the product, but it will remain Draft/setup-needed until those blockers are cleared."
                    : "The preview has no blocking setup errors. You can proceed to live adoption with any remaining drift or advisory work still visible."}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <SeedReadinessBlock
                  title="Dry-run outcome"
                  description="Preview is now complete. Live adoption is an explicit follow-up action from this reviewed surface."
                  errors={
                    hasBlockingDiagnostics
                      ? ["Live adoption will keep this product in Draft/setup-needed until blocking diagnostics are resolved."]
                      : []
                  }
                  readyMessage="No blocking setup errors remain in the preview. Live adoption will preserve any drift or advisory follow-up."
                />
                <Button
                  type="button"
                  variant="success"
                  onClick={() => void proceedLiveAdoption()}
                  disabled={isSubmittingLive || !draft}
                  className="w-full"
                >
                  {isSubmittingLive ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
                  {hasBlockingDiagnostics ? "Adopt and keep blockers visible" : "Proceed with live adoption"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={() =>
                    navigate("/products/adopt", {
                      state: {
                        adoptionDraft: draft ?? undefined,
                      } satisfies ProductAdoptionDraftState,
                    })
                  }
                  disabled={!draft}
                >
                  Edit adoption request
                </Button>
              </CardContent>
            </Card>
          ) : (
            <OnboardingFollowUpCard
              product={product}
              actorId={actorId}
              actionBusy={actionBusy}
              onProductAction={onProductAction}
              defaultRepoRoot={draft?.repoRoot ?? REFRESH_REPO_ROOT_HINT}
              defaultRefreshReason="Refresh adopted product contract from the onboarding result."
              onAfterRefresh={async () => {
                await onRefreshDashboard();
              }}
            />
          )}

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>GitHub posture snapshot</CardTitle>
              <CardDescription>
                The repo and project snapshot used during adoption remains visible instead of being hidden behind a transient toast.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Repo visibility" value={repo ? humanize(repo.visibility) : "Unknown"} />
              <InfoLine label="Repo archived" value={repo?.is_archived ? "Yes" : "No"} />
              <InfoLine
                label="Protection"
                value={
                  branchProtectionSnapshot
                    ? `${branchProtectionSnapshot.enabled ? "Enabled" : "Disabled"} • ${
                        branchProtectionSnapshot.requires_pull_request ? "PRs required" : "Direct merges allowed"
                      }`
                    : "Snapshot unavailable"
                }
              />
              <InfoLine
                label="Approvals"
                value={
                  branchProtectionSnapshot?.required_approving_review_count != null
                    ? String(branchProtectionSnapshot.required_approving_review_count)
                    : "Unknown"
                }
              />
              <InfoLine
                label="Force pushes"
                value={branchProtectionSnapshot?.allows_force_pushes ? "Allowed" : "Not allowed"}
              />
              <InfoLine
                label="Deletions"
                value={branchProtectionSnapshot?.allows_deletions ? "Allowed" : "Not allowed"}
              />
              <InfoLine
                label="Permissions"
                value={
                  permissionsSnapshot
                    ? [
                        `Contents ${humanize(String(permissionsSnapshot.contents ?? "unknown"))}`,
                        `PRs ${humanize(String(permissionsSnapshot.pull_requests ?? "unknown"))}`,
                        `Issues ${humanize(String(permissionsSnapshot.issues ?? "unknown"))}`,
                        `Projects ${humanize(String(permissionsSnapshot.projects ?? "unknown"))}`,
                      ].join(" • ")
                    : "Snapshot unavailable"
                }
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function BaselinesPage({
  baselines,
  products,
}: {
  baselines: BaselineResponse[];
  products: ProductSummaryResponse[];
}) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const query = deferredSearch.trim().toLowerCase();
  const hasQuery = query.length > 0;
  const filteredBaselines = query
    ? baselines.filter(
        (baseline) =>
          baseline.product_name.toLowerCase().includes(query) ||
          baseline.product_key.toLowerCase().includes(query) ||
          `${baseline.baseline_channel ?? ""} ${baseline.agent_core_version ?? ""}`
            .toLowerCase()
            .includes(query) ||
          `${baseline.standards_pack_key ?? ""} ${baseline.standards_pack_version ?? ""}`
            .toLowerCase()
            .includes(query),
      )
    : baselines;
  const driftedBaseline = baselines.find((baseline) => baseline.drift_status === "drift");
  const setupWarningProduct = products.find((product) => product.setup_state === "setup-needed");
  const setupReviewTarget = setupWarningProduct ? `/products/${setupWarningProduct.product_id}` : "/products";
  const baselineReviewTarget = driftedBaseline ? `/baselines/${driftedBaseline.product_id}` : "/baselines";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Baselines"
        title="Standards posture, runs, and managed-asset drift"
        description="Baselines is the governance workspace for standards posture. Operators review the current channel and pack, inspect run outcomes, and follow managed-asset or advisory follow-up here; baseline content is still authored in the approved bundle and product repo."
        action={
          <div className="flex w-full flex-col gap-2 lg:w-auto lg:items-end">
            <Link to="/products" className={buttonLinkClassName("outline")}>
              Open Products
            </Link>
            <div className="w-full max-w-sm">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search baselines or packs"
              />
            </div>
          </div>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[1.1fr,0.9fr]">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>What Baselines tracks</CardTitle>
            <CardDescription>
              Baselines is where Orcha reports evaluated standards posture, run history, operator outcomes, and managed assets. Operators review here, but baseline content is still authored in the approved bundle and product repo.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1">
            <InfoLine label="Standards pack" value="Approved channel, version, agent-core version, and latest run outcome" />
            <InfoLine label="Managed assets" value="Current posture, drift counts, and standards follow-up paths" />
            <InfoLine label="Authoring boundary" value="Review here, edit in the repo or standards bundle" />
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle>Where operators usually go next</CardTitle>
            <CardDescription>
              Start new products in Products first. Return to product detail when setup blockers need attention before baseline posture is trustworthy.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Link to="/products" className={buttonLinkClassName()}>
              Open Products
            </Link>
            <Link to={setupReviewTarget} className={buttonLinkClassName("outline")}>
              {setupWarningProduct ? "Review setup blockers" : driftedBaseline ? "Review drift detail" : "Open product workflows"}
            </Link>
          </CardContent>
        </Card>
      </div>

      {!baselines.length ? (
        <EmptyState
          title="No baseline posture is registered yet."
          description="Seed or adopt a product in Products first. Baselines starts filling in after onboarding creates managed-asset state and the first standards evaluation runs against the approved pack."
          action={
            <>
              <Link to="/products" className={buttonLinkClassName()}>
                Open Products
              </Link>
              <Link to="/products/seed" className={buttonLinkClassName("outline")}>
                Seed a product
              </Link>
              <Link to="/products/adopt" className={buttonLinkClassName("outline")}>
                Adopt a repo
              </Link>
              <Link to={setupReviewTarget} className={buttonLinkClassName("outline")}>
                {setupWarningProduct ? "Review setup blockers" : "Open product workflows"}
              </Link>
            </>
          }
        />
      ) : filteredBaselines.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {filteredBaselines.map((baseline) => {
            const diagnosticBuckets = computeDiagnosticBuckets(baseline.setup_diagnostics);
            const blockingCount = diagnosticBuckets.blocking.length || (baseline.setup_state === "setup-needed" ? 1 : 0);
            const advisoryCount = diagnosticBuckets.advisory.length + diagnosticBuckets.other.length;
            const managedAssetFollowUp = countManagedAssetFollowUp(baseline.managed_assets);
            const latestOutcomeSummary = describeStandardsRunStatus(baseline.latest_run);

            return (
              <Card key={baseline.product_id} className="shadow-none">
                <CardHeader>
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-foreground">{baseline.product_name}</CardTitle>
                    <Badge className={statusTone(baseline.drift_status)}>{humanize(baseline.drift_status)}</Badge>
                    <Badge className={statusTone(baseline.setup_state)}>{humanize(baseline.setup_state)}</Badge>
                  </div>
                  <CardDescription className="text-muted-foreground">
                    {baseline.product_key} • {baseline.standards_pack_key ?? "No standards pack"} {baseline.standards_pack_version ?? ""}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Channel</p>
                      <p className="pt-1 text-sm font-medium text-foreground">{baseline.baseline_channel ?? "Unknown"}</p>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Agent Core</p>
                      <p className="pt-1 text-sm font-medium text-foreground">{baseline.agent_core_version ?? "Unknown"}</p>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Managed Follow-up</p>
                      <p className="pt-1 text-2xl font-semibold text-foreground">{managedAssetFollowUp}</p>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Setup Blockers</p>
                      <p className="pt-1 text-2xl font-semibold text-foreground">{blockingCount}</p>
                    </div>
                  </div>
                  <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-foreground">Latest standards outcome</p>
                      {baseline.latest_run ? (
                        <>
                          <Badge className="border-border bg-secondary text-secondary-foreground">
                            {formatStandardsOutcomeKind(baseline.latest_run.outcome_kind)}
                          </Badge>
                          <Badge className={statusTone(baseline.latest_run.outcome_status ?? "unknown")}>
                            {humanize(baseline.latest_run.outcome_status ?? "unknown")}
                          </Badge>
                        </>
                      ) : null}
                    </div>
                    <p className="pt-2 text-sm text-muted-foreground">{latestOutcomeSummary}</p>
                    <p className="pt-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                      {managedAssetFollowUp
                        ? `${managedAssetFollowUp} ${pluralize(managedAssetFollowUp, "managed asset")} currently need drift follow-up.`
                        : `All ${baseline.managed_assets.length} managed ${pluralize(baseline.managed_assets.length, "asset")} are current.`}
                      {advisoryCount
                        ? ` ${advisoryCount} ${pluralize(advisoryCount, "advisory finding")} remain separate from blocking setup.`
                        : " No advisory findings are currently recorded."}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link to={`/baselines/${baseline.product_id}`} className={buttonLinkClassName()}>
                      Open standards workspace
                    </Link>
                    <Link to={`/products/${baseline.product_id}`} className={buttonLinkClassName("outline")}>
                      {blockingCount ? "Open product blockers" : "Open product"}
                    </Link>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="No baselines match the current query."
          description={hasQuery ? "Try a broader product name, channel, or standards pack key." : "Baseline summaries will appear here after the first standards evaluation completes."}
          action={
            hasQuery ? (
              <Link to={baselineReviewTarget} className={buttonLinkClassName("outline")}>
                {driftedBaseline ? "Review drift detail" : "Open Baselines"}
              </Link>
            ) : undefined
          }
        />
      )}
    </div>
  );
}

function ProductDetailPage({
  product,
  lanes,
  baseline,
  graph,
  observability,
  workspaceDefaults,
  actorId,
  actionBusy,
  onProductAction,
}: {
  product: ProductSummaryResponse | null;
  lanes: LaneResponse[];
  baseline: BaselineResponse | null;
  graph: GraphSliceResponse | null;
  observability: FleetObservabilityRecord | null;
  workspaceDefaults: ProductOnboardingDefaultsRecord;
  actorId: string;
  actionBusy: string | null;
  onProductAction: (action: ProductAction) => Promise<void>;
}) {
  const [reason, setReason] = useState("Pause for operator review.");

  if (!product) {
    return <EmptyState title="Product not found." description="The requested product route could not be resolved from the current operator dataset." />;
  }

  const actionReasonInputId = `product-action-reason-${product.product_id}`;
  const productLanes = lanes.filter((item) => item.product_id === product.product_id);
  const runnableLanes = productLanes.filter(
    (item) => !["Cancelled", "FailedTerminal", "HandedOff"].includes(item.state),
  );
  const deliveryCockpit = product.delivery_cockpit ?? null;
  const productLaneIds = new Set(productLanes.map((item) => item.lane_id));
  const laneSummariesById = new Map(
    (observability?.lanes ?? [])
      .filter((item) => item.product_id === product.product_id)
      .map((item) => [item.lane_id, item]),
  );
  const onboardingActivity = resolveProductOnboardingActivity(product);
  const diagnosticBuckets = computeDiagnosticBuckets(product.setup_diagnostics);
  const blockingCount = diagnosticBuckets.blocking.length || (product.setup_state === "setup-needed" ? 1 : 0);
  const advisoryCount = diagnosticBuckets.advisory.length + diagnosticBuckets.other.length;
  const productRuntimeNotifications = (observability?.notifications ?? []).filter((notification) => {
    if (!isRuntimeNotification(notification)) {
      return false;
    }
    if (notification.correlation.product_id === product.product_id) {
      return true;
    }
    return notification.correlation.lane_id ? productLaneIds.has(notification.correlation.lane_id) : false;
  });
  const remediationActions = collectGuidedRemediationActions({
    productId: product.product_id,
    diagnostics: product.setup_diagnostics,
    managedAssets: product.managed_assets,
    onboardingActivity,
    includeBaselineLink: true,
  });
  const managedAssetFollowUp = countManagedAssetFollowUp(product.managed_assets);
  const staleHeartbeatCount = runnableLanes.filter(
    (lane) => resolveLaneHeartbeatStatus(lane, laneSummariesById.get(lane.lane_id)) === "stale",
  ).length;
  const waitingDecisionCount = runnableLanes.filter(
    (lane) => lane.state === "AwaitingApproval" || lane.state === "AwaitingGitHub",
  ).length;
  const readyEnvironmentCount = runnableLanes.filter(
    (lane) => lane.execution_environment?.status === "Ready",
  ).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Product View"
        title={product.name}
        description={product.description ?? "Operator-facing product detail with state, setup, drift, and intervention affordances."}
        breadcrumbs={[
          { label: "Products", to: "/products" },
          { label: product.name },
        ]}
        action={
          <div className="flex flex-wrap gap-2">
            {product.status === "Paused" ? (
              <Button
                variant="success"
                onClick={() =>
                  void onProductAction({
                    kind: "resume",
                    productId: product.product_id,
                    actorId,
                    reason,
                  })
                }
                disabled={actionBusy === `product:resume:${product.product_id}`}
                className={RESUME_BUTTON_CLASS}
              >
                {actionBusy === `product:resume:${product.product_id}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : <PlayCircle className="mr-2 size-4" />}
                Resume
              </Button>
            ) : (
              <Button
                onClick={() =>
                  void onProductAction({
                    kind: "pause",
                    productId: product.product_id,
                    actorId,
                    reason,
                  })
                }
                disabled={actionBusy === `product:pause:${product.product_id}`}
                className={PAUSE_BUTTON_CLASS}
              >
                {actionBusy === `product:pause:${product.product_id}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : <PauseCircle className="mr-2 size-4" />}
                Pause
              </Button>
            )}
              <Link
                to={`/graphs/products/${product.product_id}`}
                className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
              >
                Open graph
              </Link>
          </div>
        }
      />

      {product.setup_state === "setup-needed" ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <TriangleAlert className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Setup blockers need action before resuming work.</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">
                {blockingCount} {pluralize(blockingCount, "blocking diagnostic")} still keep this product out of a safe activation posture. Managed asset drift and advisory findings stay separated below so operators can confirm what is truly blocking lane work.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-foreground">Current posture</CardTitle>
                <Badge className={statusTone(product.status)}>{humanize(product.status)}</Badge>
                <Badge className={statusTone(product.setup_state)}>{humanize(product.setup_state)}</Badge>
                {baseline ? <Badge className={statusTone(baseline.drift_status)}>{humanize(baseline.drift_status)}</Badge> : null}
              </div>
              <CardDescription className="text-muted-foreground">
                Repository binding, config freshness, and managed asset posture in one view.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Repository" value={product.primary_repo ? `${product.primary_repo.owner}/${product.primary_repo.name}` : "Not bound"} />
              <InfoLine label="Baseline channel" value={product.baseline_channel ?? "Not set"} />
              <InfoLine label="Standards pack" value={`${product.standards_pack_key ?? "Unknown"} ${product.standards_pack_version ?? ""}`} />
              <InfoLine label="Execution profile" value={product.execution_profile ?? "Unknown"} />
              <InfoLine label="Last contract refresh" value={formatDateTime(product.last_config_refresh_at)} />
              <InfoLine label="Last accepted config" value={formatDateTime(product.last_accepted_config_at)} />
            </CardContent>
          </Card>

          <ActivationReadinessCard
            description="Activation readiness keeps blocking setup, advisory findings, and managed asset drift separate so operators can see what still blocks lane work."
            setupState={product.setup_state}
            diagnostics={product.setup_diagnostics}
            managedAssets={product.managed_assets}
            lastConfigRefreshAt={product.last_config_refresh_at}
          />

          <ProductDeliveryCockpitCard
            product={product}
            cockpit={deliveryCockpit}
            lanes={productLanes}
            laneSummariesById={laneSummariesById}
            onboardingActivity={onboardingActivity}
            remediationActions={remediationActions}
            actorId={actorId}
            actionBusy={actionBusy}
            onProductAction={onProductAction}
          />

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Runtime and lane health</CardTitle>
              <CardDescription className="text-muted-foreground">
                Runner heartbeat, session wait state, execution environments, and delivery warnings stay visible here without being mixed into setup-needed onboarding blockers.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Active lanes</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{runnableLanes.length}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Waiting decisions</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{waitingDecisionCount}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Healthy environments</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{readyEnvironmentCount}</p>
                  <p className="pt-1 text-sm text-muted-foreground">
                    {staleHeartbeatCount
                      ? `${staleHeartbeatCount} stale ${pluralize(staleHeartbeatCount, "heartbeat")} still need review.`
                      : "No stale runner heartbeats are currently linked to this product."}
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <p className="font-medium text-foreground">Linked runtime warnings</p>
                  <p className="pt-1 text-sm text-muted-foreground">
                    Delivery lag and runner degradation point directly to the affected lane or product route.
                  </p>
                </div>
                <ObservabilityNotificationList
                  notifications={productRuntimeNotifications}
                  emptyTitle="No runtime or delivery warnings are linked to this product."
                  emptyDescription="Setup diagnostics still govern activation readiness. Lane rows below keep current session and environment health visible separately."
                  limit={3}
                />
              </div>

              <div className="space-y-3">
                <div>
                  <p className="font-medium text-foreground">Lane health</p>
                  <p className="pt-1 text-sm text-muted-foreground">
                    Active and recent lanes remain visible here so operators can decide whether to open lane detail, rerun work, or keep focus on onboarding blockers.
                  </p>
                </div>
                {productLanes.length ? (
                  productLanes.map((lane) => {
                    const laneSummary = laneSummariesById.get(lane.lane_id);
                    const heartbeatStatus = resolveLaneHeartbeatStatus(lane, laneSummary);
                    return (
                      <Link
                        key={lane.lane_id}
                        to={`/lanes/${lane.lane_id}`}
                        className="block rounded-3xl border border-border/70 bg-muted/30 p-4 transition hover:border-primary/30"
                      >
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-medium text-foreground">
                              #{lane.work_item.issue_number} {lane.work_item.title}
                            </p>
                            <Badge className={statusTone(lane.state)}>{humanize(lane.state)}</Badge>
                            <Badge className={statusTone(heartbeatStatus)}>{humanize(heartbeatStatus)}</Badge>
                            {lane.agent_session ? (
                              <Badge className="border-border bg-secondary text-secondary-foreground">
                                {humanize(lane.agent_session.status)}
                              </Badge>
                            ) : null}
                            {lane.execution_environment ? (
                              <Badge className="border-border bg-secondary text-secondary-foreground">
                                {humanize(lane.execution_environment.status)}
                              </Badge>
                            ) : null}
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {laneSummary?.summary ?? describeLane(lane)}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {describeLaneRuntimeHealth(lane, laneSummary)}
                          </p>
                          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                            session {formatRelativeTime(lane.agent_session?.heartbeat_at ?? lane.agent_session?.last_event_at ?? null)} • env {formatRelativeTime(lane.execution_environment?.heartbeat_at ?? null)}
                          </p>
                        </div>
                      </Link>
                    );
                  })
                ) : (
                  <EmptyState
                    title="No lanes for this product."
                    description="Use the delivery cockpit above to review ready backlog, GitHub handoff, and the next build step until scheduler-owned lanes appear."
                  />
                )}
              </div>
            </CardContent>
          </Card>

          <GuidedRemediationCard
            title="Guided remediation"
            description="Common blocker classes map to direct next steps instead of leaving setup-needed products stranded in passive warnings."
            actions={remediationActions}
          />

          <SetupFindingsCard
            title="Setup findings"
            description="Every setup diagnostic stays visible here with blocking, recoverable drift, and advisory findings rendered separately."
            diagnostics={product.setup_diagnostics}
          />
        </div>

        <div className="space-y-6">
          <OnboardingActivityPanel
            title="Onboarding activity"
            description="Product detail keeps the latest seed or adoption route one click away so onboarding progress, audit detail, and setup results stay reviewable."
            activities={onboardingActivity ? [onboardingActivity] : []}
            emptyTitle="No onboarding activity is linked."
            emptyDescription="Seed or adopt routes appear here once this product has a durable onboarding result."
            limit={1}
          />

          <WorkspaceDefaultsCard
            defaultsRecord={workspaceDefaults}
            description="Remediation routes keep the saved org defaults visible so operators can confirm whether missing repository policy or secret policy is coming from Settings or the product itself."
          />

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Operator controls</CardTitle>
              <CardDescription className="text-muted-foreground">
                Explicit operator actions are recorded as durable control-plane signals.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField label="Action reason" htmlFor={actionReasonInputId}>
                <Input
                  id={actionReasonInputId}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                />
              </FormField>
              <MirrorRefreshPanel
                productId={product.product_id}
                actorId={actorId}
                actionBusy={actionBusy}
                onProductAction={onProductAction}
                defaultReason={reason.trim() || "Refresh product mirror from GitHub."}
              />
              <ContractRefreshPanel
                productId={product.product_id}
                actorId={actorId}
                actionBusy={actionBusy}
                onProductAction={onProductAction}
                defaultRepoRoot={REFRESH_REPO_ROOT_HINT}
                defaultRefreshReason="Refresh product contract from the tracked repository."
                allowRemoteRefresh={Boolean(product.primary_repo)}
                title="Re-check activation status"
                description="Use the durable refresh endpoint after repo, settings, or secret remediation so the UI reflects the updated setup state."
                buttonLabel="Refresh contract"
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Managed asset drift</CardTitle>
              <CardDescription className="text-muted-foreground">
                Managed asset drift stays adjacent to product decisions, but separate from setup blockers and advisory findings.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {baseline ? (
                <>
                  <div className="flex items-center justify-between rounded-3xl border border-border/70 bg-muted/30 px-4 py-3">
                    <div>
                      <p className="font-medium text-foreground">{humanize(baseline.drift_status)}</p>
                      <p className="text-sm text-muted-foreground">
                        {managedAssetFollowUp
                          ? `${managedAssetFollowUp} ${pluralize(managedAssetFollowUp, "managed asset")} need follow-up out of ${baseline.managed_assets.length}.`
                          : `All ${baseline.managed_assets.length} managed ${pluralize(baseline.managed_assets.length, "asset")} are current.`}
                      </p>
                    </div>
                    <Link
                      to={`/baselines/${baseline.product_id}`}
                      className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
                    >
                      Open baseline
                    </Link>
                  </div>
                  <div className="rounded-3xl border border-border/70 bg-muted/30 px-4 py-3">
                    <p className="font-medium text-foreground">Graph freshness</p>
                    <p className="pt-1 text-sm text-muted-foreground">
                      {graph
                        ? `${humanize(graph.freshness.status)} • generated ${formatRelativeTime(graph.generated_at)}`
                        : "Graph loads on demand for this product."}
                    </p>
                  </div>
                  <div className="rounded-3xl border border-border/70 bg-muted/30 px-4 py-3">
                    <p className="font-medium text-foreground">Advisory and drift separation</p>
                    <p className="pt-1 text-sm text-muted-foreground">
                      {advisoryCount
                        ? `${advisoryCount} ${pluralize(advisoryCount, "advisory finding")} remain visible without being treated as hard blockers.`
                        : "No advisory findings are currently recorded on the product contract."}
                    </p>
                  </div>
                </>
              ) : (
                <EmptyState title="No baseline summary available." description="Baseline read models appear after product adoption and standards evaluation." />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function LaneDetailPage({
  lane,
  actorId,
  actionBusy,
  onLaneAction,
}: {
  lane: LaneResponse | null;
  actorId: string;
  actionBusy: string | null;
  onLaneAction: (action: LaneAction) => Promise<void>;
}) {
  const [reason, setReason] = useState("Operator reviewed the lane state.");
  const [note, setNote] = useState("Proceed with the documented plan.");
  const [disposition, setDisposition] = useState<"terminate" | "quarantine">("terminate");
  const [observability, setObservability] = useState<LaneObservabilityRecord | null>(null);
  const [observabilityLoading, setObservabilityLoading] = useState(false);
  const [observabilityError, setObservabilityError] = useState<string | null>(null);

  const loadLaneObservability = useEffectEvent(async () => {
    if (!lane?.lane_id) {
      startTransition(() => {
        setObservability(null);
        setObservabilityError(null);
      });
      return;
    }
    setObservabilityLoading(true);
    setObservabilityError(null);
    try {
      const nextObservability = await operatorApi.getLaneObservability(lane.lane_id);
      startTransition(() => {
        setObservability(nextObservability);
      });
    } catch (loadError) {
      setObservabilityError(loadError instanceof Error ? loadError.message : "Failed to load lane observability.");
    } finally {
      setObservabilityLoading(false);
    }
  });

  useEffect(() => {
    void loadLaneObservability();
  }, [lane?.lane_id, lane?.updated_at]);

  if (!lane) {
    return <EmptyState title="Lane not found." description="The requested lane route could not be resolved from the current operator dataset." />;
  }

  const currentLane = observability?.lane ?? lane;
  const laneReasonInputId = `lane-action-reason-${currentLane.lane_id}`;
  const laneNoteInputId = `lane-action-note-${currentLane.lane_id}`;
  const heartbeatStatus = observability?.heartbeat_status ?? resolveLaneHeartbeatStatus(currentLane);
  const artifactReferences = observability?.artifact_references ?? {
    workspace_uri: currentLane.execution_environment?.workspace_uri ?? null,
    artifact_uri: currentLane.execution_environment?.artifact_uri ?? null,
    log_uri: currentLane.execution_environment?.log_uri ?? null,
    cache_uri: currentLane.execution_environment?.cache_uri ?? null,
  };
  const actionPanel =
    currentLane.state === "AwaitingApproval" ? (
      <Button
        variant="success"
        onClick={() =>
          void onLaneAction({
            kind: "approve",
            laneId: currentLane.lane_id,
            actorId,
            reason,
            note,
          })
        }
        disabled={actionBusy === `lane:approve:${currentLane.lane_id}`}
        className="w-full"
      >
        {actionBusy === `lane:approve:${currentLane.lane_id}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : <CheckCircle2 className="mr-2 size-4" />}
        Approve lane
      </Button>
    ) : currentLane.state === "AwaitingGitHub" ? (
      <Button
        onClick={() =>
          void onLaneAction({
            kind: "human-input",
            laneId: currentLane.lane_id,
            actorId,
            reason,
            note,
          })
        }
        disabled={actionBusy === `lane:human-input:${currentLane.lane_id}`}
        className="w-full bg-primary text-primary-foreground hover:bg-primary/90"
      >
        {actionBusy === `lane:human-input:${currentLane.lane_id}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Sparkles className="mr-2 size-4" />}
        Submit human input
      </Button>
    ) : currentLane.state === "FailedTerminal" || currentLane.state === "Cancelled" || currentLane.state === "HandedOff" ? (
      <Button
        onClick={() =>
          void onLaneAction({
            kind: "retry",
            laneId: currentLane.lane_id,
            actorId,
            reason,
          })
        }
        disabled={actionBusy === `lane:retry:${currentLane.lane_id}`}
        className="w-full bg-amber-300 text-zinc-950 hover:bg-amber-200"
      >
        {actionBusy === `lane:retry:${currentLane.lane_id}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />}
        Retry lane
      </Button>
    ) : (
      <Button
        onClick={() =>
          void onLaneAction({
            kind: "cancel",
            laneId: currentLane.lane_id,
            actorId,
            reason,
            disposition,
          })
        }
        disabled={actionBusy === `lane:cancel:${currentLane.lane_id}`}
        className="w-full bg-rose-400 text-zinc-950 hover:bg-rose-300"
      >
        {actionBusy === `lane:cancel:${currentLane.lane_id}` ? <Loader2 className="mr-2 size-4 animate-spin" /> : <AlertTriangle className="mr-2 size-4" />}
        Cancel lane
      </Button>
    );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Lane Detail"
        title={`#${currentLane.work_item.issue_number} ${currentLane.work_item.title}`}
        description={observability?.summary ?? describeLane(currentLane)}
        breadcrumbs={[
          { label: "Products", to: "/products" },
          { label: currentLane.product.name, to: `/products/${currentLane.product.product_id}` },
          { label: `Lane #${currentLane.work_item.issue_number}` },
        ]}
        action={
          <div className="flex flex-wrap gap-2">
            <Badge className={statusTone(currentLane.state)}>{humanize(currentLane.state)}</Badge>
            <Badge className={statusTone(heartbeatStatus)}>{humanize(heartbeatStatus)}</Badge>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Execution summary</CardTitle>
              <CardDescription className="text-muted-foreground">
                Work item, branch, and active runtime state in one operator view.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine
                label="Product"
                value={
                  <Link className="text-primary hover:text-foreground" to={`/products/${currentLane.product.product_id}`}>
                    {currentLane.product.name}
                  </Link>
                }
              />
              <InfoLine label="Issue" value={`#${currentLane.work_item.issue_number}`} />
              <InfoLine label="Attempt" value={currentLane.attempt} />
              <InfoLine label="Branch" value={currentLane.branch_name ?? "Not assigned"} />
              <InfoLine label="Claimed" value={formatDateTime(currentLane.claimed_at)} />
              <InfoLine label="Updated" value={formatRelativeTime(currentLane.updated_at)} />
              <InfoLine label="Last error" value={currentLane.last_error ?? "None"} />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Runtime and observability</CardTitle>
              <CardDescription className="text-muted-foreground">
                Runner health, wait state, and artifact references are grouped with the derived observability summary instead of making operators open raw event streams.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Lane summary" value={observability?.summary ?? describeLane(currentLane)} />
              <InfoLine
                label="Heartbeat health"
                value={<Badge className={statusTone(heartbeatStatus)}>{humanize(heartbeatStatus)}</Badge>}
              />
              <InfoLine label="Last activity" value={formatRelativeTime(observability?.last_activity_at ?? currentLane.updated_at)} />
              <InfoLine
                label="Session status"
                value={currentLane.agent_session ? humanize(currentLane.agent_session.status) : "No session"}
              />
              <InfoLine label="Wait reason" value={currentLane.agent_session?.wait_reason ?? "Not waiting"} />
              <InfoLine
                label="Last event"
                value={currentLane.agent_session?.last_event ? humanize(currentLane.agent_session.last_event) : "None"}
              />
              <InfoLine
                label="Session heartbeat"
                value={formatRelativeTime(currentLane.agent_session?.heartbeat_at ?? currentLane.agent_session?.last_event_at ?? null)}
              />
              <InfoLine
                label="Environment status"
                value={currentLane.execution_environment ? humanize(currentLane.execution_environment.status) : "No environment"}
              />
              <InfoLine label="Workspace" value={artifactReferences.workspace_uri ?? "Not attached"} />
              <InfoLine label="Artifact store" value={artifactReferences.artifact_uri ?? "Not attached"} />
              <InfoLine label="Logs" value={artifactReferences.log_uri ?? "Not attached"} />
              <InfoLine label="Cache" value={artifactReferences.cache_uri ?? "Not attached"} />
              <InfoLine label="Environment heartbeat" value={formatRelativeTime(currentLane.execution_environment?.heartbeat_at ?? null)} />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Recent activity</CardTitle>
              <CardDescription className="text-muted-foreground">
                Durable runner events and correlated signals stay attached to lane detail so operators can read the current story before intervening.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {observabilityLoading && !observability ? (
                <p className="text-sm text-muted-foreground">Loading lane activity…</p>
              ) : null}
              {observability?.recent_activity.length ? (
                observability.recent_activity.slice(0, 8).map((item) => (
                  <div
                    key={`${item.kind}:${item.event_type}:${item.observed_at ?? "unknown"}`}
                    className="rounded-3xl border border-border/70 bg-muted/30 p-4"
                  >
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-foreground">{humanize(item.event_type)}</p>
                        <Badge className="border-border bg-secondary text-secondary-foreground">
                          {humanize(item.kind)}
                        </Badge>
                        {item.severity ? (
                          <Badge className={statusTone(item.severity)}>{humanize(item.severity)}</Badge>
                        ) : null}
                      </div>
                      <p className="text-sm text-muted-foreground">{item.summary ?? "No summary recorded."}</p>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        {humanize(item.source_kind)} • {formatRelativeTime(item.observed_at)}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState
                  title="No recent activity is attached yet."
                  description="Runner events and correlated signals will appear here as soon as the lane records durable session or control-plane activity."
                />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Correlated notifications</CardTitle>
              <CardDescription className="text-muted-foreground">
                Lane warnings derived from durable state stay one click away from the lane action itself.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {observabilityError ? (
                <div className="rounded-3xl border border-amber-400/25 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
                  {observabilityError}
                </div>
              ) : null}
              <ObservabilityNotificationList
                notifications={observability?.notifications ?? []}
                emptyTitle="No correlated notifications are active for this lane."
                emptyDescription="Lane warnings will appear here when runner health, retries, or operator wait state create an explicit signal."
                limit={4}
              />
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Operator action</CardTitle>
              <CardDescription className="text-muted-foreground">
                The available control reflects the current durable lane state.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {(currentLane.state === "AwaitingApproval" || currentLane.state === "AwaitingGitHub") && currentLane.agent_session?.wait_reason ? (
                <div className="rounded-3xl border border-amber-400/25 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
                  {currentLane.agent_session.wait_reason}
                </div>
              ) : null}
              <FormField label="Reason" htmlFor={laneReasonInputId}>
                <Input
                  id={laneReasonInputId}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                />
              </FormField>
              {(currentLane.state === "AwaitingApproval" || currentLane.state === "AwaitingGitHub") ? (
                <FormField label="Operator note" htmlFor={laneNoteInputId}>
                  <Textarea
                    id={laneNoteInputId}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    rows={5}
                    className="border-input bg-background/90 text-foreground placeholder:text-muted-foreground"
                  />
                </FormField>
              ) : null}
              {!(currentLane.state === "AwaitingApproval" || currentLane.state === "AwaitingGitHub" || currentLane.state === "FailedTerminal" || currentLane.state === "Cancelled" || currentLane.state === "HandedOff") ? (
                <FormField label="Cancel disposition">
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      className={disposition === "terminate" ? "border-primary/30 bg-primary/10 text-foreground" : "border border-input bg-background text-muted-foreground"}
                      onClick={() => setDisposition("terminate")}
                    >
                      Terminate
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      className={disposition === "quarantine" ? "border-primary/30 bg-primary/10 text-foreground" : "border border-input bg-background text-muted-foreground"}
                      onClick={() => setDisposition("quarantine")}
                    >
                      Quarantine
                    </Button>
                  </div>
                </FormField>
              ) : null}
              {actionPanel}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function BaselineDetailPage({
  baseline,
  product,
  workspaceDefaults,
  actorId,
  actionBusy,
  onProductAction,
  onRefreshDashboard,
}: {
  baseline: BaselineResponse | null;
  product: ProductSummaryResponse | null;
  workspaceDefaults: ProductOnboardingDefaultsRecord;
  actorId: string;
  actionBusy: string | null;
  onProductAction: (action: ProductAction) => Promise<void>;
  onRefreshDashboard: () => Promise<void>;
}) {
  const [standardsRuns, setStandardsRuns] = useState<StandardsRunRecord[]>([]);
  const [standardsLoading, setStandardsLoading] = useState(false);
  const [standardsError, setStandardsError] = useState<string | null>(null);
  const [standardsNotice, setStandardsNotice] = useState<string | null>(null);
  const [standardsActionBusy, setStandardsActionBusy] = useState<string | null>(null);
  const [evaluationRepoRoot, setEvaluationRepoRoot] = useState(REFRESH_REPO_ROOT_HINT);
  const [evaluationPrNumber, setEvaluationPrNumber] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [outcomePrNumber, setOutcomePrNumber] = useState("");
  const baselineProductId = baseline?.product_id ?? product?.product_id ?? "";

  const loadStandardsRuns = useEffectEvent(async (preferredRunId?: string) => {
    if (!baseline?.product_id) {
      startTransition(() => {
        setStandardsRuns([]);
        setSelectedRunId(null);
      });
      return;
    }
    setStandardsLoading(true);
    setStandardsError(null);
    try {
      const nextRuns = sortStandardsRuns(await operatorApi.listProductStandardsRuns(baseline.product_id));
      startTransition(() => {
        setStandardsRuns(nextRuns);
        const nextSelected =
          preferredRunId && nextRuns.some((run) => run.standards_upgrade_run_id === preferredRunId)
            ? preferredRunId
            : nextRuns.some((run) => run.standards_upgrade_run_id === selectedRunId)
              ? selectedRunId
              : nextRuns[0]?.standards_upgrade_run_id ?? null;
        setSelectedRunId(nextSelected);
      });
    } catch (loadError) {
      setStandardsError(loadError instanceof Error ? loadError.message : "Standards run history could not be loaded.");
    } finally {
      setStandardsLoading(false);
    }
  });

  useEffect(() => {
    setStandardsRuns([]);
    setSelectedRunId(null);
    setEvaluationRepoRoot(REFRESH_REPO_ROOT_HINT);
    setEvaluationPrNumber("");
    setOutcomePrNumber("");
    setStandardsError(null);
    setStandardsNotice(null);
    if (baseline?.product_id) {
      void loadStandardsRuns();
    }
  }, [baselineProductId]);

  const selectedStandardsRun =
    standardsRuns.find((run) => run.standards_upgrade_run_id === selectedRunId) ?? standardsRuns[0] ?? null;

  useEffect(() => {
    setOutcomePrNumber(selectedStandardsRun?.generated_pr_number ? String(selectedStandardsRun.generated_pr_number) : "");
  }, [selectedStandardsRun?.standards_upgrade_run_id]);

  if (!baseline) {
    return product ? (
      <EmptyState
        title="No baseline posture is registered yet."
        description="This product does not have a baseline read model yet. Start from Products to seed or adopt the repo, then return here after onboarding and the first standards evaluation."
        action={
          <>
            <Link to="/products" className={buttonLinkClassName()}>
              Open Products
            </Link>
            <Link to="/products/seed" className={buttonLinkClassName("outline")}>
              Seed a product
            </Link>
            <Link to="/products/adopt" className={buttonLinkClassName("outline")}>
              Adopt a repo
            </Link>
          </>
        }
      />
    ) : (
      <EmptyState
        title="Baseline not found."
        description="The requested baseline route could not be resolved from the current operator dataset."
        action={
          <Link to="/baselines" className={buttonLinkClassName()}>
            Open Baselines
          </Link>
        }
      />
    );
  }

  const diagnosticBuckets = computeDiagnosticBuckets(baseline.setup_diagnostics);
  const blockingCount = diagnosticBuckets.blocking.length || (baseline.setup_state === "setup-needed" ? 1 : 0);
  const onboardingActivity = product ? resolveProductOnboardingActivity(product) : null;
  const remediationActions = collectGuidedRemediationActions({
    productId: baseline.product_id,
    diagnostics: baseline.setup_diagnostics,
    managedAssets: baseline.managed_assets,
    onboardingActivity,
    includeProductLink: true,
  });
  const managedAssetFollowUp = countManagedAssetFollowUp(baseline.managed_assets);
  const latestStandardsSummary = standardsRuns[0] ?? baseline.latest_run ?? null;
  const baselineBreadcrumbProduct = product
    ? { label: product.name, to: `/products/${product.product_id}` }
    : { label: baseline.product_name, to: `/products/${baseline.product_id}` };

  async function startStandardsEvaluation() {
    const targetBaseline = baseline;
    if (!targetBaseline?.baseline_channel || !targetBaseline.standards_pack_key || !targetBaseline.standards_pack_version) {
      setStandardsError("Baseline channel and standards pack metadata must be present before running standards evaluation.");
      return;
    }
    if (!evaluationRepoRoot.trim()) {
      setStandardsError("Local repo root is required before starting standards evaluation.");
      return;
    }
    const parsedGeneratedPr = parseOptionalPositiveIntegerField(evaluationPrNumber, "Generated PR number");
    if (parsedGeneratedPr.error) {
      setStandardsError(parsedGeneratedPr.error);
      return;
    }
    setStandardsActionBusy("evaluate");
    setStandardsError(null);
    setStandardsNotice(null);
    try {
      const run = await operatorApi.evaluateProductStandards(targetBaseline.product_id, {
        repo_root: evaluationRepoRoot.trim(),
        pack_key: targetBaseline.standards_pack_key,
        channel: targetBaseline.baseline_channel,
        version: targetBaseline.standards_pack_version,
        generated_pr_number: parsedGeneratedPr.value,
      });
      startTransition(() => {
        setStandardsRuns((current) => mergeStandardsRun(current, run));
        setSelectedRunId(run.standards_upgrade_run_id);
      });
      setStandardsNotice(
        `Recorded ${formatStandardsOutcomeKind(run.outcome_kind).toLowerCase()} as ${humanize(run.outcome_status).toLowerCase()}.`,
      );
      await Promise.all([onRefreshDashboard(), loadStandardsRuns(run.standards_upgrade_run_id)]);
    } catch (actionError) {
      setStandardsError(actionError instanceof Error ? actionError.message : "Standards evaluation failed.");
    } finally {
      setStandardsActionBusy(null);
    }
  }

  async function submitStandardsOutcome(decision: StandardsOutcomeDecision) {
    if (!selectedStandardsRun) {
      setStandardsError("Select a standards run before recording an operator outcome.");
      return;
    }
    const parsedGeneratedPr = parseOptionalPositiveIntegerField(outcomePrNumber, "Generated PR number");
    if (parsedGeneratedPr.error) {
      setStandardsError(parsedGeneratedPr.error);
      return;
    }
    setStandardsActionBusy(`outcome:${decision}`);
    setStandardsError(null);
    setStandardsNotice(null);
    try {
      const updatedRun = await operatorApi.recordStandardsRunOutcome(selectedStandardsRun.standards_upgrade_run_id, {
        outcome_status: decision,
        generated_pr_number: parsedGeneratedPr.value,
      });
      startTransition(() => {
        setStandardsRuns((current) => mergeStandardsRun(current, updatedRun));
        setSelectedRunId(updatedRun.standards_upgrade_run_id);
      });
      setStandardsNotice(`Recorded operator outcome as ${humanize(decision).toLowerCase()}.`);
      await Promise.all([onRefreshDashboard(), loadStandardsRuns(updatedRun.standards_upgrade_run_id)]);
    } catch (actionError) {
      setStandardsError(actionError instanceof Error ? actionError.message : "Recording standards run outcome failed.");
    } finally {
      setStandardsActionBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Baseline Detail"
        title={baseline.product_name}
        description="Standards posture, run history, setup diagnostics, and managed-asset drift are grouped for direct operator review."
        breadcrumbs={[
          { label: "Products", to: "/products" },
          baselineBreadcrumbProduct,
          { label: "Baseline" },
        ]}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={statusTone(baseline.drift_status)}>{humanize(baseline.drift_status)}</Badge>
            {latestStandardsSummary ? (
              <Badge className={statusTone(latestStandardsSummary.outcome_status ?? "unknown")}>
                {humanize(latestStandardsSummary.outcome_status ?? "unknown")}
              </Badge>
            ) : null}
          </div>
        }
      />

      {baseline.setup_state === "setup-needed" ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <ShieldAlert className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div>
              <p className="font-medium text-foreground">Setup-needed warning</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">
                {blockingCount} {pluralize(blockingCount, "blocking diagnostic")} still need remediation before this baseline can be treated as activation-ready. Managed asset drift remains visible separately below.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[0.9fr,1.1fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Summary</CardTitle>
              <CardDescription className="text-muted-foreground">
                Current baseline metadata, latest standards signal, and refresh context for this product.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              <InfoLine label="Product status" value={humanize(baseline.product_status)} />
              <InfoLine label="Channel" value={baseline.baseline_channel ?? "Unknown"} />
              <InfoLine label="Standards pack" value={`${baseline.standards_pack_key ?? "Unknown"} ${baseline.standards_pack_version ?? ""}`} />
              <InfoLine label="Agent Core" value={baseline.agent_core_version ?? "Unknown"} />
              <InfoLine
                label="Latest run"
                value={latestStandardsSummary ? `${formatStandardsOutcomeKind(latestStandardsSummary.outcome_kind)} (${latestStandardsSummary.outcome_status ?? "unknown"})` : "No standards run"}
              />
              <InfoLine label="Managed follow-up" value={`${managedAssetFollowUp} of ${baseline.managed_assets.length}`} />
              <InfoLine label="Last refresh" value={formatDateTime(baseline.last_config_refresh_at)} />
            </CardContent>
          </Card>

          <WorkspaceDefaultsCard
            defaultsRecord={workspaceDefaults}
            description="Baseline remediation keeps the saved org defaults visible before you rerun contract refresh or another standards evaluation."
          />

          <StandardsWorkspaceCard
            baseline={baseline}
            runs={standardsRuns}
            selectedRun={selectedStandardsRun}
            selectedRunId={selectedRunId}
            loading={standardsLoading}
            error={standardsError}
            notice={standardsNotice}
            actionBusy={standardsActionBusy}
            evaluationRepoRoot={evaluationRepoRoot}
            evaluationPrNumber={evaluationPrNumber}
            outcomePrNumber={outcomePrNumber}
            onSelectRun={setSelectedRunId}
            onEvaluateRepoRootChange={setEvaluationRepoRoot}
            onEvaluationPrNumberChange={setEvaluationPrNumber}
            onOutcomePrNumberChange={setOutcomePrNumber}
            onEvaluate={startStandardsEvaluation}
            onSubmitOutcome={submitStandardsOutcome}
          />

          <ActivationReadinessCard
            title="Activation and standards readiness"
            description="Baseline detail keeps blocking setup, advisory standards drift, and managed-asset posture separate so standards posture does not hide activation risk."
            setupState={baseline.setup_state}
            diagnostics={baseline.setup_diagnostics}
            managedAssets={baseline.managed_assets}
            lastConfigRefreshAt={baseline.last_config_refresh_at}
          />

          <GuidedRemediationCard
            title="Guided remediation"
            description="Use direct follow-up paths for secrets, settings, onboarding context, and product blockers before rerunning contract validation."
            actions={remediationActions}
          />

          <ContractRefreshPanel
            productId={baseline.product_id}
            actorId={actorId}
            actionBusy={actionBusy}
            onProductAction={onProductAction}
            defaultRepoRoot={REFRESH_REPO_ROOT_HINT}
            defaultRefreshReason="Refresh product contract from baseline detail after remediation."
            allowRemoteRefresh
            title="Re-check activation status"
            description="Run contract refresh after repo or settings remediation so baseline and product setup state reflect the latest durable contract result."
            buttonLabel="Refresh contract"
            buttonClassName={COMPACT_ACTION_BUTTON_CLASS}
          />

          <MirrorRefreshPanel
            productId={baseline.product_id}
            actorId={actorId}
            actionBusy={actionBusy}
            onProductAction={onProductAction}
            defaultReason="Refresh product mirror from baseline detail."
            buttonClassName={COMPACT_ACTION_BUTTON_CLASS}
          />
        </div>

        <div className="space-y-6">
          <StandardsRunDetailsCard baseline={baseline} run={selectedStandardsRun} />

          <SetupFindingsCard
            title="Setup findings"
            description="Every setup diagnostic stays visible here with blocking setup, recoverable drift, and advisory findings rendered separately from standards drift and managed assets."
            diagnostics={baseline.setup_diagnostics}
          />

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Managed asset drift</CardTitle>
              <CardDescription className="text-muted-foreground">
                Drift indicators stay visible inline so operators do not need a hidden admin-only registry.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Assets</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{baseline.managed_assets.length}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Current</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{baseline.managed_asset_counts.current ?? 0}</p>
                </div>
                <div className="rounded-2xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Follow-up</p>
                  <p className="pt-1 text-2xl font-semibold text-foreground">{managedAssetFollowUp}</p>
                </div>
              </div>
              {baseline.managed_assets.map((asset) => (
                <div key={asset.managed_asset_id} className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium text-foreground">{asset.path}</p>
                    <Badge className={statusTone(asset.drift_status ?? "unknown")}>{humanize(asset.drift_status ?? "unknown")}</Badge>
                  </div>
                  <p className="pt-2 text-sm text-muted-foreground">
                    {humanize(asset.management_mode)} • upstream {asset.upstream_bundle_version ?? "unknown"}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function GraphDetailPage({
  product,
  graph,
}: {
  product: ProductSummaryResponse | null;
  graph: GraphSliceResponse | null;
}) {
  if (!product) {
    return <EmptyState title="Product not found." description="The graph route requires a known product." />;
  }

  if (!graph) {
    return <EmptyState title="Loading graph slice…" description="The graph view fetches bounded context on demand from the operator API." />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Graph View"
        title={`${product.name} graph`}
        description="This view exposes freshness, hotspots, blocked dependencies, and lane overlays from the bounded graph slice read model."
        breadcrumbs={[
          { label: "Products", to: "/products" },
          { label: product.name, to: `/products/${product.product_id}` },
          { label: "Graph" },
        ]}
        action={<Badge className={statusTone(graph.freshness.status)}>{humanize(graph.freshness.status)}</Badge>}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={<Grid2x2 className="size-5" />} label="Nodes" value={graph.nodes.length} helper={`${graph.edges.length} edges in slice`} />
        <MetricCard icon={<TriangleAlert className="size-5" />} label="Blocked" value={graph.blocked_dependencies.length} helper="Dependencies currently flagged as blocked" />
        <MetricCard icon={<Workflow className="size-5" />} label="Hotspots" value={graph.hotspots.length} helper="Nodes with stacked lane or work-item pressure" />
        <MetricCard icon={<Clock3 className="size-5" />} label="Freshness" value={humanize(graph.freshness.status)} helper={`Generated ${formatRelativeTime(graph.generated_at)}`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="text-foreground">Nodes and overlays</CardTitle>
            <CardDescription className="text-muted-foreground">
              Active lanes, pull requests, and hotspot scores stay attached to the relevant components.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {graph.nodes.map((node) => (
              <div key={node.component_node_id} className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-foreground">{node.name}</p>
                  <Badge className={statusTone(node.freshness.status)}>{humanize(node.freshness.status)}</Badge>
                  <Badge className="border-border bg-secondary text-secondary-foreground">{humanize(node.type)}</Badge>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
                  <span>{node.overlay.active_work_items.length} active work items</span>
                  <span>{node.overlay.active_lanes.length} active lanes</span>
                  <span>{node.overlay.open_pull_requests.length} open PRs</span>
                  <span>Hotspot score {node.overlay.hotspot_score}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Blocked dependencies</CardTitle>
              <CardDescription className="text-muted-foreground">
                Control-plane blockers are readable even without a full visualization canvas.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {graph.blocked_dependencies.length ? (
                graph.blocked_dependencies.map((item) => (
                  <div key={item.component_edge_id} className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                    <p className="font-medium text-foreground">{item.from_key} → {item.to_key}</p>
                    <p className="pt-2 text-sm text-muted-foreground">{item.reason}</p>
                  </div>
                ))
              ) : (
                <EmptyState title="No blocked dependencies in this slice." description="The current graph slice does not report blocked edges." />
              )}
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle className="text-foreground">Hotspots</CardTitle>
              <CardDescription className="text-muted-foreground">
                Components with concurrent operator pressure surface first.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {graph.hotspots.length ? (
                graph.hotspots.map((item) => (
                  <div key={item.component_node_id} className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-foreground">{item.name}</p>
                      <Badge className="border-border bg-secondary text-secondary-foreground">Score {item.hotspot_score}</Badge>
                    </div>
                    <p className="pt-2 text-sm text-muted-foreground">
                      {item.active_lane_count} active lanes • {item.active_work_item_count} active work items
                    </p>
                  </div>
                ))
              ) : (
                <EmptyState title="No hotspots in this slice." description="Hotspot scoring is currently low across the visible graph." />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function AppRoutes({
  user,
  dashboard,
  graphs,
  organizations,
  onboardingDefaultsByOrg,
  actorId,
  actionBusy,
  onLoadGraph,
  onRefreshDashboard,
  onSaveOnboardingDefaults,
  onProductAction,
  onLaneAction,
}: {
  user: UserInfo;
  dashboard: DashboardState;
  graphs: Record<string, GraphSliceResponse>;
  organizations: OrganizationResponse[];
  onboardingDefaultsByOrg: OnboardingDefaultsByOrg;
  actorId: string;
  actionBusy: string | null;
  onLoadGraph: (productId: string) => Promise<void>;
  onRefreshDashboard: () => Promise<void>;
  onSaveOnboardingDefaults: (
    orgId: string,
    defaults: ProductOnboardingDefaults,
    existingValue: unknown,
  ) => Promise<ProductOnboardingDefaultsRecord>;
  onProductAction: (action: ProductAction) => Promise<void>;
  onLaneAction: (action: LaneAction) => Promise<void>;
}) {
  function ProductRoute() {
    const { productId = "" } = useParams();
    useEffect(() => {
      if (productId && !graphs[productId]) {
        void onLoadGraph(productId);
      }
    }, [productId]);
    return (
      <ProductDetailPage
        product={dashboard.products.find((item) => item.product_id === productId) ?? null}
        lanes={dashboard.lanes.filter((item) => item.product_id === productId)}
        baseline={dashboard.baselines.find((item) => item.product_id === productId) ?? null}
        graph={graphs[productId] ?? null}
        observability={dashboard.observability}
        workspaceDefaults={resolveOrgOnboardingDefaultsRecord(
          dashboard.products.find((item) => item.product_id === productId)?.org_id ?? null,
          onboardingDefaultsByOrg,
        )}
        actorId={actorId}
        actionBusy={actionBusy}
        onProductAction={onProductAction}
      />
    );
  }

  function LaneRoute() {
    const { laneId = "" } = useParams();
    return (
      <LaneDetailPage
        lane={dashboard.lanes.find((item) => item.lane_id === laneId) ?? null}
        actorId={actorId}
        actionBusy={actionBusy}
        onLaneAction={onLaneAction}
      />
    );
  }

  function BaselineRoute() {
    const { productId = "" } = useParams();
    return (
      <BaselineDetailPage
        baseline={dashboard.baselines.find((item) => item.product_id === productId) ?? null}
        product={dashboard.products.find((item) => item.product_id === productId) ?? null}
        workspaceDefaults={resolveOrgOnboardingDefaultsRecord(
          dashboard.baselines.find((item) => item.product_id === productId)?.org_id ?? null,
          onboardingDefaultsByOrg,
        )}
        actorId={actorId}
        actionBusy={actionBusy}
        onProductAction={onProductAction}
        onRefreshDashboard={onRefreshDashboard}
      />
    );
  }

  function GraphRoute() {
    const { productId = "" } = useParams();
    useEffect(() => {
      if (productId && !graphs[productId]) {
        void onLoadGraph(productId);
      }
    }, [productId]);
    return (
      <GraphDetailPage
        product={dashboard.products.find((item) => item.product_id === productId) ?? null}
        graph={graphs[productId] ?? null}
      />
    );
  }

  function SharedSettingsWorkspace() {
    const settingsExtensions: ShellSettingsExtension[] = [
      {
        path: "git-repos",
        label: "Git Repositories",
        icon: GitBranch,
        render: ({ selectedOrg, organizations, hasPermission }) => (
          <GitRepositoriesPage
            selectedOrg={selectedOrg}
            organizations={organizations}
            hasPermission={hasPermission}
          />
        ),
      },
      {
        path: "workspace",
        label: "Workspace",
        icon: Wrench,
        render: ({ selectedOrg }) => (
          <WorkspaceOnboardingDefaultsPage
            selectedOrg={selectedOrg}
            defaultsRecord={resolveOrgOnboardingDefaultsRecord(selectedOrg?.org_id ?? null, onboardingDefaultsByOrg)}
            onSaveDefaults={onSaveOnboardingDefaults}
          />
        ),
      },
    ];
    return (
      <AgentCoreShellApp
        branding={productBranding}
        mode="settings-content"
        settingsExtensions={settingsExtensions}
      />
    );
  }

  return (
    <Routes>
      <Route path="/" element={<FleetPage {...dashboard} />} />
      <Route path="/fleet" element={<Navigate to="/" replace />} />
      <Route path="/products" element={<ProductsPage {...dashboard} />} />
      <Route
        path="/products/seed"
        element={
          <ProductSeedPage
            user={user}
            organizations={organizations}
            products={dashboard.products}
            onboardingDefaultsByOrg={onboardingDefaultsByOrg}
            onRefreshDashboard={onRefreshDashboard}
          />
        }
      />
      <Route
        path="/products/seed/jobs/:seedJobId"
        element={
          <ProductSeedJobPage
            organizations={organizations}
            onboardingDefaultsByOrg={onboardingDefaultsByOrg}
            actorId={actorId}
            actionBusy={actionBusy}
            onRefreshDashboard={onRefreshDashboard}
            onProductAction={onProductAction}
          />
        }
      />
      <Route
        path="/products/adopt"
        element={
          <ProductAdoptionPage
            user={user}
            organizations={organizations}
            products={dashboard.products}
            onboardingDefaultsByOrg={onboardingDefaultsByOrg}
          />
        }
      />
      <Route
        path="/products/adopt/review"
        element={
          <ProductAdoptionReviewPage
            organizations={organizations}
            products={dashboard.products}
            actorId={actorId}
            actionBusy={actionBusy}
            onRefreshDashboard={onRefreshDashboard}
            onProductAction={onProductAction}
          />
        }
      />
      <Route
        path="/products/adopt/review/:productId"
        element={
          <ProductAdoptionReviewPage
            organizations={organizations}
            products={dashboard.products}
            actorId={actorId}
            actionBusy={actionBusy}
            onRefreshDashboard={onRefreshDashboard}
            onProductAction={onProductAction}
          />
        }
      />
      <Route path="/products/:productId" element={<ProductRoute />} />
      <Route path="/lanes/:laneId" element={<LaneRoute />} />
      <Route path="/baselines" element={<BaselinesPage baselines={dashboard.baselines} products={dashboard.products} />} />
      <Route path="/baselines/:productId" element={<BaselineRoute />} />
      <Route path="/graphs/products/:productId" element={<GraphRoute />} />
      <Route path="/settings/*" element={<SharedSettingsWorkspace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function OrchaOperatorApp() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationResponse[]>([]);
  const [onboardingDefaultsByOrg, setOnboardingDefaultsByOrg] = useState<OnboardingDefaultsByOrg>({});
  const [accountLabel, setAccountLabel] = useState<string | null>(null);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardState>({
    products: [],
    lanes: [],
    baselines: [],
    observability: null,
  });
  const [graphs, setGraphs] = useState<Record<string, GraphSliceResponse>>({});
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const loadAuth = useEffectEvent(async () => {
    setIsLoadingAuth(true);
    setError(null);
    try {
      if (!AUTH_DISABLED && isAuthConfigured()) {
        const authResult = await initAuth();
        let accessToken =
          authResult?.accessToken ??
          (typeof window === "undefined" ? null : window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY));
        if (!accessToken) {
          accessToken = await acquireToken();
        }
        if (typeof window !== "undefined") {
          if (accessToken) {
            window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, accessToken);
          } else {
            window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
          }
        }
        setAccountLabel(await getAccountLabel());
      }
      const currentUser = await operatorApi.getMe();
      let nextOrganizations: OrganizationResponse[] = [];
      try {
        nextOrganizations = await operatorApi.listOrganizations();
      } catch {
        nextOrganizations = [];
      }
      const accessibleOrgIds = Array.from(
        new Set(
          (nextOrganizations.length
            ? nextOrganizations.map((org) => org.org_id)
            : [currentUser.default_org_id, ...currentUser.org_ids]
          ).filter((value): value is string => Boolean(value)),
        ),
      );
      const nextOnboardingDefaultsByOrg = Object.fromEntries(
        await Promise.all(
          accessibleOrgIds.map(async (orgId) => {
            try {
              const settings = await operatorApi.listSettings("org", orgId);
              const setting = settings.find((item) => item.key === PRODUCT_DEFAULTS_SETTING_KEY) ?? null;
              return [orgId, buildProductOnboardingDefaultsRecord(setting)] as const;
            } catch (loadError) {
              return [
                orgId,
                createErroredProductOnboardingDefaultsRecord(
                  loadError instanceof Error
                    ? loadError.message
                    : "Failed to load workspace defaults.",
                ),
              ] as const;
            }
          }),
        ),
      );
      startTransition(() => {
        setUser(currentUser);
        setOrganizations(nextOrganizations);
        setOnboardingDefaultsByOrg(nextOnboardingDefaultsByOrg);
      });
      if (!AUTH_DISABLED) {
        setAccountLabel((current) => current ?? currentUser.username ?? currentUser.user_id);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load operator identity.");
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      }
      setOrganizations([]);
      setOnboardingDefaultsByOrg({});
      setUser(null);
    } finally {
      setIsLoadingAuth(false);
    }
  });

  const loadDashboard = useEffectEvent(async () => {
    if (!user) {
      return;
    }
    setIsLoadingDashboard(true);
    setError(null);
    try {
      const [products, lanes, baselines, observability] = await Promise.all([
        operatorApi.listProducts(),
        operatorApi.listLanes(),
        operatorApi.listBaselines(),
        operatorApi.getFleetObservabilitySummary().catch(() => null),
      ]);
      startTransition(() => {
        setDashboard({ products, lanes, baselines, observability });
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load operator dashboard.");
    } finally {
      setIsLoadingDashboard(false);
    }
  });

  const loadGraph = useEffectEvent(async (productId: string) => {
    try {
      const graph = await operatorApi.getGraph(productId);
      startTransition(() => {
        setGraphs((current) => ({ ...current, [productId]: graph }));
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load graph slice.");
    }
  });

  useEffect(() => {
    void loadAuth();
  }, []);

  useEffect(() => {
    if (!isLoadingAuth && user) {
      void loadDashboard();
    }
  }, [isLoadingAuth, user]);

  useEffect(() => {
    const onAuthFailure = () => {
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
      }
      setUser(null);
      setAccountLabel(null);
      setError("Authentication expired. Sign in again to continue.");
    };
    window.addEventListener("agentCoreAuthFailed", onAuthFailure);
    return () => window.removeEventListener("agentCoreAuthFailed", onAuthFailure);
  }, []);

  async function handleLogin() {
    const result = await login();
    if (typeof window !== "undefined" && result?.accessToken) {
      window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, result.accessToken);
    }
    await loadAuth();
  }

  async function handleLogout() {
    await logout();
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
    setUser(null);
    setAccountLabel(null);
  }

  async function handleSaveOnboardingDefaults(
    orgId: string,
    defaults: ProductOnboardingDefaults,
    existingValue: unknown,
  ) {
    const updatedSetting = await operatorApi.upsertSetting(
      "org",
      orgId,
      PRODUCT_DEFAULTS_SETTING_KEY,
      buildProductOnboardingDefaultsValue(existingValue, defaults),
    );
    const nextRecord = buildProductOnboardingDefaultsRecord(updatedSetting);
    startTransition(() => {
      setOnboardingDefaultsByOrg((current) => ({
        ...current,
        [orgId]: nextRecord,
      }));
    });
    return nextRecord;
  }

  async function handleProductAction(action: ProductAction) {
    const key = `product:${action.kind}:${action.productId}`;
    setActionBusy(key);
    setError(null);
    try {
      if (action.kind === "pause") {
        await operatorApi.pauseProduct(action.productId, {
          actor_id: action.actorId,
          reason: action.reason,
        });
      } else if (action.kind === "resume") {
        await operatorApi.resumeProduct(action.productId, {
          actor_id: action.actorId,
          reason: action.reason,
        });
      } else if (action.kind === "refresh-mirror") {
        await operatorApi.refreshProductMirror(action.productId, {
          actor_id: action.actorId,
          reason: action.reason,
        });
      } else {
        await operatorApi.refreshProduct(action.productId, {
          actor_id: action.actorId,
          reason: action.reason,
          repo_root: action.repoRoot,
          operator_overrides: {},
        });
      }
      await loadDashboard();
      await loadGraph(action.productId);
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Product action failed.");
    } finally {
      setActionBusy(null);
    }
  }

  async function handleLaneAction(action: LaneAction) {
    const key = `lane:${action.kind}:${action.laneId}`;
    setActionBusy(key);
    setError(null);
    try {
      if (action.kind === "approve") {
        await operatorApi.approveLane(action.laneId, {
          actor_id: action.actorId,
          reason: action.reason,
          approval_payload: { note: action.note },
        });
      } else if (action.kind === "human-input") {
        await operatorApi.submitHumanInput(action.laneId, {
          actor_id: action.actorId,
          reason: action.reason,
          input_payload: { note: action.note },
        });
      } else if (action.kind === "cancel") {
        await operatorApi.cancelLane(action.laneId, {
          actor_id: action.actorId,
          reason: action.reason,
          disposition: action.disposition,
        });
      } else {
        await operatorApi.retryLane(action.laneId, {
          actor_id: action.actorId,
          reason: action.reason,
        });
      }
      await loadDashboard();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Lane action failed.");
    } finally {
      setActionBusy(null);
    }
  }

  if (isLoadingAuth) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="size-4 animate-spin" />
          Connecting the operator shell…
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <LoginPrompt
        onLogin={() => void handleLogin()}
        configured={AUTH_DISABLED || isAuthConfigured()}
        loading={false}
        title={productBranding.title ?? "Orcha"}
        logoLightSrc={productBranding.logoLightSrc ?? "/logo-light.svg"}
        logoDarkSrc={productBranding.logoDarkSrc ?? "/logo-dark.svg"}
        message={error ?? "Authentication required for the Orcha operator shell"}
      />
    );
  }

  const actorId = user.username ?? user.user_id;
  const criticalError = error;

  return (
    <ShellScaffold
      user={user}
      organizations={organizations}
      accountLabel={accountLabel}
      loading={isLoadingDashboard}
      authConfigured={!AUTH_DISABLED && isAuthConfigured()}
      onLogin={handleLogin}
      onLogout={handleLogout}
    >
      {criticalError ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <Wrench className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Operator data could not be refreshed</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">{criticalError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}
      <AppRoutes
        user={user}
        dashboard={dashboard}
        graphs={graphs}
        organizations={organizations}
        onboardingDefaultsByOrg={onboardingDefaultsByOrg}
        actorId={actorId}
        actionBusy={actionBusy}
        onLoadGraph={loadGraph}
        onRefreshDashboard={loadDashboard}
        onSaveOnboardingDefaults={handleSaveOnboardingDefaults}
        onProductAction={handleProductAction}
        onLaneAction={handleLaneAction}
      />
    </ShellScaffold>
  );
}

export default function App() {
  return <OrchaOperatorApp />;
}
