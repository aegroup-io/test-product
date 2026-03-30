import {
  Github,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { Fragment, useDeferredValue, useEffect, useMemo, useState } from "react";

import { operatorApi, OperatorApiError } from "../operator-api";
import type {
  GitRepoBranchResponse,
  GitRepoCreateRequestPayload,
  GitRepoLookupResultResponse,
  GitRepoResponse,
  GitRepoUpdateRequestPayload,
  SecretCreateRequestPayload,
  SecretResponse,
} from "../operator-types";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  Select,
} from "../ui";

type WorkspaceOrganization = {
  org_id: string;
  name: string;
  slug: string;
};

type WizardStep = 1 | 2 | 3 | 4;

type AuthMode = "existing" | "new";

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Not recorded";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function toMessage(error: unknown, fallback: string) {
  if (error instanceof OperatorApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function tryExtractApiMessage(error: unknown) {
  const message = error instanceof Error ? error.message : "";
  if (!message) {
    return null;
  }
  try {
    const parsed = JSON.parse(message) as {
      detail?: string | { message?: string };
    };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail && typeof parsed.detail === "object" && typeof parsed.detail.message === "string") {
      return parsed.detail.message;
    }
  } catch {
    return null;
  }
  return null;
}

function iconButtonClassName(destructive = false) {
  return [
    "inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent transition hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 dark:hover:bg-zinc-800",
    destructive ? "text-rose-600 dark:text-rose-400" : "text-zinc-600 dark:text-zinc-300",
  ].join(" ");
}

