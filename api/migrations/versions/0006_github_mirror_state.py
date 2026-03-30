"""Add durable GitHub mirror tables and normalized mirror fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_github_mirror_state"
down_revision = "0005_github_delivery_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repository_bindings", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "repository_bindings",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "repository_bindings",
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.add_column(
        "github_project_mirrors",
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.add_column("work_items", sa.Column("title_normalized", sa.Text(), nullable=True))
    op.add_column("work_items", sa.Column("body_normalized", sa.Text(), nullable=True))
    op.add_column("work_items", sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    op.create_table(
        "pull_request_mirrors",
        sa.Column("pull_request_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("github_pr_node_id", sa.String(length=128), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_normalized", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("head_branch", sa.String(length=255), nullable=True),
        sa.Column("base_branch", sa.String(length=255), nullable=True),
        sa.Column("checks_rollup", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("review_state", sa.String(length=64), nullable=True),
        sa.Column("merge_state", sa.String(length=64), nullable=True),
        sa.Column("linked_work_item_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["repo_id"], ["repository_bindings.repo_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pull_request_id"),
        sa.UniqueConstraint("repo_id", "number", name="uq_pull_request_mirrors_repo_number"),
    )
    op.create_index(
        "ix_pull_request_mirrors_github_pr_node_id",
        "pull_request_mirrors",
        ["github_pr_node_id"],
        unique=True,
    )
    op.create_index("ix_pull_request_mirrors_state", "pull_request_mirrors", ["state"], unique=False)

    op.create_table(
        "github_project_field_mirrors",
        sa.Column("project_field_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("github_project_field_node_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=64), nullable=False),
        sa.Column("settings_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["github_project_mirrors.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_field_id"),
        sa.UniqueConstraint(
            "project_id",
            "github_project_field_node_id",
            name="uq_project_field_mirrors_project_node",
        ),
    )
    op.create_index(
        "ix_project_field_mirrors_github_project_field_node_id",
        "github_project_field_mirrors",
        ["github_project_field_node_id"],
        unique=True,
    )

    op.create_table(
        "github_project_field_option_mirrors",
        sa.Column("project_field_option_id", sa.Uuid(), nullable=False),
        sa.Column("project_field_id", sa.Uuid(), nullable=False),
        sa.Column("github_project_option_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_field_id"], ["github_project_field_mirrors.project_field_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_field_option_id"),
        sa.UniqueConstraint(
            "project_field_id",
            "github_project_option_id",
            name="uq_project_field_option_mirrors_shape",
        ),
    )
    op.create_index(
        "ix_project_field_option_mirrors_github_project_option_id",
        "github_project_field_option_mirrors",
        ["github_project_option_id"],
        unique=False,
    )

    op.create_table(
        "github_project_item_mirrors",
        sa.Column("project_item_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("github_project_item_node_id", sa.String(length=128), nullable=False),
        sa.Column("github_content_node_id", sa.String(length=128), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=True),
        sa.Column("pull_request_id", sa.Uuid(), nullable=True),
        sa.Column("status_name", sa.String(length=128), nullable=True),
        sa.Column("field_values_payload", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["github_project_mirrors.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pull_request_id"], ["pull_request_mirrors.pull_request_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.work_item_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("project_item_id"),
    )
    op.create_index(
        "ix_project_item_mirrors_github_project_item_node_id",
        "github_project_item_mirrors",
        ["github_project_item_node_id"],
        unique=True,
    )
    op.create_index(
        "ix_project_item_mirrors_github_content_node_id",
        "github_project_item_mirrors",
        ["github_content_node_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_item_mirrors_github_content_node_id", table_name="github_project_item_mirrors")
    op.drop_index("ix_project_item_mirrors_github_project_item_node_id", table_name="github_project_item_mirrors")
    op.drop_table("github_project_item_mirrors")

    op.drop_index(
        "ix_project_field_option_mirrors_github_project_option_id",
        table_name="github_project_field_option_mirrors",
    )
    op.drop_table("github_project_field_option_mirrors")

    op.drop_index(
        "ix_project_field_mirrors_github_project_field_node_id",
        table_name="github_project_field_mirrors",
    )
    op.drop_table("github_project_field_mirrors")

    op.drop_index("ix_pull_request_mirrors_state", table_name="pull_request_mirrors")
    op.drop_index("ix_pull_request_mirrors_github_pr_node_id", table_name="pull_request_mirrors")
    op.drop_table("pull_request_mirrors")

    op.drop_column("work_items", "raw_payload")
    op.drop_column("work_items", "body_normalized")
    op.drop_column("work_items", "title_normalized")

    op.drop_column("github_project_mirrors", "raw_payload")

    op.drop_column("repository_bindings", "raw_payload")
    op.drop_column("repository_bindings", "is_archived")
    op.drop_column("repository_bindings", "description")
