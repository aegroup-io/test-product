"""Add workspace Git repository settings tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_workspace_repo_settings"
down_revision = "0013_settings_actor_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_repositories",
        sa.Column("repo_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("github_owner", sa.String(length=128), nullable=False),
        sa.Column("github_repo", sa.String(length=128), nullable=False),
        sa.Column("default_branch", sa.String(length=128), nullable=False),
        sa.Column("clone_url", sa.String(length=255), nullable=False),
        sa.Column("git_auth_secret_id", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["git_auth_secret_id"], ["secrets.secret_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("github_owner", "github_repo", name="uq_workspace_repositories_github"),
    )
    op.create_index("ix_workspace_repositories_org_id", "workspace_repositories", ["org_id"], unique=False)
    op.create_index(
        "ix_workspace_repositories_archived_at",
        "workspace_repositories",
        ["archived_at"],
        unique=False,
    )

    op.create_table(
        "workspace_repo_org_mappings",
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["workspace_repositories.repo_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("repo_id", "org_id"),
    )
    op.create_index(
        "ix_workspace_repo_org_mappings_org_id",
        "workspace_repo_org_mappings",
        ["org_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_repo_org_mappings_org_id", table_name="workspace_repo_org_mappings")
    op.drop_table("workspace_repo_org_mappings")
    op.drop_index("ix_workspace_repositories_archived_at", table_name="workspace_repositories")
    op.drop_index("ix_workspace_repositories_org_id", table_name="workspace_repositories")
    op.drop_table("workspace_repositories")
