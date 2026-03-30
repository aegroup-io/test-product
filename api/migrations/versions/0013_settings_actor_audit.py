"""Record setting write actors for auditable workspace defaults."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_settings_actor_audit"
down_revision = "0012_merge_component_graph_and_runner_protocol_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("created_by", sa.String(length=128), nullable=True))
    op.add_column("settings", sa.Column("updated_by", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "updated_by")
    op.drop_column("settings", "created_by")
