import { type FormEvent, useState } from "react";

import type { CreateOrganizationRequest } from "../../api/types";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";

interface AddOrganizationFormProps {
  onCreateOrg: (payload: CreateOrganizationRequest) => Promise<void>;
  onSuccess: () => void;
  onCancel: () => void;
}

export default function AddOrganizationForm({
  onCreateOrg,
  onSuccess,
  onCancel,
}: AddOrganizationFormProps) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [documentationVisibility, setDocumentationVisibility] = useState<"shared" | "isolated">("shared");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSlugChange = (value: string) => {
    const generatedSlug = value
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-");
    setSlug(generatedSlug);
  };

  const resetForm = () => {
    setName("");
    setSlug("");
    setDocumentationVisibility("shared");
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (!name.trim() || !slug.trim()) {
      return;
    }

    setIsSubmitting(true);
    try {
      await onCreateOrg({
        name: name.trim(),
        slug: slug.trim(),
        documentation_visibility: documentationVisibility,
      });
      resetForm();
      onSuccess();
    } catch (error) {
      console.error("Failed to create organization:", error);
      alert(
        error instanceof Error
          ? error.message
          : "Failed to create organization. Please try again.",
      );
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
        <CardTitle>Add New Organization</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label
              htmlFor="org-name"
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Name
            </label>
            <Input
              id="org-name"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                if (!slug) {
                  handleSlugChange(event.target.value);
                }
              }}
              placeholder="Enter organization name (e.g., Major Crimes)"
              required
            />
          </div>

          <div className="space-y-2">
            <label
              htmlFor="org-slug"
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Slug
            </label>
            <Input
              id="org-slug"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              placeholder="Enter URL-friendly slug (e.g., major-crimes)"
              required
            />
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              URL-friendly identifier (auto-generated from name, but can be edited)
            </p>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="org-doc-visibility"
              className="text-sm font-medium text-zinc-900 dark:text-zinc-100"
            >
              Documentation visibility
            </label>
            <select
              id="org-doc-visibility"
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
      </CardContent>
    </Card>
  );
}
