import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider, ThemeProvider } from "@aegroup/agent-core-web-shell";

import App from "./App";
import type { ProductSeedJobResponse, ProductSeedJobSummaryResponse, ProductSummaryResponse } from "./operator-types";

function createFixtureState() {
  const product: any = {
    product_id: "product-1",
    org_id: "org-1",
    key: "atlas",
    name: "Atlas",
    description: "Operator-ready control plane",
    status: "Active",
    baseline_channel: "stable",
    standards_pack_key: "default",
    standards_pack_version: "1.2.0",
    agent_core_version: "0.1.0",
    execution_profile: "standard-python",
    component_root_node_id: "node-root",
    manifest_schema_version: 1,
    setup_state: "setup-needed",
    setup_diagnostics: [
      {
        classification: "blocking setup error",
        code: "secret.required_missing",
        message: "GitHub webhook secret is still missing.",
        path: "github/webhook-secret",
      },
      {
        classification: "recoverable drift",
        code: "asset.recommended_missing",
        message: "Recommended baseline asset is missing: .github/workflows/orcha-standards.yml",
        path: ".github/workflows/orcha-standards.yml",
      },
      {
        classification: "advisory warning",
        code: "governance.approval_posture_capped",
        message: "Approval posture is capped by platform defaults.",
        path: ".orcha/product.yaml",
      },
    ],
    effective_config: {},
    operator_overrides: {},
    last_config_refresh_at: "2026-03-16T20:00:00Z",
    last_accepted_config_at: "2026-03-15T19:00:00Z",
    created_at: "2026-03-14T12:00:00Z",
    updated_at: "2026-03-16T20:00:00Z",
    latest_seed_job: null,
    primary_repo: {
      repo_id: "repo-1",
      github_repository_node_id: "R_kgDOAtlas",
      owner: "aegroup-io",
      name: "atlas",
      default_branch: "dev",
      visibility: "private",
      description: "Atlas repo",
      is_archived: false,
      seed_source: "agent-core",
      adoption_state: "adopted",
      raw_payload: {},
      created_at: "2026-03-14T12:00:00Z",
      updated_at: "2026-03-16T20:00:00Z",
    },
    primary_project: {
      project_id: "project-1",
      github_project_node_id: "PVT_123",
      number: 4,
      title: "Atlas",
      status_field_name: "Status",
      status_options: ["Todo", "In Progress", "Done"],
      raw_payload: {},
      mirror_version: 1,
      created_at: "2026-03-14T12:00:00Z",
      updated_at: "2026-03-16T20:00:00Z",
    },
    managed_assets: [
      {
        managed_asset_id: "asset-1",
        product_id: "product-1",
        path: "AGENTS.md",
        kind: "file",
        management_mode: "managed",
        upstream_bundle_version: "1.2.0",
        drift_status: "current",
        created_at: "2026-03-14T12:00:00Z",
        updated_at: "2026-03-16T20:00:00Z",
      },
      {
        managed_asset_id: "asset-2",
        product_id: "product-1",
        path: ".github/pull_request_template.md",
        kind: "file",
        management_mode: "managed",
        upstream_bundle_version: "1.2.0",
        drift_status: "conflict",
        created_at: "2026-03-14T12:00:00Z",
        updated_at: "2026-03-16T20:00:00Z",
      },
      {
        managed_asset_id: "asset-3",
        product_id: "product-1",
        path: ".github/workflows/orcha-standards.yml",
        kind: "file",
        management_mode: "advisory",
        upstream_bundle_version: "1.2.0",
        drift_status: "advisory-drift",
        created_at: "2026-03-14T12:00:00Z",
        updated_at: "2026-03-16T20:00:00Z",
      },
    ],
  };

  const approvalLane: any = {
    lane_id: "lane-approval",
    product_id: "product-1",
    repo_id: "repo-1",
    work_item_id: "work-item-1",
    attempt: 1,
    state: "AwaitingApproval",
    claimed_at: "2026-03-16T20:10:00Z",
    started_at: "2026-03-16T20:11:00Z",
    finished_at: null,
    branch_name: "orcha/issue-281",
    retry_due_at: null,
    handoff_reason: null,
    last_error: null,
    created_at: "2026-03-16T20:10:00Z",
    updated_at: "2026-03-16T20:12:00Z",
    product: {
      product_id: "product-1",
      key: "atlas",
      name: "Atlas",
      status: "Active",
    },
    repository: product.primary_repo,
    work_item: {
      work_item_id: "work-item-1",
      issue_number: 281,
      title: "Awaiting approval",
      status: "In Progress",
      dependency_state: "ready",
      handoff_status: "none",
      linked_prs: [],
      updated_at: "2026-03-16T20:12:00Z",
    },
    execution_environment: {
      execution_environment_id: "env-1",
      status: "Ready",
      runtime_provider: "test",
      container_image: "ghcr.io/aegroup/agent-core-runner:stable",
      container_handle: "aks://approval",
      workspace_uri: "file:///tmp/atlas",
      artifact_uri: "s3://artifacts/atlas/281",
      log_uri: "s3://logs/atlas/281",
      cache_uri: "s3://cache/atlas",
      heartbeat_at: "2026-03-16T20:12:00Z",
      terminated_at: null,
      quarantine_reason: null,
    },
    agent_session: {
      agent_session_id: "session-1",
      thread_id: null,
      turn_id: null,
      runner_session_id: "runner-1",
      runner_version: "1.0.0",
      status: "awaiting_approval",
      capabilities: ["approval-gates"],
      environment_identity: "atlas-approval",
      last_event: "awaiting_approval",
      last_event_at: "2026-03-16T20:12:00Z",
      heartbeat_at: "2026-03-16T20:12:00Z",
      wait_reason: "Need operator approval.",
      continuation_summary: {},
      last_error_category: null,
      turn_count: 5,
      input_tokens: 100,
      output_tokens: 220,
      total_tokens: 320,
      tool_call_count: 2,
      requires_human_input: false,
      created_at: "2026-03-16T20:10:00Z",
      updated_at: "2026-03-16T20:12:00Z",
    },
  };

  const runningLane: any = {
    lane_id: "lane-running",
    product_id: "product-1",
    repo_id: "repo-1",
    work_item_id: "work-item-3",
    attempt: 2,
    state: "Running",
    claimed_at: "2026-03-16T19:45:00Z",
    started_at: "2026-03-16T19:46:00Z",
    finished_at: null,
    branch_name: "orcha/issue-283",
    retry_due_at: null,
    handoff_reason: null,
    last_error: null,
    created_at: "2026-03-16T19:45:00Z",
    updated_at: "2026-03-16T20:08:00Z",
    product: {
      product_id: "product-1",
      key: "atlas",
      name: "Atlas",
      status: "Active",
    },
    repository: product.primary_repo,
    work_item: {
      work_item_id: "work-item-3",
      issue_number: 283,
      title: "Runner heartbeat stalled",
      status: "In Progress",
      dependency_state: "ready",
      handoff_status: "none",
      linked_prs: [],
      updated_at: "2026-03-16T20:08:00Z",
    },
    execution_environment: {
      execution_environment_id: "env-2",
      status: "Ready",
      runtime_provider: "test",
      container_image: "ghcr.io/aegroup/agent-core-runner:stable",
      container_handle: "aks://running",
      workspace_uri: "file:///tmp/atlas-running",
      artifact_uri: "s3://artifacts/atlas/283",
      log_uri: "s3://logs/atlas/283",
      cache_uri: "s3://cache/atlas",
      heartbeat_at: "2026-03-16T19:47:00Z",
      terminated_at: null,
      quarantine_reason: null,
    },
    agent_session: {
      agent_session_id: "session-2",
      thread_id: "thread-running",
      turn_id: "turn-running",
      runner_session_id: "runner-2",
      runner_version: "1.0.0",
      status: "running",
      capabilities: ["execution"],
      environment_identity: "atlas-running",
      last_event: "session_progress",
      last_event_at: "2026-03-16T19:47:00Z",
      heartbeat_at: "2026-03-16T19:47:00Z",
      wait_reason: null,
      continuation_summary: {},
      last_error_category: null,
      turn_count: 8,
      input_tokens: 240,
      output_tokens: 480,
      total_tokens: 720,
      tool_call_count: 5,
      requires_human_input: false,
      created_at: "2026-03-16T19:45:00Z",
      updated_at: "2026-03-16T20:08:00Z",
    },
  };

  const failedLane: any = {
    lane_id: "lane-failed",
    product_id: "product-1",
    repo_id: "repo-1",
    work_item_id: "work-item-2",
    attempt: 1,
    state: "FailedTerminal",
    claimed_at: "2026-03-16T19:00:00Z",
    started_at: "2026-03-16T19:01:00Z",
    finished_at: "2026-03-16T19:40:00Z",
    branch_name: "orcha/issue-282",
    retry_due_at: null,
    handoff_reason: null,
    last_error: "Runner timeout.",
    created_at: "2026-03-16T19:00:00Z",
    updated_at: "2026-03-16T19:40:00Z",
    product: {
      product_id: "product-1",
      key: "atlas",
      name: "Atlas",
      status: "Active",
    },
    repository: product.primary_repo,
    work_item: {
      work_item_id: "work-item-2",
      issue_number: 282,
      title: "Retry me",
      status: "In Progress",
      dependency_state: "ready",
      handoff_status: "none",
      linked_prs: [],
      updated_at: "2026-03-16T19:40:00Z",
    },
    execution_environment: null,
    agent_session: null,
  };

  product.delivery_cockpit = {
    mirror_state: "ambiguous",
    work_pressure: {
      total_open_count: 4,
      triage_count: 0,
      ready_count: 1,
      blocked_count: 1,
      in_progress_count: 2,
      in_review_count: 1,
      done_count: 0,
      ambiguous_count: 1,
      stale_count: 0,
    },
    project: {
      project_id: "project-1",
      number: 4,
      title: "Atlas",
      status_field_name: "Status",
      item_count: 5,
      issue_count: 4,
      pull_request_count: 1,
      mirror_state: "ambiguous",
      last_reconciled_at: "2026-03-16T20:09:00Z",
      url: "https://github.com/orgs/aegroup-io/projects/4",
    },
    work_items: [
      {
        work_item_id: "work-item-1",
        repo_id: "repo-1",
        repo_owner: "aegroup-io",
        repo_name: "atlas",
        issue_number: 281,
        title: "Awaiting approval",
        status: "In Progress",
        status_source: "In Progress",
        dependency_state: "clear",
        priority_hint: "high",
        handoff_status: "none",
        eligibility_flags: [],
        mirror_state: "current",
        requires_repair: false,
        repair_reasons: [],
        last_normalized_at: "2026-03-16T20:12:00Z",
        updated_at: "2026-03-16T20:12:00Z",
        project_status_name: "In Progress",
        url: "https://github.com/aegroup-io/atlas/issues/281",
        linked_pull_requests: [],
      },
      {
        work_item_id: "work-item-3",
        repo_id: "repo-1",
        repo_owner: "aegroup-io",
        repo_name: "atlas",
        issue_number: 283,
        title: "Runner heartbeat stalled",
        status: "In Progress",
        status_source: "In Progress",
        dependency_state: "clear",
        priority_hint: "medium",
        handoff_status: "none",
        eligibility_flags: [],
        mirror_state: "current",
        requires_repair: false,
        repair_reasons: [],
        last_normalized_at: "2026-03-16T20:08:00Z",
        updated_at: "2026-03-16T20:08:00Z",
        project_status_name: "In Progress",
        url: "https://github.com/aegroup-io/atlas/issues/283",
        linked_pull_requests: [],
      },
      {
        work_item_id: "work-item-review",
        repo_id: "repo-1",
        repo_owner: "aegroup-io",
        repo_name: "atlas",
        issue_number: 284,
        title: "Review PR handoff",
        status: "In Review",
        status_source: "In Review",
        dependency_state: "clear",
        priority_hint: "medium",
        handoff_status: "in_review",
        eligibility_flags: ["awaiting-review"],
        mirror_state: "current",
        requires_repair: false,
        repair_reasons: [],
        last_normalized_at: "2026-03-16T20:05:00Z",
        updated_at: "2026-03-16T20:05:00Z",
        project_status_name: "Review",
        url: "https://github.com/aegroup-io/atlas/issues/284",
        linked_pull_requests: [
          {
            github_pr_node_id: "PR_kgDOAtlas77",
            number: 77,
            title: "Implement atlas delivery cockpit",
            state: "open",
            is_draft: false,
            review_state: "APPROVED",
            merge_state: "CLEAN",
            merged_at: null,
            url: "https://github.com/aegroup-io/atlas/pull/77",
          },
        ],
      },
      {
        work_item_id: "work-item-ambiguous",
        repo_id: "repo-1",
        repo_owner: "aegroup-io",
        repo_name: "atlas",
        issue_number: 285,
        title: "Mirror needs repair",
        status: "Blocked",
        status_source: "Status",
        dependency_state: "ambiguous",
        priority_hint: "low",
        handoff_status: "none",
        eligibility_flags: ["repair-needed"],
        mirror_state: "ambiguous",
        requires_repair: true,
        repair_reasons: ["dependency.ambiguous", "status.unmapped"],
        last_normalized_at: "2026-03-16T20:03:00Z",
        updated_at: "2026-03-16T20:04:00Z",
        project_status_name: "Blocked",
        url: "https://github.com/aegroup-io/atlas/issues/285",
        linked_pull_requests: [],
      },
    ],
    remaining_work_item_count: 0,
  };

  const baseline: any = {
    product_id: "product-1",
    org_id: "org-1",
    product_key: "atlas",
    product_name: "Atlas",
    product_status: "Active",
    baseline_channel: "stable",
    standards_pack_key: "default",
    standards_pack_version: "1.2.0",
    agent_core_version: "0.1.0",
    setup_state: "setup-needed",
    setup_diagnostics: product.setup_diagnostics,
    drift_status: "drift",
    managed_asset_counts: {
      current: 1,
      conflict: 1,
      "advisory-drift": 1,
    },
    managed_assets: product.managed_assets,
    latest_run: {
      standards_upgrade_run_id: "run-1",
      outcome_kind: "upgrade-pr",
      outcome_status: "reviewable",
      generated_pr_number: 99,
      created_at: "2026-03-15T10:00:00Z",
      updated_at: "2026-03-16T12:00:00Z",
    },
    last_config_refresh_at: "2026-03-16T20:00:00Z",
    last_accepted_config_at: "2026-03-15T19:00:00Z",
  };

  const standardsRun: any = {
    standards_upgrade_run_id: "run-1",
    product_id: "product-1",
    repo_id: "repo-1",
    standards_pack_id: "pack-1",
    source_bundle: "agent-core/default",
    source_version: "1.2.0",
    outcome_kind: "upgrade-pr",
    outcome_status: "reviewable",
    generated_pr_number: 99,
    pr_title: "Refresh default 1.2.0 for atlas",
    pr_body: "Managed updates: `.github/pull_request_template.md`\nFollow-up items: 1",
    summary_payload: {
      source_bundle: "agent-core/default",
      pack_key: "default",
      channel: "stable",
      version: "1.2.0",
      counts: {
        conflict: 1,
        "advisory-drift": 1,
        noop: 1,
      },
      changed_paths: [],
      advisory_paths: [".github/workflows/orcha-standards.yml"],
      follow_up_count: 1,
    },
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-16T12:00:00Z",
    assets: [
      {
        standards_upgrade_asset_id: "run-asset-1",
        standards_upgrade_run_id: "run-1",
        path: ".github/pull_request_template.md",
        management_mode: "managed",
        action: "conflict",
        drift_status: "conflict",
        patch_text: null,
        detail: "Managed section refresh could not be applied cleanly.",
        metadata_payload: {
          exists: true,
        },
        created_at: "2026-03-15T10:00:00Z",
        updated_at: "2026-03-16T12:00:00Z",
      },
      {
        standards_upgrade_asset_id: "run-asset-2",
        standards_upgrade_run_id: "run-1",
        path: ".github/workflows/orcha-standards.yml",
        management_mode: "advisory",
        action: "advisory-drift",
        drift_status: "advisory-drift",
        patch_text: "--- a/.github/workflows/orcha-standards.yml\n+++ b/.github/workflows/orcha-standards.yml\n@@ -1 +1 @@\n-old\n+new",
        detail: "Local file diverges from the adopted standards pack.",
        metadata_payload: {
          exists: true,
        },
        created_at: "2026-03-15T10:00:00Z",
        updated_at: "2026-03-16T12:00:00Z",
      },
      {
        standards_upgrade_asset_id: "run-asset-3",
        standards_upgrade_run_id: "run-1",
        path: "AGENTS.md",
        management_mode: "managed",
        action: "noop",
        drift_status: "current",
        patch_text: null,
        detail: null,
        metadata_payload: {
          exists: true,
        },
        created_at: "2026-03-15T10:00:00Z",
        updated_at: "2026-03-16T12:00:00Z",
      },
    ],
    follow_up_items: [
      {
        standards_follow_up_item_id: "follow-up-1",
        standards_upgrade_run_id: "run-1",
        product_id: "product-1",
        repo_id: "repo-1",
        path: ".github/pull_request_template.md",
        title: "Resolve standards conflict for .github/pull_request_template.md",
        detail: "Managed section refresh could not be applied cleanly.",
        status: "open",
        created_at: "2026-03-15T10:00:00Z",
        updated_at: "2026-03-16T12:00:00Z",
      },
    ],
  };

  const graph: any = {
    scope: "product",
    product_id: "product-1",
    lane_id: null,
    generated_at: "2026-03-16T20:15:00Z",
    freshness: {
      observed_at: "2026-03-16T20:15:00Z",
      status: "current",
      stale_after_seconds: 900,
    },
    anchor_node_ids: ["node-root"],
    depth: 2,
    nodes: [
      {
        component_node_id: "node-root",
        product_id: "product-1",
        type: "product",
        key: "atlas",
        name: "Atlas",
        owner: "aegroup",
        version: null,
        status: "healthy",
        source_kind: "manifest",
        source_ref: ".orcha/components.yaml",
        distance: 0,
        freshness: {
          observed_at: "2026-03-16T20:15:00Z",
          status: "current",
          stale_after_seconds: 900,
        },
        overlay: {
          active_work_items: [
            {
              work_item_id: "work-item-1",
              issue_number: 281,
              title: "Awaiting approval",
              status: "In Progress",
              dependency_state: "ready",
              updated_at: "2026-03-16T20:12:00Z",
            },
          ],
          open_pull_requests: [],
          active_lanes: [
            {
              lane_id: "lane-approval",
              work_item_id: "work-item-1",
              state: "AwaitingApproval",
              attempt: 1,
              updated_at: "2026-03-16T20:12:00Z",
            },
          ],
          incidents: [],
          signals: [],
          hotspot_score: 4,
          blocked_dependency_count: 1,
        },
      },
    ],
    edges: [
      {
        component_edge_id: "edge-1",
        from_node_id: "node-root",
        to_node_id: "node-api",
        relationship_type: "depends_on",
        source_kind: "manifest",
        confidence: 1,
        last_verified_at: "2026-03-16T20:15:00Z",
        freshness: {
          observed_at: "2026-03-16T20:15:00Z",
          status: "current",
          stale_after_seconds: 900,
        },
        blocked: true,
      },
    ],
    blocked_dependencies: [
      {
        component_edge_id: "edge-1",
        from_node_id: "node-root",
        from_key: "atlas",
        to_node_id: "node-api",
        to_key: "api-service",
        relationship_type: "depends_on",
        reason: "Active incident on the API dependency.",
        cross_product: false,
        observed_at: "2026-03-16T20:14:00Z",
      },
    ],
    hotspots: [
      {
        component_node_id: "node-root",
        product_id: "product-1",
        key: "atlas",
        name: "Atlas",
        type: "product",
        hotspot_score: 4,
        active_lane_count: 1,
        active_work_item_count: 1,
        observed_at: "2026-03-16T20:15:00Z",
      },
    ],
  };

  return {
    me: {
      user_id: "local-dev",
      username: "operator@example.com",
      roles: ["admin"],
      permissions: [
        "org.read",
        "org.manage",
        "org.members.read",
        "org.members.manage",
        "platform.read",
        "platform.manage",
        "repo.read",
        "repo.manage",
        "repo.delete",
        "observability.read",
        "ai.read",
        "ai.manage",
        "worker.manage",
      ],
      feature_flags: ["agent.chat"],
      org_ids: ["org-1"],
      default_org_id: "org-1" as string | null,
      claims: {},
    },
    organizations: [
      {
        org_id: "org-1",
        name: "Primary",
        slug: "primary",
        documentation_visibility: "shared",
        created_at: "2026-03-11T00:00:00Z",
        updated_at: "2026-03-11T00:00:00Z",
      },
    ],
    secrets: [
      {
        secret_id: "secret-1",
        key: "ORCHA_GITHUB_APP_PRIVATE_KEY",
        name: "GitHub App Private Key",
        kind: "opaque",
        description: "Used by the GitHub App installation.",
        has_value: true,
        created_at: "2026-03-11T00:00:00Z",
        updated_at: "2026-03-11T00:00:00Z",
        last_rotated_at: "2026-03-12T00:00:00Z",
      },
      {
        secret_id: "secret-2",
        key: "AZURE_OPENAI_API_KEY",
        name: "Azure OpenAI Key",
        kind: "opaque",
        description: "Intentionally missing for validation coverage.",
        has_value: false,
        created_at: "2026-03-11T00:00:00Z",
        updated_at: "2026-03-11T00:00:00Z",
        last_rotated_at: null,
      },
      {
        secret_id: "secret-3",
        key: "github-pat-primary",
        name: "Primary GitHub PAT",
        kind: "git_personal_access_token",
        description: "Used for workspace repo lookup tests.",
        has_value: true,
        created_at: "2026-03-11T00:00:00Z",
        updated_at: "2026-03-11T00:00:00Z",
        last_rotated_at: "2026-03-12T00:00:00Z",
      },
    ],
    workspaceRepos: [
      {
        repo_id: "workspace-repo-1",
        org_id: "org-1",
        key: "atlas",
        name: "atlas",
        provider: "github",
        github_owner: "aegroup-io",
        github_repo: "atlas",
        visibility: "private",
        default_branch: "dev",
        clone_url: "https://github.com/aegroup-io/atlas.git",
        git_auth_secret_id: "secret-3",
        org_ids: ["org-1"],
        org_mappings: [
          {
            org_id: "org-1",
            org_name: "Primary",
            active_product_count: 1,
          },
        ],
        archived_at: null,
        created_at: "2026-03-18T08:00:00Z",
        updated_at: "2026-03-18T09:30:00Z",
      },
    ],
    settingsByScope: {
      platform: {},
      org: {
        "org-1": [],
      },
      user: {
        "local-dev": [
          {
            setting_id: "setting-1",
            scope_type: "user",
            scope_id: "local-dev",
            key: "shell.theme",
            value_json: "light",
            created_by: "local-dev",
            updated_by: "local-dev",
            created_at: "2026-03-11T00:00:00Z",
            updated_at: "2026-03-11T00:00:00Z",
          },
        ],
      },
    } as Record<string, Record<string, any[]>>,
    seedJobs: {} as Record<string, any>,
    nextSeedIndex: 0,
    nextAdoptionIndex: 0,
    nextStandardsRunIndex: 1,
    products: [product],
    lanes: [approvalLane, runningLane, failedLane],
    baselines: [baseline],
    standardsRuns: {
      "product-1": [standardsRun],
    } as Record<string, any[]>,
    graph,
  };
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function buildWorkspaceDefaultsSetting(
  value_json: Record<string, unknown>,
  overrides: Partial<{
    setting_id: string;
    created_by: string | null;
    updated_by: string | null;
    created_at: string;
    updated_at: string;
  }> = {},
) {
  return {
    setting_id: overrides.setting_id ?? "setting-workspace-defaults",
    scope_type: "org",
    scope_id: "org-1",
    key: "orcha.product_defaults",
    value_json,
    created_by: overrides.created_by ?? "platform-bootstrap",
    updated_by: overrides.updated_by ?? "platform-admin",
    created_at: overrides.created_at ?? "2026-03-17T09:00:00Z",
    updated_at: overrides.updated_at ?? "2026-03-18T09:30:00Z",
  };
}

function buildSeedRepoSummary(payload: any, index: number) {
  return {
    github_repository_node_id: `R_seed_${index}`,
    owner: payload.github_owner,
    name: payload.github_repo,
    default_branch: payload.github_default_branch,
    visibility: payload.github_visibility,
    description: payload.description ?? null,
    permissions: {
      metadata: "read",
      contents: "write",
      issues: "write",
      pull_requests: "write",
      administration: "write",
      organization_projects: "write",
    },
    branch_protection: {
      enabled: true,
      required_pull_request_reviews: {
        required_approving_review_count: 1,
      },
    },
    raw_payload: {
      node_id: `R_seed_${index}`,
      owner: { login: payload.github_owner },
      name: payload.github_repo,
      default_branch: payload.github_default_branch,
      visibility: payload.github_visibility,
    },
  };
}

function buildSeedProjectSummary(payload: any, index: number) {
  const statusOptions = [payload.ready_status, "In Progress", payload.done_status];
  return {
    github_project_node_id: payload.github_project_node_id ?? `PVT_seed_${index}`,
    number: payload.github_project_number ?? index,
    title: payload.github_project_title ?? payload.product_name,
    status_field_name: payload.status_field,
    status_options: statusOptions,
    fields: [
      {
        node_id: `field-status-${index}`,
        name: payload.status_field,
        data_type: "single_select",
        options: statusOptions.map((name) => ({ name })),
      },
      {
        node_id: `field-priority-${index}`,
        name: "Priority",
        data_type: "single_select",
        options: [{ name: "P1" }, { name: "P2" }],
      },
      {
        node_id: `field-depends-${index}`,
        name: "Depends On",
        data_type: "text",
        options: [],
      },
    ],
    views: ["Board", "Ready Queue"],
    templates: [".github/pull_request_template.md"],
    raw_payload: {
      node_id: payload.github_project_node_id ?? `PVT_seed_${index}`,
      number: payload.github_project_number ?? index,
      title: payload.github_project_title ?? payload.product_name,
      status_field_name: payload.status_field,
      status_options: statusOptions,
    },
  };
}

function buildSeededProduct(
  payload: any,
  repoSummary: any,
  projectSummary: any,
  index: number,
): ProductSummaryResponse {
  return {
    product_id: `product-seed-${index}`,
    org_id: payload.org_id,
    key: payload.product_key,
    name: payload.product_name,
    description: payload.description ?? null,
    status: "Active",
    baseline_channel: payload.baseline_channel ?? "stable",
    standards_pack_key: payload.standards_pack ?? "default",
    standards_pack_version: "0.1.0",
    agent_core_version: "0.1.0",
    execution_profile: payload.execution_profile ?? "standard-python",
    component_root_node_id: `node-seed-${index}`,
    manifest_schema_version: 1,
    setup_state: "ready",
    setup_diagnostics: [],
    effective_config: {},
    operator_overrides: payload.required_secret_keys?.length
      ? {
          activation: {
            required_secret_keys: payload.required_secret_keys,
          },
        }
      : {},
    last_config_refresh_at: "2026-03-18T10:12:00Z",
    last_accepted_config_at: "2026-03-18T10:12:00Z",
    created_at: "2026-03-18T10:10:00Z",
    updated_at: "2026-03-18T10:12:00Z",
    latest_seed_job: null,
    primary_repo: {
      repo_id: `repo-seed-${index}`,
      ...repoSummary,
      is_archived: false,
      seed_source: "approved-baseline:0.1.0",
      adoption_state: "seeded",
      created_at: "2026-03-18T10:10:00Z",
      updated_at: "2026-03-18T10:12:00Z",
    },
    primary_project: {
      project_id: `project-seed-${index}`,
      ...projectSummary,
      mirror_version: 1,
      created_at: "2026-03-18T10:10:00Z",
      updated_at: "2026-03-18T10:12:00Z",
    },
    managed_assets: [
      {
        managed_asset_id: `asset-seed-${index}-1`,
        product_id: `product-seed-${index}`,
        path: "AGENTS.md",
        kind: "file",
        management_mode: "managed",
        upstream_bundle_version: "0.1.0",
        drift_status: "current",
        created_at: "2026-03-18T10:10:00Z",
        updated_at: "2026-03-18T10:12:00Z",
      },
      {
        managed_asset_id: `asset-seed-${index}-2`,
        product_id: `product-seed-${index}`,
        path: ".github/pull_request_template.md",
        kind: "file",
        management_mode: "managed",
        upstream_bundle_version: "0.1.0",
        drift_status: "current",
        created_at: "2026-03-18T10:10:00Z",
        updated_at: "2026-03-18T10:12:00Z",
      },
    ],
  };
}

function buildSeedBaseline(product: any) {
  return {
    product_id: product.product_id,
    org_id: product.org_id,
    product_key: product.key,
    product_name: product.name,
    product_status: product.status,
    baseline_channel: product.baseline_channel,
    standards_pack_key: product.standards_pack_key,
    standards_pack_version: product.standards_pack_version,
    agent_core_version: product.agent_core_version,
    setup_state: product.setup_state,
    setup_diagnostics: product.setup_diagnostics,
    drift_status: "current",
    managed_asset_counts: {
      current: product.managed_assets.length,
      "update-available": 0,
    },
    managed_assets: product.managed_assets,
    latest_run: null,
    last_config_refresh_at: product.last_config_refresh_at,
    last_accepted_config_at: product.last_accepted_config_at,
  };
}

function buildSeedJob(payload: any, index: number, product: ProductSummaryResponse | null): ProductSeedJobResponse {
  const repoSummary = buildSeedRepoSummary(payload, index);
  const projectSummary = buildSeedProjectSummary(payload, index);
  const dryRun = Boolean(payload.dry_run);
  return {
    seed_job_id: `seed-job-${index}`,
    org_id: payload.org_id,
    product_id: product?.product_id ?? null,
    requested_by: "local-dev",
    status: dryRun ? "DryRun" : "Succeeded",
    dry_run: dryRun,
    request_payload: deepClone(payload),
    progress_payload: [
      {
        step: "seed",
        status: "running",
        message: "Seed workflow started.",
        recorded_at: "2026-03-18T10:10:00Z",
      },
      {
        step: "github.repo",
        status: "completed",
        message: `Prepared repository ${repoSummary.owner}/${repoSummary.name}.`,
        recorded_at: "2026-03-18T10:11:00Z",
      },
      {
        step: "github.project",
        status: "completed",
        message: `Prepared project ${projectSummary.title} (#${projectSummary.number}).`,
        recorded_at: "2026-03-18T10:11:30Z",
      },
      {
        step: "seed",
        status: "completed",
        message: dryRun ? "Dry-run completed." : "Seed workflow completed.",
        recorded_at: "2026-03-18T10:12:00Z",
      },
    ],
    error_payload: [],
    audit_payload: [
      {
        step: "bundle.rendered",
        status: "succeeded",
        message: dryRun
          ? "Rendered approved baseline bundle for dry-run inspection."
          : "Applied the approved baseline bundle to the repository.",
        details: {
          rendered_file_count: 4,
          repository: `${repoSummary.owner}/${repoSummary.name}`,
        },
        recorded_at: "2026-03-18T10:11:45Z",
      },
    ],
    rendered_file_paths: [
      "README.md",
      "AGENTS.md",
      ".orcha/product.yaml",
      ".orcha/components.yaml",
    ],
    repo_summary: repoSummary,
    project_summary: projectSummary,
    setup_state: "ready",
    setup_diagnostics: [],
    started_at: "2026-03-18T10:10:00Z",
    finished_at: "2026-03-18T10:12:00Z",
    created_at: "2026-03-18T10:10:00Z",
    updated_at: "2026-03-18T10:12:00Z",
    product,
  };
}

function buildSeedJobSummary(job: ProductSeedJobResponse): ProductSeedJobSummaryResponse {
  return {
    seed_job_id: job.seed_job_id,
    product_id: job.product_id,
    requested_by: job.requested_by,
    status: job.status,
    dry_run: job.dry_run,
    setup_state: job.setup_state,
    started_at: job.started_at,
    finished_at: job.finished_at,
    created_at: job.created_at,
    updated_at: job.updated_at,
  };
}

function hasWriteLikePermission(value: string | null | undefined) {
  return value === "write" || value === "maintain" || value === "admin";
}

function buildManagedAssetCounts(managedAssets: any[]) {
  return managedAssets.reduce<Record<string, number>>((counts, asset) => {
    const key = asset.drift_status ?? "unknown";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

function buildStandardsRunSummary(run: any) {
  return {
    standards_upgrade_run_id: run.standards_upgrade_run_id,
    outcome_kind: run.outcome_kind,
    outcome_status: run.outcome_status,
    generated_pr_number: run.generated_pr_number ?? null,
    created_at: run.created_at,
    updated_at: run.updated_at,
  };
}

function buildStandardsEvaluationRun(productId: string, payload: any, index: number) {
  return {
    standards_upgrade_run_id: `run-${index}`,
    product_id: productId,
    repo_id: "repo-1",
    standards_pack_id: `pack-${index}`,
    source_bundle: `agent-core/${payload.pack_key}`,
    source_version: payload.version,
    outcome_kind: "upgrade-pr",
    outcome_status: "reviewable",
    generated_pr_number: payload.generated_pr_number ?? null,
    pr_title: `Refresh ${payload.pack_key} ${payload.version} for atlas`,
    pr_body: `Managed updates: \`.github/pull_request_template.md\`\nAdvisory drift: \`.github/workflows/orcha-standards.yml\``,
    summary_payload: {
      source_bundle: `agent-core/${payload.pack_key}`,
      pack_key: payload.pack_key,
      channel: payload.channel,
      version: payload.version,
      counts: {
        "update-file": 1,
        "advisory-drift": 1,
        noop: 1,
      },
      changed_paths: [".github/pull_request_template.md"],
      advisory_paths: [".github/workflows/orcha-standards.yml"],
      follow_up_count: 0,
    },
    created_at: `2026-03-18T14:0${index}:00Z`,
    updated_at: `2026-03-18T14:0${index}:00Z`,
    assets: [
      {
        standards_upgrade_asset_id: `run-${index}-asset-1`,
        standards_upgrade_run_id: `run-${index}`,
        path: ".github/pull_request_template.md",
        management_mode: "managed",
        action: "update-file",
        drift_status: "update-available",
        patch_text: "--- a/.github/pull_request_template.md\n+++ b/.github/pull_request_template.md\n@@ -1 +1 @@\n-old\n+new",
        detail: null,
        metadata_payload: {
          exists: true,
        },
        created_at: `2026-03-18T14:0${index}:00Z`,
        updated_at: `2026-03-18T14:0${index}:00Z`,
      },
      {
        standards_upgrade_asset_id: `run-${index}-asset-2`,
        standards_upgrade_run_id: `run-${index}`,
        path: ".github/workflows/orcha-standards.yml",
        management_mode: "advisory",
        action: "advisory-drift",
        drift_status: "advisory-drift",
        patch_text: "--- a/.github/workflows/orcha-standards.yml\n+++ b/.github/workflows/orcha-standards.yml\n@@ -1 +1 @@\n-old\n+new",
        detail: "Local file diverges from the adopted standards pack.",
        metadata_payload: {
          exists: true,
        },
        created_at: `2026-03-18T14:0${index}:00Z`,
        updated_at: `2026-03-18T14:0${index}:00Z`,
      },
      {
        standards_upgrade_asset_id: `run-${index}-asset-3`,
        standards_upgrade_run_id: `run-${index}`,
        path: "AGENTS.md",
        management_mode: "managed",
        action: "noop",
        drift_status: "current",
        patch_text: null,
        detail: null,
        metadata_payload: {
          exists: true,
        },
        created_at: `2026-03-18T14:0${index}:00Z`,
        updated_at: `2026-03-18T14:0${index}:00Z`,
      },
    ],
    follow_up_items: [],
  };
}

function findStandardsRun(standardsUpgradeRunId: string) {
  for (const runs of Object.values(state.standardsRuns)) {
    const run = runs.find((item) => item.standards_upgrade_run_id === standardsUpgradeRunId);
    if (run) {
      return run;
    }
  }
  return null;
}

function syncBaselineManagedAssets(productId: string) {
  const product = state.products.find((item) => item.product_id === productId);
  const baseline = state.baselines.find((item) => item.product_id === productId);
  if (!product || !baseline) {
    return;
  }
  baseline.managed_assets = deepClone(product.managed_assets);
  baseline.managed_asset_counts = buildManagedAssetCounts(baseline.managed_assets);
}

function applyStandardsRunOutcome(standardsUpgradeRunId: string, payload: any) {
  const run = findStandardsRun(standardsUpgradeRunId);
  if (!run) {
    return null;
  }

  if (payload.generated_pr_number) {
    run.generated_pr_number = payload.generated_pr_number;
  }
  run.outcome_status = payload.outcome_status;
  run.updated_at = "2026-03-18T14:30:00Z";
  run.follow_up_items = run.follow_up_items.map((item: any) => ({
    ...item,
    status: payload.outcome_status,
    updated_at: "2026-03-18T14:30:00Z",
  }));

  const product = state.products.find((item) => item.product_id === run.product_id);
  if (product) {
    product.managed_assets = product.managed_assets.map((asset: any) => {
      const runAsset = run.assets.find((item: any) => item.path === asset.path);
      if (!runAsset) {
        return asset;
      }
      let driftStatus = runAsset.drift_status;
      if (payload.outcome_status === "accepted") {
        if (["create-file", "update-file", "refresh-sections"].includes(runAsset.action)) {
          driftStatus = "current";
        } else if (runAsset.action === "advisory-drift") {
          driftStatus = "advisory-reviewed";
        }
      } else if (payload.outcome_status === "rejected") {
        driftStatus = "rejected";
      } else if (payload.outcome_status === "deferred") {
        driftStatus = "deferred";
      }
      return {
        ...asset,
        drift_status: driftStatus,
        last_pr_number: run.generated_pr_number ?? asset.last_pr_number ?? null,
        updated_at: "2026-03-18T14:30:00Z",
      };
    });
  }

  const baseline = state.baselines.find((item) => item.product_id === run.product_id);
  if (baseline) {
    baseline.latest_run = buildStandardsRunSummary(run);
  }
  syncBaselineManagedAssets(run.product_id);
  return run;
}

function buildAdoptionDiagnostics(payload: any) {
  const branchProtection = payload.repository?.branch_protection ?? {};
  const permissions = payload.repository?.permissions ?? {};
  const statusOptions = (payload.project?.status_options ?? []).map((value: unknown) =>
    String(value).trim().toLowerCase(),
  );
  const diagnostics = [];

  if (payload.repository?.is_archived) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "repository-archived",
      message: "Archived repositories cannot enter active adoption.",
      path: payload.repo_root,
    });
  }
  if (!branchProtection.enabled) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "default-branch-protection-disabled",
      message: "Default branch protection is disabled.",
      path: payload.repository?.default_branch,
    });
  }
  if (!branchProtection.requires_pull_request) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "default-branch-pr-required",
      message: "Pull requests are not required on the default branch.",
      path: payload.repository?.default_branch,
    });
  }
  if (Number(branchProtection.required_approving_review_count ?? 0) < 1) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "default-branch-approvals-missing",
      message: "At least one approving review is required on the default branch.",
      path: payload.repository?.default_branch,
    });
  }
  if (!hasWriteLikePermission(permissions.contents)) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "github-app-contents-write-missing",
      message: "GitHub contents permission does not include write access.",
      path: "permissions.contents",
    });
  }
  if (!hasWriteLikePermission(permissions.pull_requests)) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "github-app-pull-requests-write-missing",
      message: "GitHub pull request permission does not include write access.",
      path: "permissions.pull_requests",
    });
  }
  if (!hasWriteLikePermission(permissions.projects)) {
    diagnostics.push({
      classification: "blocking-setup",
      code: "github-app-projects-write-missing",
      message: "GitHub projects permission does not include write access.",
      path: "permissions.projects",
    });
  }

  if (branchProtection.allows_force_pushes) {
    diagnostics.push({
      classification: "recoverable-drift",
      code: "default-branch-force-pushes-allowed",
      message: "Force pushes are allowed on the default branch.",
      path: payload.repository?.default_branch,
    });
  }
  if (branchProtection.allows_deletions) {
    diagnostics.push({
      classification: "recoverable-drift",
      code: "default-branch-deletions-allowed",
      message: "Default branch deletions are allowed.",
      path: payload.repository?.default_branch,
    });
  }
  if (!statusOptions.includes("ready")) {
    diagnostics.push({
      classification: "advisory-warning",
      code: "project-ready-status-missing",
      message: "Project status options do not include Ready.",
      path: payload.project?.status_field_name,
    });
  }

  return diagnostics;
}

