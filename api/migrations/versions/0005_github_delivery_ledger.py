"""Extend webhook deliveries into a replayable GitHub ledger."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_github_delivery_ledger"
down_revision = "0004_product_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "webhook_deliveries",
        sa.Column(
            "delivery_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column("webhook_deliveries", sa.Column("payload_json", sa.JSON(), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("raw_body", sa.Text(), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("webhook_deliveries", "error_detail")
    op.drop_column("webhook_deliveries", "raw_body")
    op.drop_column("webhook_deliveries", "payload_json")
    op.drop_column("webhook_deliveries", "delivery_attempts")
