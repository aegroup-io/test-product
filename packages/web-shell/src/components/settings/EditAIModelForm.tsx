import { type FormEvent, useEffect, useState } from "react";

import type { AIModel, UpdateAIModelRequest } from "../../api/types";
import { api } from "../../lib/api";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface EditAIModelFormProps {
  model: AIModel;
  onSuccess: () => void;
  onCancel: () => void;
}

const WORKLOAD_OPTIONS = [
  "document_analyze",
  "image_enrich",
  "video_enrich",
  "search_rerank",
  "text_index",
  "ai_artifact_embed",
  "agent_run",
];

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

const parseOptionalInt = (value: string): number | null => {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
};

export default function EditAIModelForm({ model, onSuccess, onCancel }: EditAIModelFormProps) {
  const [keyValue, setKeyValue] = useState(model.key);
  const [name, setName] = useState(model.name);
  const [providerModelId, setProviderModelId] = useState(model.provider_model_id ?? "");
  const [canEmbed, setCanEmbed] = useState(model.can_embed);
  const [canRerank, setCanRerank] = useState(model.can_rerank);
  const [canChat, setCanChat] = useState(model.can_chat);
  const [canVision, setCanVision] = useState(model.can_vision);
  const [canAudio, setCanAudio] = useState(model.can_audio);
  const [defaultWorkload, setDefaultWorkload] = useState(model.default_workload ?? "");
  const [isDefault, setIsDefault] = useState(model.is_default);
  const [restrictedContentOnly, setRestrictedContentOnly] = useState(model.restricted_content_only);
  const [isActive, setIsActive] = useState(model.is_active);
  const [contextWindowTokens, setContextWindowTokens] = useState(model.context_window_tokens?.toString() ?? "");
  const [maxOutputTokens, setMaxOutputTokens] = useState(model.max_output_tokens?.toString() ?? "");
  const [costJson, setCostJson] = useState(formatJson(model.cost));
  const [defaultParamsJson, setDefaultParamsJson] = useState(formatJson(model.default_params));
  const [complianceJson, setComplianceJson] = useState(formatJson(model.compliance));
  const [costError, setCostError] = useState<string | null>(null);
  const [defaultParamsError, setDefaultParamsError] = useState<string | null>(null);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setKeyValue(model.key);
    setName(model.name);
    setProviderModelId(model.provider_model_id ?? "");
    setCanEmbed(model.can_embed);
    setCanRerank(model.can_rerank);
    setCanChat(model.can_chat);
    setCanVision(model.can_vision);
    setCanAudio(model.can_audio);
    setDefaultWorkload(model.default_workload ?? "");
    setIsDefault(model.is_default);
    setRestrictedContentOnly(model.restricted_content_only);
    setIsActive(model.is_active);
    setContextWindowTokens(model.context_window_tokens?.toString() ?? "");
    setMaxOutputTokens(model.max_output_tokens?.toString() ?? "");
    setCostJson(formatJson(model.cost));
    setDefaultParamsJson(formatJson(model.default_params));
    setComplianceJson(formatJson(model.compliance));
    setCostError(null);
    setDefaultParamsError(null);
    setComplianceError(null);
  }, [model]);

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

    const updates: UpdateAIModelRequest = {};
    if (keyValue.trim() !== model.key) {
      updates.key = keyValue.trim();
    }
    if (name.trim() !== model.name) {
      updates.name = name.trim();
    }
    const trimmedProviderModelId = providerModelId.trim();
    if ((model.provider_model_id ?? "") !== trimmedProviderModelId) {
      updates.provider_model_id = trimmedProviderModelId ? trimmedProviderModelId : null;
    }
    if (canEmbed !== model.can_embed) {
      updates.can_embed = canEmbed;
    }
    if (canRerank !== model.can_rerank) {
      updates.can_rerank = canRerank;
    }
    if (canChat !== model.can_chat) {
      updates.can_chat = canChat;
    }
    if (canVision !== model.can_vision) {
      updates.can_vision = canVision;
    }
    if (canAudio !== model.can_audio) {
      updates.can_audio = canAudio;
    }
    const trimmedDefaultWorkload = defaultWorkload.trim();
    if ((model.default_workload ?? "") !== trimmedDefaultWorkload) {
      updates.default_workload = trimmedDefaultWorkload ? trimmedDefaultWorkload : null;
    }
    if (isDefault !== model.is_default) {
      updates.is_default = isDefault;
    }
    if (restrictedContentOnly !== model.restricted_content_only) {
      updates.restricted_content_only = restrictedContentOnly;
    }
    if (isActive !== model.is_active) {
      updates.is_active = isActive;
    }
    const parsedContextTokens = parseOptionalInt(contextWindowTokens);
    if ((model.context_window_tokens ?? null) !== parsedContextTokens) {
      updates.context_window_tokens = parsedContextTokens;
    }
    const parsedMaxOutputTokens = parseOptionalInt(maxOutputTokens);
    if ((model.max_output_tokens ?? null) !== parsedMaxOutputTokens) {
      updates.max_output_tokens = parsedMaxOutputTokens;
    }
    if (JSON.stringify(parsedCost.value) !== JSON.stringify(model.cost ?? {})) {
      updates.cost = parsedCost.value;
    }
    if (JSON.stringify(parsedDefaultParams.value) !== JSON.stringify(model.default_params ?? {})) {
      updates.default_params = parsedDefaultParams.value;
    }
    if (JSON.stringify(parsedCompliance.value) !== JSON.stringify(model.compliance ?? {})) {
      updates.compliance = parsedCompliance.value;
    }

    if (Object.keys(updates).length === 0) {
      onSuccess();
      return;
    }

    setIsSubmitting(true);
    try {
      await api.updateModel(model.model_id, updates);
      onSuccess();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to update AI model. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setKeyValue(model.key);
    setName(model.name);
    setProviderModelId(model.provider_model_id ?? "");
    setCanEmbed(model.can_embed);
    setCanRerank(model.can_rerank);
    setCanChat(model.can_chat);
    setCanVision(model.can_vision);
    setCanAudio(model.can_audio);
    setDefaultWorkload(model.default_workload ?? "");
    setIsDefault(model.is_default);
    setRestrictedContentOnly(model.restricted_content_only);
    setIsActive(model.is_active);
    setContextWindowTokens(model.context_window_tokens?.toString() ?? "");
    setMaxOutputTokens(model.max_output_tokens?.toString() ?? "");
    setCostJson(formatJson(model.cost));
    setDefaultParamsJson(formatJson(model.default_params));
    setComplianceJson(formatJson(model.compliance));
    setCostError(null);
    setDefaultParamsError(null);
    setComplianceError(null);
    onCancel();
  };

  return (
    <Card className="mb-6 w-full max-w-full">
      <CardHeader>
        <CardTitle>Edit Model</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label htmlFor="edit-model-key" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Key
              </label>
              <Input id="edit-model-key" value={keyValue} onChange={(event) => setKeyValue(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <label htmlFor="edit-model-name" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Name
              </label>
              <Input id="edit-model-name" value={name} onChange={(event) => setName(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="edit-provider-model-id"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Provider Model ID
              </label>
              <Input id="edit-provider-model-id" value={providerModelId} onChange={(event) => setProviderModelId(event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label
                htmlFor="edit-context-window-tokens"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Context Window Tokens
              </label>
              <Input
                id="edit-context-window-tokens"
                value={contextWindowTokens}
                onChange={(event) => setContextWindowTokens(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="edit-max-output-tokens"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Max Output Tokens
              </label>
              <Input
                id="edit-max-output-tokens"
                value={maxOutputTokens}
                onChange={(event) => setMaxOutputTokens(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="edit-default-workload"
                className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
              >
                Default Workload
              </label>
              <Input
                id="edit-default-workload"
                list="edit-ai-workload-options"
                value={defaultWorkload}
                onChange={(event) => setDefaultWorkload(event.target.value)}
              />
              <datalist id="edit-ai-workload-options">
                {WORKLOAD_OPTIONS.map((option) => (
                  <option key={option} value={option} />
                ))}
              </datalist>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={canEmbed} onChange={(event) => setCanEmbed(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Supports Embeddings
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={canRerank} onChange={(event) => setCanRerank(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Supports Rerank
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={canChat} onChange={(event) => setCanChat(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Supports Chat
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={canVision} onChange={(event) => setCanVision(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Supports Vision
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={canAudio} onChange={(event) => setCanAudio(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Supports Audio
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Default Model
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={restrictedContentOnly} onChange={(event) => setRestrictedContentOnly(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Restricted Content Only
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
              <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100" />
              Active
            </label>
          </div>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Cost (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea value={costJson} onChange={(event) => { setCostJson(event.target.value); setCostError(null); }} className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600" />
              {costError ? <p className="text-sm text-red-600 dark:text-red-400">{costError}</p> : null}
            </div>
          </details>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Default Params (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea value={defaultParamsJson} onChange={(event) => { setDefaultParamsJson(event.target.value); setDefaultParamsError(null); }} className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600" />
              {defaultParamsError ? <p className="text-sm text-red-600 dark:text-red-400">{defaultParamsError}</p> : null}
            </div>
          </details>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Compliance (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea value={complianceJson} onChange={(event) => { setComplianceJson(event.target.value); setComplianceError(null); }} className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600" />
              {complianceError ? <p className="text-sm text-red-600 dark:text-red-400">{complianceError}</p> : null}
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