function buildAdoptionRepoSummary(payload: any, index: number, setupState: string) {
  const branchProtection = payload.repository?.branch_protection ?? {};
  const permissions = payload.repository?.permissions ?? {};
  return {
    repo_id: `repo-adopt-${index}`,
    github_repository_node_id: payload.repository?.github_repository_node_id ?? `R_adopt_${index}`,
    owner: payload.repository?.owner,
    name: payload.repository?.name,
    default_branch: payload.repository?.default_branch,
    visibility: payload.repository?.visibility ?? "private",
    description: payload.repository?.description ?? null,
    is_archived: Boolean(payload.repository?.is_archived),
    seed_source: null,
    adoption_state: setupState === "setup-needed" ? "setup-needed" : "adopted",
    raw_payload: {
      default_branch_protection: {
        enabled: Boolean(branchProtection.enabled),
        requires_pull_request: Boolean(branchProtection.requires_pull_request),
        required_approving_review_count: Number(branchProtection.required_approving_review_count ?? 0),
        allows_force_pushes: Boolean(branchProtection.allows_force_pushes),
        allows_deletions: Boolean(branchProtection.allows_deletions),
      },
      orcha_permissions: {
        contents: permissions.contents ?? "none",
        pull_requests: permissions.pull_requests ?? "none",
        issues: permissions.issues ?? "none",
        projects: permissions.projects ?? "none",
      },
    },
    created_at: "2026-03-18T12:00:00Z",
    updated_at: "2026-03-18T12:05:00Z",
  };
}

