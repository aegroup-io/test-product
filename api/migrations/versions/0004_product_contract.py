"""Persist effective product contract state and setup diagnostics."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_product_contract"
down_revision = "0003_orcha_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("manifest_schema_version", sa.Integer(), nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "setup_state",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'setup-needed'"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "setup_diagnostics",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "effective_config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "operator_overrides",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column("products", sa.Column("last_config_refresh_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("last_accepted_config_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "last_accepted_config_at")
    op.drop_column("products", "last_config_refresh_at")
    op.drop_column("products", "operator_overrides")
    op.drop_column("products", "effective_config")
    op.drop_column("products", "setup_diagnostics")
    op.drop_column("products", "setup_state")
    op.drop_column("products", "manifest_schema_version")
