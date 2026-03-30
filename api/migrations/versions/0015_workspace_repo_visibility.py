"""Add visibility to workspace Git repository settings."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_workspace_repo_visibility"
down_revision = "0014_workspace_repo_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_repositories",
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"),
    )


def downgrade() -> None:
    op.drop_column("workspace_repositories", "visibility")
