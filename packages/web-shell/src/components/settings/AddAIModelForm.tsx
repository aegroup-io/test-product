import { type FormEvent, useState } from "react";

import { api } from "../../lib/api";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface AddAIModelFormProps {
  providerId: string;
  onSuccess: () => void;
  onCancel: () => void;
}

const EMPTY_JSON = "{}";
const WORKLOAD_OPTIONS = [
  "document_analyze",
  "image_enrich",
  "video_enrich",
  "search_rerank",
  "text_index",
  "ai_artifact_embed",
  "agent_run",
];

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

const parseOptionalInt = (value: string): number | null => {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
};

export default function AddAIModelForm({ providerId, onSuccess, onCancel }: AddAIModelFormProps) {
  const [keyValue, setKeyValue] = useState("");
  const [name, setName] = useState("");
  const [providerModelId, setProviderModelId] = useState("");
  const [canEmbed, setCanEmbed] = useState(false);
  const [canRerank, setCanRerank] = useState(false);
  const [canChat, setCanChat] = useState(false);
  const [canVision, setCanVision] = useState(false);
  const [canAudio, setCanAudio] = useState(false);
  const [defaultWorkload, setDefaultWorkload] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [restrictedContentOnly, setRestrictedContentOnly] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [contextWindowTokens, setContextWindowTokens] = useState("");
  const [maxOutputTokens, setMaxOutputTokens] = useState("");
  const [costJson, setCostJson] = useState(EMPTY_JSON);
  const [defaultParamsJson, setDefaultParamsJson] = useState(EMPTY_JSON);
  const [complianceJson, setComplianceJson] = useState(EMPTY_JSON);
  const [costError, setCostError] = useState<string | null>(null);
  const [defaultParamsError, setDefaultParamsError] = useState<string | null>(null);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetForm = () => {
    setKeyValue("");
    setName("");
    setProviderModelId("");
    setCanEmbed(false);
    setCanRerank(false);
    setCanChat(false);
    setCanVision(false);
    setCanAudio(false);
    setDefaultWorkload("");
    setIsDefault(false);
    setRestrictedContentOnly(false);
    setIsActive(true);
    setContextWindowTokens("");
    setMaxOutputTokens("");
    setCostJson(EMPTY_JSON);
    setDefaultParamsJson(EMPTY_JSON);
    setComplianceJson(EMPTY_JSON);
    setCostError(null);
    setDefaultParamsError(null);
    setComplianceError(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!keyValue.trim() || !name.trim()) {
      return;
    }

    const parsedCost = parseJsonField(costJson);
    const parsedDefaultParams = parseJsonField(defaultParamsJson);
    const parsedCompliance = parseJsonField(complianceJson);

    setCostError(parsedCost.error);
    setDefaultParamsError(parsedDefaultParams.error);
    setComplianceError(parsedCompliance.error);

    if (parsedCost.error || parsedDefaultParams.error || parsedCompliance.error) {
      return;
    }

    setIsSubmitting(true);
    try {
      await api.createModel(providerId, {
        key: keyValue.trim(),
        name: name.trim(),
        provider_model_id: providerModelId.trim() ? providerModelId.trim() : null,
        can_embed: canEmbed,
        can_rerank: canRerank,
        can_chat: canChat,
        can_vision: canVision,
        can_audio: canAudio,
        default_workload: defaultWorkload.trim() ? defaultWorkload.trim() : null,
        is_default: isDefault,
        restricted_content_only: restrictedContentOnly,
        is_active: isActive,
        context_window_tokens: parseOptionalInt(contextWindowTokens),
        max_output_tokens: parseOptionalInt(maxOutputTokens),
        cost: parsedCost.value,
        default_params: parsedDefaultParams.value,
        compliance: parsedCompliance.value,
      });
      resetForm();
      onSuccess();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to create AI model. Please try again.");
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
        <CardTitle>Add AI Model</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label htmlFor="model-key" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Key
              </label>
              <Input
                id="model-key"
                value={keyValue}
                onChange={(event) => setKeyValue(event.target.value)}
                placeholder="claude-3-5"
                required
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="model-name" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Name
              </label>
              <Input
                id="model-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Claude 3.5 Sonnet"
                required
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="provider-model-id"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Provider Model ID
              </label>
              <Input
                id="provider-model-id"
                value={providerModelId}
                onChange={(event) => setProviderModelId(event.target.value)}
                placeholder="anthropic.claude-3-5-sonnet-20241022-v2"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label
                htmlFor="context-window-tokens"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Context Window Tokens
              </label>
              <Input
                id="context-window-tokens"
                value={contextWindowTokens}
                onChange={(event) => setContextWindowTokens(event.target.value)}
                placeholder="200000"
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="max-output-tokens"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Max Output Tokens
              </label>
              <Input
                id="max-output-tokens"
                value={maxOutputTokens}
                onChange={(event) => setMaxOutputTokens(event.target.value)}
                placeholder="4096"
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="default-workload"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Default Workload
              </label>
              <Input
                id="default-workload"
                list="ai-workload-options"
                value={defaultWorkload}
                onChange={(event) => setDefaultWorkload(event.target.value)}
                placeholder="document_analyze"
              />
              <datalist id="ai-workload-options">
                {WORKLOAD_OPTIONS.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-can-embed"
                type="checkbox"
                checked={canEmbed}
                onChange={(event) => setCanEmbed(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Supports Embeddings
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-can-rerank"
                type="checkbox"
                checked={canRerank}
                onChange={(event) => setCanRerank(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Supports Rerank
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-can-chat"
                type="checkbox"
                checked={canChat}
                onChange={(event) => setCanChat(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Supports Chat
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-can-vision"
                type="checkbox"
                checked={canVision}
                onChange={(event) => setCanVision(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Supports Vision
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-can-audio"
                type="checkbox"
                checked={canAudio}
                onChange={(event) => setCanAudio(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Supports Audio
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-is-default"
                type="checkbox"
                checked={isDefault}
                onChange={(event) => setIsDefault(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Default Model
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-restricted-content"
                type="checkbox"
                checked={restrictedContentOnly}
                onChange={(event) => setRestrictedContentOnly(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Restricted Content Only
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input
                id="model-is-active"
                type="checkbox"
                checked={isActive}
                onChange={(event) => setIsActive(event.target.checked)}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
              />
              Active
            </label>
          </div>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Cost (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea
                value={costJson}
                onChange={(event) => {
                  setCostJson(event.target.value);
                  setCostError(null);
                }}
                className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
              {costError ? <p className="text-sm text-red-600 dark:text-red-400">{costError}</p> : null}
            </div>
          </details>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Default Params (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea
                value={defaultParamsJson}
                onChange={(event) => {
                  setDefaultParamsJson(event.target.value);
                  setDefaultParamsError(null);
                }}
                className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
              {defaultParamsError ? (
                <p className="text-sm text-red-600 dark:text-red-400">{defaultParamsError}</p>
              ) : null}
            </div>
          </details>

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
              {complianceError ? (
                <p className="text-sm text-red-600 dark:text-red-400">{complianceError}</p>
              ) : null}
            </div>
          </details>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
