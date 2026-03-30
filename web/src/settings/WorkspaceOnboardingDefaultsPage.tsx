import { AlertTriangle, Loader2, Save, Wrench } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { operatorApi } from "../operator-api";
import type { SecretResponse } from "../operator-types";
import {
  normalizeOnboardingSecretKeys,
  type ProductOnboardingDefaults,
  type ProductOnboardingDefaultsRecord,
} from "../onboarding-defaults";
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

type BaselineMode = "stable" | "candidate" | "custom";

function resolveBaselineMode(channel: string): BaselineMode {
  return channel === "stable" || channel === "candidate" ? channel : "custom";
}

function buildStatusOptionsText(defaults: ProductOnboardingDefaults) {
  return normalizeOnboardingSecretKeys([
    defaults.github.readyStatus,
    "In Progress",
    defaults.github.doneStatus,
  ]).join(", ");
}

function formatAuditDate(value: string | null | undefined) {
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

function FieldBlock({
  label,
  htmlFor,
  hint,
  required = false,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <FormField
      label={label}
      htmlFor={htmlFor}
      description={hint}
      required={required}
    >
      {children}
    </FormField>
  );
}

export default function WorkspaceOnboardingDefaultsPage({
  selectedOrg,
  defaultsRecord,
  onSaveDefaults,
}: {
  selectedOrg: WorkspaceOrganization | null;
  defaultsRecord: ProductOnboardingDefaultsRecord;
  onSaveDefaults: (
    orgId: string,
    defaults: ProductOnboardingDefaults,
    existingValue: unknown,
  ) => Promise<ProductOnboardingDefaultsRecord>;
}) {
  const [draft, setDraft] = useState<ProductOnboardingDefaults>(defaultsRecord.defaults);
  const [baselineMode, setBaselineMode] = useState<BaselineMode>(
    resolveBaselineMode(defaultsRecord.defaults.baseline.channel),
  );
  const [customBaselineChannel, setCustomBaselineChannel] = useState(
    resolveBaselineMode(defaultsRecord.defaults.baseline.channel) === "custom"
      ? defaultsRecord.defaults.baseline.channel
      : "",
  );
  const [secretSelection, setSecretSelection] = useState("");
  const [secrets, setSecrets] = useState<SecretResponse[]>([]);
  const [secretsLoading, setSecretsLoading] = useState(true);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [formNotice, setFormNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(defaultsRecord.defaults);
    setBaselineMode(resolveBaselineMode(defaultsRecord.defaults.baseline.channel));
    setCustomBaselineChannel(
      resolveBaselineMode(defaultsRecord.defaults.baseline.channel) === "custom"
        ? defaultsRecord.defaults.baseline.channel
        : "",
    );
    setSecretSelection("");
    setFormError(null);
    setFormNotice(null);
  }, [selectedOrg?.org_id, defaultsRecord.setting?.updated_at, defaultsRecord.error]);

  useEffect(() => {
    let cancelled = false;
    setSecretsLoading(true);
    setSecretsError(null);
    operatorApi
      .listSecrets()
      .then((nextSecrets) => {
        if (!cancelled) {
          setSecrets(nextSecrets);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setSecrets([]);
          setSecretsError(error instanceof Error ? error.message : "Failed to load secret inventory.");
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
  }, []);

  function updateDraft(
    updater: (current: ProductOnboardingDefaults) => ProductOnboardingDefaults,
  ) {
    setFormError(null);
    setFormNotice(null);
    setDraft((current) => updater(current));
  }

  function toggleSecretKey(secretKey: string) {
    updateDraft((current) => ({
      ...current,
      activation: {
        ...current.activation,
        requiredSecretKeys: current.activation.requiredSecretKeys.includes(secretKey)
          ? current.activation.requiredSecretKeys.filter((item) => item !== secretKey)
          : normalizeOnboardingSecretKeys([...current.activation.requiredSecretKeys, secretKey]),
      },
    }));
  }

  function addSelectedSecretKey(secretKey: string) {
    const normalized = secretKey.trim();
    if (!normalized) {
      return;
    }
    updateDraft((current) => ({
      ...current,
      activation: {
        ...current.activation,
        requiredSecretKeys: normalizeOnboardingSecretKeys([
          ...current.activation.requiredSecretKeys,
          normalized,
        ]),
      },
    }));
    setSecretSelection("");
  }

  async function saveDefaults() {
    if (!selectedOrg) {
      setFormError("Select an organization from the header before saving workspace defaults.");
      return;
    }

    const resolvedBaselineChannel =
      baselineMode === "custom"
        ? customBaselineChannel.trim()
        : baselineMode;

    if (!draft.github.statusField.trim()) {
      setFormError("Status field is required.");
      return;
    }
    if (!draft.github.readyStatus.trim()) {
      setFormError("Ready status is required.");
      return;
    }
    if (!draft.github.doneStatus.trim()) {
      setFormError("Done status is required.");
      return;
    }
    if (!resolvedBaselineChannel) {
      setFormError("Choose a baseline channel or provide a custom channel.");
      return;
    }
    if (/\s/.test(resolvedBaselineChannel)) {
      setFormError("Baseline channel cannot contain spaces.");
      return;
    }

    setSaving(true);
    setFormError(null);
    setFormNotice(null);
    try {
      const nextRecord = await onSaveDefaults(
        selectedOrg.org_id,
        {
          ...draft,
          baseline: {
            channel: resolvedBaselineChannel,
          },
          activation: {
            requiredSecretKeys: normalizeOnboardingSecretKeys(draft.activation.requiredSecretKeys),
          },
        },
        defaultsRecord.rawValue,
      );
      setDraft(nextRecord.defaults);
      setBaselineMode(resolveBaselineMode(nextRecord.defaults.baseline.channel));
      setCustomBaselineChannel(
        resolveBaselineMode(nextRecord.defaults.baseline.channel) === "custom"
          ? nextRecord.defaults.baseline.channel
          : "",
      );
      setFormNotice("Saved workspace onboarding defaults.");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Saving workspace defaults failed.");
    } finally {
      setSaving(false);
    }
  }

  if (!selectedOrg) {
    return (
      <div className="space-y-6">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-muted-foreground">Settings</p>
          <h1 className="pt-2 text-2xl font-semibold text-foreground">Workspace</h1>
          <p className="pt-2 text-sm text-muted-foreground">
            Choose an organization from the header before editing onboarding defaults.
          </p>
        </div>
        <Card className="shadow-none">
          <CardContent className="py-8 text-sm text-muted-foreground">
            No organization is currently selected.
          </CardContent>
        </Card>
      </div>
    );
  }

  const baselineSummary =
    baselineMode === "custom"
      ? customBaselineChannel.trim() || "Custom channel pending"
      : baselineMode;
  const selectedSecretKeys = normalizeOnboardingSecretKeys(draft.activation.requiredSecretKeys);
  const availableSecrets = secrets.filter((secret) => !selectedSecretKeys.includes(secret.key));
  const unknownSecretKeys = selectedSecretKeys.filter(
    (secretKey) => !secrets.some((secret) => secret.key === secretKey),
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm uppercase tracking-[0.2em] text-muted-foreground">Settings</p>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">Workspace</h1>
          <Badge className="border-border bg-secondary text-secondary-foreground">
            {selectedOrg.name}
          </Badge>
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Save onboarding defaults once for this organization, then let seed, adoption, and
          remediation routes start from the same GitHub repository policy, project mapping,
          baseline, execution, and secret policy.
        </p>
      </div>

      {defaultsRecord.error ? (
        <Card className="border-amber-200 bg-amber-50 shadow-none dark:border-amber-900/60 dark:bg-amber-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <AlertTriangle className="mt-0.5 size-5 text-amber-600 dark:text-amber-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Saved defaults need review</p>
              <p className="text-sm text-amber-700 dark:text-amber-200">{defaultsRecord.error}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {formError ? (
        <Card className="border-rose-200 bg-rose-50 shadow-none dark:border-rose-900/60 dark:bg-rose-950/30">
          <CardContent className="flex items-start gap-3 py-5">
            <AlertTriangle className="mt-0.5 size-5 text-rose-600 dark:text-rose-300" />
            <div className="space-y-1">
              <p className="font-medium text-foreground">Workspace defaults were not saved</p>
              <p className="text-sm text-rose-700 dark:text-rose-200">{formError}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {formNotice ? (
        <Card className="border-emerald-200 bg-emerald-50 shadow-none dark:border-emerald-900/60 dark:bg-emerald-950/30">
          <CardContent className="py-5 text-sm text-emerald-700 dark:text-emerald-300">
            {formNotice}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.05fr,0.95fr]">
        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>GitHub bring-up defaults</CardTitle>
              <CardDescription>
                Keep GitHub Project defaults readable and reusable across onboarding flows.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <FieldBlock
                label="Status field"
                htmlFor="workspace-status-field"
                hint="Default GitHub Project field name used during seed and adoption."
                required
              >
                <Input
                  id="workspace-status-field"
                  value={draft.github.statusField}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      github: { ...current.github, statusField: event.target.value },
                    }))
                  }
                />
              </FieldBlock>
              <FieldBlock
                label="Ready status"
                htmlFor="workspace-ready-status"
                hint="Default status option for new work."
                required
              >
                <Input
                  id="workspace-ready-status"
                  value={draft.github.readyStatus}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      github: { ...current.github, readyStatus: event.target.value },
                    }))
                  }
                />
              </FieldBlock>
              <FieldBlock
                label="Done status"
                htmlFor="workspace-done-status"
                hint="Default status option used for completed work."
                required
              >
                <Input
                  id="workspace-done-status"
                  value={draft.github.doneStatus}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      github: { ...current.github, doneStatus: event.target.value },
                    }))
                  }
                />
              </FieldBlock>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Baseline and execution defaults</CardTitle>
              <CardDescription>
                Keep new-product bring-up aligned to the same approved channel and execution profile.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <FieldBlock
                label="Baseline channel"
                htmlFor="workspace-baseline-mode"
                hint="Applies to new seed and adoption requests before product-level overrides."
                required
              >
                <Select
                  id="workspace-baseline-mode"
                  value={baselineMode}
                  onChange={(event) => setBaselineMode(event.target.value as BaselineMode)}
                >
                  <option value="stable">Stable</option>
                  <option value="candidate">Candidate</option>
                  <option value="custom">Custom</option>
                </Select>
              </FieldBlock>
              {baselineMode === "custom" ? (
                <FieldBlock
                  label="Custom channel"
                  htmlFor="workspace-custom-baseline"
                  hint="Use a channel name only when the approved baseline does not map to stable or candidate."
                  required
                >
                  <Input
                    id="workspace-custom-baseline"
                    value={customBaselineChannel}
                    onChange={(event) => setCustomBaselineChannel(event.target.value)}
                    placeholder="release-2026-03"
                  />
                </FieldBlock>
              ) : null}
              <FieldBlock
                label="Execution profile"
                htmlFor="workspace-execution-profile"
                hint="Current operator flows only support the standard Python profile."
                required
              >
                <Select
                  id="workspace-execution-profile"
                  value={draft.execution.profile}
                  onChange={(event) =>
                    updateDraft((current) => ({
                      ...current,
                      execution: { ...current.execution, profile: event.target.value },
                    }))
                  }
                >
                  <option value="standard-python">standard-python</option>
                </Select>
              </FieldBlock>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Required secret policy</CardTitle>
              <CardDescription>
                Reuse the shared secret inventory instead of retyping key names in every onboarding request.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to="/settings/secrets"
                  className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
                >
                  Open secrets
                </Link>
                {secretsLoading ? (
                  <Badge className="border-border bg-secondary text-secondary-foreground">
                    Loading inventory
                  </Badge>
                ) : null}
              </div>
              {secretsError ? (
                <p className="text-sm text-amber-700 dark:text-amber-300">{secretsError}</p>
              ) : null}
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr),auto] md:items-end">
                <FieldBlock
                  label="Add required secret"
                  htmlFor="workspace-required-secret"
                  hint="Select from the shared secret inventory. Create or update secrets in Settings > Secrets."
                >
                  <Select
                    id="workspace-required-secret"
                    value={secretSelection}
                    onChange={(event) => setSecretSelection(event.target.value)}
                    disabled={secretsLoading || availableSecrets.length === 0}
                  >
                    <option value="">
                      {secretsLoading
                        ? "Loading secret inventory..."
                        : availableSecrets.length === 0
                          ? "No additional secrets available"
                          : "Select a secret"}
                    </option>
                    {availableSecrets.map((secret) => (
                      <option key={secret.secret_id} value={secret.key}>
                        {secret.name} • {secret.key} • {secret.has_value ? "Value stored" : "Value missing"}
                      </option>
                    ))}
                  </Select>
                </FieldBlock>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => addSelectedSecretKey(secretSelection)}
                    disabled={!secretSelection.trim()}
                  >
                    Add secret
                  </Button>
                  <Link
                    to="/settings/secrets"
                    className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition hover:bg-accent hover:text-accent-foreground"
                  >
                    Add new secret
                  </Link>
                </div>
              </div>
              {!secretsLoading && !secrets.length ? (
                <p className="text-sm text-muted-foreground">
                  No secrets are currently registered. Create them in Settings before adding them to the required-secret policy.
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {selectedSecretKeys.length ? (
                  selectedSecretKeys.map((secretKey) => {
                    const secret = secrets.find((item) => item.key === secretKey);
                    return (
                      <button
                        key={secretKey}
                        type="button"
                        onClick={() => toggleSecretKey(secretKey)}
                        className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary px-3 py-1 text-sm text-secondary-foreground transition hover:bg-secondary/80"
                      >
                        <span>{secretKey}</span>
                        <Badge
                          className={
                            secret?.has_value
                              ? "border-emerald-400/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              : "border-amber-400/25 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                          }
                        >
                          {secret ? (secret.has_value ? "Value stored" : "Value missing") : "Not in inventory"}
                        </Badge>
                      </button>
                    );
                  })
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No extra secret keys are required beyond the current standard profile defaults.
                  </p>
                )}
              </div>
              {unknownSecretKeys.length ? (
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  Some saved keys are not in the current inventory: {unknownSecretKeys.join(", ")}.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Workspace summary</CardTitle>
              <CardDescription>
                The saved defaults below prepopulate onboarding routes for this organization.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Project field mapping
                </p>
                <p className="pt-2 font-medium text-foreground">
                  {draft.github.statusField} • {buildStatusOptionsText(draft)}
                </p>
              </div>
              <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Baseline and execution
                </p>
                <p className="pt-2 font-medium text-foreground">
                  {baselineSummary} • {draft.execution.profile}
                </p>
              </div>
              <div className="rounded-3xl border border-border/70 bg-muted/30 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  Required secrets
                </p>
                <p className="pt-2 font-medium text-foreground">
                  {selectedSecretKeys.length
                    ? selectedSecretKeys.join(", ")
                    : "No additional org-level secret requirements"}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Audit trail</CardTitle>
              <CardDescription>
                Workspace defaults remain reviewable even after onboarding routes reuse them.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>
                Last updated by{" "}
                <span className="font-medium text-foreground">
                  {defaultsRecord.setting?.updated_by ?? defaultsRecord.setting?.created_by ?? "Not recorded"}
                </span>
              </p>
              <p>{formatAuditDate(defaultsRecord.setting?.updated_at ?? defaultsRecord.setting?.created_at)}</p>
              {!defaultsRecord.setting ? (
                <p>No workspace defaults are saved for this organization yet.</p>
              ) : null}
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader>
              <CardTitle>Operator notes</CardTitle>
              <CardDescription>
                Keep the workspace opinionated, but do not hide per-product overrides.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <div className="flex items-start gap-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
                <Wrench className="mt-0.5 size-4 text-muted-foreground" />
                <p>
                  Seed and adoption start from these values, but operators can still override them
                  per product when a repo needs a different baseline or project mapping.
                </p>
              </div>
              <div className="flex items-start gap-3 rounded-3xl border border-border/70 bg-muted/30 p-4">
                <AlertTriangle className="mt-0.5 size-4 text-muted-foreground" />
                <p>
                  GitHub auth stays in Settings &gt; Git Repositories. Workspace defaults only store
                  the reusable project, baseline, execution, and secret policy that onboarding should
                  start from.
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void saveDefaults()} disabled={saving}>
              {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
              Save defaults
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraft(defaultsRecord.defaults);
                setBaselineMode(resolveBaselineMode(defaultsRecord.defaults.baseline.channel));
                setCustomBaselineChannel(
                  resolveBaselineMode(defaultsRecord.defaults.baseline.channel) === "custom"
                    ? defaultsRecord.defaults.baseline.channel
                    : "",
                );
                setSecretSelection("");
                setFormError(null);
                setFormNotice(null);
              }}
            >
              Reset form
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
