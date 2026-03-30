import { Fragment, useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, Pencil, Plus } from "lucide-react";

import type { AIModel, AIProvider } from "../api/types";
import AddAIModelForm from "../components/settings/AddAIModelForm";
import AddAIProviderForm from "../components/settings/AddAIProviderForm";
import EditAIModelForm from "../components/settings/EditAIModelForm";
import EditAIProviderForm from "../components/settings/EditAIProviderForm";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { formatDateTime } from "../lib/date-utils";
import { cn } from "../lib/utils";

const formatCapabilities = (model: AIModel): string[] => {
  const caps: string[] = [];
  if (model.can_embed) caps.push("Embed");
  if (model.can_rerank) caps.push("Rerank");
  if (model.can_chat) caps.push("Chat");
  if (model.can_vision) caps.push("Vision");
  if (model.can_audio) caps.push("Audio");
  return caps;
};

export default function Models() {
  const { hasPermission, isLoading } = useAuth();
  const canManage = hasPermission("ai.manage");
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [expandedProviderId, setExpandedProviderId] = useState<string | null>(null);
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, AIModel[]>>({});
  const [modelsLoading, setModelsLoading] = useState<Record<string, boolean>>({});
  const [modelsError, setModelsError] = useState<Record<string, string | null>>({});
  const [showAddModelForProvider, setShowAddModelForProvider] = useState<string | null>(null);
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [modelTestState, setModelTestState] = useState<
    Record<string, { loading: boolean; ok?: boolean; message?: string }>
  >({});

  const fetchProviders = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      if (!canManage) {
        setError("You do not have permission to access AI registry settings.");
        return;
      }

      const providerData = await api.listProviders();
      setProviders(providerData);
    } catch (err) {
      setProviders([]);
      setError(err instanceof Error ? err.message : "Failed to load AI providers.");
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  const fetchModels = useCallback(async (providerId: string) => {
    try {
      setModelsLoading((prev) => ({ ...prev, [providerId]: true }));
      setModelsError((prev) => ({ ...prev, [providerId]: null }));
      const models = await api.listModels(providerId);
      setModelsByProvider((prev) => ({ ...prev, [providerId]: models }));
    } catch (err) {
      setModelsByProvider((prev) => ({ ...prev, [providerId]: [] }));
      setModelsError((prev) => ({
        ...prev,
        [providerId]: err instanceof Error ? err.message : "Failed to load AI models.",
      }));
    } finally {
      setModelsLoading((prev) => ({ ...prev, [providerId]: false }));
    }
  }, []);

  const handleTestModel = useCallback(async (modelId: string) => {
    setModelTestState((prev) => ({
      ...prev,
      [modelId]: { loading: true, ok: prev[modelId]?.ok, message: prev[modelId]?.message },
    }));
    try {
      const response = await api.testModel(modelId);
      setModelTestState((prev) => ({
        ...prev,
        [modelId]: { loading: false, ok: response.ok, message: response.message },
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Model test failed.";
      setModelTestState((prev) => ({
        ...prev,
        [modelId]: { loading: false, ok: false, message },
      }));
    }
  }, []);

  useEffect(() => {
    if (!isLoading && canManage) {
      void fetchProviders();
    }
  }, [isLoading, canManage, fetchProviders]);

  useEffect(() => {
    if (!isLoading && !canManage) {
      setLoading(false);
    }
  }, [isLoading, canManage]);

  const handleToggleProvider = (providerId: string) => {
    setEditingModelId(null);
    setShowAddModelForProvider(null);
    if (expandedProviderId === providerId) {
      setExpandedProviderId(null);
      return;
    }
    setExpandedProviderId(providerId);
    void fetchModels(providerId);
  };

  const handleAddProviderSuccess = () => {
    setShowAddProvider(false);
    void fetchProviders();
  };

  const handleEditProviderSuccess = () => {
    void fetchProviders();
  };

  const handleAddModelSuccess = (providerId: string) => {
    setShowAddModelForProvider(null);
    void fetchModels(providerId);
  };

  const handleEditModelSuccess = (providerId: string) => {
    setEditingModelId(null);
    void fetchModels(providerId);
  };

  if (isLoading || loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-zinc-400" />
          <p className="text-zinc-600 dark:text-zinc-400">Loading AI model registry...</p>
        </div>
      </div>
    );
  }

  if (!canManage) {
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
              You do not have permission to access AI registry settings. This section requires administrator privileges.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">AI Models</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Manage AI providers and the models available for each provider.
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

      <div className="mb-6 flex items-center justify-between">
        <div className="text-sm text-zinc-500 dark:text-zinc-400">
          {providers.length} provider{providers.length === 1 ? "" : "s"}
        </div>
        <Button
          onClick={() => {
            setShowAddProvider(true);
            setExpandedProviderId(null);
          }}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Provider
        </Button>
      </div>

      {showAddProvider ? (
        <AddAIProviderForm
          onSuccess={handleAddProviderSuccess}
          onCancel={() => setShowAddProvider(false)}
        />
      ) : null}

      <div className="space-y-4">
        <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-200 dark:border-zinc-800">
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Key</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Name</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Type</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Status</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Updated</TableHead>
                <TableHead className="w-20 font-semibold text-zinc-900 dark:text-zinc-100">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {providers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                    No AI providers found. Click "Add Provider" to create one.
                  </TableCell>
                </TableRow>
              ) : (
                providers.map((provider, index) => (
                  <Fragment key={provider.provider_id}>
                    <TableRow
                      className={cn(
                        "border-zinc-200 dark:border-zinc-800",
                        index % 2 === 1 && "bg-zinc-50 dark:bg-zinc-900/50",
                      )}
                    >
                      <TableCell className="font-medium text-zinc-900 dark:text-zinc-100">{provider.key}</TableCell>
                      <TableCell className="text-zinc-700 dark:text-zinc-300">{provider.name}</TableCell>
                      <TableCell className="text-zinc-600 capitalize dark:text-zinc-400">{provider.type.replaceAll("_", " ")}</TableCell>
                      <TableCell>
                        <Badge variant={provider.is_active ? "secondary" : "outline"}>
                          {provider.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                        {formatDateTime(provider.updated_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => handleToggleProvider(provider.provider_id)}
                            className="h-8 px-2"
                          >
                            {expandedProviderId === provider.provider_id ? "Hide" : "Models"}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                    {expandedProviderId === provider.provider_id ? (
                      <TableRow key={`${provider.provider_id}-details`}>
                        <TableCell colSpan={6} className="p-0 border-0">
                          <div className="space-y-4 border-t border-zinc-200 px-6 py-4 dark:border-zinc-800">
                            <div className="flex items-center justify-between gap-4">
                              <div className="flex items-center gap-2">
                                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                                  {provider.name}
                                </h3>
                                <Badge variant="outline">{provider.type}</Badge>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    setShowAddModelForProvider((prev) =>
                                      prev === provider.provider_id ? null : provider.provider_id,
                                    );
                                    setEditingModelId(null);
                                  }}
                                >
                                  <Plus className="mr-2 h-4 w-4" />
                                  Add Model
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setShowAddModelForProvider(null);
                                    setEditingModelId((prev) =>
                                      prev === `provider:${provider.provider_id}` ? null : `provider:${provider.provider_id}`,
                                    );
                                  }}
                                  className="h-8 w-8 p-0"
                                >
                                  <Pencil className="h-4 w-4" />
                                </Button>
                              </div>
                            </div>

                            {editingModelId === `provider:${provider.provider_id}` ? (
                              <EditAIProviderForm
                                provider={provider}
                                onSuccess={handleEditProviderSuccess}
                                onCancel={() => setEditingModelId(null)}
                              />
                            ) : null}

                            {showAddModelForProvider === provider.provider_id ? (
                              <AddAIModelForm
                                providerId={provider.provider_id}
                                onSuccess={() => handleAddModelSuccess(provider.provider_id)}
                                onCancel={() => setShowAddModelForProvider(null)}
                              />
                            ) : null}

                            {modelsError[provider.provider_id] ? (
                              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200">
                                {modelsError[provider.provider_id]}
                              </div>
                            ) : null}

                            <div className="rounded-lg border border-zinc-200 dark:border-zinc-800">
                              <Table>
                                <TableHeader>
                                  <TableRow className="border-zinc-200 dark:border-zinc-800">
                                    <TableHead>Key</TableHead>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Capabilities</TableHead>
                                    <TableHead>Workload</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Updated</TableHead>
                                    <TableHead className="w-32">Actions</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {modelsLoading[provider.provider_id] ? (
                                    <TableRow>
                                      <TableCell colSpan={7} className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                                        Loading models...
                                      </TableCell>
                                    </TableRow>
                                  ) : (modelsByProvider[provider.provider_id] ?? []).length === 0 ? (
                                    <TableRow>
                                      <TableCell colSpan={7} className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                                        No models for this provider yet.
                                      </TableCell>
                                    </TableRow>
                                  ) : (
                                    (modelsByProvider[provider.provider_id] ?? []).map((model, modelIndex) => {
                                      const modelState = modelTestState[model.model_id];
                                      const capabilities = formatCapabilities(model);
                                      return (
                                        <Fragment key={model.model_id}>
                                          <TableRow
                                            className={cn(
                                              "border-zinc-200 dark:border-zinc-800",
                                              modelIndex % 2 === 1 && "bg-zinc-50 dark:bg-zinc-900/50",
                                            )}
                                          >
                                            <TableCell className="font-medium text-zinc-900 dark:text-zinc-100">{model.key}</TableCell>
                                            <TableCell className="text-zinc-700 dark:text-zinc-300">{model.name}</TableCell>
                                            <TableCell>
                                              <div className="flex flex-wrap gap-1">
                                                {capabilities.length === 0 ? (
                                                  <span className="text-sm text-zinc-500 dark:text-zinc-400">None</span>
                                                ) : (
                                                  capabilities.map((capability) => (
                                                    <Badge key={capability} variant="outline">
                                                      {capability}
                                                    </Badge>
                                                  ))
                                                )}
                                              </div>
                                            </TableCell>
                                            <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                                              {model.default_workload || "None"}
                                            </TableCell>
                                            <TableCell>
                                              <Badge variant={model.is_active ? "secondary" : "outline"}>
                                                {model.is_active ? "Active" : "Inactive"}
                                              </Badge>
                                            </TableCell>
                                            <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                                              {formatDateTime(model.updated_at)}
                                            </TableCell>
                                            <TableCell>
                                              <div className="flex items-center gap-1">
                                                <Button
                                                  type="button"
                                                  variant="outline"
                                                  size="sm"
                                                  onClick={() => void handleTestModel(model.model_id)}
                                                  disabled={modelState?.loading}
                                                >
                                                  {modelState?.loading ? (
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                  ) : (
                                                    "Test"
                                                  )}
                                                </Button>
                                                <Button
                                                  type="button"
                                                  variant="ghost"
                                                  size="sm"
                                                  onClick={() => setEditingModelId((prev) => (prev === model.model_id ? null : model.model_id))}
                                                  className="h-8 w-8 p-0"
                                                >
                                                  <Pencil className="h-4 w-4" />
                                                </Button>
                                              </div>
                                            </TableCell>
                                          </TableRow>
                                          {modelState?.message ? (
                                            <TableRow key={`${model.model_id}-test`}>
                                              <TableCell colSpan={7} className="border-0 bg-zinc-50 px-6 py-3 text-sm dark:bg-zinc-900/40">
                                                <span className={modelState.ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                                                  {modelState.message}
                                                </span>
                                              </TableCell>
                                            </TableRow>
                                          ) : null}
                                          {editingModelId === model.model_id ? (
                                            <TableRow key={`${model.model_id}-edit`}>
                                              <TableCell colSpan={7} className="p-0 border-0">
                                                <div className="w-full max-w-full overflow-hidden px-6 py-4">
                                                  <EditAIModelForm
                                                    model={model}
                                                    onSuccess={() => handleEditModelSuccess(provider.provider_id)}
                                                    onCancel={() => setEditingModelId(null)}
                                                  />
                                                </div>
                                              </TableCell>
                                            </TableRow>
                                          ) : null}
                                        </Fragment>
                                      );
                                    })
                                  )}
                                </TableBody>
                              </Table>
                            </div>
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
