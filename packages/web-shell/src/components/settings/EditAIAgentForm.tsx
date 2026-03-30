import { type FormEvent, useEffect, useState } from "react";

import type { AIAgent, AIModel, UpdateAIAgentRequest } from "../../api/types";
import { api } from "../../lib/api";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface EditAIAgentFormProps {
  agent: AIAgent;
  onSuccess: () => void;
  onCancel: () => void;
}

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

export default function EditAIAgentForm({ agent, onSuccess, onCancel }: EditAIAgentFormProps) {
  const [keyValue, setKeyValue] = useState(agent.key);
  const [name, setName] = useState(agent.name);
  const [description, setDescription] = useState(agent.description ?? "");
  const [systemPrompt, setSystemPrompt] = useState(agent.system_prompt);
  const [defaultModelId, setDefaultModelId] = useState(agent.default_model_id ?? "");
  const [isActive, setIsActive] = useState(agent.is_active);
  const [toolPolicyJson, setToolPolicyJson] = useState(formatJson(agent.tool_policy));
  const [outputSchemaJson, setOutputSchemaJson] = useState(formatJson(agent.output_schema));
  const [modelOptions, setModelOptions] = useState<AIModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [toolPolicyError, setToolPolicyError] = useState<string | null>(null);
  const [outputSchemaError, setOutputSchemaError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const loadModels = async () => {
      setModelsLoading(true);
      setModelsError(null);
      try {
        const models = await api.listModels();
        const filtered = models.filter((model) => model.is_active && model.can_chat);
        const selected = agent.default_model_id
          ? models.find((model) => model.model_id === agent.default_model_id)
          : undefined;
        const optionsById = new Map<string, AIModel>();
        for (const model of filtered) {
          optionsById.set(model.model_id, model);
        }
        if (selected) {
          optionsById.set(selected.model_id, selected);
        }
        const options = Array.from(optionsById.values()).sort((a, b) => a.name.localeCompare(b.name));
        setModelOptions(options);
      } catch (error) {
        setModelOptions([]);
        setModelsError(error instanceof Error ? error.message : "Failed to load models.");
      } finally {
        setModelsLoading(false);
      }
    };
    void loadModels();
  }, [agent.default_model_id]);

  useEffect(() => {
    setKeyValue(agent.key);
    setName(agent.name);
    setDescription(agent.description ?? "");
    setSystemPrompt(agent.system_prompt);
    setDefaultModelId(agent.default_model_id ?? "");
    setIsActive(agent.is_active);
    setToolPolicyJson(formatJson(agent.tool_policy));
    setOutputSchemaJson(formatJson(agent.output_schema));
    setToolPolicyError(null);
    setOutputSchemaError(null);
  }, [agent]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!keyValue.trim() || !name.trim() || !systemPrompt.trim()) {
      return;
    }

    const parsedToolPolicy = parseJsonField(toolPolicyJson);
    const parsedOutputSchema = parseJsonField(outputSchemaJson);

    setToolPolicyError(parsedToolPolicy.error);
    setOutputSchemaError(parsedOutputSchema.error);

    if (parsedToolPolicy.error || parsedOutputSchema.error) {
      return;
    }

    const updates: UpdateAIAgentRequest = {};
    if (keyValue.trim() !== agent.key) {
      updates.key = keyValue.trim();
    }
    if (name.trim() !== agent.name) {
      updates.name = name.trim();
    }
    const trimmedDescription = description.trim();
    if ((agent.description ?? "") !== trimmedDescription) {
      updates.description = trimmedDescription ? trimmedDescription : null;
    }
    if (systemPrompt.trim() !== agent.system_prompt) {
      updates.system_prompt = systemPrompt.trim();
    }
    const currentModelId = agent.default_model_id ?? "";
    if (defaultModelId !== currentModelId) {
      updates.default_model_id = defaultModelId || null;
    }
    if (isActive !== agent.is_active) {
      updates.is_active = isActive;
    }
    if (JSON.stringify(parsedToolPolicy.value) !== JSON.stringify(agent.tool_policy ?? {})) {
      updates.tool_policy = parsedToolPolicy.value;
    }
    if (JSON.stringify(parsedOutputSchema.value) !== JSON.stringify(agent.output_schema ?? {})) {
      updates.output_schema = parsedOutputSchema.value;
    }

    if (Object.keys(updates).length === 0) {
      onSuccess();
      return;
    }

    setIsSubmitting(true);
    try {
      await api.updateAgent(agent.agent_id, updates);
      onSuccess();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to update AI agent. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setKeyValue(agent.key);
    setName(agent.name);
    setDescription(agent.description ?? "");
    setSystemPrompt(agent.system_prompt);
    setDefaultModelId(agent.default_model_id ?? "");
    setIsActive(agent.is_active);
    setToolPolicyJson(formatJson(agent.tool_policy));
    setOutputSchemaJson(formatJson(agent.output_schema));
    setToolPolicyError(null);
    setOutputSchemaError(null);
    onCancel();
  };

  return (
    <Card className="mb-6 w-full max-w-full">
      <CardHeader>
        <CardTitle>Edit Agent</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label htmlFor="edit-agent-key" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Key
              </label>
              <Input id="edit-agent-key" value={keyValue} onChange={(event) => setKeyValue(event.target.value)} required />
            </div>
            <div className="space-y-2">
              <label htmlFor="edit-agent-name" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Name
              </label>
              <Input id="edit-agent-name" value={name} onChange={(event) => setName(event.target.value)} required />
            </div>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="edit-agent-description"
              className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Description
            </label>
            <Input id="edit-agent-description" value={description} onChange={(event) => setDescription(event.target.value)} />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="edit-agent-system-prompt"
              className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              System Prompt
            </label>
            <textarea
              id="edit-agent-system-prompt"
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              className="min-h-[180px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              required
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="edit-agent-default-model"
              className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Default Chat Model
            </label>
            <select
              id="edit-agent-default-model"
              value={defaultModelId}
              onChange={(event) => setDefaultModelId(event.target.value)}
              disabled={modelsLoading || modelOptions.length === 0}
              className="h-9 w-full rounded-md border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 disabled:cursor-not-allowed disabled:opacity-70 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
            >
              <option value="">
                {modelsLoading
                  ? "Loading chat models..."
                  : modelOptions.length === 0
                    ? "No active chat models available"
                    : "No default model"}
              </option>
              {modelOptions.map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {`${model.name} (${model.key})`}
                </option>
              ))}
            </select>
            {modelsError ? <p className="text-sm text-red-600 dark:text-red-400">{modelsError}</p> : null}
          </div>

          <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <input
              id="edit-agent-active"
              type="checkbox"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
            />
            Active
          </label>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Tool Policy (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea value={toolPolicyJson} onChange={(event) => { setToolPolicyJson(event.target.value); setToolPolicyError(null); }} className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600" />
              {toolPolicyError ? <p className="text-sm text-red-600 dark:text-red-400">{toolPolicyError}</p> : null}
            </div>
          </details>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Output Schema (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea value={outputSchemaJson} onChange={(event) => { setOutputSchemaJson(event.target.value); setOutputSchemaError(null); }} className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600" />
              {outputSchemaError ? <p className="text-sm text-red-600 dark:text-red-400">{outputSchemaError}</p> : null}
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