function buildAdoptionProjectSummary(payload: any, index: number) {
  return {
    project_id: `project-adopt-${index}`,
    github_project_node_id: payload.project?.github_project_node_id ?? `PVT_adopt_${index}`,
    number: payload.project?.number ?? index,
    title: payload.project?.title ?? payload.name,
    status_field_name: payload.project?.status_field_name ?? "Status",
    status_options: payload.project?.status_options ?? ["Todo", "In Progress", "Done"],
    raw_payload: {
      node_id: payload.project?.github_project_node_id ?? `PVT_adopt_${index}`,
      number: payload.project?.number ?? index,
      title: payload.project?.title ?? payload.name,
    },
    mirror_version: 1,
    created_at: "2026-03-18T12:00:00Z",
    updated_at: "2026-03-18T12:05:00Z",
  };
}

function buildAdoptionManagedAssets(productId: string, index: number) {
  return [
    {
      managed_asset_id: `asset-adopt-${index}-1`,
      product_id: productId,
      path: "AGENTS.md",
      kind: "file",
      management_mode: "managed",
      upstream_bundle_version: "0.1.0",
      drift_status: "current",
      created_at: "2026-03-18T12:00:00Z",
      updated_at: "2026-03-18T12:05:00Z",
    },
    {
      managed_asset_id: `asset-adopt-${index}-2`,
      product_id: productId,
      path: ".github/workflows/orcha-standards.yml",
      kind: "file",
      management_mode: "managed",
      upstream_bundle_version: "0.1.0",
      drift_status: "update-available",
      created_at: "2026-03-18T12:00:00Z",
      updated_at: "2026-03-18T12:05:00Z",
    },
  ];
}

