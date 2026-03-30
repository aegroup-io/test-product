"""Persist product seed jobs and audit state."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_product_seed_jobs"
down_revision = "0007_work_item_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_seed_jobs",
        sa.Column("seed_job_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("progress_payload", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("error_payload", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("audit_payload", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("rendered_file_paths", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("repo_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("project_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("setup_state", sa.String(length=32), nullable=True),
        sa.Column("setup_diagnostics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("seed_job_id"),
    )
    op.create_index("ix_product_seed_jobs_org_id", "product_seed_jobs", ["org_id"], unique=False)
    op.create_index("ix_product_seed_jobs_product_id", "product_seed_jobs", ["product_id"], unique=False)
    op.create_index("ix_product_seed_jobs_status", "product_seed_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_product_seed_jobs_status", table_name="product_seed_jobs")
    op.drop_index("ix_product_seed_jobs_product_id", table_name="product_seed_jobs")
    op.drop_index("ix_product_seed_jobs_org_id", table_name="product_seed_jobs")
    op.drop_table("product_seed_jobs")
