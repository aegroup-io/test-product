import { type FormEvent, useEffect, useState } from "react";

import type { Organization, UpdateOrganizationRequest } from "../../api/types";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import OrgMembersSection from "./OrgMembersSection";

interface EditOrganizationFormProps {
  organization: Organization;
  onUpdateOrg: (orgId: string, payload: UpdateOrganizationRequest) => Promise<void>;
  onSuccess: () => void;
  onCancel: () => void;
}

export default function EditOrganizationForm({
  organization,
  onUpdateOrg,
  onSuccess,
  onCancel,
}: EditOrganizationFormProps) {
  const [name, setName] = useState(organization.name);
  const [slug, setSlug] = useState(organization.slug);
  const [documentationVisibility, setDocumentationVisibility] = useState<"shared" | "isolated">(
    organization.documentation_visibility,
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setName(organization.name);
    setSlug(organization.slug);
    setDocumentationVisibility(organization.documentation_visibility);
  }, [organization]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!name.trim() || !slug.trim()) {
      return;
    }

    const updates: UpdateOrganizationRequest = {};
    if (name.trim() !== organization.name) {
      updates.name = name.trim();
    }
    if (slug.trim() !== organization.slug) {
      updates.slug = slug.trim();
    }
    if (documentationVisibility !== organization.documentation_visibility) {
      updates.documentation_visibility = documentationVisibility;
    }

    if (Object.keys(updates).length === 0) {
      onSuccess();
      return;
    }

    setIsSubmitting(true);
    try {
      await onUpdateOrg(organization.org_id, updates);
      onSuccess();
    } catch (error) {
      console.error("Failed to update organization:", error);
      alert(
        error instanceof Error
          ? error.message
          : "Failed to update organization. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setName(organization.name);
    setSlug(organization.slug);
    setDocumentationVisibility(organization.documentation_visibility);
    onCancel();
  };

  return (
    <Card className="mb-6 w-full max-w-full">
      <CardHeader>
        <CardTitle>Edit Organization</CardTitle>
      </CardHeader>
      <CardContent className="w-full max-w-full">
        <form onSubmit={handleSubmit} className="space-y-4 w-full max-w-full">
          <div className="space-y-2">
            <label
              htmlFor="edit-org-name"
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100 block"
            >
              Name
            </label>
            <Input
              id="edit-org-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Enter organization name"
              required
              className="w-full"
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="edit-org-slug"
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100 block"
            >
              Slug
            </label>
            <Input
              id="edit-org-slug"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              placeholder="Enter URL-friendly slug"
              required
              className="w-full"
            />
            <p className="text-xs text-zinc-500 dark:text-zinc-400">URL-friendly identifier</p>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="edit-org-doc-visibility"
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100 block"
            >
              Documentation visibility
            </label>
            <select
              id="edit-org-doc-visibility"
              value={documentationVisibility}
              onChange={(event) =>
                setDocumentationVisibility(event.target.value === "isolated" ? "isolated" : "shared")
              }
              className="block w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            >
              <option value="shared">Shared</option>
              <option value="isolated">Isolated</option>
            </select>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Shared orgs are discoverable in Documentation Workspace. Isolated orgs stay hidden outside their org.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="outline" onClick={handleCancel}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || !name.trim() || !slug.trim()}>
              {isSubmitting ? "Saving..." : "Save"}
            </Button>
          </div>
        </form>
        <OrgMembersSection orgId={organization.org_id} />
      </CardContent>
    </Card>
  );
}