function buildAdoptedProduct(payload: any, index: number, dryRun: boolean): ProductSummaryResponse {
  const diagnostics = buildAdoptionDiagnostics(payload);
  const setupState = diagnostics.some((diagnostic) => diagnostic.classification.includes("blocking"))
    ? "setup-needed"
    : "ready";
  const productId = `product-adopt-${index}`;
  const managedAssets = buildAdoptionManagedAssets(productId, index);

  return {
    product_id: productId,
    org_id: payload.org_id,
    key: payload.key,
    name: payload.name,
    description: payload.description ?? null,
    status: setupState === "setup-needed" ? "Draft" : "Active",
    baseline_channel: payload.baseline_channel ?? "stable",
    standards_pack_key: "default",
    standards_pack_version: "0.1.0",
    agent_core_version: payload.agent_core_version ?? "0.1.0",
    execution_profile: payload.execution_profile ?? "standard-python",
    component_root_node_id: `node-adopt-${index}`,
    manifest_schema_version: 1,
    setup_state: setupState,
    setup_diagnostics: diagnostics,
    effective_config: {},
    operator_overrides: payload.operator_overrides ?? {},
    last_config_refresh_at: "2026-03-18T12:05:00Z",
    last_accepted_config_at: dryRun ? null : "2026-03-18T12:05:00Z",
    created_at: "2026-03-18T12:00:00Z",
    updated_at: "2026-03-18T12:05:00Z",
    latest_seed_job: null,
    primary_repo: buildAdoptionRepoSummary(payload, index, setupState),
    primary_project: buildAdoptionProjectSummary(payload, index),
    managed_assets: managedAssets,
  };
}

function buildAdoptionBaseline(product: any) {
  const managedAssetCounts = buildManagedAssetCounts(product.managed_assets);
  const driftStatus = Object.entries(managedAssetCounts).some(([key, count]) => key !== "current" && count > 0)
    ? "drift"
    : "current";
  return {
    product_id: product.product_id,
    org_id: product.org_id,
    product_key: product.key,
    product_name: product.name,
    product_status: product.status,
    baseline_channel: product.baseline_channel,
    standards_pack_key: product.standards_pack_key,
    standards_pack_version: product.standards_pack_version,
    agent_core_version: product.agent_core_version,
    setup_state: product.setup_state,
    setup_diagnostics: product.setup_diagnostics,
    drift_status: driftStatus,
    managed_asset_counts: managedAssetCounts,
    managed_assets: product.managed_assets,
    latest_run: null,
    last_config_refresh_at: product.last_config_refresh_at,
    last_accepted_config_at: product.last_accepted_config_at,
  };
}

function applyProductRefresh(productId: string) {
  const product = state.products.find((item) => item.product_id === productId);
  if (!product) {
    return null;
  }

  product.setup_state = "ready";
  product.setup_diagnostics = [
    {
      classification: "advisory warning",
      code: "governance.approval_posture_capped",
      message: "Approval posture is capped by platform defaults.",
      path: ".orcha/product.yaml",
    },
  ];
  product.last_config_refresh_at = "2026-03-18T13:15:00Z";
  product.last_accepted_config_at = "2026-03-18T13:15:00Z";
  product.updated_at = "2026-03-18T13:15:00Z";

  const baseline = state.baselines.find((item) => item.product_id === productId);
  if (baseline) {
    baseline.setup_state = "ready";
    baseline.setup_diagnostics = deepClone(product.setup_diagnostics);
    baseline.last_config_refresh_at = product.last_config_refresh_at;
    baseline.last_accepted_config_at = product.last_accepted_config_at;
  }

  return product;
}

function buildLaneHeartbeatStatus(lane: any) {
  if (lane.finished_at || ["Cancelled", "FailedTerminal", "HandedOff"].includes(lane.state)) {
    return "terminal";
  }
  if (lane.state === "AwaitingApproval" || lane.state === "AwaitingGitHub") {
    return "waiting";
  }
  if (lane.lane_id === "lane-running") {
    return "stale";
  }
  if (lane.state === "Running") {
    return "healthy";
  }
  return "active";
}

function buildLaneSummaryText(lane: any) {
  if (lane.state === "AwaitingApproval") {
    return lane.agent_session?.wait_reason ?? "Waiting on operator approval.";
  }
  if (lane.state === "AwaitingGitHub") {
    return lane.agent_session?.wait_reason ?? "Waiting on human input.";
  }
  if (lane.lane_id === "lane-running") {
    return "Runner heartbeat has gone stale while work is still running.";
  }
  if (lane.state === "Running") {
    return "Runner is active with an attached workspace.";
  }
  if (lane.state === "FailedTerminal") {
    return lane.last_error ?? "Execution failed and may need a retry decision.";
  }
  return `Lane is ${lane.state}.`;
}

function buildObservabilityCorrelation(lane: any) {
  const product = state.products.find((item) => item.product_id === lane.product_id);
  return {
    org_id: product?.org_id ?? null,
    product_id: lane.product_id,
    repo_id: lane.repo_id,
    work_item_id: lane.work_item_id,
    lane_id: lane.lane_id,
    agent_session_id: lane.agent_session?.agent_session_id ?? null,
    delivery_id: null,
    github_delivery_guid: null,
    installation_id: "12345678",
  };
}

function buildLaneStatusSummary(lane: any) {
  return {
    lane_id: lane.lane_id,
    product_id: lane.product_id,
    work_item_id: lane.work_item_id,
    issue_number: lane.work_item.issue_number,
    title: lane.work_item.title,
    state: lane.state,
    attempt: lane.attempt,
    retry_due_at: lane.retry_due_at ?? null,
    heartbeat_status: buildLaneHeartbeatStatus(lane),
    summary: buildLaneSummaryText(lane),
    updated_at: lane.updated_at,
  };
}

function buildFleetObservabilityNotifications() {
  const notifications: any[] = [];

  for (const lane of state.lanes) {
    if (lane.state === "AwaitingApproval" || lane.state === "AwaitingGitHub") {
      notifications.push({
        notification_type: "blocked-lane",
        severity: "warning",
        title: "Lane is blocked awaiting operator action",
        summary: buildLaneSummaryText(lane),
        observed_at: lane.updated_at,
        target_kind: "lane",
        target_id: lane.lane_id,
        source_kind: "derived",
        correlation: buildObservabilityCorrelation(lane),
      });
    }
  }

  const staleLane = state.lanes.find((lane) => buildLaneHeartbeatStatus(lane) === "stale");
  if (staleLane) {
    notifications.push({
      notification_type: "heartbeat-degraded",
      severity: "error",
      title: "Runner heartbeat health is degraded",
      summary: "1 lane(s) have stale runner heartbeats.",
      observed_at: "2026-03-16T20:13:00Z",
      target_kind: "lane",
      target_id: staleLane.lane_id,
      source_kind: "derived",
      correlation: buildObservabilityCorrelation(staleLane),
    });
  }

  notifications.push({
    notification_type: "degraded-sync-health",
    severity: "error",
    title: "GitHub sync health is degraded",
    summary: "2 webhook deliveries are in the dead-letter backlog.",
    observed_at: "2026-03-16T20:13:00Z",
    target_kind: "webhook_delivery",
    target_id: "delivery-1",
    source_kind: "derived",
    correlation: {
      org_id: "org-1",
      product_id: "product-1",
      repo_id: "repo-1",
      work_item_id: "work-item-3",
      lane_id: "lane-running",
      agent_session_id: "session-2",
      delivery_id: "delivery-1",
      github_delivery_guid: "guid-1",
      installation_id: "12345678",
    },
  });

  return notifications;
}

