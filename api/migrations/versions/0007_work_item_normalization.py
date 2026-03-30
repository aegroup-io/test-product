"""Add normalized work-item state for orchestration eligibility."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_work_item_normalization"
down_revision = "0006_github_mirror_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_items", sa.Column("status_source", sa.String(length=128), nullable=True))
    op.add_column(
        "work_items",
        sa.Column("dependency_state", sa.String(length=32), nullable=False, server_default="clear"),
    )
    op.add_column(
        "work_items",
        sa.Column("dependency_details", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "work_items",
        sa.Column("eligibility_flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "work_items",
        sa.Column("handoff_status", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column(
        "work_items",
        sa.Column("requires_repair", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "work_items",
        sa.Column("repair_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("work_items", sa.Column("last_normalized_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_work_items_dependency_state", "work_items", ["dependency_state"], unique=False)
    op.create_index("ix_work_items_requires_repair", "work_items", ["requires_repair"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_work_items_requires_repair", table_name="work_items")
    op.drop_index("ix_work_items_dependency_state", table_name="work_items")

    op.drop_column("work_items", "last_normalized_at")
    op.drop_column("work_items", "repair_reasons")
    op.drop_column("work_items", "requires_repair")
    op.drop_column("work_items", "handoff_status")
    op.drop_column("work_items", "eligibility_flags")
    op.drop_column("work_items", "dependency_details")
    op.drop_column("work_items", "dependency_state")
    op.drop_column("work_items", "status_source")
