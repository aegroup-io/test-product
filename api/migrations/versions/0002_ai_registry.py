"""Add AI registry and agent core tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_ai_registry"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("provider_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("compliance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_ai_providers_key", "ai_providers", ["key"], unique=True)
    op.create_index("ix_ai_providers_type", "ai_providers", ["type"], unique=False)

    op.create_table(
        "ai_models",
        sa.Column("model_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider_model_id", sa.String(length=256), nullable=True),
        sa.Column("can_embed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_rerank", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_chat", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_vision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("can_audio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_workload", sa.String(length=64), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("restricted_content_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("context_window_tokens", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.JSON(), nullable=False),
        sa.Column("default_params", sa.JSON(), nullable=False),
        sa.Column("compliance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.provider_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ai_models_key", "ai_models", ["key"], unique=True)
    op.create_index("ix_ai_models_provider_id", "ai_models", ["provider_id"], unique=False)
    op.create_index("ix_ai_models_default_workload", "ai_models", ["default_workload"], unique=False)
    op.create_index("ix_ai_models_active_chat", "ai_models", ["is_active", "can_chat"], unique=False)

    op.create_table(
        "ai_agents",
        sa.Column("agent_id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("tool_policy", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("default_model_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["default_model_id"], ["ai_models.model_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_agents_key", "ai_agents", ["key"], unique=True)
    op.create_index("ix_ai_agents_is_active", "ai_agents", ["is_active"], unique=False)
    op.create_index("ix_ai_agents_default_model_id", "ai_agents", ["default_model_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_agents_default_model_id", table_name="ai_agents")
    op.drop_index("ix_ai_agents_is_active", table_name="ai_agents")
    op.drop_index("ix_ai_agents_key", table_name="ai_agents")
    op.drop_table("ai_agents")

    op.drop_index("ix_ai_models_active_chat", table_name="ai_models")
    op.drop_index("ix_ai_models_default_workload", table_name="ai_models")
    op.drop_index("ix_ai_models_provider_id", table_name="ai_models")
    op.drop_index("ix_ai_models_key", table_name="ai_models")
    op.drop_table("ai_models")

    op.drop_index("ix_ai_providers_type", table_name="ai_providers")
    op.drop_index("ix_ai_providers_key", table_name="ai_providers")
    op.drop_table("ai_providers")