function buildFleetObservability() {
  const notifications = buildFleetObservabilityNotifications();
  const laneStateCounts = state.lanes.reduce<Record<string, number>>((counts, lane) => {
    counts[lane.state] = (counts[lane.state] ?? 0) + 1;
    return counts;
  }, {});
  const activeLaneCount = state.lanes.filter(
    (lane) => !["Cancelled", "FailedTerminal", "HandedOff"].includes(lane.state) && !lane.finished_at,
  ).length;
  const staleHeartbeatCount = state.lanes.filter((lane) => buildLaneHeartbeatStatus(lane) === "stale").length;

  return {
    generated_at: "2026-03-18T15:00:00Z",
    queue_depth: activeLaneCount,
    active_lane_count: activeLaneCount,
    retry_backlog_count: 1,
    dead_letter_backlog_count: 2,
    mirror_lag_seconds: 420,
    stale_heartbeat_count: staleHeartbeatCount,
    lane_state_counts: laneStateCounts,
    notification_count: notifications.length,
    notifications,
    lanes: state.lanes.map((lane) => buildLaneStatusSummary(lane)),
  };
}

function buildLaneObservability(laneId: string) {
  const lane = state.lanes.find((item) => item.lane_id === laneId);
  if (!lane) {
    return null;
  }
  const correlation = buildObservabilityCorrelation(lane);
  const notifications = buildFleetObservabilityNotifications().filter(
    (notification) => notification.target_id === laneId || notification.correlation.lane_id === laneId,
  );
  const recentActivity = [
    lane.agent_session
      ? {
          kind: "session_event",
          event_type: lane.agent_session.last_event ?? "session_updated",
          summary: lane.agent_session.wait_reason ?? buildLaneSummaryText(lane),
          severity: lane.state === "FailedTerminal" ? "error" : "info",
          observed_at: lane.agent_session.last_event_at ?? lane.updated_at,
          source_kind: "runner",
          correlation,
          payload: {
            wait_reason: lane.agent_session.wait_reason,
            status: lane.agent_session.status,
          },
        }
      : null,
    {
      kind: "signal",
      event_type: "lane_state",
      summary: buildLaneSummaryText(lane),
      severity: buildLaneHeartbeatStatus(lane) === "stale" ? "warning" : "info",
      observed_at: lane.updated_at,
      source_kind: "control-plane",
      correlation,
      payload: {
        state: lane.state,
        attempt: lane.attempt,
      },
    },
  ].filter(Boolean);

  return {
    lane: deepClone(lane),
    correlation,
    heartbeat_status: buildLaneHeartbeatStatus(lane),
    summary: buildLaneSummaryText(lane),
    last_activity_at:
      lane.agent_session?.last_event_at ?? lane.execution_environment?.heartbeat_at ?? lane.updated_at,
    recent_activity: recentActivity,
    notifications,
    artifact_references: {
      workspace_uri: lane.execution_environment?.workspace_uri ?? null,
      artifact_uri: lane.execution_environment?.artifact_uri ?? null,
      log_uri: lane.execution_environment?.log_uri ?? null,
      cache_uri: lane.execution_environment?.cache_uri ?? null,
    },
  };
}

