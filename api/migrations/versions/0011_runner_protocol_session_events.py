"""Add runner-protocol session metadata and durable event persistence."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_runner_protocol_session_events"
down_revision = "0010_execution_environment_runtime_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch_op:
        batch_op.add_column(sa.Column("runner_session_id", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'launching'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "capabilities",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("environment_identity", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("wait_reason", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "continuation_summary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(sa.Column("last_error_category", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column(
                "launch_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "policy_snapshot",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.create_index("ix_agent_sessions_status", ["status"], unique=False)

    op.create_table(
        "agent_session_events",
        sa.Column("agent_session_event_id", sa.Uuid(), nullable=False),
        sa.Column("agent_session_id", sa.Uuid(), nullable=False),
        sa.Column("lane_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "input_tokens_delta",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "output_tokens_delta",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_tokens_delta",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("tool_status", sa.String(length=32), nullable=True),
        sa.Column("error_category", sa.String(length=32), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["agent_session_id"], ["agent_sessions.agent_session_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lane_id"], ["orchestration_lanes.lane_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_session_event_id"),
        sa.UniqueConstraint("agent_session_id", "sequence", name="uq_agent_session_events_session_sequence"),
    )
    op.create_index("ix_agent_session_events_lane_id", "agent_session_events", ["lane_id"], unique=False)
    op.create_index("ix_agent_session_events_event_type", "agent_session_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_session_events_event_type", table_name="agent_session_events")
    op.drop_index("ix_agent_session_events_lane_id", table_name="agent_session_events")
    op.drop_table("agent_session_events")

    with op.batch_alter_table("agent_sessions") as batch_op:
        batch_op.drop_index("ix_agent_sessions_status")
        batch_op.drop_column("policy_snapshot")
        batch_op.drop_column("launch_payload")
        batch_op.drop_column("last_error_category")
        batch_op.drop_column("continuation_summary")
        batch_op.drop_column("wait_reason")
        batch_op.drop_column("heartbeat_at")
        batch_op.drop_column("environment_identity")
        batch_op.drop_column("capabilities")
        batch_op.drop_column("status")
        batch_op.drop_column("runner_session_id")
