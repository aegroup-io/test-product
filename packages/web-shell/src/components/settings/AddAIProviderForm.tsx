import { type FormEvent, useEffect, useMemo, useState } from "react";

import type { Secret } from "../../api/types";
import { useAuth } from "../../lib/auth-context";
import { api } from "../../lib/api";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface AddAIProviderFormProps {
  onSuccess: () => void;
  onCancel: () => void;
}

type ProviderType = "openai" | "azure_openai" | "anthropic";
type SecretMode = "existing" | "new";

const PROVIDER_OPTIONS: Array<{ value: ProviderType; label: string }> = [
  { value: "openai", label: "OpenAI" },
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "anthropic", label: "Anthropic" },
];

const EMPTY_JSON = "{}";

const parseJsonField = (
  value: string,
): { value: Record<string, unknown>; error: string | null } => {
  if (!value.trim()) {
    return { value: {}, error: null };
  }
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    return { value: parsed, error: null };
  } catch {
    return { value: {}, error: "Invalid JSON. Please provide valid JSON." };
  }
};

const buildSecretKey = (name: string): string => {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const safeSlug = slug || "ai_key";
  return `ai_api_key_${safeSlug}_${Date.now()}`;
};

export default function AddAIProviderForm({ onSuccess, onCancel }: AddAIProviderFormProps) {
  const { hasPermission } = useAuth();
  const canReadSecrets = hasPermission("platform.read");
  const canManageSecrets = hasPermission("platform.manage");

  const [keyValue, setKeyValue] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<ProviderType>("openai");
  const [isActive, setIsActive] = useState(true);
  const [secretMode, setSecretMode] = useState<SecretMode>(canReadSecrets ? "existing" : "new");
  const [apiKeySecretId, setApiKeySecretId] = useState("");
  const [newSecretName, setNewSecretName] = useState("");
  const [newSecretValue, setNewSecretValue] = useState("");
  const [newSecretDescription, setNewSecretDescription] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [organization, setOrganization] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [anthropicVersion, setAnthropicVersion] = useState("");
  const [complianceJson, setComplianceJson] = useState(EMPTY_JSON);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [secretFlowError, setSecretFlowError] = useState<string | null>(null);
  const [secretOptions, setSecretOptions] = useState<Secret[]>([]);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!canReadSecrets) {
      setSecretOptions([]);
      setApiKeySecretId("");
      setSecretsError(null);
      setSecretsLoading(false);
      return;
    }

    let cancelled = false;
    const loadSecrets = async () => {
      setSecretsLoading(true);
      setSecretsError(null);
      try {
        const secrets = await api.listSecrets();
        if (cancelled) {
          return;
        }
        const aiSecrets = secrets.filter((secret) => secret.kind === "ai_api_key");
        setSecretOptions(aiSecrets);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSecretOptions([]);
        setSecretsError(error instanceof Error ? error.message : "Failed to load secrets.");
      } finally {
        if (!cancelled) {
          setSecretsLoading(false);
        }
      }
    };

    void loadSecrets();
    return () => {
      cancelled = true;
    };
  }, [canReadSecrets]);

  useEffect(() => {
    if (!canReadSecrets && secretMode === "existing") {
      setSecretMode("new");
      return;
    }
    if (!canManageSecrets && secretMode === "new" && canReadSecrets) {
      setSecretMode("existing");
    }
  }, [canManageSecrets, canReadSecrets, secretMode]);

  useEffect(() => {
    if (secretMode !== "existing") {
      return;
    }
    if (!apiKeySecretId && secretOptions.length > 0) {
      setApiKeySecretId(secretOptions[0].secret_id);
    }
  }, [apiKeySecretId, secretMode, secretOptions]);

  const secretLabel = useMemo(
    () =>
      secretOptions.reduce<Record<string, string>>((acc, secret) => {
        acc[secret.secret_id] = `${secret.name} (${secret.key})`;
        return acc;
      }, {}),
    [secretOptions],
  );

  const resetForm = () => {
    setKeyValue("");
    setName("");
    setType("openai");
    setIsActive(true);
    setSecretMode(canReadSecrets ? "existing" : "new");
    setApiKeySecretId(secretOptions[0]?.secret_id ?? "");
    setNewSecretName("");
    setNewSecretValue("");
    setNewSecretDescription("");
    setBaseUrl("");
    setOrganization("");
    setEndpoint("");
    setApiVersion("");
    setAnthropicVersion("");
    setComplianceJson(EMPTY_JSON);
    setComplianceError(null);
    setSecretFlowError(null);
  };

  const buildConfig = (secretId: string): Record<string, unknown> => {
    if (type === "openai") {
      const config: Record<string, unknown> = { api_key_secret_id: secretId };
      if (baseUrl.trim()) {
        config.base_url = baseUrl.trim();
      }
      if (organization.trim()) {
        config.organization = organization.trim();
      }
      return config;
    }
    if (type === "azure_openai") {
      return {
        api_key_secret_id: secretId,
        endpoint: endpoint.trim(),
        api_version: apiVersion.trim(),
      };
    }
    const config: Record<string, unknown> = { api_key_secret_id: secretId };
    if (baseUrl.trim()) {
      config.base_url = baseUrl.trim();
    }
    if (anthropicVersion.trim()) {
      config.anthropic_version = anthropicVersion.trim();
    }
    return config;
  };

  const isValid = (): boolean => {
    if (!keyValue.trim() || !name.trim()) {
      return false;
    }
    if (type === "azure_openai" && (!endpoint.trim() || !apiVersion.trim())) {
      return false;
    }
    if (secretMode === "existing") {
      return canReadSecrets && Boolean(apiKeySecretId.trim());
    }
    return canManageSecrets && Boolean(newSecretName.trim() && newSecretValue.trim());
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!isValid()) {
      return;
    }

    const parsedCompliance = parseJsonField(complianceJson);
    setComplianceError(parsedCompliance.error);
    if (parsedCompliance.error) {
      return;
    }

    setIsSubmitting(true);
    setSecretFlowError(null);
    try {
      let resolvedSecretId = apiKeySecretId.trim();
      if (secretMode === "new") {
        const createdSecret = await api.createSecret({
          key: buildSecretKey(newSecretName),
          name: newSecretName.trim(),
          kind: "ai_api_key",
          value: newSecretValue.trim(),
          description: newSecretDescription.trim() || null,
        });
        resolvedSecretId = createdSecret.secret_id;
        setApiKeySecretId(createdSecret.secret_id);
        if (canReadSecrets) {
          setSecretOptions((prev) => {
            const existing = prev.filter((secret) => secret.secret_id !== createdSecret.secret_id);
            return [createdSecret, ...existing];
          });
        }
      }

      await api.createProvider({
        key: keyValue.trim(),
        name: name.trim(),
        type,
        is_active: isActive,
        config: buildConfig(resolvedSecretId),
        compliance: parsedCompliance.value,
      });
      resetForm();
      onSuccess();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to create AI provider. Please try again.";
      setSecretFlowError(message);
      alert(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    resetForm();
    onCancel();
  };

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>Add Provider</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label
                htmlFor="provider-key"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Key
              </label>
              <Input
                id="provider-key"
                value={keyValue}
                onChange={(event) => setKeyValue(event.target.value)}
                placeholder="openai-gpt"
                required
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="provider-name"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Name
              </label>
              <Input
                id="provider-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="OpenAI GPT"
                required
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="provider-type"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Type
              </label>
              <select
                id="provider-type"
                value={type}
                onChange={(event) => setType(event.target.value as ProviderType)}
                className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
                required
              >
                {PROVIDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              id="provider-active"
              type="checkbox"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
            />
            <label htmlFor="provider-active" className="text-sm text-zinc-700 dark:text-zinc-300">
              Active
            </label>
          </div>

          <div className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">API Key Secret</h3>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Select an existing AI API key secret or create a new one inline.
              </p>
            </div>
            <div className="flex flex-wrap gap-4">
              <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="radio"
                  name="provider-secret-mode"
                  value="existing"
                  checked={secretMode === "existing"}
                  onChange={() => setSecretMode("existing")}
                  disabled={!canReadSecrets}
                />
                Use existing secret
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="radio"
                  name="provider-secret-mode"
                  value="new"
                  checked={secretMode === "new"}
                  onChange={() => setSecretMode("new")}
                  disabled={!canManageSecrets}
                />
                Create new secret
              </label>
            </div>

            {secretMode === "existing" ? (
              <div className="space-y-2">
                <label
                  htmlFor="provider-secret-id"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Secret
                </label>
                <select
                  id="provider-secret-id"
                  value={apiKeySecretId}
                  onChange={(event) => setApiKeySecretId(event.target.value)}
                  disabled={secretsLoading || secretOptions.length === 0}
                  className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-70 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
                  required
                >
                  {secretOptions.length === 0 ? (
                    <option value="">No AI API key secrets found</option>
                  ) : (
                    secretOptions.map((secret) => (
                      <option key={secret.secret_id} value={secret.secret_id}>
                        {secretLabel[secret.secret_id]}
                      </option>
                    ))
                  )}
                </select>
                {secretsError ? <p className="text-sm text-red-600 dark:text-red-400">{secretsError}</p> : null}
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <label
                    htmlFor="provider-new-secret-name"
                    className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                  >
                    Secret Name
                  </label>
                  <Input
                    id="provider-new-secret-name"
                    value={newSecretName}
                    onChange={(event) => setNewSecretName(event.target.value)}
                    placeholder="OpenAI API Key"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label
                    htmlFor="provider-new-secret-value"
                    className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                  >
                    Secret Value
                  </label>
                  <Input
                    id="provider-new-secret-value"
                    type="password"
                    value={newSecretValue}
                    onChange={(event) => setNewSecretValue(event.target.value)}
                    placeholder="sk-..."
                    required
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <label
                    htmlFor="provider-new-secret-description"
                    className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                  >
                    Secret Description
                  </label>
                  <Input
                    id="provider-new-secret-description"
                    value={newSecretDescription}
                    onChange={(event) => setNewSecretDescription(event.target.value)}
                    placeholder="Optional description"
                  />
                </div>
              </div>
            )}
            {secretFlowError ? <p className="text-sm text-red-600 dark:text-red-400">{secretFlowError}</p> : null}
          </div>

          {type === "azure_openai" ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label
                  htmlFor="provider-endpoint"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Endpoint
                </label>
                <Input
                  id="provider-endpoint"
                  value={endpoint}
                  onChange={(event) => setEndpoint(event.target.value)}
                  placeholder="https://your-resource.openai.azure.com"
                  required
                />
              </div>
              <div className="space-y-2">
                <label
                  htmlFor="provider-api-version"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  API Version
                </label>
                <Input
                  id="provider-api-version"
                  value={apiVersion}
                  onChange={(event) => setApiVersion(event.target.value)}
                  placeholder="2024-10-21"
                  required
                />
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label
                  htmlFor="provider-base-url"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Base URL
                </label>
                <Input
                  id="provider-base-url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder={type === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1"}
                />
              </div>
              {type === "openai" ? (
                <div className="space-y-2">
                  <label
                    htmlFor="provider-organization"
                    className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                  >
                    Organization
                  </label>
                  <Input
                    id="provider-organization"
                    value={organization}
                    onChange={(event) => setOrganization(event.target.value)}
                    placeholder="Optional OpenAI organization ID"
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <label
                    htmlFor="provider-anthropic-version"
                    className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                  >
                    Anthropic Version
                  </label>
                  <Input
                    id="provider-anthropic-version"
                    value={anthropicVersion}
                    onChange={(event) => setAnthropicVersion(event.target.value)}
                    placeholder="2023-06-01"
                  />
                </div>
              )}
            </div>
          )}

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Compliance (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea
                value={complianceJson}
                onChange={(event) => {
                  setComplianceJson(event.target.value);
                  setComplianceError(null);
                }}
                className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
              {complianceError ? (
                <p className="text-sm text-red-600 dark:text-red-400">{complianceError}</p>
              ) : null}
            </div>
          </details>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || !isValid()}>
              {isSubmitting ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
