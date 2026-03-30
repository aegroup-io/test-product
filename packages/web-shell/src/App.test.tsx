import type { ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Wrench } from "lucide-react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { LocaleProvider } from "./lib/locale-context";
import { ThemeProvider } from "./lib/theme-context";

function renderApp({
  branding,
  initialEntries = ["/"],
  settingsExtensions,
}: {
  branding?: {
    title?: string;
    kicker?: string;
    logoLightSrc?: string;
    logoDarkSrc?: string;
  };
  initialEntries?: string[];
  settingsExtensions?: ComponentProps<typeof App>["settingsExtensions"];
} = {}) {
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <App branding={branding} settingsExtensions={settingsExtensions} />
        </MemoryRouter>
      </LocaleProvider>
    </ThemeProvider>,
  );
}

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("App", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_AUTH_DISABLED", "1");
    let members = [
      {
        org_id: "org-1",
        user_id: "local-dev",
        email: "local-dev@example.com",
        display_name: "Local Developer",
        is_active: true,
        is_default: true,
        archived_at: null,
        created_at: "2026-03-11T00:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL, init?: RequestInit) => {
        const url = String(input);
        const requestUrl = new URL(url);
        const path = requestUrl.pathname;
        const method = init?.method ?? "GET";
        const memberMatch = path.match(/^\/orgs\/org-1\/members\/([^/]+)$/);
        const defaultMatch = path.match(/^\/orgs\/org-1\/members\/([^/]+)\/default$/);

        if (path === "/orgs/org-1/members" && method === "GET") {
          return jsonResponse(members);
        }

        if (path === "/orgs/org-1/members" && method === "POST") {
          const payload = JSON.parse(String(init?.body ?? "{}")) as {
            user_id: string;
            email?: string | null;
            display_name?: string | null;
          };
          const member = {
            org_id: "org-1",
            user_id: payload.user_id,
            email: payload.email ?? null,
            display_name: payload.display_name ?? null,
            is_active: true,
            is_default: members.length === 0,
            archived_at: null,
            created_at: "2026-03-12T00:00:00Z",
          };
          members = [...members.filter((item) => item.user_id !== payload.user_id), member];
          return jsonResponse(member, 201);
        }

        if (defaultMatch && method === "POST") {
          const userId = decodeURIComponent(defaultMatch[1] ?? "");
          members = members.map((member) => ({
            ...member,
            is_default: member.user_id === userId,
          }));
          const member = members.find((item) => item.user_id === userId);
          return member
            ? jsonResponse(member)
            : Promise.resolve(new Response("Not found", { status: 404 }));
        }

        if (memberMatch && method === "DELETE") {
          const userId = decodeURIComponent(memberMatch[1] ?? "");
          members = members.filter((member) => member.user_id !== userId);
          return Promise.resolve(new Response(null, { status: 204 }));
        }

        if (path === "/users" && method === "GET") {
          const query = requestUrl.searchParams.get("query");
          if (query?.toLowerCase().includes("operator")) {
            return jsonResponse({
              users: [
                {
                  user_id: "operator-2",
                  username: "operator.two@example.com",
                  email: "operator-2@example.com",
                  display_name: "Operator Two",
                  status: "Enabled",
                },
              ],
              next_token: null,
            });
          }
          return jsonResponse({ users: [], next_token: null });
        }

        const responses: Record<string, unknown> = {
          "/me": {
            user_id: "local-dev",
            username: "local-dev@example.com",
            roles: ["admin"],
            permissions: [
              "org.read",
              "org.manage",
              "org.members.read",
              "org.members.manage",
              "platform.read",
              "platform.manage",
              "observability.read",
              "ai.read",
              "ai.manage",
              "worker.manage",
            ],
            feature_flags: ["agent.chat"],
            org_ids: ["org-1"],
            default_org_id: "org-1",
            claims: {},
          },
          "/orgs": [
            {
              org_id: "org-1",
              name: "Primary",
              slug: "primary",
              documentation_visibility: "shared",
              created_at: "2026-03-11T00:00:00Z",
              updated_at: "2026-03-11T00:00:00Z",
            },
          ],
          "/platform/summary": {
            organization_count: 1,
            provider_count: 1,
            model_count: 1,
            agent_count: 1,
            product_count: 1,
            repository_binding_count: 1,
            lane_count: 1,
            component_node_count: 2,
            webhook_delivery_count: 1,
            membership_count: 1,
            role_count: 4,
            permission_count: 10,
            feature_flag_count: 3,
            secret_count: 1,
            setting_count: 2,
          },
          "/ai/providers": [],
          "/ai/models": [],
          "/ai/agents": [],
          "/rbac/roles": [],
          "/rbac/permissions": [],
          "/rbac/feature-flags": [],
          "/secrets": [],
          "/settings": [
            {
              setting_id: "setting-1",
              scope_type: "user",
              scope_id: "local-dev",
              key: "shell.theme",
              value_json: "light",
              created_at: "2026-03-11T00:00:00Z",
              updated_at: "2026-03-11T00:00:00Z",
            },
          ],
        };
        const payload = path === "/settings" ? responses["/settings"] : responses[path];
        if (!payload) {
          return Promise.resolve(
            new Response("Not found", {
              status: 404,
            }),
          );
        }
        return jsonResponse(payload);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("renders the DataVein-style shell chrome", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
    });

    expect(screen.getByAltText("Agent Core Starter")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getAllByText("Primary").length).toBeGreaterThan(0);
    expect(screen.getByText("Organizations")).toBeInTheDocument();
    expect(screen.getByText("Secrets")).toBeInTheDocument();
  });

  it("renders the settings workspace with starter branding overrides", async () => {
    renderApp({
      branding: {
        title: "Orcha",
        kicker: "Agent orchestration",
        logoLightSrc: "/logo-light.svg",
        logoDarkSrc: "/logo-dark.svg",
      },
      initialEntries: ["/settings/orgs"],
    });

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Organizations" }),
      ).toBeInTheDocument();
    });

    expect(screen.getByAltText("Orcha")).toHaveAttribute("src", "/logo-light.svg");
    expect(screen.getByText("System Configuration")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search organizations...")).toBeInTheDocument();
    expect(screen.queryByText("Connections")).not.toBeInTheDocument();
    expect(screen.queryByText("Environments")).not.toBeInTheDocument();
    expect(screen.queryByText("Catalogs")).not.toBeInTheDocument();
    expect(screen.queryByText("Git Repositories")).not.toBeInTheDocument();
  });

  it("renders extension pages inside the shared settings shell", async () => {
    renderApp({
      initialEntries: ["/settings/workspace"],
      settingsExtensions: [
        {
          path: "workspace",
          label: "Workspace",
          icon: Wrench,
          render: ({ selectedOrg }) => (
            <div>
              <h1>Workspace</h1>
              <p>{selectedOrg?.name ?? "No organization selected"}</p>
            </div>
          ),
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Workspace" })).toBeInTheDocument();
    });

    expect(screen.getByText("Primary")).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
  });

  it("renders dbt-miner-style org members and supports Entra lookup actions", async () => {
    renderApp({
      initialEntries: ["/settings/orgs"],
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Organizations" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Edit organization" })[0]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Members" })).toBeInTheDocument();
    });

    expect(screen.getByText("Search for Entra users and add them to this organization.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Member" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add Member" }));
    fireEvent.change(screen.getByLabelText("Search for User"), {
      target: { value: "operator" },
    });

    await waitFor(() => {
      expect(screen.getByText("Operator Two")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Operator Two"));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(screen.getAllByText("Operator Two").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: "Set default" }));

    await waitFor(() => {
      expect(screen.getAllByText(/Default/).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => {
      expect(screen.queryByText("Operator Two")).not.toBeInTheDocument();
    });
  });

  it("renders the shared AI models settings page instead of a placeholder", async () => {
    renderApp({
      initialEntries: ["/settings/models"],
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "AI Models" })).toBeInTheDocument();
    });

    expect(
      screen.getByText("Manage AI providers and the models available for each provider."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Provider" })).toBeInTheDocument();
  });
});
