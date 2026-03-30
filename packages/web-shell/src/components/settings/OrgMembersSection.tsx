import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Search, Star, Trash2, X } from "lucide-react";

import { api } from "../../lib/api";
import type { OrgMember, UserResponse } from "../../api/types";
import { useAuth } from "../../lib/auth-context";
import { formatDateTime } from "../../lib/date-utils";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";

interface OrgMembersSectionProps {
  orgId: string;
}

export default function OrgMembersSection({ orgId }: OrgMembersSectionProps) {
  const { hasPermission, refresh } = useAuth();
  const canReadMembers = hasPermission("org.members.read");
  const canManageMembers = hasPermission("org.members.manage");

  const [members, setMembers] = useState<OrgMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [settingDefault, setSettingDefault] = useState<string | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UserResponse[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserResponse | null>(null);
  const [showResults, setShowResults] = useState(false);

  const fetchMembers = useCallback(async () => {
    if (!canReadMembers) {
      setMembers([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const membersList = await api.listOrgMembers(orgId, includeInactive);
      setMembers(membersList);
    } catch (error) {
      console.error("Failed to fetch org members:", error);
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }, [canReadMembers, includeInactive, orgId]);

  useEffect(() => {
    if (!canReadMembers) {
      setMembers([]);
      setLoading(false);
      return;
    }
    if (orgId) {
      void fetchMembers();
    }
  }, [canReadMembers, fetchMembers, orgId]);

  const existingUserIds = useMemo(() => new Set(members.map((member) => member.user_id)), [members]);

  useEffect(() => {
    if (!canManageMembers || !searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await api.searchUsers(searchQuery.trim(), 25);
        const filtered = response.users.filter((user) => !existingUserIds.has(user.user_id));
        setSearchResults(filtered);
        setShowResults(true);
      } catch (error) {
        console.error("Failed to search users:", error);
        setSearchResults([]);
        setShowResults(true);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [canManageMembers, existingUserIds, searchQuery]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest("[data-user-search]")) {
        setShowResults(false);
      }
    };

    if (showResults) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
    return undefined;
  }, [showResults]);

  const handleSelectUser = (user: UserResponse) => {
    setSelectedUser(user);
    setSearchQuery("");
    setSearchResults([]);
    setShowResults(false);
  };

  const handleAddMember = async (event: FormEvent) => {
    event.preventDefault();
    if (!canManageMembers || !selectedUser) {
      return;
    }

    setAdding(true);
    try {
      await api.addOrgMember(orgId, {
        user_id: selectedUser.user_id,
        email: selectedUser.email ?? null,
        display_name: selectedUser.display_name ?? null,
      });
      setSelectedUser(null);
      setSearchQuery("");
      setShowAddForm(false);
      await fetchMembers();
      await refresh();
    } catch (error) {
      console.error("Failed to add member:", error);
      const message =
        error instanceof Error
          ? error.message
          : "Failed to add member. Please try again.";
      if (message.includes("already exists") || message.includes("409")) {
        alert("This user is already a member of this organization.");
      } else {
        alert(message);
      }
    } finally {
      setAdding(false);
    }
  };

  const handleRemoveMember = async (memberUserId: string) => {
    if (!canManageMembers) {
      return;
    }
    if (!confirm("Are you sure you want to remove this member from the organization?")) {
      return;
    }

    setRemoving(memberUserId);
    try {
      await api.removeOrgMember(orgId, memberUserId);
      await fetchMembers();
      await refresh();
    } catch (error) {
      console.error("Failed to remove member:", error);
      alert(error instanceof Error ? error.message : "Failed to remove member.");
    } finally {
      setRemoving(null);
    }
  };

  const handleSetDefault = async (memberUserId: string) => {
    if (!canManageMembers) {
      return;
    }
    setSettingDefault(memberUserId);
    try {
      await api.setOrgMemberDefault(orgId, memberUserId);
      await fetchMembers();
      await refresh();
    } catch (error) {
      console.error("Failed to set default member:", error);
      alert(error instanceof Error ? error.message : "Failed to set default member.");
    } finally {
      setSettingDefault(null);
    }
  };

  if (!canReadMembers) {
    return null;
  }

  return (
    <div className="mt-8 border-t border-zinc-200 pt-8 dark:border-zinc-800">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Members</h3>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {canManageMembers
              ? "Search for Entra users and add them to this organization."
              : "View organization membership."}
          </p>
        </div>
        {canManageMembers && !showAddForm ? (
          <Button type="button" size="sm" onClick={() => setShowAddForm(true)} variant="outline">
            <Plus className="mr-2 h-4 w-4" />
            Add Member
          </Button>
        ) : null}
      </div>

      <div className="mb-4 flex items-center gap-2">
        <input
          id="org-members-include-inactive"
          type="checkbox"
          checked={includeInactive}
          onChange={(event) => setIncludeInactive(event.target.checked)}
          className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900 dark:border-zinc-700 dark:focus:ring-zinc-100"
        />
        <label
          htmlFor="org-members-include-inactive"
          className="text-sm text-zinc-700 dark:text-zinc-300"
        >
          Show inactive members
        </label>
      </div>

      {canManageMembers && showAddForm ? (
        <div className="mb-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
          <h4 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">Add Member</h4>
          <form onSubmit={handleAddMember} className="space-y-4">
            {!selectedUser ? (
              <div className="relative space-y-2" data-user-search>
                <label
                  htmlFor="member-search"
                  className="block text-sm font-medium text-zinc-900 dark:text-zinc-100"
                >
                  Search for User
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                  <Input
                    id="member-search"
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Search by name or email"
                    className="pl-9"
                  />
                </div>
                {showResults ? (
                  <div className="absolute z-20 mt-2 w-full rounded-md border border-zinc-200 bg-white shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
                    {searching ? (
                      <div className="p-3 text-sm text-zinc-500 dark:text-zinc-400">Searching...</div>
                    ) : searchResults.length === 0 ? (
                      <div className="p-3 text-sm text-zinc-500 dark:text-zinc-400">No users found.</div>
                    ) : (
                      <ul className="max-h-64 overflow-y-auto">
                        {searchResults.map((user) => (
                          <li key={user.user_id}>
                            <button
                              type="button"
                              onClick={() => handleSelectUser(user)}
                              className="w-full px-4 py-3 text-left hover:bg-zinc-50 dark:hover:bg-zinc-900"
                            >
                              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                                {user.display_name || user.username || user.user_id}
                              </div>
                              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                                {user.email || user.username || user.user_id}
                              </div>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-md border border-zinc-200 px-4 py-3 dark:border-zinc-800">
                <div>
                  <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {selectedUser.display_name || selectedUser.username || selectedUser.user_id}
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">
                    {selectedUser.email || selectedUser.username || selectedUser.user_id}
                  </div>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedUser(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowAddForm(false);
                  setSelectedUser(null);
                  setSearchQuery("");
                  setSearchResults([]);
                  setShowResults(false);
                }}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={adding || !selectedUser}>
                {adding ? "Adding..." : "Add"}
              </Button>
            </div>
          </form>
        </div>
      ) : null}

      <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <Table>
          <TableHeader>
            <TableRow className="border-zinc-200 dark:border-zinc-800">
              <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">User</TableHead>
              <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Email</TableHead>
              <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Added</TableHead>
              <TableHead className="font-semibold text-zinc-900 dark:text-zinc-100">Status</TableHead>
              {canManageMembers ? (
                <TableHead className="w-36 font-semibold text-zinc-900 dark:text-zinc-100">
                  Actions
                </TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={canManageMembers ? 5 : 4} className="py-6 text-center text-zinc-500 dark:text-zinc-400">
                  Loading members...
                </TableCell>
              </TableRow>
            ) : members.length === 0 ? (
              <TableRow>
                <TableCell colSpan={canManageMembers ? 5 : 4} className="py-6 text-center text-zinc-500 dark:text-zinc-400">
                  No members found.
                </TableCell>
              </TableRow>
            ) : (
              members.map((member, index) => (
                <TableRow
                  key={`${member.user_id}-${member.org_id}`}
                  className={cn(
                    "border-zinc-200 dark:border-zinc-800",
                    index % 2 === 1 && "bg-zinc-50 dark:bg-zinc-900/50",
                  )}
                >
                  <TableCell className="text-zinc-900 dark:text-zinc-100">
                    <div className="flex flex-col">
                      <span className="font-medium">{member.display_name || member.user_id}</span>
                      {member.display_name ? (
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">{member.user_id}</span>
                      ) : null}
                    </div>
                  </TableCell>
                  <TableCell className="text-zinc-700 dark:text-zinc-300">{member.email || "-"}</TableCell>
                  <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">{formatDateTime(member.created_at)}</TableCell>
                  <TableCell className="text-sm text-zinc-600 dark:text-zinc-400">
                    <div className="flex items-center gap-2">
                      <span>{member.is_active ? "Active" : "Inactive"}</span>
                      {member.is_default ? (
                        <span className="inline-flex items-center gap-1 text-xs text-zinc-600 dark:text-zinc-300">
                          <Star className="h-3 w-3" /> Default
                        </span>
                      ) : null}
                    </div>
                  </TableCell>
                  {canManageMembers ? (
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleSetDefault(member.user_id)}
                          disabled={settingDefault === member.user_id || !member.is_active}
                          className="h-8 w-8 p-0"
                          title="Set default"
                          aria-label="Set default"
                        >
                          <Star className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveMember(member.user_id)}
                          disabled={removing === member.user_id || !member.is_active}
                          className="h-8 w-8 p-0"
                          title="Remove"
                          aria-label="Remove"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