function json(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderApp(initialEntries: NonNullable<ComponentProps<typeof MemoryRouter>["initialEntries"]> = ["/"]) {
  return render(
    <ThemeProvider>
      <LocaleProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <App />
        </MemoryRouter>
      </LocaleProvider>
    </ThemeProvider>,
  );
}

function expectBreadcrumb(items: Array<{ label: string; href?: string }>) {
  const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
  items.forEach((item) => {
    if (item.href) {
      expect(within(breadcrumb).getByRole("link", { name: item.label })).toHaveAttribute("href", item.href);
      return;
    }
    expect(within(breadcrumb).getByText(item.label)).toBeInTheDocument();
  });
}

async function chooseConnectedRepo(
  repoId = "workspace-repo-1",
  optionName = "aegroup-io/atlas • Private • dev",
) {
  await waitFor(() => {
    expect(screen.getByRole("option", { name: optionName })).toBeInTheDocument();
  });
  fireEvent.change(screen.getByLabelText("Connected repository"), {
    target: { value: repoId },
  });
}

async function addRequiredSecret(
  secretKey = "AZURE_OPENAI_API_KEY",
  optionName = "Azure OpenAI Key • AZURE_OPENAI_API_KEY • Missing value",
) {
  await waitFor(() => {
    expect(screen.getByRole("option", { name: optionName })).toBeInTheDocument();
  });
  fireEvent.change(screen.getByLabelText("Add required secret"), {
    target: { value: secretKey },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add secret" }));
}

let state: ReturnType<typeof createFixtureState>;

describe("App", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_AUTH_DISABLED", "1");
    vi.stubEnv("VITE_API_BASE_URL", "http://127.0.0.1:7100");

    state = createFixtureState();

    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const path = url.pathname;
        const method = init?.method ?? "GET";

        if (path === "/me" && method === "GET") {
          return json(state.me);
        }
        if (path === "/v1/products" && method === "GET") {
          return json(state.products);
        }
        if (path === "/v1/lanes" && method === "GET") {
          return json(state.lanes);
        }
        if (path === "/v1/baselines" && method === "GET") {
          return json(state.baselines);
        }
        if (path === "/v1/observability/summary" && method === "GET") {
          return json(buildFleetObservability());
        }
        if (/^\/v1\/observability\/lanes\/[^/]+$/.test(path) && method === "GET") {
          const laneId = decodeURIComponent(path.split("/").pop() ?? "");
          const detail = buildLaneObservability(laneId);
          return detail ? json(detail) : Promise.resolve(new Response("Not found", { status: 404 }));
        }
        if (/^\/products\/[^/]+\/standards\/runs$/.test(path) && method === "GET") {
          const productId = decodeURIComponent(path.split("/")[2] ?? "");
          return json(state.standardsRuns[productId] ?? []);
        }
        if (/^\/products\/[^/]+\/standards\/evaluations$/.test(path) && method === "POST") {
          const productId = decodeURIComponent(path.split("/")[2] ?? "");
          const payload = JSON.parse(String(init?.body ?? "{}"));
          state.nextStandardsRunIndex += 1;
          const run = buildStandardsEvaluationRun(productId, payload, state.nextStandardsRunIndex);
          state.standardsRuns[productId] = [run, ...(state.standardsRuns[productId] ?? [])];

          const product = state.products.find((item) => item.product_id === productId);
          if (product) {
            product.baseline_channel = payload.channel;
            product.standards_pack_key = payload.pack_key;
            product.standards_pack_version = payload.version;
            product.managed_assets = product.managed_assets.map((asset: any) => {
              const runAsset = run.assets.find((item: any) => item.path === asset.path);
              return runAsset
                ? {
                    ...asset,
                    drift_status: runAsset.drift_status,
                    last_pr_number: run.generated_pr_number ?? asset.last_pr_number ?? null,
                    updated_at: run.updated_at,
                  }
                : asset;
            });
          }

          const baseline = state.baselines.find((item) => item.product_id === productId);
          if (baseline) {
            baseline.baseline_channel = payload.channel;
            baseline.standards_pack_key = payload.pack_key;
            baseline.standards_pack_version = payload.version;
            baseline.latest_run = buildStandardsRunSummary(run);
          }
          syncBaselineManagedAssets(productId);
          return json(run, 201);
        }
        if (/^\/standards\/runs\/[^/]+\/outcome$/.test(path) && method === "POST") {
          const standardsUpgradeRunId = decodeURIComponent(path.split("/")[3] ?? "");
          const payload = JSON.parse(String(init?.body ?? "{}"));
          const run = applyStandardsRunOutcome(standardsUpgradeRunId, payload);
          return run ? json(run, 201) : Promise.resolve(new Response("Not found", { status: 404 }));
        }
        if (path === "/orgs" && method === "GET") {
          return json(state.organizations);
        }
        if (path === "/platform/summary" && method === "GET") {
          return json({
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
          });
        }
        if (path === "/ai/providers" && method === "GET") {
          return json([]);
        }
        if (path === "/ai/models" && method === "GET") {
          return json([]);
        }
        if (path === "/ai/agents" && method === "GET") {
          return json([]);
        }
        if (path === "/rbac/roles" && method === "GET") {
          return json([]);
        }
        if (path === "/rbac/permissions" && method === "GET") {
          return json([]);
        }
        if (path === "/rbac/feature-flags" && method === "GET") {
          return json([]);
        }
        if (path === "/secrets" && method === "GET") {
          return json(state.secrets);
        }
        if (path === "/secrets" && method === "POST") {
          const payload = JSON.parse(String(init?.body ?? "{}"));
          const secret = {
            secret_id: `secret-${state.secrets.length + 1}`,
            key: payload.key,
            name: payload.name,
            kind: payload.kind,
            description: payload.description ?? null,
            has_value: true,
            created_at: "2026-03-19T09:00:00Z",
            updated_at: "2026-03-19T09:00:00Z",
            last_rotated_at: "2026-03-19T09:00:00Z",
          };
          state.secrets = [...state.secrets, secret];
          return json(secret, 201);
        }
        if (path === "/settings" && method === "GET") {
          const scopeType = url.searchParams.get("scope_type") ?? "user";
          const scopeId = url.searchParams.get("scope_id") ?? (scopeType === "user" ? state.me.user_id : "");
          return json(deepClone(state.settingsByScope[scopeType]?.[scopeId] ?? []));
        }
        if (/^\/settings\/(platform|org|user)\/[^/]+\/[^/]+$/.test(path) && method === "PUT") {
          const [, , scopeType, encodedScopeId, encodedKey] = path.split("/");
          const scopeId = decodeURIComponent(encodedScopeId ?? "");
          const key = decodeURIComponent(encodedKey ?? "");
          const payload = JSON.parse(String(init?.body ?? "{}"));
          const settingsByScope = state.settingsByScope[scopeType] ?? {};
          const existingSettings = settingsByScope[scopeId] ?? [];
          const existingSetting = existingSettings.find((item: any) => item.key === key) ?? null;
          const nextSetting = {
            setting_id:
              existingSetting?.setting_id ??
              `setting-${scopeType}-${scopeId}-${existingSettings.length + 1}`,
            scope_type: scopeType,
            scope_id: scopeId,
            key,
            value_json: payload.value,
            created_by: existingSetting?.created_by ?? state.me.user_id,
            updated_by: state.me.user_id,
            created_at: existingSetting?.created_at ?? "2026-03-18T16:00:00Z",
            updated_at: "2026-03-18T16:00:00Z",
          };
          state.settingsByScope[scopeType] = settingsByScope;
          state.settingsByScope[scopeType][scopeId] = [
            ...existingSettings.filter((item: any) => item.key !== key),
            deepClone(nextSetting),
          ];
          return json(nextSetting);
        }
        if (/^\/orgs\/[^/]+\/repos$/.test(path) && method === "GET") {
          const orgId = decodeURIComponent(path.split("/")[2] ?? "");
          const query = (url.searchParams.get("q") ?? "").trim().toLowerCase();
          const repos = state.workspaceRepos.filter((repo: any) => {
            if (!repo.org_ids.includes(orgId)) {
              return false;
            }
            if (!query) {
              return true;
            }
            return [
              repo.key,
              repo.name,
              repo.github_owner,
              repo.github_repo,
            ].some((value) => String(value).toLowerCase().includes(query));
          });
          return json(deepClone(repos));
        }
        if (/^\/orgs\/[^/]+\/repos$/.test(path) && method === "POST") {
          const orgId = decodeURIComponent(path.split("/")[2] ?? "");
          const payload = JSON.parse(String(init?.body ?? "{}"));
          const existing = state.workspaceRepos.find(
            (repo: any) =>
              repo.github_owner === payload.github_owner &&
              repo.github_repo === payload.github_repo,
          );
          if (existing) {
            const nextOrgIds = Array.from(new Set([...(existing.org_ids ?? []), ...payload.org_ids, orgId]));
            existing.org_ids = nextOrgIds;
            existing.visibility = payload.visibility ?? existing.visibility ?? "private";
            existing.org_mappings = nextOrgIds.map((mappedOrgId) => {
              const organization = state.organizations.find((org: any) => org.org_id === mappedOrgId);
              const prior = existing.org_mappings.find((mapping: any) => mapping.org_id === mappedOrgId);
              return {
                org_id: mappedOrgId,
                org_name: organization?.name ?? prior?.org_name ?? mappedOrgId,
                active_product_count: prior?.active_product_count ?? 0,
              };
            });
            existing.updated_at = "2026-03-19T09:15:00Z";
            return json(deepClone(existing), 201);
          }
          const repo = {
            repo_id: `workspace-repo-${state.workspaceRepos.length + 1}`,
            org_id: orgId,
            key: payload.key,
            name: payload.name,
            provider: "github",
            github_owner: payload.github_owner,
            github_repo: payload.github_repo,
            visibility: payload.visibility ?? "private",
            default_branch: payload.default_branch,
            clone_url: `https://github.com/${payload.github_owner}/${payload.github_repo}.git`,
            git_auth_secret_id: payload.git_auth_secret_id,
            org_ids: Array.from(new Set([...(payload.org_ids ?? []), orgId])),
            org_mappings: Array.from(new Set([...(payload.org_ids ?? []), orgId])).map((mappedOrgId) => {
              const organization = state.organizations.find((org: any) => org.org_id === mappedOrgId);
              return {
                org_id: mappedOrgId,
                org_name: organization?.name ?? mappedOrgId,
                active_product_count: 0,
              };
            }),
            archived_at: null,
            created_at: "2026-03-19T09:10:00Z",
            updated_at: "2026-03-19T09:10:00Z",
          };
          state.workspaceRepos = [...state.workspaceRepos, repo];
          return json(deepClone(repo), 201);
        }
        if (/^\/repos\/[^/]+$/.test(path) && method === "PATCH") {
          const repoId = decodeURIComponent(path.split("/")[2] ?? "");
          const payload = JSON.parse(String(init?.body ?? "{}"));
          const repo = state.workspaceRepos.find((item: any) => item.repo_id === repoId);
          if (!repo) {
            return Promise.resolve(new Response("Not found", { status: 404 }));
          }
          if (payload.org_ids) {
            repo.org_ids = [...payload.org_ids];
            repo.org_mappings = payload.org_ids.map((mappedOrgId: string) => {
              const organization = state.organizations.find((org: any) => org.org_id === mappedOrgId);
              const prior = repo.org_mappings.find((mapping: any) => mapping.org_id === mappedOrgId);
              return {
                org_id: mappedOrgId,
                org_name: organization?.name ?? prior?.org_name ?? mappedOrgId,
                active_product_count: prior?.active_product_count ?? 0,
              };
            });
          }
          repo.updated_at = "2026-03-19T09:20:00Z";
          return json(deepClone(repo));
        }
        if (/^\/repos\/[^/]+$/.test(path) && method === "DELETE") {
          const repoId = decodeURIComponent(path.split("/")[2] ?? "");
          const repo = state.workspaceRepos.find((item: any) => item.repo_id === repoId);
          if (!repo) {
            return Promise.resolve(new Response("Not found", { status: 404 }));
          }
          if (repo.org_mappings.some((mapping: any) => mapping.active_product_count > 0)) {
            return Promise.resolve(
              new Response(
                JSON.stringify({
                  detail: {
                    message: "Repo has active products",
                  },
                }),
                { status: 409, headers: { "Content-Type": "application/json" } },
              ),
            );
          }
          state.workspaceRepos = state.workspaceRepos.filter((item: any) => item.repo_id !== repoId);
          return Promise.resolve(new Response(null, { status: 204 }));
        }
        if (/^\/orgs\/[^/]+\/github\/repos\/lookup$/.test(path) && method === "POST") {
          return json([
            {
              github_owner: "aegroup-io",
              github_repo: "apollo",
              full_name: "aegroup-io/apollo",
              visibility: "private",
              is_private: true,
              is_archived: false,
              default_branch: "dev",
              permissions: {
                pull: true,
                push: true,
                admin: false,
              },
            },
          ]);
        }
        if (/^\/orgs\/[^/]+\/github\/repos\/branches$/.test(path) && method === "POST") {
          return json([
            {
              name: "dev",
              head_sha: "abc123",
              is_default: true,
            },
            {
              name: "main",
              head_sha: "def456",
              is_default: false,
            },
          ]);
        }
        if (path === "/products/seed" && method === "POST") {
          const payload = JSON.parse(String(init?.body ?? "{}"));
          if (!state.organizations.some((org: any) => org.org_id === payload.org_id)) {
            return Promise.resolve(
              new Response(JSON.stringify({ detail: `Organization not found: ${payload.org_id}` }), {
                status: 404,
                headers: { "Content-Type": "application/json" },
              }),
            );
          }
          state.nextSeedIndex += 1;
          const index = state.nextSeedIndex;
          const repoSummary = buildSeedRepoSummary(payload, index);
          const projectSummary = buildSeedProjectSummary(payload, index);
          const product = payload.dry_run ? null : buildSeededProduct(payload, repoSummary, projectSummary, index);
          const job = buildSeedJob(payload, index, product);
          if (product) {
            product.latest_seed_job = buildSeedJobSummary(job);
            state.products = [...state.products, product];
            state.baselines = [...state.baselines, buildSeedBaseline(product)];
          }
          state.seedJobs[job.seed_job_id] = deepClone(job);
          return json(job, 201);
        }
        if (path.startsWith("/products/seed-jobs/") && method === "GET") {
          const seedJobId = decodeURIComponent(path.split("/").pop() ?? "");
          const job = state.seedJobs[seedJobId];
          return job ? json(job) : Promise.resolve(new Response("Not found", { status: 404 }));
        }
        if (path === "/products/adoptions/dry-run" && method === "POST") {
          const payload = JSON.parse(String(init?.body ?? "{}"));
          state.nextAdoptionIndex += 1;
          const product = buildAdoptedProduct(payload, state.nextAdoptionIndex, true);
          return json({ dry_run: true, product }, 201);
        }
        if (path === "/products/adoptions" && method === "POST") {
          const payload = JSON.parse(String(init?.body ?? "{}"));
          state.nextAdoptionIndex += 1;
          const product = buildAdoptedProduct(payload, state.nextAdoptionIndex, false);
          state.products = [...state.products, product];
          state.baselines = [...state.baselines, buildAdoptionBaseline(product)];
          return json({ dry_run: false, product }, 201);
        }
        if (path === "/v1/graph/products/product-1" && method === "GET") {
          return json(state.graph);
        }
        if (path === "/v1/products/product-1/pause" && method === "POST") {
          state.products[0].status = "Paused";
          return json(state.products[0]);
        }
        if (path === "/v1/products/product-1/refresh" && method === "POST") {
          const product = applyProductRefresh("product-1");
          return product ? json(product) : Promise.resolve(new Response("Not found", { status: 404 }));
        }
        if (path === "/v1/lanes/lane-approval/approve" && method === "POST") {
          state.lanes[0].state = "Running";
          state.lanes[0].agent_session.status = "running";
          state.lanes[0].agent_session.wait_reason = null;
          state.lanes[0].agent_session.last_event = "operator_approved";
          return json(state.lanes[0]);
        }
        return Promise.resolve(new Response("Not found", { status: 404 }));
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("renders the Orcha fleet shell instead of the starter AI registry pages", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Operator-ready control plane")).toBeInTheDocument();
    });

    expect(screen.getByAltText("Orcha")).toHaveAttribute("src", "/logo-light.svg");
    expect(screen.getByRole("button", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fleet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Baselines" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Some More" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Help" })).toBeInTheDocument();
    expect(screen.getByText("aegroup-io/atlas")).toBeInTheDocument();
    expect(screen.queryByText("AI Models")).not.toBeInTheDocument();
    expect(screen.queryByText("Organizations")).not.toBeInTheDocument();
    expect(screen.queryByText("System Configuration")).not.toBeInTheDocument();
  });

  it("renders the exact shared settings workspace used by tyler-test", async () => {
    renderApp(["/settings/orgs"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Organizations" })).toBeInTheDocument();
    });

    expect(screen.getByAltText("Orcha")).toHaveAttribute("src", "/logo-light.svg");
    expect(screen.getByRole("button", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fleet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Baselines" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Some More" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("System Configuration")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search organizations...")).toBeInTheDocument();
    expect(screen.getByText("Secrets")).toBeInTheDocument();
    expect(screen.getByText("AI Models")).toBeInTheDocument();
    expect(screen.getByText("Git Repositories")).toBeInTheDocument();
    expect(screen.queryByText("Operator control plane")).not.toBeInTheDocument();
    expect(screen.queryByText("Connections")).not.toBeInTheDocument();
    expect(screen.queryByText("Environments")).not.toBeInTheDocument();
    expect(screen.queryByText("Catalogs")).not.toBeInTheDocument();
  });

  it("renders the Git Repositories settings page with org-scoped mappings", async () => {
    renderApp(["/settings/git-repos"]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Add Repository" })).toBeInTheDocument();
    });

    expect(screen.getByRole("heading", { name: "Git Repositories" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Repository" })).toBeInTheDocument();
    expect(screen.getByText("Connected repositories")).toBeInTheDocument();
    expect(
      screen.getByText((_, node) => node?.textContent?.replace(/\s+/g, " ").trim() === "aegroup-io/atlas"),
    ).toBeInTheDocument();
    expect(screen.getByText("Orgs: Primary")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Git Repositories" })).toHaveAttribute("href", "/settings/git-repos");
  });

  it("renders Some More with Barrick and Ford 1-year charts", async () => {
    renderApp(["/some-more/ford"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "1 year stock charts" })).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "Barrick B" })).toHaveAttribute("href", "/some-more/barrick");
    expect(screen.getByRole("link", { name: "Ford F" })).toHaveAttribute("href", "/some-more/ford");
    expect(screen.getByTitle("Barrick Gold 1 year stock chart")).toBeInTheDocument();
    expect(screen.getByTitle("Ford Motor Co. 1 year stock chart")).toBeInTheDocument();
  });

  it("requires organization context before rendering repository settings actions", async () => {
    state.organizations = [];
    state.me.org_ids = [];
    state.me.default_org_id = null;

    renderApp(["/settings/git-repos"]);

    await waitFor(() => {
      expect(screen.getByText("Select an organization")).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        "Use the shared settings header to choose the organization that should own or review the current repository mappings.",
      ),
    ).toBeInTheDocument();
  });

  it("renders the shared AI models settings page instead of a local placeholder", async () => {
    renderApp(["/settings/models"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "AI Models" })).toBeInTheDocument();
    });

    expect(
      screen.getByText("Manage AI providers and the models available for each provider."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Provider" })).toBeInTheDocument();
  });

  it("keeps Products as the onboarding home with explicit seed and adoption entrypoints", async () => {
    renderApp(["/products"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Seed, adopt, and operate products" })).toBeInTheDocument();
    });

    expect(screen.getAllByRole("link", { name: "Seed a product" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Adopt a repo" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open seed flow" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open adoption flow" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Resume onboarding work")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Open adoption result").length).toBeGreaterThan(0);
  });

  it("renders the guided seed-product flow with onboarding defaults", async () => {
    renderApp(["/products/seed"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Seed a new product" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Seed request" },
    ]);
    expect(screen.getByRole("button", { name: "Run dry-run preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit live seed" })).toBeInTheDocument();
    expect(screen.getByLabelText("Connected repository")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "aegroup-io/atlas • Private • dev" })).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue("Status")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Todo")).toBeInTheDocument();
    expect(screen.getByText("GitHub auth source")).toBeInTheDocument();
    expect(screen.getByText("Settings > Git Repositories")).toBeInTheDocument();
    expect(screen.getByText("Seed summary")).toBeInTheDocument();
  });

  it("prepopulates seed, adoption, and remediation routes from saved workspace defaults", async () => {
    state.settingsByScope.org["org-1"] = [
      buildWorkspaceDefaultsSetting({
        github: {
          installation_id: "87654321",
          installation_label: "Production GitHub App",
          status_field: "Delivery Status",
          ready_status: "Ready",
          done_status: "Shipped",
        },
        baseline: {
          channel: "candidate",
        },
        execution: {
          profile: "standard-python",
        },
        activation: {
          required_secret_keys: ["ORCHA_GITHUB_APP_PRIVATE_KEY", "AZURE_OPENAI_API_KEY"],
        },
      }),
    ];

    renderApp(["/products/seed"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Seed a new product" })).toBeInTheDocument();
    });

    expect(screen.queryByLabelText("Installation id")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Status field")).toHaveValue("Delivery Status");
    expect(screen.getByLabelText("Ready status")).toHaveValue("Ready");
    expect(screen.getByLabelText("Done status")).toHaveValue("Shipped");
    expect(screen.getByLabelText("Baseline preset")).toHaveValue("candidate");
    expect(screen.getByText("GitHub auth source")).toBeInTheDocument();
    expect(screen.getByText("Settings > Git Repositories")).toBeInTheDocument();

    cleanup();

    renderApp(["/products/adopt"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Adopt an existing repo" })).toBeInTheDocument();
    });

    expect(screen.getByLabelText("Status field")).toHaveValue("Delivery Status");
    expect(screen.getByLabelText("Status options")).toHaveValue("Ready, In Progress, Shipped");
    expect(screen.getByLabelText("Baseline preset")).toHaveValue("candidate");
    expect(screen.getByText("GitHub auth source")).toBeInTheDocument();

    cleanup();

    renderApp(["/products/product-1"]);

    await waitFor(() => {
      expect(screen.getByText("Workspace defaults")).toBeInTheDocument();
    });

    expect(screen.getByText("GitHub auth source")).toBeInTheDocument();
    expect(screen.getByText("Settings > Git Repositories")).toBeInTheDocument();
    expect(screen.getByText("Delivery Status • Ready, In Progress, Shipped")).toBeInTheDocument();
    expect(screen.getByText("candidate • standard-python")).toBeInTheDocument();
    expect(screen.getByText("ORCHA_GITHUB_APP_PRIVATE_KEY, AZURE_OPENAI_API_KEY")).toBeInTheDocument();
    expect(screen.getByText("platform-admin")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review workspace defaults" })).toBeInTheDocument();
  });

  it("renders the guided adoption flow with product-safe defaults", async () => {
    renderApp(["/products/adopt"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Adopt an existing repo" })).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Run dry-run adoption" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue("aegroup-io")).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue("dev")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Status")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Todo, In Progress, Done")).toBeInTheDocument();
    expect(screen.getByText("Adoption summary")).toBeInTheDocument();
  });

  it("routes a dry-run adoption into the review surface with blockers, drift, and advisory diagnostics", async () => {
    renderApp(["/products/adopt"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Adopt an existing repo" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Local repo root"), {
      target: { value: "/Users/tyler/Git/aegroup/nimbus" },
    });
    fireEvent.change(screen.getByLabelText("Repository name"), {
      target: { value: "nimbus" },
    });
    fireEvent.change(screen.getByLabelText("Protection enabled"), {
      target: { value: "false" },
    });
    fireEvent.change(screen.getByLabelText("Force pushes allowed"), {
      target: { value: "true" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run dry-run adoption" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review adoption preview" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Adoption request", href: "/products/adopt" },
      { label: "Preview" },
    ]);
    expect(screen.getByText("Compatibility results")).toBeInTheDocument();
    expect(screen.getByText("Default branch protection is disabled.")).toBeInTheDocument();
    expect(screen.getByText("Force pushes are allowed on the default branch.")).toBeInTheDocument();
    expect(screen.getByText("Project status options do not include Ready.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adopt and keep blockers visible" })).toBeInTheDocument();
  });

  it("promotes an adoption preview into the live result surface and keeps blockers explicit", async () => {
    renderApp(["/products/adopt"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Adopt an existing repo" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Local repo root"), {
      target: { value: "/Users/tyler/Git/aegroup/nimbus" },
    });
    fireEvent.change(screen.getByLabelText("Repository name"), {
      target: { value: "nimbus" },
    });
    fireEvent.change(screen.getByLabelText("Protection enabled"), {
      target: { value: "false" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run dry-run adoption" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review adoption preview" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Adopt and keep blockers visible" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review onboarding result" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Nimbus", href: "/products/product-adopt-2" },
      { label: "Adoption result" },
    ]);
    expect(screen.getByRole("link", { name: "Open product blockers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review baselines" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rerun contract refresh" })).toBeInTheDocument();
    expect(screen.getByText("GitHub posture snapshot")).toBeInTheDocument();
  });

  it("routes a dry-run preview into the dedicated seed-job surface", async () => {
    renderApp(["/products/seed"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Seed a new product" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Product name"), { target: { value: "Nimbus" } });
    await chooseConnectedRepo();
    fireEvent.click(screen.getByRole("button", { name: "Run dry-run preview" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review seed preview" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Seed request", href: "/products/seed" },
      { label: "Preview" },
    ]);
    expect(screen.getByRole("button", { name: "Run live seed" })).toHaveClass("w-full", "sm:w-[200px]");
    expect(screen.getByRole("button", { name: "Edit seed request" })).toHaveClass("w-full", "sm:w-[200px]");
    expect(screen.getByText("GitHub target shape")).toBeInTheDocument();
    expect(screen.getByText("Rendered bundle")).toBeInTheDocument();
  });

  it("blocks live seed attempts with explicit secret guidance", async () => {
    renderApp(["/products/seed"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Seed a new product" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Product name"), { target: { value: "Nimbus" } });
    await chooseConnectedRepo();
    await addRequiredSecret();
    fireEvent.click(screen.getByRole("button", { name: "Submit live seed" }));

    await waitFor(() => {
      expect(screen.getByText("Fix the highlighted seed inputs before continuing.")).toBeInTheDocument();
    });

    expect(
      screen.getAllByText("Required secret is missing or has no value: AZURE_OPENAI_API_KEY.").length,
    ).toBeGreaterThan(0);
  });

  it("promotes a dry-run preview into the live onboarding result surface", async () => {
    renderApp(["/products/seed"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Seed a new product" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Product name"), { target: { value: "Nimbus" } });
    await chooseConnectedRepo();
    fireEvent.click(screen.getByRole("button", { name: "Run dry-run preview" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review seed preview" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Run live seed" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review onboarding result" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Nimbus", href: "/products/product-seed-2" },
      { label: "Seed result" },
    ]);
    expect(screen.getByRole("link", { name: "Open product" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review baselines" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rerun contract refresh" })).toHaveClass("w-full", "max-w-[200px]", "justify-start");
    expect(screen.getByText("Onboarding summary")).toBeInTheDocument();
  });

  it("rehydrates a legacy installation id from workspace defaults when promoting a preview job", async () => {
    state.settingsByScope.org["org-1"] = [
      buildWorkspaceDefaultsSetting({
        github: {
          installation_id: "87654321",
          installation_label: "Production GitHub App",
          status_field: "Status",
          ready_status: "Todo",
          done_status: "Done",
        },
        baseline: {
          channel: "stable",
        },
        execution: {
          profile: "standard-python",
        },
        activation: {
          required_secret_keys: [],
        },
      }),
    ];

    const previewPayload = {
      org_id: "org-1",
      installation_id: null,
      product_key: "nimbus",
      product_name: "Nimbus",
      description: "Seeded service",
      github_owner: "aegroup-io",
      github_repo: "nimbus",
      github_visibility: "private",
      github_default_branch: "dev",
      github_project_node_id: null,
      github_project_number: null,
      github_project_title: "Nimbus",
      status_field: "Status",
      ready_status: "Todo",
      done_status: "Done",
      baseline_channel: "stable",
      standards_pack: "default",
      execution_profile: "standard-python",
      max_concurrent_lanes: 4,
      required_secret_keys: [],
      dry_run: true,
    };
    const previewJob = buildSeedJob(previewPayload, 60, null);
    state.seedJobs[previewJob.seed_job_id] = deepClone(previewJob);

    renderApp([`/products/seed/jobs/${previewJob.seed_job_id}`]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review seed preview" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Run live seed" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review onboarding result" })).toBeInTheDocument();
    });

    const promotedJob = Object.values(state.seedJobs).find(
      (job: any) => !job.dry_run && job.request_payload.product_key === "nimbus",
    );
    expect(promotedJob?.request_payload.installation_id).toBe("87654321");
  });

  it("blocks live seed promotion when the preview org no longer exists", async () => {
    const previewPayload = {
      org_id: "org-missing",
      installation_id: "12345678",
      product_key: "nimbus",
      product_name: "Nimbus",
      description: "Seeded service",
      github_owner: "aegroup-io",
      github_repo: "nimbus",
      github_visibility: "private",
      github_default_branch: "dev",
      github_project_node_id: null,
      github_project_number: null,
      github_project_title: "Nimbus",
      status_field: "Status",
      ready_status: "Todo",
      done_status: "Done",
      baseline_channel: "stable",
      standards_pack: "default",
      execution_profile: "standard-python",
      max_concurrent_lanes: 4,
      required_secret_keys: [],
      dry_run: true,
    };
    const previewJob = buildSeedJob(previewPayload, 61, null);
    state.seedJobs[previewJob.seed_job_id] = deepClone(previewJob);

    renderApp([`/products/seed/jobs/${previewJob.seed_job_id}`]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review seed preview" })).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        "This preview targets an organization that no longer exists in the current local environment. Open Edit seed request, choose an active org, and create a new dry-run preview before promoting it to live.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run live seed" })).toBeDisabled();
  });

  it("revalidates cached preview routes before allowing live seed promotion", async () => {
    const previewPayload = {
      org_id: "org-1",
      installation_id: "12345678",
      product_key: "nimbus",
      product_name: "Nimbus",
      description: "Seeded service",
      github_owner: "aegroup-io",
      github_repo: "nimbus",
      github_visibility: "private",
      github_default_branch: "dev",
      github_project_node_id: null,
      github_project_number: null,
      github_project_title: "Nimbus",
      status_field: "Status",
      ready_status: "Todo",
      done_status: "Done",
      baseline_channel: "stable",
      standards_pack: "default",
      execution_profile: "standard-python",
      max_concurrent_lanes: 4,
      required_secret_keys: [],
      dry_run: true,
    };
    const previewJob = buildSeedJob(previewPayload, 62, null);

    renderApp([
      {
        pathname: `/products/seed/jobs/${previewJob.seed_job_id}`,
        state: {
          seedJob: previewJob,
        },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review seed preview" })).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("The job surface is showing the last known payload")).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        "This preview could not be reloaded from the API. Recreate the dry-run preview before promoting it to a live seed.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run live seed" })).toBeDisabled();
  });

  it("loads a running seed job directly from its durable route", async () => {
    const payload = {
      org_id: "org-1",
      installation_id: "12345678",
      product_key: "nimbus",
      product_name: "Nimbus",
      description: "Seeded service",
      github_owner: "aegroup-io",
      github_repo: "nimbus",
      github_visibility: "private",
      github_default_branch: "dev",
      github_project_node_id: null,
      github_project_number: null,
      github_project_title: "Nimbus",
      status_field: "Status",
      ready_status: "Todo",
      done_status: "Done",
      baseline_channel: "stable",
      standards_pack: "default",
      execution_profile: "standard-python",
      max_concurrent_lanes: 4,
      required_secret_keys: [],
      dry_run: false,
    };
    const runningJob = buildSeedJob(payload, 40, null);
    runningJob.status = "Running";
    runningJob.finished_at = null;
    runningJob.updated_at = "2026-03-18T10:11:00Z";
    runningJob.progress_payload = runningJob.progress_payload.slice(0, 2);
    state.seedJobs[runningJob.seed_job_id] = deepClone(runningJob);

    renderApp([`/products/seed/jobs/${runningJob.seed_job_id}`]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review onboarding result" })).toBeInTheDocument();
    });

    expect(screen.getByText("Progress and audit trail")).toBeInTheDocument();
    expect(screen.getByText("Seed workflow started.")).toBeInTheDocument();
    expect(screen.getByText("Prepared repository aegroup-io/nimbus.")).toBeInTheDocument();
  });

  it("loads a failed seed job directly from its durable route and keeps errors visible", async () => {
    const payload = {
      org_id: "org-1",
      installation_id: "12345678",
      product_key: "badger",
      product_name: "Badger",
      description: "Broken seed",
      github_owner: "aegroup-io",
      github_repo: "badger",
      github_visibility: "private",
      github_default_branch: "dev",
      github_project_node_id: null,
      github_project_number: null,
      github_project_title: "Badger",
      status_field: "Status",
      ready_status: "Todo",
      done_status: "Done",
      baseline_channel: "stable",
      standards_pack: "default",
      execution_profile: "standard-python",
      max_concurrent_lanes: 4,
      required_secret_keys: [],
      dry_run: false,
    };
    const failedJob = buildSeedJob(payload, 41, null);
    failedJob.status = "Failed";
    failedJob.setup_state = "setup-needed";
    failedJob.error_payload = [
      {
        code: "seed.failed",
        message: "GitHub project creation failed.",
        recorded_at: "2026-03-18T10:11:45Z",
      },
    ];
    state.seedJobs[failedJob.seed_job_id] = deepClone(failedJob);

    renderApp([`/products/seed/jobs/${failedJob.seed_job_id}`]);

    await waitFor(() => {
      expect(screen.getByText("Durable workflow errors")).toBeInTheDocument();
    });

    expect(screen.getByText("GitHub project creation failed.")).toBeInTheDocument();
    expect(screen.getByText("Onboarding summary")).toBeInTheDocument();
  });

  it("renders failed live seed jobs even when repo and project summaries are missing", async () => {
    const payload = {
      org_id: "org-1",
      installation_id: null,
      product_key: "the-test",
      product_name: "The Test",
      description: "test product",
      github_owner: "aegroup-io",
      github_repo: "test-product",
      github_visibility: "public",
      github_default_branch: "master",
      github_project_node_id: null,
      github_project_number: null,
      github_project_title: "The Test Product",
      status_field: "Status",
      ready_status: "Todo",
      done_status: "Done",
      baseline_channel: "stable",
      standards_pack: "default",
      execution_profile: "standard-python",
      max_concurrent_lanes: 4,
      required_secret_keys: [],
      dry_run: false,
    };
    const failedJob = buildSeedJob(payload, 63, null);
    failedJob.status = "Failed";
    failedJob.repo_summary = {} as any;
    failedJob.project_summary = {} as any;
    failedJob.rendered_file_paths = [];
    failedJob.progress_payload = [
      {
        step: "seed",
        status: "running",
        message: "Seed workflow started.",
        recorded_at: "2026-03-23T14:25:11Z",
      },
    ];
    failedJob.audit_payload = [
      {
        step: "seed.failed",
        status: "failed",
        message: "Seed workflow failed.",
        details: { error: "Not Found" },
        recorded_at: "2026-03-23T14:25:11Z",
      },
    ];
    failedJob.error_payload = [
      {
        code: "seed.failed",
        message: "Not Found",
        recorded_at: "2026-03-23T14:25:11Z",
      },
    ];
    state.seedJobs[failedJob.seed_job_id] = deepClone(failedJob);

    renderApp([`/products/seed/jobs/${failedJob.seed_job_id}`]);

    await waitFor(() => {
      expect(screen.getByText("Durable workflow errors")).toBeInTheDocument();
    });

    expect(screen.getByText("aegroup-io/test-product")).toBeInTheDocument();
    expect(screen.getAllByText("The Test Product").length).toBeGreaterThan(0);
    expect(screen.getByText("No status options recorded")).toBeInTheDocument();
    expect(screen.getByText("No views recorded")).toBeInTheDocument();
    expect(screen.getByText("Not Found")).toBeInTheDocument();
  });

  it("renders an actionable empty state when no products are registered", async () => {
    state.products = [];
    state.lanes = [];
    state.baselines = [];

    renderApp(["/products"]);

    await waitFor(() => {
      expect(screen.getByText("No products are registered yet.")).toBeInTheDocument();
    });

    expect(screen.getAllByRole("link", { name: "Seed a product" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Adopt a repo" }).length).toBeGreaterThan(0);
    expect(screen.getByText("What appears here after onboarding")).toBeInTheDocument();
  });

  it("renders an actionable empty state when no baselines are registered", async () => {
    state.baselines = [];

    renderApp(["/baselines"]);

    await waitFor(() => {
      expect(screen.getByText("No baseline posture is registered yet.")).toBeInTheDocument();
    });

    expect(screen.getAllByRole("link", { name: "Open Products" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Seed a product" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Adopt a repo" })).toBeInTheDocument();
    expect(screen.getByText("What Baselines tracks")).toBeInTheDocument();
  });

  it("routes a missing baseline detail back to onboarding", async () => {
    state.baselines = [];

    renderApp(["/baselines/product-1"]);

    await waitFor(() => {
      expect(screen.getByText("No baseline posture is registered yet.")).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "Open Products" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Seed a product" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Adopt a repo" })).toBeInTheDocument();
  });

  it("routes fleet setup warnings to the matching product follow-up surface", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Review setup blockers" })).toBeInTheDocument();
    });

    expect(screen.getByText("Onboarding activity")).toBeInTheDocument();
    expect(screen.getByText("Open adoption result")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Review setup blockers" }));

    await waitFor(() => {
      expect(screen.getByText("Setup blockers need action before resuming work.")).toBeInTheDocument();
    });
  });

  it("routes fleet drift warnings to the matching baseline follow-up surface", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Review standards drift" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("link", { name: "Review standards drift" }));

    await waitFor(() => {
      expect(screen.getAllByText("Managed asset drift").length).toBeGreaterThan(0);
    });
  });

  it("renders live fleet observability separately from onboarding blockers", async () => {
    renderApp();

    await waitFor(() => {
      expect(screen.getByText("Runtime and delivery health")).toBeInTheDocument();
    });

    expect(screen.getByText(/Queue depth/i)).toBeInTheDocument();
    expect(screen.getByText("Setup blockers and runtime health are rendered separately.")).toBeInTheDocument();
  });

  it("renders product detail with guided remediation and activation readiness", async () => {
    renderApp(["/products/product-1"]);

    await waitFor(() => {
      expect(screen.getByText("GitHub webhook secret is still missing.")).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Atlas" },
    ]);
    expect(screen.getByText("Setup blockers need action before resuming work.")).toBeInTheDocument();
    expect(screen.getByText("GitHub webhook secret is still missing.")).toBeInTheDocument();
    expect(screen.getByText("Recommended baseline asset is missing: .github/workflows/orcha-standards.yml")).toBeInTheDocument();
    expect(screen.getByText("Approval posture is capped by platform defaults.")).toBeInTheDocument();
    expect(screen.getByText("Activation readiness")).toBeInTheDocument();
    expect(screen.getAllByText("Blocking setup errors").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open secrets").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review baselines").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reopen adoption result").length).toBeGreaterThan(0);
    expect(screen.getByText("Onboarding activity")).toBeInTheDocument();
    expect(screen.getByText("Open adoption result")).toBeInTheDocument();
    expect(screen.getByText("Delivery cockpit")).toBeInTheDocument();
    expect(screen.getByText("Resolve setup blockers before the first build")).toBeInTheDocument();
    expect(screen.getByText("GitHub project mirror")).toBeInTheDocument();
    expect(screen.getByText("Tracked build work")).toBeInTheDocument();
    expect(screen.getByText("PR #77")).toBeInTheDocument();
    expect(screen.getByText(/Mirror ambiguity:/i)).toBeInTheDocument();
    expect(screen.getByText("Runtime and lane health")).toBeInTheDocument();
    expect(screen.getByText("Linked runtime warnings")).toBeInTheDocument();
    expect(screen.getAllByText(/Runner heartbeat stalled/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Healthy environments")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
    });
  });

  it("keeps the pause button readable and allows hosted contract refresh without a local repo root", async () => {
    renderApp(["/products/product-1"]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    });

    const pauseButton = screen.getByRole("button", { name: "Pause" });
    expect(pauseButton).toHaveClass("bg-amber-300", "text-zinc-950", "disabled:!opacity-100");

    const refreshButton = screen.getByRole("button", { name: "Refresh contract" });
    expect(refreshButton).toBeEnabled();

    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(screen.getByText("Blocking setup is clear")).toBeInTheDocument();
    });
  });

  it("makes the next build step explicit when onboarding is complete but no lanes are active yet", async () => {
    state.lanes = [];
    state.products[0].setup_state = "ready";
    state.products[0].setup_diagnostics = [];
    state.products[0].delivery_cockpit = {
      mirror_state: "current",
      work_pressure: {
        total_open_count: 1,
        triage_count: 0,
        ready_count: 1,
        blocked_count: 0,
        in_progress_count: 0,
        in_review_count: 0,
        done_count: 0,
        ambiguous_count: 0,
        stale_count: 0,
      },
      project: {
        project_id: "project-1",
        number: 4,
        title: "Atlas",
        status_field_name: "Status",
        item_count: 1,
        issue_count: 1,
        pull_request_count: 0,
        mirror_state: "current",
        last_reconciled_at: "2026-03-16T20:09:00Z",
        url: "https://github.com/orgs/aegroup-io/projects/4",
      },
      work_items: [
        {
          work_item_id: "work-item-ready",
          repo_id: "repo-1",
          repo_owner: "aegroup-io",
          repo_name: "atlas",
          issue_number: 286,
          title: "Prepare the first queued build",
          status: "Ready",
          status_source: "Todo",
          dependency_state: "clear",
          priority_hint: "high",
          handoff_status: "none",
          eligibility_flags: ["eligible"],
          mirror_state: "current",
          requires_repair: false,
          repair_reasons: [],
          last_normalized_at: "2026-03-16T20:14:00Z",
          updated_at: "2026-03-16T20:14:00Z",
          project_status_name: "Todo",
          url: "https://github.com/aegroup-io/atlas/issues/286",
          linked_pull_requests: [],
        },
      ],
      remaining_work_item_count: 0,
    };

    renderApp(["/products/product-1"]);

    await waitFor(() => {
      expect(screen.getByText("Track the first ready build item")).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: "Issue #286" })).toBeInTheDocument();
    expect(screen.getByText("No lanes for this product.")).toBeInTheDocument();
    expect(
      screen.getByText("Use the delivery cockpit above to review ready backlog, GitHub handoff, and the next build step until scheduler-owned lanes appear."),
    ).toBeInTheDocument();
  });

  it("keeps setup blockers separate from managed asset drift on baseline detail and reflects refresh remediation", async () => {
    renderApp(["/baselines/product-1"]);

    await waitFor(() => {
      expect(screen.getByText("Setup findings")).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Atlas", href: "/products/product-1" },
      { label: "Baseline" },
    ]);
    expect(screen.getByText("GitHub webhook secret is still missing.")).toBeInTheDocument();
    expect(screen.getByText("Recommended baseline asset is missing: .github/workflows/orcha-standards.yml")).toBeInTheDocument();
    expect(screen.getByText("Approval posture is capped by platform defaults.")).toBeInTheDocument();
    expect(screen.getAllByText("Managed asset drift").length).toBeGreaterThan(0);
    expect(screen.getByText(".github/pull_request_template.md")).toBeInTheDocument();
    expect(screen.getByText("Open product blockers")).toBeInTheDocument();
    expect(screen.getByText("Open secrets")).toBeInTheDocument();
    expect(screen.getByText("Reopen adoption result")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh contract" })).toHaveClass("w-full", "max-w-[200px]", "justify-start");

    fireEvent.change(screen.getByLabelText(/Repo root/), {
      target: { value: "/tmp/atlas" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Refresh contract" }));

    await waitFor(() => {
      expect(screen.getByText("Blocking setup is clear")).toBeInTheDocument();
    });

    expect(screen.queryByText("GitHub webhook secret is still missing.")).not.toBeInTheDocument();
    expect(screen.getByText("Approval posture is capped by platform defaults.")).toBeInTheDocument();
    expect(screen.getByText("No blocking setup errors are preventing activation.")).toBeInTheDocument();
  });

  it("supports standards evaluation review and operator outcomes from baseline detail", async () => {
    renderApp(["/baselines/product-1"]);

    await waitFor(() => {
      expect(screen.getByText("Standards workspace")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Follow-up review")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Managed section refresh could not be applied cleanly.").length).toBeGreaterThan(0);
    expect(screen.getByText("Standards run detail")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start standards evaluation" })).toHaveClass("w-full", "sm:w-[200px]");

    fireEvent.change(screen.getByLabelText("Local repo root"), {
      target: { value: "/tmp/atlas" },
    });
    fireEvent.change(screen.getAllByLabelText("Generated PR Number")[0], {
      target: { value: "123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start standards evaluation" }));

    await waitFor(() => {
      expect(screen.getByText("Reviewable upgrade pr on PR #123 is ready for operator review.")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Accept run" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Accept run" }));

    await waitFor(() => {
      expect(screen.getByText("Operator accepted the latest upgrade pr on PR #123.")).toBeInTheDocument();
    });

    expect(screen.getAllByText("Accepted").length).toBeGreaterThan(0);
  });

  it("renders lane detail and allows operator approval", async () => {
    renderApp(["/lanes/lane-approval"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "#281 Awaiting approval" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Atlas", href: "/products/product-1" },
      { label: "Lane #281" },
    ]);
    expect(screen.getAllByText("Need operator approval.").length).toBeGreaterThan(0);
    expect(screen.getByText("Runtime and observability")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText("Correlated notifications")).toBeInTheDocument();
    expect(screen.getByText("Artifact store")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve lane" }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Approve lane" })).not.toBeInTheDocument();
      expect(screen.getAllByText("Running").length).toBeGreaterThan(0);
    });
  });

  it("recovers the live adoption result from the durable product route after refresh", async () => {
    renderApp(["/products/adopt/review/product-1"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Review onboarding result" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Atlas", href: "/products/product-1" },
      { label: "Adoption result" },
    ]);
    expect(screen.getByText("Showing persisted product context only")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review baselines" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rerun contract refresh" })).toHaveClass("w-full", "max-w-[200px]", "justify-start");
  });

  it("renders baseline and graph routes with drift and topology context", async () => {
    renderApp(["/graphs/products/product-1"]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Atlas graph" })).toBeInTheDocument();
    });

    expectBreadcrumb([
      { label: "Products", href: "/products" },
      { label: "Atlas", href: "/products/product-1" },
      { label: "Graph" },
    ]);
    expect(screen.getByText("Active incident on the API dependency.")).toBeInTheDocument();
    expect(screen.getByText("Score 4")).toBeInTheDocument();
  });
});
