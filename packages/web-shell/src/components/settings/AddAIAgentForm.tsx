import { type FormEvent, useEffect, useState } from "react";

import type { AIModel } from "../../api/types";
import { api } from "../../lib/api";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface AddAIAgentFormProps {
  onSuccess: () => void;
  onCancel: () => void;
}

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

export default function AddAIAgentForm({ onSuccess, onCancel }: AddAIAgentFormProps) {
  const [keyValue, setKeyValue] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [defaultModelId, setDefaultModelId] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [toolPolicyJson, setToolPolicyJson] = useState(EMPTY_JSON);
  const [outputSchemaJson, setOutputSchemaJson] = useState(EMPTY_JSON);
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
        const options = models
          .filter((model) => model.is_active && model.can_chat)
          .sort((a, b) => a.name.localeCompare(b.name));
        setModelOptions(options);
      } catch (error) {
        setModelOptions([]);
        setModelsError(error instanceof Error ? error.message : "Failed to load models.");
      } finally {
        setModelsLoading(false);
      }
    };
    void loadModels();
  }, []);

  const resetForm = () => {
    setKeyValue("");
    setName("");
    setDescription("");
    setSystemPrompt("");
    setDefaultModelId("");
    setIsActive(true);
    setToolPolicyJson(EMPTY_JSON);
    setOutputSchemaJson(EMPTY_JSON);
    setModelsError(null);
    setToolPolicyError(null);
    setOutputSchemaError(null);
  };

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

    setIsSubmitting(true);
    try {
      await api.createAgent({
        key: keyValue.trim(),
        name: name.trim(),
        description: description.trim() ? description.trim() : null,
        system_prompt: systemPrompt.trim(),
        default_model_id: defaultModelId || null,
        is_active: isActive,
        tool_policy: parsedToolPolicy.value,
        output_schema: parsedOutputSchema.value,
      });
      resetForm();
      onSuccess();
    } catch (error) {
      alert(error instanceof Error ? error.message : "Failed to create AI agent. Please try again.");
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
        <CardTitle>Add Agent</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label htmlFor="agent-key" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Key
              </label>
              <Input
                id="agent-key"
                value={keyValue}
                onChange={(event) => setKeyValue(event.target.value)}
                placeholder="case-summary"
                required
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="agent-name" className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
                Name
              </label>
              <Input
                id="agent-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Case Summary"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="agent-description"
              className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Description
            </label>
            <Input
              id="agent-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional summary for teammates"
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="agent-system-prompt"
              className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              System Prompt
            </label>
            <textarea
              id="agent-system-prompt"
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              className="min-h-[180px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              placeholder="Describe how the agent should behave."
              required
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="agent-default-model"
              className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Default Chat Model
            </label>
            <select
              id="agent-default-model"
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
              id="agent-active"
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
              <textarea
                value={toolPolicyJson}
                onChange={(event) => {
                  setToolPolicyJson(event.target.value);
                  setToolPolicyError(null);
                }}
                className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
              {toolPolicyError ? (
                <p className="text-sm text-red-600 dark:text-red-400">{toolPolicyError}</p>
              ) : null}
            </div>
          </details>

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Output Schema (JSON)
            </summary>
            <div className="mt-4 space-y-2">
              <textarea
                value={outputSchemaJson}
                onChange={(event) => {
                  setOutputSchemaJson(event.target.value);
                  setOutputSchemaError(null);
                }}
                className="min-h-[140px] w-full rounded-md border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:focus:ring-zinc-600"
              />
              {outputSchemaError ? (
                <p className="text-sm text-red-600 dark:text-red-400">{outputSchemaError}</p>
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
