"""Add component-graph provenance and freshness metadata."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_component_graph_provenance_and_freshness"
down_revision = "0010_execution_environment_runtime_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component_nodes") as batch_op:
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "freshness_status",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            )
        )

    with op.batch_alter_table("component_edges") as batch_op:
        batch_op.add_column(sa.Column("source_ref", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "freshness_status",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("component_edges") as batch_op:
        batch_op.drop_column("freshness_status")
        batch_op.drop_column("source_ref")

    with op.batch_alter_table("component_nodes") as batch_op:
        batch_op.drop_column("freshness_status")
        batch_op.drop_column("last_verified_at")
        batch_op.drop_column("confidence")
