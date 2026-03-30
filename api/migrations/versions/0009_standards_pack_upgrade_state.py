"""Add standards-pack persistence and upgrade evaluation state."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_standards_pack_upgrade_state"
down_revision = "0008_product_seed_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("standards_pack_key", sa.String(length=64), nullable=True))
    op.add_column("products", sa.Column("standards_pack_version", sa.String(length=64), nullable=True))

    op.create_table(
        "standards_packs",
        sa.Column("standards_pack_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("source_bundle", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("standards_pack_id"),
        sa.UniqueConstraint("key", "channel", "version", name="uq_standards_packs_identity"),
    )
    op.create_index("ix_standards_packs_channel", "standards_packs", ["channel"], unique=False)

    op.create_table(
        "standards_pack_assets",
        sa.Column("standards_pack_asset_id", sa.Uuid(), nullable=False),
        sa.Column("standards_pack_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("default_mode", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("ownership_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["standards_pack_id"], ["standards_packs.standards_pack_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("standards_pack_asset_id"),
        sa.UniqueConstraint("standards_pack_id", "path", name="uq_standards_pack_assets_path"),
    )
    op.create_index("ix_standards_pack_assets_mode", "standards_pack_assets", ["default_mode"], unique=False)

    op.create_table(
        "product_standards_overrides",
        sa.Column("standards_override_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("override_mode", sa.String(length=64), nullable=True),
        sa.Column("is_deferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("override_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("standards_override_id"),
        sa.UniqueConstraint("product_id", "path", name="uq_product_standards_overrides_product_path"),
    )
    op.create_index(
        "ix_product_standards_overrides_deferred",
        "product_standards_overrides",
        ["is_deferred"],
        unique=False,
    )

    op.create_table(
        "standards_upgrade_runs",
        sa.Column("standards_upgrade_run_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=True),
        sa.Column("standards_pack_id", sa.Uuid(), nullable=False),
        sa.Column("source_bundle", sa.String(length=255), nullable=False),
        sa.Column("source_version", sa.String(length=64), nullable=False),
        sa.Column("outcome_kind", sa.String(length=32), nullable=False),
        sa.Column("outcome_status", sa.String(length=32), nullable=False),
        sa.Column("generated_pr_number", sa.Integer(), nullable=True),
        sa.Column("pr_title", sa.String(length=255), nullable=True),
        sa.Column("pr_body", sa.Text(), nullable=True),
        sa.Column("summary_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repository_bindings.repo_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["standards_pack_id"], ["standards_packs.standards_pack_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("standards_upgrade_run_id"),
    )
    op.create_index("ix_standards_upgrade_runs_product_id", "standards_upgrade_runs", ["product_id"], unique=False)
    op.create_index(
        "ix_standards_upgrade_runs_outcome_status",
        "standards_upgrade_runs",
        ["outcome_status"],
        unique=False,
    )

    op.create_table(
        "standards_upgrade_assets",
        sa.Column("standards_upgrade_asset_id", sa.Uuid(), nullable=False),
        sa.Column("standards_upgrade_run_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("management_mode", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("drift_status", sa.String(length=64), nullable=False),
        sa.Column("patch_text", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["standards_upgrade_run_id"], ["standards_upgrade_runs.standards_upgrade_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("standards_upgrade_asset_id"),
        sa.UniqueConstraint("standards_upgrade_run_id", "path", name="uq_standards_upgrade_assets_run_path"),
    )
    op.create_index("ix_standards_upgrade_assets_action", "standards_upgrade_assets", ["action"], unique=False)

    op.create_table(
        "standards_follow_up_items",
        sa.Column("standards_follow_up_item_id", sa.Uuid(), nullable=False),
        sa.Column("standards_upgrade_run_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repository_bindings.repo_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["standards_upgrade_run_id"], ["standards_upgrade_runs.standards_upgrade_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("standards_follow_up_item_id"),
    )
    op.create_index("ix_standards_follow_up_items_status", "standards_follow_up_items", ["status"], unique=False)
    op.create_index(
        "ix_standards_follow_up_items_product_path",
        "standards_follow_up_items",
        ["product_id", "path"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_standards_follow_up_items_product_path", table_name="standards_follow_up_items")
    op.drop_index("ix_standards_follow_up_items_status", table_name="standards_follow_up_items")
    op.drop_table("standards_follow_up_items")

    op.drop_index("ix_standards_upgrade_assets_action", table_name="standards_upgrade_assets")
    op.drop_table("standards_upgrade_assets")

    op.drop_index("ix_standards_upgrade_runs_outcome_status", table_name="standards_upgrade_runs")
    op.drop_index("ix_standards_upgrade_runs_product_id", table_name="standards_upgrade_runs")
    op.drop_table("standards_upgrade_runs")

    op.drop_index("ix_product_standards_overrides_deferred", table_name="product_standards_overrides")
    op.drop_table("product_standards_overrides")

    op.drop_index("ix_standards_pack_assets_mode", table_name="standards_pack_assets")
    op.drop_table("standards_pack_assets")

    op.drop_index("ix_standards_packs_channel", table_name="standards_packs")
    op.drop_table("standards_packs")

    op.drop_column("products", "standards_pack_version")
    op.drop_column("products", "standards_pack_key")
