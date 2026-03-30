"""Create starter runtime core schema and baseline seed."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from agent_core_platform_api.bootstrap import seed_baseline
from agent_core_platform_api.config import get_settings


revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("org_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column(
            "documentation_visibility",
            sa.String(length=32),
            nullable=False,
            server_default="shared",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "org_memberships",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.org_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id", "user_id", name="pk_org_memberships"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_org_memberships_org_user"),
    )
    op.create_index("ix_org_memberships_org_id", "org_memberships", ["org_id"], unique=False)
    op.create_index("ix_org_memberships_user_id", "org_memberships", ["user_id"], unique=False)
    op.create_index("ix_org_memberships_active", "org_memberships", ["org_id", "is_active"], unique=False)

    op.create_table(
        "permissions",
        sa.Column("permission_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_permissions_key", "permissions", ["key"], unique=True)

    op.create_table(
        "feature_flags",
        sa.Column("feature_flag_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_feature_flags_key", "feature_flags", ["key"], unique=True)

    op.create_table(
        "roles",
        sa.Column("role_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_roles_slug", "roles", ["slug"], unique=True)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.permission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )

    op.create_table(
        "role_feature_flags",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("feature_flag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.role_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_flag_id"], ["feature_flags.feature_flag_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "feature_flag_id", name="pk_role_feature_flags"),
    )

    op.create_table(
        "secrets",
        sa.Column("secret_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("value_ciphertext", sa.Text(), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_secrets_key", "secrets", ["key"], unique=True)
    op.create_index("ix_secrets_kind", "secrets", ["kind"], unique=False)

    op.create_table(
        "settings",
        sa.Column("setting_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("scope_type", "scope_id", "key", name="uq_settings_scope_key"),
    )
    op.create_index("ix_settings_scope", "settings", ["scope_type", "scope_id"], unique=False)

    settings = get_settings()
    session = Session(bind=op.get_bind(), join_transaction_mode="create_savepoint")
    try:
        seed_baseline(
            session,
            initial_org_name=settings.initial_org_name,
            initial_org_slug=settings.initial_org_slug,
            dev_user_id=settings.dev_user_id,
            dev_username=settings.dev_username,
            commit=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index("ix_settings_scope", table_name="settings")
    op.drop_table("settings")
    op.drop_index("ix_secrets_kind", table_name="secrets")
    op.drop_index("ix_secrets_key", table_name="secrets")
    op.drop_table("secrets")
    op.drop_table("role_feature_flags")
    op.drop_table("role_permissions")
    op.drop_index("ix_roles_slug", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_feature_flags_key", table_name="feature_flags")
    op.drop_table("feature_flags")
    op.drop_index("ix_permissions_key", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_org_memberships_active", table_name="org_memberships")
    op.drop_index("ix_org_memberships_user_id", table_name="org_memberships")
    op.drop_index("ix_org_memberships_org_id", table_name="org_memberships")
    op.drop_table("org_memberships")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
