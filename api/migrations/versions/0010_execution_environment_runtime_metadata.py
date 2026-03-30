"""Add execution-environment runtime metadata for lane provisioning."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_execution_environment_runtime_metadata"
down_revision = ("0009_scheduler_lane_claim_guard", "0009_standards_pack_upgrade_state")
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("execution_environments") as batch_op:
        batch_op.add_column(sa.Column("log_uri", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("cache_uri", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("checkout_revision", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("manifest_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("secret_fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("quarantine_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table("execution_environments") as batch_op:
        batch_op.drop_column("provider_metadata")
        batch_op.drop_column("quarantine_reason")
        batch_op.drop_column("secret_fingerprint")
        batch_op.drop_column("manifest_fingerprint")
        batch_op.drop_column("checkout_revision")
        batch_op.drop_column("cache_uri")
        batch_op.drop_column("log_uri")