export default function GitRepositoriesPage({
  selectedOrg,
  organizations,
  hasPermission,
}: {
  selectedOrg: WorkspaceOrganization | null;
  organizations: WorkspaceOrganization[];
  hasPermission: (permission: string) => boolean;
}) {
  const canReadRepos = hasPermission("repo.read");
  const canManageRepos = hasPermission("repo.manage");
  const canDeleteRepos = hasPermission("repo.delete");
  const canReadSecrets = hasPermission("platform.read");
  const canManageSecrets = hasPermission("platform.manage");

  const [repos, setRepos] = useState<GitRepoResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [listStatus, setListStatus] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  const [wizardError, setWizardError] = useState<string | null>(null);
  const [wizardSaving, setWizardSaving] = useState(false);

  const [authMode, setAuthMode] = useState<AuthMode>(canReadSecrets ? "existing" : "new");
  const [secrets, setSecrets] = useState<SecretResponse[]>([]);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const [selectedSecretId, setSelectedSecretId] = useState("");
  const [newSecretForm, setNewSecretForm] = useState<Omit<SecretCreateRequestPayload, "key">>({
    name: "",
    kind: "git_personal_access_token",
    value: "",
    description: "",
  });

  const [repoForm, setRepoForm] = useState<GitRepoCreateRequestPayload>({
    key: "",
    name: "",
    github_owner: "",
    github_repo: "",
    visibility: "private",
    default_branch: "",
    git_auth_secret_id: "",
    org_ids: selectedOrg ? [selectedOrg.org_id] : [],
  });
  const [repoLookupQuery, setRepoLookupQuery] = useState("");
  const [repoLookupLoading, setRepoLookupLoading] = useState(false);
  const [repoLookupResults, setRepoLookupResults] = useState<GitRepoLookupResultResponse[]>([]);
  const [selectedRepoLookup, setSelectedRepoLookup] = useState<GitRepoLookupResultResponse | null>(null);
  const [branchLoading, setBranchLoading] = useState(false);
  const [branches, setBranches] = useState<GitRepoBranchResponse[]>([]);
  const [selectedBranch, setSelectedBranch] = useState<GitRepoBranchResponse | null>(null);

  const [editingRepoId, setEditingRepoId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<GitRepoUpdateRequestPayload | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editAddOrgId, setEditAddOrgId] = useState("");
  const [confirmDeleteRepoId, setConfirmDeleteRepoId] = useState<string | null>(null);
  const [deletingRepoId, setDeletingRepoId] = useState<string | null>(null);

  const gitSecrets = useMemo(
    () => secrets.filter((secret) => secret.kind === "git_personal_access_token"),
    [secrets],
  );

  useEffect(() => {
    if (!canReadRepos || !selectedOrg) {
      setRepos([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    operatorApi
      .listOrgRepos(selectedOrg.org_id, deferredSearchQuery)
      .then((nextRepos) => {
        if (!cancelled) {
          setRepos(nextRepos);
          setConfirmDeleteRepoId(null);
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setRepos([]);
          setConfirmDeleteRepoId(null);
          setError(tryExtractApiMessage(loadError) ?? toMessage(loadError, "Failed to load repositories."));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canReadRepos, deferredSearchQuery, selectedOrg?.org_id]);

  useEffect(() => {
    if (!showWizard || !canManageRepos || !canReadSecrets) {
      return;
    }
    let cancelled = false;
    setSecretsLoading(true);
    operatorApi
      .listSecrets()
      .then((nextSecrets) => {
        if (!cancelled) {
          setSecrets(nextSecrets);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSecrets([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSecretsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [canManageRepos, canReadSecrets, showWizard]);

  useEffect(() => {
    if (!selectedOrg) {
      return;
    }
    setRepoForm((current) => {
      if (current.org_ids.includes(selectedOrg.org_id)) {
        return current;
      }
      return {
        ...current,
        org_ids: Array.from(new Set([...current.org_ids, selectedOrg.org_id])),
      };
    });
  }, [selectedOrg?.org_id]);

  useEffect(() => {
    if (!showWizard || wizardStep !== 2 || !selectedOrg || !repoForm.git_auth_secret_id) {
      return;
    }
    void loadRepoLookup(repoLookupQuery);
  }, [showWizard, wizardStep, selectedOrg?.org_id]);

  useEffect(() => {
    if (!showWizard || wizardStep !== 3 || !selectedOrg || !selectedRepoLookup) {
      return;
    }
    void loadBranches(selectedRepoLookup);
  }, [showWizard, wizardStep, selectedOrg?.org_id, selectedRepoLookup?.full_name]);

  function resetWizard() {
    setWizardStep(1);
    setWizardError(null);
    setWizardSaving(false);
    setAuthMode(canReadSecrets ? "existing" : "new");
    setSelectedSecretId("");
    setNewSecretForm({
      name: "",
      kind: "git_personal_access_token",
      value: "",
      description: "",
    });
    setRepoForm({
      key: "",
      name: "",
      github_owner: "",
      github_repo: "",
      visibility: "private",
      default_branch: "",
      git_auth_secret_id: "",
      org_ids: selectedOrg ? [selectedOrg.org_id] : [],
    });
    setRepoLookupQuery("");
    setRepoLookupResults([]);
    setSelectedRepoLookup(null);
    setBranches([]);
    setSelectedBranch(null);
  }

  function startWizard() {
    if (!canManageRepos || !selectedOrg) {
      return;
    }
    cancelEditRepo();
    setShowWizard(true);
    resetWizard();
  }

  function cancelEditRepo() {
    setEditingRepoId(null);
    setEditForm(null);
    setEditAddOrgId("");
  }

  function validateStep1() {
    if (authMode === "existing") {
      if (!canReadSecrets) {
        return "You do not have permission to read PAT secrets.";
      }
      if (!selectedSecretId) {
        return "Select a PAT secret to continue.";
      }
      return null;
    }
    if (!canManageSecrets) {
      return "You do not have permission to create PAT secrets.";
    }
    if (!newSecretForm.name.trim()) {
      return "Secret name is required.";
    }
    if (!newSecretForm.value.trim()) {
      return "Paste a GitHub personal access token.";
    }
    return null;
  }

  async function handleStep1Next() {
    const validation = validateStep1();
    if (validation) {
      setWizardError(validation);
      return;
    }
    setWizardError(null);
    if (authMode === "existing") {
      setRepoForm((current) => ({ ...current, git_auth_secret_id: selectedSecretId }));
      setWizardStep(2);
      return;
    }
    try {
      setWizardSaving(true);
      const generatedKey = `github_pat_${newSecretForm.name
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")}_${Date.now()}`;
      const created = await operatorApi.createSecret({
        ...newSecretForm,
        key: generatedKey,
        name: newSecretForm.name.trim(),
        value: newSecretForm.value.trim(),
        description: newSecretForm.description?.trim() || undefined,
      });
      setSelectedSecretId(created.secret_id);
      setRepoForm((current) => ({ ...current, git_auth_secret_id: created.secret_id }));
      setWizardStep(2);
      setRepoLookupResults([]);
      setSelectedRepoLookup(null);
      setBranches([]);
      setSelectedBranch(null);
    } catch (saveError) {
      setWizardError(tryExtractApiMessage(saveError) ?? toMessage(saveError, "Failed to save token secret."));
    } finally {
      setWizardSaving(false);
    }
  }

  function validateStep2() {
    if (!selectedRepoLookup) {
      return "Select a GitHub repository to continue.";
    }
    return null;
  }

  function handleStep2Next() {
    const validation = validateStep2();
    if (validation) {
      setWizardError(validation);
      return;
    }
    setWizardError(null);
    setWizardStep(3);
  }

  function validateStep3() {
    if (!repoForm.key.trim()) {
      return "Repo key is required.";
    }
    if (!repoForm.name.trim()) {
      return "Repo name is required.";
    }
    if (!repoForm.default_branch.trim()) {
      return "Select a default branch to continue.";
    }
    return null;
  }

  function handleStep3Next() {
    const validation = validateStep3();
    if (validation) {
      setWizardError(validation);
      return;
    }
    setWizardError(null);
    setWizardStep(4);
  }

  function validateStep4() {
    if (repoForm.org_ids.length === 0) {
      return "Select at least one organization.";
    }
    return null;
  }

  async function handleSave() {
    if (!selectedOrg) {
      setWizardError("Select an organization to continue.");
      return;
    }
    const validation = validateStep4();
    if (validation) {
      setWizardError(validation);
      return;
    }
    setWizardError(null);
    try {
      setWizardSaving(true);
      await operatorApi.createRepo(selectedOrg.org_id, {
        ...repoForm,
        key: repoForm.key.trim(),
        name: repoForm.name.trim(),
        github_owner: repoForm.github_owner.trim(),
        github_repo: repoForm.github_repo.trim(),
        visibility: repoForm.visibility,
        default_branch: repoForm.default_branch.trim(),
        org_ids: Array.from(new Set([...repoForm.org_ids, selectedOrg.org_id])),
      });
      setListStatus("Repository connected.");
      setError(null);
      setShowWizard(false);
      resetWizard();
      setLoading(true);
      const nextRepos = await operatorApi.listOrgRepos(selectedOrg.org_id, deferredSearchQuery);
      setRepos(nextRepos);
    } catch (saveError) {
      setWizardError(tryExtractApiMessage(saveError) ?? toMessage(saveError, "Failed to create repository."));
    } finally {
      setWizardSaving(false);
      setLoading(false);
    }
  }

  async function loadRepoLookup(query?: string) {
    if (!selectedOrg || !repoForm.git_auth_secret_id) {
      return;
    }
    try {
      setRepoLookupLoading(true);
      setWizardError(null);
      const results = await operatorApi.lookupGithubRepos(selectedOrg.org_id, {
        secret_id: repoForm.git_auth_secret_id,
        q: query?.trim() || undefined,
        limit: 50,
      });
      setRepoLookupResults(results);
    } catch (loadError) {
      setWizardError(tryExtractApiMessage(loadError) ?? toMessage(loadError, "Failed to look up GitHub repositories."));
      setRepoLookupResults([]);
    } finally {
      setRepoLookupLoading(false);
    }
  }

  async function loadBranches(repo: GitRepoLookupResultResponse) {
    if (!selectedOrg || !repoForm.git_auth_secret_id) {
      return;
    }
    try {
      setBranchLoading(true);
      setWizardError(null);
      const results = await operatorApi.listGithubRepoBranches(selectedOrg.org_id, {
        secret_id: repoForm.git_auth_secret_id,
        github_owner: repo.github_owner,
        github_repo: repo.github_repo,
      });
      setBranches(results);
      const defaultBranch = results.find((branch) => branch.is_default) ?? results[0] ?? null;
      setSelectedBranch(defaultBranch);
      if (defaultBranch) {
        setRepoForm((current) => ({ ...current, default_branch: defaultBranch.name }));
      }
    } catch (loadError) {
      setWizardError(tryExtractApiMessage(loadError) ?? toMessage(loadError, "Failed to load branches."));
      setBranches([]);
      setSelectedBranch(null);
    } finally {
      setBranchLoading(false);
    }
  }

  async function refreshRepoList() {
    if (!selectedOrg || !canReadRepos) {
      return;
    }
    setLoading(true);
    try {
      const nextRepos = await operatorApi.listOrgRepos(selectedOrg.org_id, deferredSearchQuery);
      setRepos(nextRepos);
    } catch (loadError) {
      setError(tryExtractApiMessage(loadError) ?? toMessage(loadError, "Failed to load repositories."));
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteRepo(repo: GitRepoResponse) {
    if (!canDeleteRepos) {
      return;
    }
    try {
      setDeletingRepoId(repo.repo_id);
      setError(null);
      setListStatus(null);
      await operatorApi.deleteRepo(repo.repo_id);
      setListStatus("Repository archived.");
      setConfirmDeleteRepoId(null);
      await refreshRepoList();
    } catch (deleteError) {
      setError(tryExtractApiMessage(deleteError) ?? toMessage(deleteError, "Failed to delete repository."));
    } finally {
      setDeletingRepoId(null);
    }
  }

  function startEditRepo(repo: GitRepoResponse) {
    setEditingRepoId(repo.repo_id);
    setEditForm({
      org_ids: [...repo.org_ids],
    });
    setEditAddOrgId("");
    setError(null);
    setListStatus(null);
  }

  async function handleSaveRepoEdit(repo: GitRepoResponse) {
    const nextOrgIds = editForm?.org_ids ?? [];
    if (nextOrgIds.length === 0) {
      setError("At least one organization must remain mapped.");
      return;
    }
    try {
      setEditSaving(true);
      setError(null);
      setListStatus(null);
      await operatorApi.updateRepo(repo.repo_id, {
        org_ids: nextOrgIds,
      });
      setListStatus("Repository updated.");
      cancelEditRepo();
      await refreshRepoList();
    } catch (saveError) {
      setError(tryExtractApiMessage(saveError) ?? toMessage(saveError, "Failed to update repository."));
    } finally {
      setEditSaving(false);
    }
  }

  function handleAddOrgMapping() {
    if (!editAddOrgId) {
      return;
    }
    setEditForm((current) => {
      if (!current) {
        return current;
      }
      const nextOrgIds = current.org_ids ?? [];
      if (nextOrgIds.includes(editAddOrgId)) {
        return current;
      }
      return {
        ...current,
        org_ids: [...nextOrgIds, editAddOrgId],
      };
    });
    setEditAddOrgId("");
  }

  function handleRemoveOrgMapping(orgId: string) {
    setEditForm((current) => {
      if (!current) {
        return current;
      }
      const nextOrgIds = current.org_ids ?? [];
      return {
        ...current,
        org_ids: nextOrgIds.filter((value) => value !== orgId),
      };
    });
  }

  if (!canReadRepos) {
    return (
      <div className="space-y-6">
        <div className="mb-6">
          <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Git Repositories
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Connect GitHub repositories and manage the organization mappings that make them available to Orcha.
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Access denied</CardTitle>
            <CardDescription>
              This settings page requires the `repo.read` permission.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (!selectedOrg) {
    const organizationsAvailable = organizations.length > 0;
    return (
      <div className="space-y-6">
        <div className="mb-6">
          <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Git Repositories
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            {organizationsAvailable
              ? "Loading the active organization before rendering repository settings."
              : "Select an organization to manage workspace repository integrations."}
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>{organizationsAvailable ? "Loading organization context" : "Select an organization"}</CardTitle>
            <CardDescription>
              {organizationsAvailable
                ? "The shared settings shell is still resolving the organization tied to this workspace. Repository actions will appear as soon as that context is ready."
                : "Use the shared settings header to choose the organization that should own or review the current repository mappings."}
            </CardDescription>
          </CardHeader>
          {organizationsAvailable ? (
            <CardContent>
              <div className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
                <Loader2 className="size-4 animate-spin" />
                <span>Resolving workspace organization...</span>
              </div>
            </CardContent>
          ) : null}
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Git Repositories
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Connect GitHub repositories, keep PAT-backed access current, and control which organizations can use each workspace repository integration.
          </p>
        </div>
        <Badge className="border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
          {selectedOrg.name}
        </Badge>
      </div>

      {error ? (
        <Card className="border-rose-200 dark:border-rose-900/50">
          <CardContent className="pt-6">
            <p className="font-medium text-rose-700 dark:text-rose-300">Error</p>
            <p className="pt-1 text-sm text-rose-700 dark:text-rose-300">{error}</p>
            <Button className="mt-3" variant="outline" onClick={() => void refreshRepoList()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {listStatus ? (
        <Card className="border-emerald-200 dark:border-emerald-900/50">
          <CardContent className="pt-6">
            <p className="text-sm text-emerald-700 dark:text-emerald-300">{listStatus}</p>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-500" />
            <Input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search repositories..."
              className="pl-10"
            />
          </div>
          {canManageRepos ? (
            <Button onClick={startWizard} disabled={!selectedOrg}>
              <Plus className="size-4" />
              Add Repository
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {showWizard && canManageRepos ? (
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <CardTitle>
                  {wizardStep === 1
                    ? "Connect GitHub repository"
                    : wizardStep === 2
                      ? "Select repository"
                      : wizardStep === 3
                        ? "Confirm repository"
                        : "Organization mapping"}
                </CardTitle>
                <CardDescription>Step {wizardStep} of 4</CardDescription>
              </div>
              <Badge className="border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                PAT flow
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            {wizardError ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-300">
                {wizardError}
              </div>
            ) : null}

            {wizardStep === 1 ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-4 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
                  <p className="font-medium text-zinc-900 dark:text-zinc-100">Use a GitHub personal access token (classic).</p>
                  <p className="pt-2">
                    Create one in GitHub under Developer Settings and grant `repo` plus `admin:repo_hook`. Store that token as a secret here so Orcha can discover and validate repositories without exposing the token after save.
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Button
                    variant={authMode === "existing" ? "default" : "outline"}
                    onClick={() => setAuthMode("existing")}
                    disabled={!canReadSecrets}
                  >
                    Use existing PAT
                  </Button>
                  <Button
                    variant={authMode === "new" ? "default" : "outline"}
                    onClick={() => setAuthMode("new")}
                    disabled={!canManageSecrets}
                  >
                    Create new PAT
                  </Button>
                </div>

                {authMode === "existing" ? (
                  <FormField label="PAT secret" htmlFor="git-repo-pat-secret" required>
                    <Select
                      id="git-repo-pat-secret"
                      value={selectedSecretId}
                      onChange={(event) => setSelectedSecretId(event.target.value)}
                    >
                      <option value="">
                        {!canReadSecrets
                          ? "Permission required to read secrets"
                          : secretsLoading
                            ? "Loading secrets..."
                            : "Select a secret"}
                      </option>
                      {gitSecrets.map((secret) => (
                        <option key={secret.secret_id} value={secret.secret_id}>
                          {secret.name || secret.key}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField label="Secret name" htmlFor="git-repo-secret-name" required>
                      <Input
                        id="git-repo-secret-name"
                        value={newSecretForm.name}
                        onChange={(event) =>
                          setNewSecretForm((current) => ({ ...current, name: event.target.value }))
                        }
                        placeholder="GitHub PAT"
                      />
                    </FormField>
                    <FormField
                      className="md:col-span-2"
                      label="Personal access token"
                      htmlFor="git-repo-secret-value"
                      required
                    >
                      <Input
                        id="git-repo-secret-value"
                        value={newSecretForm.value}
                        onChange={(event) =>
                          setNewSecretForm((current) => ({ ...current, value: event.target.value }))
                        }
                        placeholder="ghp_..."
                      />
                    </FormField>
                  </div>
                )}
              </div>
            ) : null}

            {wizardStep === 2 ? (
              <div className="space-y-4">
                <div className="relative max-w-md">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-500" />
                  <Input
                    value={repoLookupQuery}
                    onChange={(event) => {
                      const nextQuery = event.target.value;
                      setRepoLookupQuery(nextQuery);
                      void loadRepoLookup(nextQuery);
                    }}
                    placeholder="Search GitHub repositories..."
                    className="pl-10"
                  />
                </div>
                <div className="max-h-80 overflow-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
                  {repoLookupLoading ? (
                    <div className="p-6 text-sm text-zinc-500">Loading repositories…</div>
                  ) : repoLookupResults.length === 0 ? (
                    <div className="p-6 text-sm text-zinc-500">No repositories found. Try refining your search.</div>
                  ) : (
                    <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
                      {repoLookupResults.map((repo) => {
                        const isSelected = selectedRepoLookup?.full_name === repo.full_name;
                        return (
                          <button
                            key={repo.full_name}
                            type="button"
                            className={[
                              "w-full px-4 py-3 text-left transition",
                              isSelected
                                ? "bg-zinc-100 dark:bg-zinc-800"
                                : "hover:bg-zinc-50 dark:hover:bg-zinc-900",
                            ].join(" ")}
                            onClick={() => {
                              setSelectedRepoLookup(repo);
                              setRepoForm((current) => ({
                                ...current,
                                key: repo.github_repo,
                                name: repo.github_repo,
                                github_owner: repo.github_owner,
                                github_repo: repo.github_repo,
                                visibility: repo.visibility,
                                default_branch: repo.default_branch,
                              }));
                            }}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <p className="font-medium text-zinc-900 dark:text-zinc-100">{repo.full_name}</p>
                                <p className="pt-1 text-xs text-zinc-500">Default branch: {repo.default_branch}</p>
                              </div>
                              <div className="flex flex-wrap items-center justify-end gap-2">
                                <Badge className="border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                                  {repo.visibility === "internal"
                                    ? "Internal"
                                    : repo.is_private
                                      ? "Private"
                                      : "Public"}
                                </Badge>
                                {repo.is_archived ? (
                                  <Badge className="border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300">
                                    Archived
                                  </Badge>
                                ) : null}
                                {isSelected ? (
                                  <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-300">
                                    Selected
                                  </Badge>
                                ) : null}
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {wizardStep === 3 ? (
              <div className="space-y-6">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Select branch</h3>
                    {branchLoading ? (
                      <span className="text-xs text-zinc-500">Loading…</span>
                    ) : null}
                  </div>
                  <div className="rounded-xl border border-zinc-200 dark:border-zinc-800">
                    {branches.length === 0 ? (
                      <div className="p-4 text-sm text-zinc-500">No branches found.</div>
                    ) : (
                      <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
                        {branches.map((branch) => {
                          const isSelected = selectedBranch?.name === branch.name;
                          return (
                            <button
                              key={branch.name}
                              type="button"
                              className={[
                                "w-full px-4 py-3 text-left text-sm transition",
                                isSelected
                                  ? "bg-zinc-100 dark:bg-zinc-800"
                                  : "hover:bg-zinc-50 dark:hover:bg-zinc-900",
                              ].join(" ")}
                              onClick={() => {
                                setSelectedBranch(branch);
                                setRepoForm((current) => ({ ...current, default_branch: branch.name }));
                              }}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <span className="text-zinc-900 dark:text-zinc-100">{branch.name}</span>
                                <div className="flex flex-wrap items-center gap-2">
                                  {branch.is_default ? (
                                    <Badge className="border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                                      Default
                                    </Badge>
                                  ) : null}
                                  {isSelected ? (
                                    <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-300">
                                      Selected
                                    </Badge>
                                  ) : null}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <FormField label="Repo key" htmlFor="git-repo-key" required>
                    <Input id="git-repo-key" value={repoForm.key} readOnly className="bg-zinc-50 dark:bg-zinc-950" />
                  </FormField>
                  <FormField label="Repo name" htmlFor="git-repo-name" required>
                    <Input id="git-repo-name" value={repoForm.name} readOnly className="bg-zinc-50 dark:bg-zinc-950" />
                  </FormField>
                  <FormField label="Visibility" htmlFor="git-repo-visibility" required>
                    <Input
                      id="git-repo-visibility"
                      value={repoForm.visibility}
                      readOnly
                      className="bg-zinc-50 capitalize dark:bg-zinc-950"
                    />
                  </FormField>
                  <FormField label="Default branch" htmlFor="git-repo-default-branch" required>
                    <Input
                      id="git-repo-default-branch"
                      value={repoForm.default_branch}
                      readOnly
                      className="bg-zinc-50 dark:bg-zinc-950"
                    />
                  </FormField>
                </div>
              </div>
            ) : null}

            {wizardStep === 4 ? (
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Organization mappings</h3>
                  <p className="pt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    Select one or more organizations that can use this workspace repository integration.
                  </p>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {organizations.map((org) => {
                    const checked = repoForm.org_ids.includes(org.org_id);
                    return (
                      <label
                        key={org.org_id}
                        className="flex items-center gap-3 rounded-xl border border-zinc-200 px-4 py-3 text-sm dark:border-zinc-800"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => {
                            const nextOrgIds = event.target.checked
                              ? [...repoForm.org_ids, org.org_id]
                              : repoForm.org_ids.filter((value) => value !== org.org_id);
                            setRepoForm((current) => ({
                              ...current,
                              org_ids: Array.from(new Set(nextOrgIds)),
                            }));
                          }}
                        />
                        <span className="text-zinc-900 dark:text-zinc-100">{org.name}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            ) : null}

            <div className="flex flex-col gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                {wizardStep > 1 ? (
                  <Button
                    variant="outline"
                    onClick={() => setWizardStep((current) => (current - 1) as WizardStep)}
                    disabled={wizardSaving}
                  >
                    Back
                  </Button>
                ) : null}
              </div>
              <div className="flex items-center justify-center gap-2">
                {[1, 2, 3, 4].map((step) => (
                  <span
                    key={step}
                    className={[
                      "h-2 w-2 rounded-full",
                      wizardStep === step
                        ? "bg-zinc-900 dark:bg-zinc-100"
                        : "bg-zinc-300 dark:bg-zinc-700",
                    ].join(" ")}
                  />
                ))}
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowWizard(false);
                    resetWizard();
                  }}
                  disabled={wizardSaving}
                >
                  Cancel
                </Button>
                {wizardStep < 4 ? (
                  <Button
                    onClick={() => {
                      if (wizardStep === 1) {
                        void handleStep1Next();
                      } else if (wizardStep === 2) {
                        handleStep2Next();
                      } else {
                        handleStep3Next();
                      }
                    }}
                    disabled={wizardSaving}
                  >
                    {wizardSaving ? <Loader2 className="size-4 animate-spin" /> : null}
                    Next
                  </Button>
                ) : (
                  <Button onClick={() => void handleSave()} disabled={wizardSaving}>
                    {wizardSaving ? <Loader2 className="size-4 animate-spin" /> : null}
                    Save Repository
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card className="[&_td]:align-top [&_th]:align-top">
        <CardHeader>
          <CardTitle>Connected repositories</CardTitle>
          <CardDescription>
            Repositories here stay tied to the selected organization context and can be shared across additional organizations through explicit mappings.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">Repo</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">GitHub</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">Default branch</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">Updated</th>
                  {canManageRepos || canDeleteRepos ? (
                    <th className="px-4 py-3 text-right text-sm font-semibold text-zinc-900 dark:text-zinc-100">Actions</th>
                  ) : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {loading ? (
                  <tr>
                    <td
                      colSpan={canManageRepos || canDeleteRepos ? 6 : 5}
                      className="px-4 py-10 text-center text-sm text-zinc-500"
                    >
                      Loading…
                    </td>
                  </tr>
                ) : repos.length === 0 ? (
                  <tr>
                    <td
                      colSpan={canManageRepos || canDeleteRepos ? 6 : 5}
                      className="px-4 py-10 text-center text-sm text-zinc-500"
                    >
                      <div className="space-y-3">
                        <p className="font-medium text-zinc-900 dark:text-zinc-100">
                          No Git repositories are connected for {selectedOrg.name} yet.
                        </p>
                        {canManageRepos ? (
                          <Button variant="outline" onClick={startWizard}>
                            <Github className="size-4" />
                            Add Repository
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ) : (
                  repos.map((repo, index) => {
                    const archived = Boolean(repo.archived_at);
                    const showEdit = editingRepoId === repo.repo_id;
                    const showDeleteConfirm = confirmDeleteRepoId === repo.repo_id;
                    const orgsWithProducts = repo.org_mappings.filter((mapping) => mapping.active_product_count > 0);
                    const deleteBlocked = archived || orgsWithProducts.length > 0;
                    const deleteHint = orgsWithProducts.length
                      ? `Used by: ${orgsWithProducts.map((mapping) => `${mapping.org_name} (${mapping.active_product_count})`).join(", ")}`
                      : archived
                        ? "Repository already archived"
                        : "Archive repository";
                    return (
                      <Fragment key={repo.repo_id}>
                        <tr className={index % 2 === 1 ? "bg-zinc-50/70 dark:bg-zinc-900/30" : undefined}>
                          <td className="px-4 py-4 text-sm text-zinc-900 dark:text-zinc-100">
                            <p className="font-medium">{repo.name}</p>
                            <p className="pt-1 text-xs text-zinc-500">{repo.key}</p>
                            <p className="pt-2 text-xs text-zinc-500">
                              Orgs: {repo.org_mappings.map((mapping) => mapping.org_name).join(", ")}
                            </p>
                          </td>
                          <td className="px-4 py-4 text-sm text-zinc-600 dark:text-zinc-400">
                            <div className="space-y-2">
                              <p>
                                {repo.github_owner}/{repo.github_repo}
                              </p>
                              <Badge className="border-zinc-200 bg-zinc-100 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
                                {repo.visibility === "internal"
                                  ? "Internal"
                                  : repo.visibility === "public"
                                    ? "Public"
                                    : "Private"}
                              </Badge>
                            </div>
                          </td>
                          <td className="px-4 py-4 text-sm text-zinc-600 dark:text-zinc-400">{repo.default_branch}</td>
                          <td className="px-4 py-4">
                            <Badge
                              className={
                                archived
                                  ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300"
                                  : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-300"
                              }
                            >
                              {archived ? "Archived" : "Active"}
                            </Badge>
                          </td>
                          <td className="px-4 py-4 text-sm text-zinc-600 dark:text-zinc-400">
                            {formatDateTime(repo.updated_at)}
                          </td>
                          {canManageRepos || canDeleteRepos ? (
                            <td className="relative px-4 py-4 text-right">
                              <div className="inline-flex items-center justify-end gap-1">
                                {canManageRepos ? (
                                  <button
                                    type="button"
                                    className={iconButtonClassName()}
                                    title="Edit repository"
                                    aria-label={`Edit ${repo.name}`}
                                    onClick={() => {
                                      if (showEdit) {
                                        cancelEditRepo();
                                      } else {
                                        startEditRepo(repo);
                                      }
                                    }}
                                  >
                                    <Pencil className="size-4" />
                                  </button>
                                ) : null}
                                {canDeleteRepos ? (
                                  <button
                                    type="button"
                                    className={iconButtonClassName(true)}
                                    title={deleteHint}
                                    aria-label={`Delete ${repo.name}`}
                                    disabled={deleteBlocked || deletingRepoId === repo.repo_id}
                                    onClick={() =>
                                      setConfirmDeleteRepoId((current) =>
                                        current === repo.repo_id ? null : repo.repo_id,
                                      )
                                    }
                                  >
                                    <Trash2 className="size-4" />
                                  </button>
                                ) : null}
                              </div>

                              {showDeleteConfirm && !deleteBlocked ? (
                                <div className="absolute right-4 top-full z-20 mt-2 w-72 rounded-xl border border-rose-200 bg-rose-50 p-3 text-left shadow-lg dark:border-rose-900/50 dark:bg-rose-950/40">
                                  <p className="text-sm text-rose-700 dark:text-rose-300">
                                    Archive this repository integration?
                                  </p>
                                  <div className="mt-3 flex items-center justify-end gap-2">
                                    <Button
                                      variant="outline"
                                      className="h-8 px-3"
                                      onClick={() => setConfirmDeleteRepoId(null)}
                                      disabled={deletingRepoId === repo.repo_id}
                                    >
                                      Cancel
                                    </Button>
                                    <button
                                      type="button"
                                      className="inline-flex h-8 items-center justify-center rounded-md bg-rose-600 px-3 text-sm font-medium text-white transition hover:bg-rose-700 disabled:opacity-60"
                                      onClick={() => void handleDeleteRepo(repo)}
                                      disabled={deletingRepoId === repo.repo_id}
                                    >
                                      {deletingRepoId === repo.repo_id ? (
                                        <Loader2 className="size-4 animate-spin" />
                                      ) : null}
                                      Delete
                                    </button>
                                  </div>
                                </div>
                              ) : null}
                            </td>
                          ) : null}
                        </tr>
                        {showEdit && editForm ? (
                          <tr>
                            <td
                              colSpan={canManageRepos || canDeleteRepos ? 6 : 5}
                              className="bg-zinc-50/60 px-4 py-4 dark:bg-zinc-950/40"
                            >
                              <div className="space-y-4">
                                <div>
                                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                    Organization mappings
                                  </p>
                                  <p className="pt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                    Control which organizations can use this repository. Mappings with active products cannot be removed.
                                  </p>
                                </div>

                                <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
                                  <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
                                    <thead>
                                      <tr>
                                        <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">Organization</th>
                                        <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-900 dark:text-zinc-100">Active products</th>
                                        <th className="px-4 py-3 text-right text-sm font-semibold text-zinc-900 dark:text-zinc-100">Actions</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                                      {(editForm.org_ids ?? []).map((orgId, rowIndex) => {
                                        const fromOrg = organizations.find((org) => org.org_id === orgId);
                                        const fromMapping = repo.org_mappings.find((mapping) => mapping.org_id === orgId);
                                        const orgName = fromOrg?.name ?? fromMapping?.org_name ?? orgId;
                                        const activeProductCount = fromMapping?.active_product_count ?? 0;
                                        const canRemove = (editForm.org_ids?.length ?? 0) > 1 && activeProductCount === 0;
                                        return (
                                          <tr key={orgId} className={rowIndex % 2 === 1 ? "bg-zinc-50/70 dark:bg-zinc-900/30" : undefined}>
                                            <td className="px-4 py-3 text-sm text-zinc-900 dark:text-zinc-100">{orgName}</td>
                                            <td className="px-4 py-3 text-sm text-zinc-600 dark:text-zinc-400">{activeProductCount}</td>
                                            <td className="px-4 py-3 text-right">
                                              <button
                                                type="button"
                                                className={iconButtonClassName(true)}
                                                title={
                                                  activeProductCount > 0
                                                    ? "Mapping has active products"
                                                    : (editForm.org_ids?.length ?? 0) <= 1
                                                      ? "At least one mapping is required"
                                                      : "Remove mapping"
                                                }
                                                disabled={!canRemove}
                                                onClick={() => handleRemoveOrgMapping(orgId)}
                                              >
                                                <Trash2 className="size-4" />
                                              </button>
                                            </td>
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                </div>

                                <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                                  <Select
                                    value={editAddOrgId}
                                    onChange={(event) => setEditAddOrgId(event.target.value)}
                                    disabled={
                                      organizations.filter(
                                        (org) => !(editForm.org_ids ?? []).includes(org.org_id),
                                      ).length === 0
                                    }
                                  >
                                    <option value="">
                                      {organizations.filter(
                                        (org) => !(editForm.org_ids ?? []).includes(org.org_id),
                                      ).length === 0
                                        ? "No remaining organizations"
                                        : "Select organization"}
                                    </option>
                                    {organizations
                                      .filter((org) => !(editForm.org_ids ?? []).includes(org.org_id))
                                      .map((org) => (
                                        <option key={org.org_id} value={org.org_id}>
                                          {org.name}
                                        </option>
                                      ))}
                                  </Select>
                                  <Button variant="outline" onClick={handleAddOrgMapping} disabled={!editAddOrgId}>
                                    <Plus className="size-4" />
                                    Save mapping
                                  </Button>
                                </div>

                                <div className="flex items-center justify-end gap-2">
                                  <Button variant="outline" onClick={cancelEditRepo} disabled={editSaving}>
                                    Cancel
                                  </Button>
                                  <Button onClick={() => void handleSaveRepoEdit(repo)} disabled={editSaving}>
                                    {editSaving ? <Loader2 className="size-4 animate-spin" /> : null}
                                    Save
                                  </Button>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
