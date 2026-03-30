import {
  AlertCircle,
  Bot,
  Brain,
  Building2,
  ChevronDown,
  CircleHelp,
  Key,
  Loader2,
  Monitor,
  Moon,
  Pencil,
  Plus,
  Save,
  Search,
  Shield,
  Sun,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { Fragment, type ReactNode, useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import type {
  CreateOrganizationRequest,
  CreateSecretRequest,
  FeatureFlag,
  Organization,
  Permission,
  PlatformSummary,
  Role,
  Secret,
  Setting,
  UpdateOrganizationRequest,
  UpdateSecretRequest,
  UserInfo,
} from "./api/types";
import LoginPrompt from "./components/LoginPrompt";
import SettingsSidebar from "./components/SettingsSidebar";
import AddOrganizationForm from "./components/settings/AddOrganizationForm";
import EditOrganizationForm from "./components/settings/EditOrganizationForm";
import { UserMenu } from "./components/UserMenu";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "./components/ui/dropdown-menu";
import { Input } from "./components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./components/ui/table";
import { api } from "./lib/api";
import { AuthProvider, useAuth } from "./lib/auth-context";
import AgentsPage from "./pages/Agents";
import ModelsPage from "./pages/Models";
import {
  acquireToken,
  getAccountLabel,
  initAuth,
  isAuthConfigured,
  login,
  logout,
} from "./lib/auth";
import { formatDateTime } from "./lib/date-utils";
import { type ThemePreference, useTheme } from "./lib/theme-context";
import { cn } from "./lib/utils";

const TOKEN_STORAGE_KEY = "agentCoreToken";
const ORG_STORAGE_KEY = "agentCoreSelectedOrgId";

export type ShellBranding = {
  title?: string;
  kicker?: string;
  logoLightSrc?: string;
  logoDarkSrc?: string;
};

export type ShellMode = "full" | "settings-content";

export type ShellSettingsExtensionProps = {
  user: UserInfo | null;
  organizations: Organization[];
  selectedOrg: Organization | null;
  hasPermission: (permission: string) => boolean;
};

export type ShellSettingsExtension = {
  path: string;
  label: string;
  icon: LucideIcon;
  render: (props: ShellSettingsExtensionProps) => ReactNode;
};

async function optional<T>(read: Promise<T>, fallback: T) {
  try {
    return await read;
  } catch {
    return fallback;
  }
}

function HomePage({
  summary,
  status,
}: {
  summary: PlatformSummary | null;
  status: string;
}) {
  const cards = [
    { label: "Organizations", value: summary?.organization_count ?? 0 },
    { label: "AI Providers", value: summary?.provider_count ?? 0 },
    { label: "AI Models", value: summary?.model_count ?? 0 },
    { label: "AI Agents", value: summary?.agent_count ?? 0 },
    { label: "Roles", value: summary?.role_count ?? 0 },
    { label: "Secrets", value: summary?.secret_count ?? 0 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Home</h1>
        <p className="text-sm text-muted-foreground">{status}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((item) => (
          <Card key={item.label}>
            <CardHeader className="pb-2">
              <CardDescription>{item.label}</CardDescription>
              <CardTitle className="text-2xl">{item.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

function OrganizationsPage({
  organizations,
  loading,
  hasPermission,
  onCreateOrg,
  onUpdateOrg,
}: {
  organizations: Organization[];
  loading: boolean;
  hasPermission: (permission: string) => boolean;
  onCreateOrg: (payload: CreateOrganizationRequest) => Promise<void>;
  onUpdateOrg: (orgId: string, payload: UpdateOrganizationRequest) => Promise<void>;
}) {
  const { userInfo } = useAuth();
  const canReadOrgs = hasPermission("org.read");
  const canManageOrgs = hasPermission("org.manage");
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingOrgId, setEditingOrgId] = useState<string | null>(null);
  const filteredOrganizations = useMemo(() => {
    let visibleOrganizations = organizations;
    if (!canManageOrgs) {
      const accessibleOrgIds = new Set(userInfo?.org_ids ?? []);
      visibleOrganizations = visibleOrganizations.filter((org) => accessibleOrgIds.has(org.org_id));
    }
    if (!searchQuery.trim()) {
      return visibleOrganizations;
    }
    const query = searchQuery.trim().toLowerCase();
    return visibleOrganizations.filter(
      (org) =>
        org.name.toLowerCase().includes(query) ||
        org.slug.toLowerCase().includes(query),
    );
  }, [canManageOrgs, organizations, searchQuery, userInfo]);

  const editingOrg = editingOrgId
    ? organizations.find((org) => org.org_id === editingOrgId) ?? null
    : null;

  const handleAddSuccess = () => {
    setShowAddForm(false);
  };

  const handleEditSuccess = () => {
    setEditingOrgId(null);
  };

  if (!canReadOrgs) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Organizations
          </h1>
        </div>
        <Card>
          <CardContent className="pt-6">
            <p className="text-zinc-600 dark:text-zinc-400">
              You do not have permission to view organizations.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Organizations
        </h1>
      </div>

      <div className="mb-6">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div className="relative max-w-sm flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <Input
              placeholder="Search organizations..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="pl-10"
            />
          </div>
          {canManageOrgs ? (
            <Button
              onClick={() => {
                setShowAddForm(true);
                setEditingOrgId(null);
              }}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add
            </Button>
          ) : null}
        </div>
      </div>

      {showAddForm ? (
        <AddOrganizationForm
          onCreateOrg={onCreateOrg}
          onSuccess={handleAddSuccess}
          onCancel={() => setShowAddForm(false)}
        />
      ) : null}

      <div className="space-y-4">
        <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-200 dark:border-zinc-800">
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Name
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Slug
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Docs visibility
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Created At
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Updated At
                </TableHead>
                {canManageOrgs ? (
                  <TableHead className="w-20 font-semibold text-zinc-900 dark:text-zinc-100">
                    Actions
                  </TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell
                    colSpan={canManageOrgs ? 6 : 5}
                    className="py-8 text-center text-zinc-500 dark:text-zinc-400"
                  >
                    Loading...
                  </TableCell>
                </TableRow>
              ) : filteredOrganizations.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={canManageOrgs ? 6 : 5}
                    className="py-8 text-center text-zinc-500 dark:text-zinc-400"
                  >
                    {searchQuery
                      ? "No organizations found matching your search."
                      : "No organizations found. Click 'Add' to create one."}
                  </TableCell>
                </TableRow>
              ) : (
                filteredOrganizations.map((org, index) => (
                  <Fragment key={org.org_id}>
                    <TableRow
                      className={cn(
                        "border-zinc-200 dark:border-zinc-800",
                        index % 2 === 1 && "bg-zinc-50 dark:bg-zinc-900/50",
                      )}
                    >
                      <TableCell className="font-medium text-zinc-900 dark:text-zinc-100">
                        {org.name}
                      </TableCell>
                      <TableCell className="font-mono text-sm text-zinc-700 dark:text-zinc-300">
                        {org.slug}
                      </TableCell>
                      <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                        {(org.documentation_visibility ?? "shared") === "isolated"
                          ? "Isolated"
                          : "Shared"}
                      </TableCell>
                      <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                        {formatDateTime(org.created_at)}
                      </TableCell>
                      <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                        {formatDateTime(org.updated_at)}
                      </TableCell>
                      {canManageOrgs ? (
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setEditingOrgId((prev) =>
                                  prev === org.org_id ? null : org.org_id,
                                );
                                setShowAddForm(false);
                              }}
                              className="h-8 w-8 p-0"
                              title="Edit organization"
                              aria-label="Edit organization"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      ) : null}
                    </TableRow>
                    {editingOrgId === org.org_id && editingOrg ? (
                      <TableRow key={`${org.org_id}-edit`}>
                        <TableCell
                          colSpan={canManageOrgs ? 6 : 5}
                          className="border-0 p-0"
                        >
                          <div className="w-full max-w-full overflow-hidden px-6 py-4">
                            <EditOrganizationForm
                              organization={editingOrg}
                              onUpdateOrg={onUpdateOrg}
                              onSuccess={handleEditSuccess}
                              onCancel={() => setEditingOrgId(null)}
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

function sameSet(current: Set<string>, baseline: Set<string>) {
  if (current.size !== baseline.size) {
    return false;
  }
  for (const item of current) {
    if (!baseline.has(item)) {
      return false;
    }
  }
  return true;
}

function RolesPage({
  roles,
  permissions,
  featureFlags,
  hasPermission,
  onSaveRolePermissions,
  onSaveRoleFeatureFlags,
}: {
  roles: Role[];
  permissions: Permission[];
  featureFlags: FeatureFlag[];
  hasPermission: (permission: string) => boolean;
  onSaveRolePermissions: (roleId: string, permissionKeys: string[]) => Promise<void>;
  onSaveRoleFeatureFlags: (roleId: string, featureFlagKeys: string[]) => Promise<void>;
}) {
  const canRead = hasPermission("platform.read");
  const canManagePermissions = hasPermission("platform.manage");
  const canManageFeatureFlags = hasPermission("platform.manage");
  const [permissionDrafts, setPermissionDrafts] = useState<Record<string, Set<string>>>({});
  const [featureFlagDrafts, setFeatureFlagDrafts] = useState<Record<string, Set<string>>>({});
  const [savingRoleId, setSavingRoleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const nextPermissionDrafts: Record<string, Set<string>> = {};
    const nextFeatureFlagDrafts: Record<string, Set<string>> = {};
    for (const role of roles) {
      nextPermissionDrafts[role.role_id] = new Set(
        role.permissions.map((permission) => permission.key),
      );
      nextFeatureFlagDrafts[role.role_id] = new Set(
        role.feature_flags.map((featureFlag) => featureFlag.key),
      );
    }
    setPermissionDrafts(nextPermissionDrafts);
    setFeatureFlagDrafts(nextFeatureFlagDrafts);
  }, [roles]);

  const permissionsByCategory = useMemo(() => {
    const grouped = permissions.reduce<Record<string, Permission[]>>(
      (acc, permission) => {
        const category = permission.category || "Other";
        acc[category] = [...(acc[category] ?? []), permission];
        return acc;
      },
      {},
    );
    return Object.fromEntries(
      Object.entries(grouped).map(([category, items]) => [
        category,
        [...items].sort((a, b) => a.key.localeCompare(b.key)),
      ]),
    );
  }, [permissions]);

  const featureFlagsByCategory = useMemo(() => {
    const grouped = featureFlags.reduce<Record<string, FeatureFlag[]>>(
      (acc, featureFlag) => {
        const category = featureFlag.category || "Other";
        acc[category] = [...(acc[category] ?? []), featureFlag];
        return acc;
      },
      {},
    );
    return Object.fromEntries(
      Object.entries(grouped).map(([category, items]) => [
        category,
        [...items].sort((a, b) => a.key.localeCompare(b.key)),
      ]),
    );
  }, [featureFlags]);

  function togglePermission(roleId: string, permissionKey: string) {
    if (!canManagePermissions) {
      return;
    }
    setPermissionDrafts((current) => {
      const next = new Set(current[roleId] ?? []);
      if (next.has(permissionKey)) {
        next.delete(permissionKey);
      } else {
        next.add(permissionKey);
      }
      return { ...current, [roleId]: next };
    });
  }

  function toggleFeatureFlag(roleId: string, featureFlagKey: string) {
    if (!canManageFeatureFlags) {
      return;
    }
    setFeatureFlagDrafts((current) => {
      const next = new Set(current[roleId] ?? []);
      if (next.has(featureFlagKey)) {
        next.delete(featureFlagKey);
      } else {
        next.add(featureFlagKey);
      }
      return { ...current, [roleId]: next };
    });
  }

  async function saveRole(roleId: string) {
    setSavingRoleId(roleId);
    setError(null);
    try {
      if (canManagePermissions) {
        await onSaveRolePermissions(roleId, Array.from(permissionDrafts[roleId] ?? []));
      }
      if (canManageFeatureFlags) {
        await onSaveRoleFeatureFlags(
          roleId,
          Array.from(featureFlagDrafts[roleId] ?? []),
        );
      }
    } catch (saveError) {
      setError(
        saveError instanceof Error ? saveError.message : "Failed to update role.",
      );
    } finally {
      setSavingRoleId(null);
    }
  }

  function roleIsDirty(role: Role) {
    const permissionDraft = permissionDrafts[role.role_id] ?? new Set<string>();
    const baselinePermissions = new Set(role.permissions.map((item) => item.key));
    const flagDraft = featureFlagDrafts[role.role_id] ?? new Set<string>();
    const baselineFlags = new Set(role.feature_flags.map((item) => item.key));
    return !sameSet(permissionDraft, baselinePermissions) || !sameSet(flagDraft, baselineFlags);
  }

  if (!canRead) {
    return (
      <div className="flex items-center justify-center py-12">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-600 dark:text-red-400">
              <AlertCircle className="h-5 w-5" />
              Access Denied
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-zinc-600 dark:text-zinc-400">
              You do not have permission to access RBAC settings.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Roles &amp; Permissions
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Manage role permissions and feature flags.
        </p>
      </div>

      {error ? (
        <Card className="mb-6 border-red-200 dark:border-red-800">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-red-600 dark:text-red-400">
              <AlertCircle className="h-5 w-5" />
              <p>{error}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Permissions Matrix</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <div className="min-w-full inline-block align-middle">
                <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
                  <thead>
                    <tr>
                      <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-semibold text-zinc-900 border-r border-zinc-200 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800">
                        Permission
                      </th>
                      {roles.map((role) => (
                        <th
                          key={role.role_id}
                          className="px-4 py-3 text-center text-sm font-semibold text-zinc-900 dark:text-zinc-100 min-w-[120px]"
                        >
                          <div className="flex flex-col items-center gap-1">
                            <span>{role.name}</span>
                            {role.is_system ? (
                              <Badge variant="outline" className="text-xs">
                                System
                              </Badge>
                            ) : null}
                            {roleIsDirty(role) ? (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => void saveRole(role.role_id)}
                                disabled={savingRoleId === role.role_id}
                                className="mt-1 h-6 text-xs"
                              >
                                {savingRoleId === role.role_id ? (
                                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                                ) : (
                                  <Save className="h-3 w-3 mr-1" />
                                )}
                                Save
                              </Button>
                            ) : null}
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {Object.entries(permissionsByCategory).map(([category, items]) => (
                      <Fragment key={category}>
                        <tr className="bg-zinc-50 dark:bg-zinc-900/50">
                          <td
                            colSpan={roles.length + 1}
                            className="px-4 py-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300 uppercase tracking-wider"
                          >
                            {category}
                          </td>
                        </tr>
                        {items.map((permission) => (
                          <tr key={permission.permission_id}>
                            <td className="sticky left-0 z-10 bg-white px-4 py-3 border-r border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800">
                              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                                {permission.key}
                              </div>
                              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                                {permission.description}
                              </div>
                            </td>
                            {roles.map((role) => (
                              <td
                                key={`${permission.permission_id}-${role.role_id}`}
                                className="px-4 py-3 text-center"
                              >
                                <input
                                  type="checkbox"
                                  className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-500 dark:border-zinc-700 dark:bg-zinc-950"
                                  checked={Boolean(
                                    permissionDrafts[role.role_id]?.has(permission.key),
                                  )}
                                  onChange={() =>
                                    togglePermission(role.role_id, permission.key)
                                  }
                                  disabled={!canManagePermissions}
                                />
                              </td>
                            ))}
                          </tr>
                        ))}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Feature Flags</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <div className="min-w-full inline-block align-middle">
                <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
                  <thead>
                    <tr>
                      <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-semibold text-zinc-900 border-r border-zinc-200 dark:bg-zinc-900 dark:text-zinc-100 dark:border-zinc-800">
                        Feature Flag
                      </th>
                      {roles.map((role) => (
                        <th
                          key={role.role_id}
                          className="px-4 py-3 text-center text-sm font-semibold text-zinc-900 dark:text-zinc-100 min-w-[120px]"
                        >
                          {role.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {Object.entries(featureFlagsByCategory).map(([category, items]) => (
                      <Fragment key={category}>
                        <tr className="bg-zinc-50 dark:bg-zinc-900/50">
                          <td
                            colSpan={roles.length + 1}
                            className="px-4 py-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300 uppercase tracking-wider"
                          >
                            {category}
                          </td>
                        </tr>
                        {items.map((featureFlag) => (
                          <tr key={featureFlag.feature_flag_id}>
                            <td className="sticky left-0 z-10 bg-white px-4 py-3 border-r border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800">
                              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                                {featureFlag.key}
                              </div>
                              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                                {featureFlag.description}
                              </div>
                            </td>
                            {roles.map((role) => (
                              <td
                                key={`${featureFlag.feature_flag_id}-${role.role_id}`}
                                className="px-4 py-3 text-center"
                              >
                                <input
                                  type="checkbox"
                                  className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-500 dark:border-zinc-700 dark:bg-zinc-950"
                                  checked={Boolean(
                                    featureFlagDrafts[role.role_id]?.has(featureFlag.key),
                                  )}
                                  onChange={() =>
                                    toggleFeatureFlag(role.role_id, featureFlag.key)
                                  }
                                  disabled={!canManageFeatureFlags}
                                />
                              </td>
                            ))}
                          </tr>
                        ))}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SecretsPage({
  secrets,
  hasPermission,
  onCreateSecret,
  onUpdateSecret,
  onDeleteSecret,
}: {
  secrets: Secret[];
  hasPermission: (permission: string) => boolean;
  onCreateSecret: (payload: CreateSecretRequest) => Promise<void>;
  onUpdateSecret: (secretId: string, payload: UpdateSecretRequest) => Promise<void>;
  onDeleteSecret: (secretId: string) => Promise<void>;
}) {
  const canReadSecrets = hasPermission("platform.read");
  const canManageSecrets = hasPermission("platform.manage");
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingSecretId, setEditingSecretId] = useState<string | null>(null);
  const [formState, setFormState] = useState({
    key: "",
    name: "",
    kind: "ai_api_key" as Secret["kind"],
    value: "",
    description: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [deletingSecretId, setDeletingSecretId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filteredSecrets = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return secrets;
    }
    return secrets.filter(
      (secret) =>
        secret.key.toLowerCase().includes(query) ||
        secret.name.toLowerCase().includes(query) ||
        secret.kind.toLowerCase().includes(query),
    );
  }, [searchQuery, secrets]);

  const editingSecret = editingSecretId
    ? secrets.find((secret) => secret.secret_id === editingSecretId) ?? null
    : null;

  useEffect(() => {
    if (!editingSecret) {
      return;
    }
    setFormState({
      key: editingSecret.key,
      name: editingSecret.name,
      kind: editingSecret.kind,
      value: "",
      description: editingSecret.description ?? "",
    });
  }, [editingSecret]);

  async function handleCreateSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!formState.key.trim() || !formState.name.trim() || !formState.value.trim()) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onCreateSecret({
        key: formState.key.trim(),
        name: formState.name.trim(),
        kind: formState.kind,
        value: formState.value.trim(),
        description: formState.description.trim() || undefined,
      });
      setFormState({
        key: "",
        name: "",
        kind: "ai_api_key",
        value: "",
        description: "",
      });
      setShowAddForm(false);
    } catch (createError) {
      setError(
        createError instanceof Error ? createError.message : "Failed to create secret.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEditSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingSecret || !formState.key.trim() || !formState.name.trim()) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onUpdateSecret(editingSecret.secret_id, {
        key: formState.key.trim(),
        name: formState.name.trim(),
        kind: formState.kind,
        value: formState.value.trim() || undefined,
        description: formState.description.trim() || undefined,
      });
      setEditingSecretId(null);
    } catch (updateError) {
      setError(
        updateError instanceof Error ? updateError.message : "Failed to update secret.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(secretId: string) {
    if (!window.confirm("Are you sure you want to delete this secret?")) {
      return;
    }
    setDeletingSecretId(secretId);
    setError(null);
    try {
      await onDeleteSecret(secretId);
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : "Failed to delete secret.",
      );
    } finally {
      setDeletingSecretId(null);
    }
  }

  if (!canReadSecrets) {
    return (
      <div>
        <div className="mb-6">
          <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Secrets
          </h1>
        </div>
        <Card>
          <CardContent className="pt-6">
            <p className="text-zinc-600 dark:text-zinc-400">
              You do not have permission to view secrets.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Secrets
        </h1>
      </div>

      {error ? (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200">
          <p className="font-medium">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      ) : null}

      <div className="mb-6">
        <div className="flex items-center justify-between mb-6 gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <Input
              placeholder="Search secrets..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="pl-10"
            />
          </div>
          {canManageSecrets ? (
            <Button
              onClick={() => {
                setShowAddForm(true);
                setEditingSecretId(null);
                setFormState({
                  key: "",
                  name: "",
                  kind: "ai_api_key",
                  value: "",
                  description: "",
                });
                setError(null);
              }}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add
            </Button>
          ) : null}
        </div>
      </div>

      {showAddForm && canManageSecrets ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Add New Secret</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div className="space-y-2">
                <label
                  htmlFor="secret-key"
                  className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Key
                </label>
                <Input
                  id="secret-key"
                  value={formState.key}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      key: event.target.value,
                    }))
                  }
                  placeholder="Enter secret key"
                  required
                />
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="secret-name"
                  className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Name
                </label>
                <Input
                  id="secret-name"
                  value={formState.name}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                  placeholder="Enter secret name"
                  required
                />
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="secret-kind"
                  className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Kind
                </label>
                <select
                  id="secret-kind"
                  value={formState.kind}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      kind: event.target.value as Secret["kind"],
                    }))
                  }
                  className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
                >
                  <option value="ai_api_key">AI API Key</option>
                  <option value="git_personal_access_token">
                    Git Personal Access Token
                  </option>
                  <option value="databricks_access_token">
                    Databricks Access Token
                  </option>
                  <option value="gcp_service_account_key">
                    GCP Service Account Key
                  </option>
                  <option value="github_webhook_secret">
                    GitHub Webhook Secret
                  </option>
                  <option value="shared_secret">Shared Secret</option>
                  <option value="signing_key">Signing Key</option>
                  <option value="client_secret">Client Secret</option>
                  <option value="api_token">API Token</option>
                </select>
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="secret-description"
                  className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Description
                </label>
                <Input
                  id="secret-description"
                  value={formState.description}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      description: event.target.value,
                    }))
                  }
                  placeholder="Enter optional description"
                />
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="secret-value"
                  className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Value
                </label>
                <Input
                  id="secret-value"
                  type="password"
                  value={formState.value}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      value: event.target.value,
                    }))
                  }
                  placeholder="Enter secret value"
                  required
                />
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Secret values are encrypted and never displayed after saving.
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowAddForm(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    submitting ||
                    !formState.key.trim() ||
                    !formState.name.trim() ||
                    !formState.value.trim()
                  }
                >
                  {submitting ? "Saving..." : "Save"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-4">
        <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-200 dark:border-zinc-800">
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Key
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Name
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Kind
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Status
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Last Rotated
                </TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">
                  Created At
                </TableHead>
                {canManageSecrets ? (
                  <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100 w-20">
                    Actions
                  </TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredSecrets.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={canManageSecrets ? 7 : 6}
                    className="text-center py-8 text-zinc-500 dark:text-zinc-400"
                  >
                    {searchQuery
                      ? "No secrets found matching your search."
                      : "No secrets found. Click 'Add' to create one."}
                  </TableCell>
                </TableRow>
              ) : (
                filteredSecrets.map((secret, index) => (
                  <Fragment key={secret.secret_id}>
                    <TableRow
                      className={cn(
                        "border-zinc-200 dark:border-zinc-800",
                        index % 2 === 1 && "bg-zinc-50 dark:bg-zinc-900/50",
                      )}
                    >
                      <TableCell className="font-medium text-zinc-900 dark:text-zinc-100 font-mono text-sm">
                        {secret.key}
                      </TableCell>
                      <TableCell className="font-medium text-zinc-900 dark:text-zinc-100">
                        {secret.name}
                      </TableCell>
                      <TableCell className="text-zinc-600 dark:text-zinc-400 text-sm">
                        {secret.kind}
                      </TableCell>
                      <TableCell className="text-zinc-600 dark:text-zinc-400 text-sm">
                        {secret.has_value ? "Configured" : "Missing value"}
                      </TableCell>
                      <TableCell className="text-zinc-600 dark:text-zinc-400 text-sm">
                        {secret.last_rotated_at
                          ? formatDateTime(secret.last_rotated_at)
                          : "Never"}
                      </TableCell>
                      <TableCell className="text-zinc-600 dark:text-zinc-400 text-sm">
                        {formatDateTime(secret.created_at)}
                      </TableCell>
                      {canManageSecrets ? (
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setEditingSecretId((prev) =>
                                  prev === secret.secret_id ? null : secret.secret_id,
                                );
                                setShowAddForm(false);
                                setError(null);
                              }}
                              className="h-8 w-8 p-0"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => void handleDelete(secret.secret_id)}
                              disabled={deletingSecretId === secret.secret_id}
                              className="h-8 w-8 p-0 text-red-600 hover:text-red-700"
                            >
                              {deletingSecretId === secret.secret_id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                        </TableCell>
                      ) : null}
                    </TableRow>
                    {editingSecretId === secret.secret_id && editingSecret ? (
                      <TableRow key={`${secret.secret_id}-edit`}>
                        <TableCell
                          colSpan={canManageSecrets ? 7 : 6}
                          className="p-0 border-0"
                        >
                          <div className="px-6 py-4 w-full max-w-full overflow-hidden">
                            <Card className="mb-0 w-full max-w-full">
                              <CardHeader>
                                <div className="flex items-center justify-between gap-4">
                                  <CardTitle>Edit Secret</CardTitle>
                                  <Button
                                    type="button"
                                    variant="destructive"
                                    size="sm"
                                    onClick={() =>
                                      void handleDelete(editingSecret.secret_id)
                                    }
                                    disabled={deletingSecretId === editingSecret.secret_id}
                                  >
                                    <Trash2 className="h-4 w-4 mr-2" />
                                    {deletingSecretId === editingSecret.secret_id
                                      ? "Deleting..."
                                      : "Delete"}
                                  </Button>
                                </div>
                              </CardHeader>
                              <CardContent className="w-full max-w-full">
                                <form
                                  onSubmit={handleEditSubmit}
                                  className="space-y-4 w-full max-w-full"
                                >
                                  <div className="space-y-2">
                                    <label
                                      htmlFor="edit-secret-key"
                                      className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                                    >
                                      Key
                                    </label>
                                    <Input
                                      id="edit-secret-key"
                                      value={formState.key}
                                      onChange={(event) =>
                                        setFormState((current) => ({
                                          ...current,
                                          key: event.target.value,
                                        }))
                                      }
                                      required
                                      className="w-full"
                                    />
                                  </div>

                                  <div className="space-y-2">
                                    <label
                                      htmlFor="edit-secret-name"
                                      className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                                    >
                                      Name
                                    </label>
                                    <Input
                                      id="edit-secret-name"
                                      value={formState.name}
                                      onChange={(event) =>
                                        setFormState((current) => ({
                                          ...current,
                                          name: event.target.value,
                                        }))
                                      }
                                      required
                                      className="w-full"
                                    />
                                  </div>

                                  <div className="space-y-2">
                                    <label
                                      htmlFor="edit-secret-kind"
                                      className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                                    >
                                      Kind
                                    </label>
                                    <select
                                      id="edit-secret-kind"
                                      value={formState.kind}
                                      onChange={(event) =>
                                        setFormState((current) => ({
                                          ...current,
                                          kind: event.target.value as Secret["kind"],
                                        }))
                                      }
                                      className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
                                    >
                                      <option value="ai_api_key">AI API Key</option>
                                      <option value="git_personal_access_token">
                                        Git Personal Access Token
                                      </option>
                                      <option value="databricks_access_token">
                                        Databricks Access Token
                                      </option>
                                      <option value="gcp_service_account_key">
                                        GCP Service Account Key
                                      </option>
                                      <option value="github_webhook_secret">
                                        GitHub Webhook Secret
                                      </option>
                                      <option value="shared_secret">Shared Secret</option>
                                      <option value="signing_key">Signing Key</option>
                                      <option value="client_secret">Client Secret</option>
                                      <option value="api_token">API Token</option>
                                    </select>
                                  </div>

                                  <div className="space-y-2">
                                    <label
                                      htmlFor="edit-secret-description"
                                      className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                                    >
                                      Description
                                    </label>
                                    <Input
                                      id="edit-secret-description"
                                      value={formState.description}
                                      onChange={(event) =>
                                        setFormState((current) => ({
                                          ...current,
                                          description: event.target.value,
                                        }))
                                      }
                                      className="w-full"
                                    />
                                  </div>

                                  <div className="space-y-2">
                                    <label
                                      htmlFor="edit-secret-value"
                                      className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
                                    >
                                      New Value
                                    </label>
                                    <Input
                                      id="edit-secret-value"
                                      type="password"
                                      value={formState.value}
                                      onChange={(event) =>
                                        setFormState((current) => ({
                                          ...current,
                                          value: event.target.value,
                                        }))
                                      }
                                      placeholder="Leave blank to keep existing value"
                                    />
                                  </div>

                                  <div className="flex justify-end gap-2 pt-4">
                                    <Button
                                      type="button"
                                      variant="outline"
                                      onClick={() => setEditingSecretId(null)}
                                    >
                                      Cancel
                                    </Button>
                                    <Button
                                      type="submit"
                                      disabled={
                                        submitting ||
                                        !formState.key.trim() ||
                                        !formState.name.trim()
                                      }
                                    >
                                      {submitting ? "Saving..." : "Save"}
                                    </Button>
                                  </div>
                                </form>
                              </CardContent>
                            </Card>
                          </div>
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </Fragment>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}

export default function App({
  branding,
  mode = "full",
  settingsExtensions = [],
}: {
  branding?: ShellBranding;
  mode?: ShellMode;
  settingsExtensions?: ShellSettingsExtension[];
}) {
  const { preference: themePreference, resolvedDark, setPreference } = useTheme();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(
    () => window.localStorage.getItem(TOKEN_STORAGE_KEY),
  );
  const [authReady, setAuthReady] = useState(false);
  const [authInFlight, setAuthInFlight] = useState(false);
  const [accountLabel, setAccountLabel] = useState<string | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null);
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [featureFlags, setFeatureFlags] = useState<FeatureFlag[]>([]);
  const [secrets, setSecrets] = useState<Secret[]>([]);
  const [settings, setSettings] = useState<Setting[]>([]);
  const [status, setStatus] = useState("Loading workspace metrics...");
  const [orgLoading, setOrgLoading] = useState(false);
  const location = useLocation();
  const isSettings = location.pathname.startsWith("/settings");
  const authDisabled = import.meta.env.VITE_AUTH_DISABLED === "1";
  const authConfigured = isAuthConfigured();
  const authLoading = !authDisabled && (!authReady || Boolean(token && !user && !error));
  const appTitle = branding?.title?.trim() || "Agent Core Starter";
  const logoLightSrc = branding?.logoLightSrc?.trim() || "/logo-light.svg";
  const logoDarkSrc = branding?.logoDarkSrc?.trim() || "/logo-dark.svg";
  const activeLogoSrc = resolvedDark ? logoDarkSrc : logoLightSrc;
  const showHeader = mode === "full";
  const primaryNav = [
    { to: "/", label: "Home", isActive: location.pathname === "/" },
    { to: "/settings/orgs", label: "Settings", isActive: isSettings },
  ];
  const settingsBasePath = showHeader
    ? "/settings"
    : (location.pathname.match(/^(.*\/settings)(?:\/.*)?$/)?.[1] ?? "/settings");
  const settingsIndexPath = mode === "full" ? "/settings" : undefined;
  const settingsOrgsPath = mode === "full" ? "/settings/orgs" : "orgs";
  const settingsRolesPath = mode === "full" ? "/settings/roles" : "roles";
  const settingsSecretsPath = mode === "full" ? "/settings/secrets" : "secrets";
  const settingsModelsPath = mode === "full" ? "/settings/models" : "models";
  const settingsAgentsPath = mode === "full" ? "/settings/agents" : "agents";
  const settingsItems = [
    { to: `${settingsBasePath}/orgs`, label: "Organizations", icon: Building2 },
    { to: `${settingsBasePath}/roles`, label: "Roles & Permissions", icon: Shield },
    ...settingsExtensions.map((extension) => ({
      to: `${settingsBasePath}/${extension.path}`,
      label: extension.label,
      icon: extension.icon,
    })),
    { to: `${settingsBasePath}/secrets`, label: "Secrets", icon: Key },
    { to: `${settingsBasePath}/models`, label: "AI Models", icon: Brain },
    { to: `${settingsBasePath}/agents`, label: "Agents", icon: Bot },
  ];

  const userLabel = useMemo(() => {
    const claims = user?.claims as Record<string, unknown> | undefined;
    const claimName =
      (typeof claims?.name === "string" && claims.name) ||
      (typeof claims?.preferred_username === "string" &&
        claims.preferred_username);
    if (claimName) {
      return claimName;
    }
    if (accountLabel) {
      return accountLabel;
    }
    if (user?.username) {
      return user.username;
    }
    if (user?.user_id) {
      return user.user_id;
    }
    if (error) {
      return "User unavailable";
    }
    return "Loading user...";
  }, [accountLabel, error, user]);

  const userEmail = useMemo(() => {
    const claims = user?.claims as Record<string, unknown> | undefined;
    const claimEmail =
      (typeof claims?.email === "string" && claims.email) ||
      (typeof claims?.preferred_username === "string" &&
        claims.preferred_username);
    return claimEmail ?? user?.username ?? null;
  }, [user]);

  async function refreshAll() {
    const me = await api.getMe();
    const [
      nextSummary,
      nextRoles,
      nextPermissions,
      nextFeatureFlags,
      nextSecrets,
      nextSettings,
    ] = await Promise.all([
      optional(api.getPlatformSummary(), null as PlatformSummary | null),
      optional(api.listRoles(), [] as Role[]),
      optional(api.listPermissions(), [] as Permission[]),
      optional(api.listFeatureFlags(), [] as FeatureFlag[]),
      optional(api.listSecrets(), [] as Secret[]),
      optional(api.listSettings("user", "me"), [] as Setting[]),
    ]);

    setUser(me);
    setSummary(nextSummary);
    setRoles(nextRoles);
    setPermissions(nextPermissions);
    setFeatureFlags(nextFeatureFlags);
    setSecrets(nextSecrets);
    setSettings(nextSettings);
    setStatus("Workspace metrics synced.");
    setError(null);
  }

  async function refreshOrganizations(defaultOrgId?: string | null) {
    setOrgLoading(true);
    try {
      const nextOrganizations = await api.listOrgs();
      setOrganizations(nextOrganizations);
      const storedOrgId =
        typeof window !== "undefined"
          ? window.localStorage.getItem(ORG_STORAGE_KEY)
          : null;
      const nextSelectedOrg =
        nextOrganizations.find((org) => org.org_id === defaultOrgId) ??
        nextOrganizations.find((org) => org.org_id === storedOrgId) ??
        nextOrganizations[0] ??
        null;
      setSelectedOrg(nextSelectedOrg);
      if (nextSelectedOrg) {
        window.localStorage.setItem(ORG_STORAGE_KEY, nextSelectedOrg.org_id);
      } else {
        window.localStorage.removeItem(ORG_STORAGE_KEY);
      }
    } catch {
      setOrganizations([]);
      setSelectedOrg(null);
      window.localStorage.removeItem(ORG_STORAGE_KEY);
    } finally {
      setOrgLoading(false);
    }
  }

  async function persistUserSetting(key: string, value: unknown) {
    if (!user) {
      return;
    }
    const updated = await api.upsertSetting("user", "me", key, value);
    setSettings((current) => {
      const remaining = current.filter((item) => item.key !== updated.key);
      return [...remaining, updated];
    });
  }

  function handleThemeChange(nextPreference: ThemePreference, persist = true) {
    setPreference(nextPreference);
    if (persist) {
      void persistUserSetting("shell.theme", nextPreference);
    }
  }

  async function handleLogin() {
    if (authInFlight) {
      return;
    }
    setAuthInFlight(true);
    try {
      const result = await login();
      const accessToken = result?.accessToken ?? (await acquireToken());
      if (accessToken) {
        window.localStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
        setToken(accessToken);
      }
    } finally {
      setAuthInFlight(false);
    }
  }

  async function handleLogout() {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setAccountLabel(null);
    await logout();
  }

  function handleSelectOrg(org: Organization) {
    if (selectedOrg?.org_id === org.org_id) {
      return;
    }
    setSelectedOrg(org);
    window.localStorage.setItem(ORG_STORAGE_KEY, org.org_id);
  }

  useEffect(() => {
    let cancelled = false;
    if (authDisabled) {
      setAuthReady(true);
      return () => {
        cancelled = true;
      };
    }
    initAuth()
      .then(async (result) => {
        if (cancelled) {
          return;
        }
        const nextToken = result?.accessToken ?? token ?? (await acquireToken());
        if (nextToken) {
          window.localStorage.setItem(TOKEN_STORAGE_KEY, nextToken);
          setToken(nextToken);
        }
      })
      .catch(() => {
        // Silent auth is best-effort.
      })
      .finally(() => {
        if (!cancelled) {
          setAuthReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authDisabled, token]);

  useEffect(() => {
    if (!authDisabled && !token) {
      return;
    }
    void refreshAll()
      .then(() => refreshOrganizations(user?.default_org_id ?? null))
      .catch((loadError: unknown) => {
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load starter shell.",
        );
        setStatus("Unable to reach the API. Check starter API config.");
      });
  }, [authDisabled, token]);

  useEffect(() => {
    const defaultOrgId = user?.default_org_id ?? null;
    if (!authDisabled && !token) {
      return;
    }
    void refreshOrganizations(defaultOrgId);
  }, [authDisabled, token, user?.default_org_id]);

  useEffect(() => {
    const themeSetting = settings.find((item) => item.key === "shell.theme");
    if (
      themeSetting &&
      (themeSetting.value_json === "light" ||
        themeSetting.value_json === "dark" ||
        themeSetting.value_json === "system")
    ) {
      handleThemeChange(themeSetting.value_json, false);
    }
  }, [settings]);

  useEffect(() => {
    let cancelled = false;
    if (authDisabled) {
      setAccountLabel("Local developer");
      return () => {
        cancelled = true;
      };
    }
    void getAccountLabel()
      .then((label) => {
        if (!cancelled) {
          setAccountLabel(label);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAccountLabel(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authDisabled, token]);

  useEffect(() => {
    const resetAuth = () => {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken(null);
      setUser(null);
    };
    window.addEventListener("agentCoreAuthFailed", resetAuth);
    return () => window.removeEventListener("agentCoreAuthFailed", resetAuth);
  }, []);

  async function createOrg(payload: CreateOrganizationRequest) {
    await api.createOrg(payload);
    await refreshOrganizations(selectedOrg?.org_id ?? user?.default_org_id ?? null);
  }

  async function updateOrg(orgId: string, payload: UpdateOrganizationRequest) {
    await api.updateOrg(orgId, payload);
    await refreshOrganizations(selectedOrg?.org_id ?? user?.default_org_id ?? null);
  }

  async function saveRolePermissions(roleId: string, permissionKeys: string[]) {
    await api.updateRolePermissions(roleId, { permission_keys: permissionKeys });
    await refreshAll();
  }

  async function saveRoleFeatureFlags(roleId: string, featureFlagKeys: string[]) {
    await api.updateRoleFeatureFlags(roleId, { feature_flag_keys: featureFlagKeys });
    await refreshAll();
  }

  async function createSecret(payload: CreateSecretRequest) {
    await api.createSecret(payload);
    await refreshAll();
  }

  async function updateSecret(secretId: string, payload: UpdateSecretRequest) {
    await api.updateSecret(secretId, payload);
    await refreshAll();
  }

  async function deleteSecret(secretId: string) {
    await api.deleteSecret(secretId);
    await refreshAll();
  }

  function hasPermission(permission: string) {
    return authDisabled ? true : (user?.permissions ?? []).includes(permission);
  }

  if (!authDisabled && authReady && !token) {
    return (
      <LoginPrompt
        onLogin={() => void handleLogin()}
        configured={authConfigured}
        loading={authInFlight}
        title={appTitle}
        logoLightSrc={logoLightSrc}
        logoDarkSrc={logoDarkSrc}
      />
    );
  }

  if (!authDisabled && !authReady) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center text-sm text-muted-foreground">
        Checking session...
      </div>
    );
  }

  const workspace = (
    <>
      {error ? (
        <div
          role="alert"
          className={cn(
            "border-b border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-4 py-2 text-sm text-red-700 dark:text-red-200",
            !showHeader && "border-t",
          )}
        >
          <div className={cn(showHeader ? "container mx-auto flex items-center gap-2 px-6" : "flex items-center gap-2")}>
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        </div>
      ) : null}

      <div className={cn("bg-zinc-50 dark:bg-zinc-950", isSettings ? "flex min-h-[calc(100vh-50px)]" : "min-h-[calc(100vh-50px)]")}>
        {isSettings ? <SettingsSidebar items={settingsItems} /> : null}
        <main className={cn(isSettings ? "flex-1 p-8" : "container mx-auto px-6 py-8")}>
          <AuthProvider
            user={user}
            isLoading={authLoading}
            authDisabled={authDisabled}
            refresh={refreshAll}
          >
            <Routes>
              {showHeader ? (
                <Route path="/" element={<HomePage summary={summary} status={status} />} />
              ) : null}
              {showHeader ? (
                <Route path={settingsIndexPath} element={<Navigate to="/settings/orgs" replace />} />
              ) : (
                <Route index element={<Navigate to={`${settingsBasePath}/orgs`} replace />} />
              )}
              <Route
                path={settingsOrgsPath}
                element={
                  <OrganizationsPage
                    organizations={organizations}
                    loading={orgLoading}
                    hasPermission={hasPermission}
                    onCreateOrg={createOrg}
                    onUpdateOrg={updateOrg}
                  />
                }
              />
              <Route
                path={settingsRolesPath}
                element={
                  <RolesPage
                    roles={roles}
                    permissions={permissions}
                    featureFlags={featureFlags}
                    hasPermission={hasPermission}
                    onSaveRolePermissions={saveRolePermissions}
                    onSaveRoleFeatureFlags={saveRoleFeatureFlags}
                  />
                }
              />
              {settingsExtensions.map((extension) => {
                const extensionPath = mode === "full" ? `/settings/${extension.path}` : extension.path;
                return (
                  <Route
                    key={extension.path}
                    path={extensionPath}
                    element={
                      extension.render({
                        user,
                        organizations,
                        selectedOrg,
                        hasPermission,
                      })
                    }
                  />
                );
              })}
              <Route
                path={settingsSecretsPath}
                element={
                  <SecretsPage
                    secrets={secrets}
                    hasPermission={hasPermission}
                    onCreateSecret={createSecret}
                    onUpdateSecret={updateSecret}
                    onDeleteSecret={deleteSecret}
                  />
                }
              />
              <Route path={settingsModelsPath} element={<ModelsPage />} />
              <Route path={settingsAgentsPath} element={<AgentsPage />} />
              {showHeader ? (
                <>
                  <Route
                    path="/settings/*"
                    element={<Navigate to="/settings/orgs" replace />}
                  />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </>
              ) : (
                <Route path="*" element={<Navigate to={`${settingsBasePath}/orgs`} replace />} />
              )}
            </Routes>
          </AuthProvider>
        </main>
      </div>
    </>
  );

  if (!showHeader) {
    return workspace;
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-50 w-full border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
        <div className="container mx-auto flex h-[50px] items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <NavLink to="/" className="flex items-center">
              <img
                src={activeLogoSrc}
                alt={appTitle}
                className="h-8 w-auto"
              />
            </NavLink>
            <div className="h-4 w-px bg-zinc-200 dark:bg-zinc-800" />
            <DropdownMenu>
              <DropdownMenuTrigger
                disabled={orgLoading || organizations.length === 0}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Building2 className="h-4 w-4" />
                <span>
                  {orgLoading
                    ? "Loading..."
                    : selectedOrg?.name || "Select Organization"}
                </span>
                <ChevronDown className="h-3 w-3" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="min-w-[200px]">
                {organizations.length === 0 && !orgLoading ? (
                  <div className="px-2 py-1.5 text-sm text-zinc-500 dark:text-zinc-400">
                    No organization access assigned
                  </div>
                ) : (
                  organizations.map((org) => (
                    <DropdownMenuItem
                      key={org.org_id}
                      onClick={() => handleSelectOrg(org)}
                      className={cn(
                        "cursor-pointer",
                        selectedOrg?.org_id === org.org_id &&
                          "bg-zinc-100 dark:bg-zinc-800",
                      )}
                    >
                      {org.name}
                    </DropdownMenuItem>
                  ))
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            <nav className="flex items-center gap-1">
              {primaryNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={() =>
                    cn(
                      "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      item.isActive
                        ? "bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100"
                        : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100",
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="rounded-md p-2 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                  aria-label="Theme"
                  title="Theme"
                >
                  {themePreference === "dark" ? (
                    <Moon className="h-5 w-5" />
                  ) : themePreference === "light" ? (
                    <Sun className="h-5 w-5" />
                  ) : (
                    <Monitor className="h-5 w-5" />
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuRadioGroup
                  value={themePreference}
                  onValueChange={(value) =>
                    handleThemeChange(value as ThemePreference)
                  }
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
            <button
              type="button"
              className="rounded-md p-2 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
              aria-label="Help"
              title="Help"
              onClick={() => {
                window.open("/docs", "_blank", "noopener,noreferrer");
              }}
            >
              <CircleHelp className="h-5 w-5" />
            </button>
            {authLoading ? (
              <div className="text-sm text-zinc-600 dark:text-zinc-400">
                Loading...
              </div>
            ) : (
              <UserMenu
                label={userLabel}
                email={userEmail}
                roles={user?.roles ?? []}
                themePreference={themePreference}
                onThemeChange={handleThemeChange}
                authDisabled={authDisabled}
                onLogin={handleLogin}
                onLogout={handleLogout}
              />
            )}
          </div>
        </div>
      </header>
      {workspace}
    </div>
  );
}
