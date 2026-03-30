"""Add Orcha durable control-plane foundation tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_orcha_control_plane"
down_revision = "0002_ai_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("product_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("primary_repo_id", sa.Uuid(), nullable=True),
        sa.Column("primary_project_id", sa.Uuid(), nullable=True),
        sa.Column("baseline_channel", sa.String(length=64), nullable=True),
        sa.Column("agent_core_version", sa.String(length=64), nullable=True),
        sa.Column("execution_profile", sa.String(length=64), nullable=True),
        sa.Column("component_root_node_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_id", "key", name="uq_products_org_key"),
    )
    op.create_index("ix_products_org_id", "products", ["org_id"], unique=False)
    op.create_index("ix_products_status", "products", ["status"], unique=False)

    op.create_table(
        "repository_bindings",
        sa.Column("repo_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("github_repository_node_id", sa.String(length=128), nullable=True),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("default_branch", sa.String(length=128), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("seed_source", sa.String(length=128), nullable=True),
        sa.Column("adoption_state", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", "owner", "name", name="uq_repository_bindings_product_repo"),
    )
    op.create_index(
        "ix_repository_bindings_github_repository_node_id",
        "repository_bindings",
        ["github_repository_node_id"],
        unique=True,
    )
    op.create_index("ix_repository_bindings_product_id", "repository_bindings", ["product_id"], unique=False)

    op.create_table(
        "github_project_mirrors",
        sa.Column("project_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("github_project_node_id", sa.String(length=128), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status_field_name", sa.String(length=128), nullable=False),
        sa.Column("status_options", sa.JSON(), nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mirror_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", name="uq_github_project_mirrors_product"),
    )
    op.create_index(
        "ix_github_project_mirrors_github_project_node_id",
        "github_project_mirrors",
        ["github_project_node_id"],
        unique=True,
    )

    op.create_table(
        "work_items",
        sa.Column("work_item_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("github_issue_node_id", sa.String(length=128), nullable=True),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("assignees", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("priority_hint", sa.String(length=32), nullable=True),
        sa.Column("linked_prs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["github_project_mirrors.project_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["repo_id"], ["repository_bindings.repo_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("repo_id", "issue_number", name="uq_work_items_repo_issue_number"),
    )
    op.create_index("ix_work_items_github_issue_node_id", "work_items", ["github_issue_node_id"], unique=True)
    op.create_index("ix_work_items_project_id", "work_items", ["project_id"], unique=False)
    op.create_index("ix_work_items_status", "work_items", ["status"], unique=False)

    op.create_table(
        "orchestration_lanes",
        sa.Column("lane_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("execution_environment_id", sa.Uuid(), nullable=True),
        sa.Column("agent_session_id", sa.Uuid(), nullable=True),
        sa.Column("retry_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handoff_reason", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repository_bindings.repo_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.work_item_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("work_item_id", "attempt", name="uq_orchestration_lanes_work_item_attempt"),
    )
    op.create_index("ix_orchestration_lanes_product_id", "orchestration_lanes", ["product_id"], unique=False)
    op.create_index("ix_orchestration_lanes_repo_id", "orchestration_lanes", ["repo_id"], unique=False)
    op.create_index(
        "ix_orchestration_lanes_work_item_state",
        "orchestration_lanes",
        ["work_item_id", "state"],
        unique=False,
    )

    op.create_table(
        "execution_environments",
        sa.Column("execution_environment_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("lane_id", sa.Uuid(), nullable=False),
        sa.Column("runtime_provider", sa.String(length=64), nullable=False),
        sa.Column("container_image", sa.String(length=255), nullable=True),
        sa.Column("container_handle", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workspace_uri", sa.String(length=255), nullable=True),
        sa.Column("artifact_uri", sa.String(length=255), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["lane_id"], ["orchestration_lanes.lane_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_execution_environments_lane_id", "execution_environments", ["lane_id"], unique=True)
    op.create_index("ix_execution_environments_status", "execution_environments", ["status"], unique=False)

    op.create_table(
        "agent_sessions",
        sa.Column("agent_session_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("lane_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("turn_id", sa.String(length=128), nullable=True),
        sa.Column("runner_version", sa.String(length=64), nullable=True),
        sa.Column("last_event", sa.String(length=64), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("requires_human_input", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lane_id"], ["orchestration_lanes.lane_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_sessions_lane_id", "agent_sessions", ["lane_id"], unique=True)
    op.create_index(
        "ix_agent_sessions_requires_human_input",
        "agent_sessions",
        ["requires_human_input"],
        unique=False,
    )

    op.create_table(
        "managed_assets",
        sa.Column("asset_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("management_mode", sa.String(length=64), nullable=False),
        sa.Column("upstream_bundle_version", sa.String(length=64), nullable=True),
        sa.Column("drift_status", sa.String(length=32), nullable=True),
        sa.Column("last_pr_number", sa.Integer(), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", "path", name="uq_managed_assets_product_path"),
    )
    op.create_index("ix_managed_assets_drift_status", "managed_assets", ["drift_status"], unique=False)

    op.create_table(
        "component_nodes",
        sa.Column("component_node_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("version", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", "key", name="uq_component_nodes_product_key"),
    )
    op.create_index("ix_component_nodes_type", "component_nodes", ["type"], unique=False)
    op.create_index("ix_component_nodes_status", "component_nodes", ["status"], unique=False)

    op.create_table(
        "component_edges",
        sa.Column("component_edge_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("from_node_id", sa.Uuid(), nullable=False),
        sa.Column("to_node_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["from_node_id"], ["component_nodes.component_node_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_node_id"], ["component_nodes.component_node_id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "relationship",
            "source_kind",
            name="uq_component_edges_shape",
        ),
    )
    op.create_index("ix_component_edges_to_node_id", "component_edges", ["to_node_id"], unique=False)

    op.create_table(
        "operational_signals",
        sa.Column("signal_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ix_operational_signals_target",
        "operational_signals",
        ["target_kind", "target_id"],
        unique=False,
    )
    op.create_index("ix_operational_signals_observed_at", "operational_signals", ["observed_at"], unique=False)

    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("github_delivery_guid", sa.String(length=128), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("installation_id", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index(
        "ix_webhook_deliveries_github_delivery_guid",
        "webhook_deliveries",
        ["github_delivery_guid"],
        unique=True,
    )
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"], unique=False)
    op.create_index("ix_webhook_deliveries_received_at", "webhook_deliveries", ["received_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_received_at", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_github_delivery_guid", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    op.drop_index("ix_operational_signals_observed_at", table_name="operational_signals")
    op.drop_index("ix_operational_signals_target", table_name="operational_signals")
    op.drop_table("operational_signals")

    op.drop_index("ix_component_edges_to_node_id", table_name="component_edges")
    op.drop_table("component_edges")

    op.drop_index("ix_component_nodes_status", table_name="component_nodes")
    op.drop_index("ix_component_nodes_type", table_name="component_nodes")
    op.drop_table("component_nodes")

    op.drop_index("ix_managed_assets_drift_status", table_name="managed_assets")
    op.drop_table("managed_assets")

    op.drop_index("ix_agent_sessions_requires_human_input", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_lane_id", table_name="agent_sessions")
    op.drop_table("agent_sessions")

    op.drop_index("ix_execution_environments_status", table_name="execution_environments")
    op.drop_index("ix_execution_environments_lane_id", table_name="execution_environments")
    op.drop_table("execution_environments")

    op.drop_index("ix_orchestration_lanes_work_item_state", table_name="orchestration_lanes")
    op.drop_index("ix_orchestration_lanes_repo_id", table_name="orchestration_lanes")
    op.drop_index("ix_orchestration_lanes_product_id", table_name="orchestration_lanes")
    op.drop_table("orchestration_lanes")

    op.drop_index("ix_work_items_status", table_name="work_items")
    op.drop_index("ix_work_items_project_id", table_name="work_items")
    op.drop_index("ix_work_items_github_issue_node_id", table_name="work_items")
    op.drop_table("work_items")

    op.drop_index("ix_github_project_mirrors_github_project_node_id", table_name="github_project_mirrors")
    op.drop_table("github_project_mirrors")

    op.drop_index("ix_repository_bindings_product_id", table_name="repository_bindings")
    op.drop_index("ix_repository_bindings_github_repository_node_id", table_name="repository_bindings")
    op.drop_table("repository_bindings")

    op.drop_index("ix_products_status", table_name="products")
    op.drop_index("ix_products_org_id", table_name="products")
    op.drop_table("products")
