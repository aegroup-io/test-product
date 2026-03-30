import { Fragment, useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader2, Pencil, Plus, Search } from "lucide-react";

import type { AIAgent } from "../api/types";
import AddAIAgentForm from "../components/settings/AddAIAgentForm";
import EditAIAgentForm from "../components/settings/EditAIAgentForm";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
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

export default function Agents() {
  const { hasPermission, isLoading } = useAuth();
  const canManage = hasPermission("ai.manage");
  const [agents, setAgents] = useState<AIAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && canManage) {
      void fetchAgents();
    }
  }, [isLoading, canManage]);

  useEffect(() => {
    if (!isLoading && !canManage) {
      setLoading(false);
    }
  }, [isLoading, canManage]);

  const fetchAgents = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listAgents();
      setAgents(data);
    } catch (err) {
      setAgents([]);
      setError(err instanceof Error ? err.message : "Failed to load AI agents.");
    } finally {
      setLoading(false);
    }
  };

  const filteredAgents = useMemo(() => {
    if (!searchQuery.trim()) {
      return agents;
    }
    const query = searchQuery.toLowerCase();
    return agents.filter(
      (agent) => agent.key.toLowerCase().includes(query) || agent.name.toLowerCase().includes(query),
    );
  }, [agents, searchQuery]);

  if (isLoading || loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-zinc-400" />
          <p className="text-zinc-600 dark:text-zinc-400">Loading agents...</p>
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
              You do not have permission to access Agent settings. This section requires administrator privileges.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Agents</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Manage AI agents and review their activity logs.
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

      <div className="mb-6">
        <div className="mb-6 flex items-center justify-between">
          <div className="relative max-w-sm flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
            <Input
              placeholder="Search agents..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="pl-10"
            />
          </div>
          <Button
            onClick={() => {
              setShowAddForm(true);
              setEditingAgentId(null);
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            Add Agent
          </Button>
        </div>
      </div>

      {showAddForm ? (
        <AddAIAgentForm
          onSuccess={() => {
            setShowAddForm(false);
            void fetchAgents();
          }}
          onCancel={() => setShowAddForm(false)}
        />
      ) : null}

      <div className="space-y-4">
        <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <TableHeader>
              <TableRow className="border-zinc-200 dark:border-zinc-800">
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Key</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Name</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Active</TableHead>
                <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Updated</TableHead>
                <TableHead className="w-20 font-semibold text-zinc-900 dark:text-zinc-100">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredAgents.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                    {searchQuery
                      ? "No agents found matching your search."
                      : "No agents found. Click 'Add Agent' to create one."}
                  </TableCell>
                </TableRow>
              ) : (
                filteredAgents.map((agent, index) => (
                  <Fragment key={agent.agent_id}>
                    <TableRow
                      className={cn(
                        "border-zinc-200 dark:border-zinc-800",
                        index % 2 === 1 && "bg-zinc-50 dark:bg-zinc-900/50",
                      )}
                    >
                      <TableCell className="font-medium text-zinc-900 dark:text-zinc-100">{agent.key}</TableCell>
                      <TableCell className="text-zinc-700 dark:text-zinc-300">{agent.name}</TableCell>
                      <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                        {agent.is_active ? "Active" : "Inactive"}
                      </TableCell>
                      <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                        {formatDateTime(agent.updated_at)}
                      </TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingAgentId((prev) => (prev === agent.agent_id ? null : agent.agent_id));
                            setShowAddForm(false);
                          }}
                          className="h-8 w-8 p-0"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                    {editingAgentId === agent.agent_id ? (
                      <TableRow>
                        <TableCell colSpan={5} className="border-0 p-0">
                          <div className="w-full max-w-full overflow-hidden px-6 py-4">
                            <EditAIAgentForm
                              agent={agent}
                              onSuccess={() => {
                                setEditingAgentId(null);
                                void fetchAgents();
                              }}
                              onCancel={() => setEditingAgentId(null)}
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
