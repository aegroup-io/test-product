import { type FormEvent, useEffect, useMemo, useState } from "react";

import type { AIProvider, Secret, UpdateAIProviderRequest } from "../../api/types";
import { api } from "../../lib/api";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface EditAIProviderFormProps {
  provider: AIProvider;
  onSuccess: () => void;
  onCancel: () => void;
}

type ProviderType = "openai" | "azure_openai" | "anthropic";

const PROVIDER_OPTIONS: Array<{ value: ProviderType; label: string }> = [
  { value: "openai", label: "OpenAI" },
  { value: "azure_openai", label: "Azure OpenAI" },
  { value: "anthropic", label: "Anthropic" },
];

const DEFAULT_PROVIDER_TYPE: ProviderType = "openai";

const formatJson = (value: Record<string, unknown> | null | undefined): string => {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
};

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

const parseProviderType = (value: string | null | undefined): ProviderType => {
  if (value === "openai" || value === "azure_openai" || value === "anthropic") {
    return value;
  }
  return DEFAULT_PROVIDER_TYPE;
};

const readConfigValue = (config: Record<string, unknown> | null | undefined, key: string): string => {
  const value = config?.[key];
  return typeof value === "string" ? value : "";
};

export default function EditAIProviderForm({ provider, onSuccess, onCancel }: EditAIProviderFormProps) {
  const [keyValue, setKeyValue] = useState(provider.key);
  const [name, setName] = useState(provider.name);
  const [type, setType] = useState<ProviderType>(parseProviderType(provider.type));
  const [isActive, setIsActive] = useState(provider.is_active);
  const [apiKeySecretId, setApiKeySecretId] = useState(readConfigValue(provider.config, "api_key_secret_id"));
  const [baseUrl, setBaseUrl] = useState(readConfigValue(provider.config, "base_url"));
  const [organization, setOrganization] = useState(readConfigValue(provider.config, "organization"));
  const [endpoint, setEndpoint] = useState(readConfigValue(provider.config, "endpoint"));
  const [apiVersion, setApiVersion] = useState(readConfigValue(provider.config, "api_version"));
  const [anthropicVersion, setAnthropicVersion] = useState(readConfigValue(provider.config, "anthropic_version"));
  const [complianceJson, setComplianceJson] = useState(formatJson(provider.compliance));
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [secretsLoading, setSecretsLoading] = useState(false);
  const [secretsError, setSecretsError] = useState<string | null>(null);
  const [secretOptions, setSecretOptions] = useState<Secret[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const loadSecrets = async () => {
      setSecretsLoading(true);
      setSecretsError(null);
      try {
        const secrets = await api.listSecrets();
        if (cancelled) {
          return;
        }
        setSecretOptions(secrets.filter((secret) => secret.kind === "ai_api_key"));
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
  }, []);

  useEffect(() => {
    const normalizedType = parseProviderType(provider.type);
    setKeyValue(provider.key);
    setName(provider.name);
    setType(normalizedType);
    setIsActive(provider.is_active);
    setApiKeySecretId(readConfigValue(provider.config, "api_key_secret_id"));
    setBaseUrl(readConfigValue(provider.config, "base_url"));
    setOrganization(readConfigValue(provider.config, "organization"));
    setEndpoint(readConfigValue(provider.config, "endpoint"));
    setApiVersion(readConfigValue(provider.config, "api_version"));
    setAnthropicVersion(readConfigValue(provider.config, "anthropic_version"));
    setComplianceJson(formatJson(provider.compliance));
    setComplianceError(null);
  }, [provider]);

  useEffect(() => {
    if (!apiKeySecretId && secretOptions.length > 0) {
      setApiKeySecretId(secretOptions[0].secret_id);
    }
  }, [apiKeySecretId, secretOptions]);

  const secretLabel = useMemo(
    () =>
      secretOptions.reduce<Record<string, string>>((acc, secret) => {
        acc[secret.secret_id] = `${secret.name} (${secret.key})`;
        return acc;
      }, {}),
    [secretOptions],
  );

  const buildConfig = (): Record<string, unknown> => {
    if (type === "openai") {
      const config: Record<string, unknown> = { api_key_secret_id: apiKeySecretId.trim() };
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
        api_key_secret_id: apiKeySecretId.trim(),
        endpoint: endpoint.trim(),
        api_version: apiVersion.trim(),
      };
    }
    const config: Record<string, unknown> = { api_key_secret_id: apiKeySecretId.trim() };
    if (baseUrl.trim()) {
      config.base_url = baseUrl.trim();
    }
    if (anthropicVersion.trim()) {
      config.anthropic_version = anthropicVersion.trim();
    }
    return config;
  };

  const isValid = (): boolean => {
    if (!keyValue.trim() || !name.trim() || !apiKeySecretId.trim()) {
      return false;
    }
    if (type === "azure_openai") {
      return Boolean(endpoint.trim() && apiVersion.trim());
    }
    return true;
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

    const updates: UpdateAIProviderRequest = {};
    const nextConfig = buildConfig();
    if (keyValue.trim() !== provider.key) {
      updates.key = keyValue.trim();
    }
    if (name.trim() !== provider.name) {
      updates.name = name.trim();
    }
    if (type !== provider.type) {
      updates.type = type;
    }
    if (isActive !== provider.is_active) {
      updates.is_active = isActive;
    }
    if (JSON.stringify(nextConfig) !== JSON.stringify(provider.config ?? {})) {
      updates.config = nextConfig;
    }
    if (JSON.stringify(parsedCompliance.value) !== JSON.stringify(provider.compliance ?? {})) {
      updates.compliance = parsedCompliance.value;
    }

    if (Object.keys(updates).length === 0) {
      onSuccess();
      return;
    }

    setIsSubmitting(true);
    try {
      await api.updateProvider(provider.provider_id, updates);
      onSuccess();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to update AI provider. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setKeyValue(provider.key);
    setName(provider.name);
    setType(parseProviderType(provider.type));
    setIsActive(provider.is_active);
    setApiKeySecretId(readConfigValue(provider.config, "api_key_secret_id"));
    setBaseUrl(readConfigValue(provider.config, "base_url"));
    setOrganization(readConfigValue(provider.config, "organization"));
    setEndpoint(readConfigValue(provider.config, "endpoint"));
    setApiVersion(readConfigValue(provider.config, "api_version"));
    setAnthropicVersion(readConfigValue(provider.config, "anthropic_version"));
    setComplianceJson(formatJson(provider.compliance));
    setComplianceError(null);
    onCancel();
  };

  return (
    <Card className="mb-6 w-full max-w-full">
      <CardHeader>
        <CardTitle>Edit Provider</CardTitle>
      </CardHeader>
      <CardContent className="w-full max-w-full">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label htmlFor="edit-provider-key" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Key
              </label>
              <Input id="edit-provider-key" value={keyValue} onChange={(event) => setKeyValue(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <label htmlFor="edit-provider-name" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Name
              </label>
              <Input id="edit-provider-name" value={name} onChange={(event) => setName(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <label htmlFor="edit-provider-type" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Type
              </label>
              <select
                id="edit-provider-type"
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

          <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <input
              id="edit-provider-active"
              type="checkbox"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
            />
            Active
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label
                htmlFor="edit-provider-secret-id"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                API Key Secret
              </label>
              <select
                id="edit-provider-secret-id"
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
            {type === "azure_openai" ? (
              <div className="space-y-2">
                <label
                  htmlFor="edit-provider-endpoint"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Endpoint
                </label>
                <Input
                  id="edit-provider-endpoint"
                  value={endpoint}
                  onChange={(event) => setEndpoint(event.target.value)}
                  placeholder="https://your-resource.openai.azure.com"
                  required
                />
              </div>
            ) : (
              <div className="space-y-2">
                <label
                  htmlFor="edit-provider-base-url"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Base URL
                </label>
                <Input
                  id="edit-provider-base-url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder={type === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1"}
                />
              </div>
            )}
          </div>

          {type === "openai" ? (
            <div className="space-y-2">
              <label
                htmlFor="edit-provider-organization"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Organization
              </label>
              <Input
                id="edit-provider-organization"
                value={organization}
                onChange={(event) => setOrganization(event.target.value)}
                placeholder="Optional OpenAI organization ID"
              />
            </div>
          ) : null}

          {type === "azure_openai" ? (
            <div className="space-y-2">
              <label
                htmlFor="edit-provider-api-version"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                API Version
              </label>
              <Input
                id="edit-provider-api-version"
                value={apiVersion}
                onChange={(event) => setApiVersion(event.target.value)}
                placeholder="2024-10-21"
                required
              />
            </div>
          ) : null}

          {type === "anthropic" ? (
            <div className="space-y-2">
              <label
                htmlFor="edit-provider-anthropic-version"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Anthropic Version
              </label>
              <Input
                id="edit-provider-anthropic-version"
                value={anthropicVersion}
                onChange={(event) => setAnthropicVersion(event.target.value)}
                placeholder="2023-06-01"
              />
            </div>
          ) : null}

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
                className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
              {complianceError ? <p className="text-sm text-red-600 dark:text-red-400">{complianceError}</p> : null}
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
