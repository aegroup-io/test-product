"""Add an active-lane ownership guard for work-item claims."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_scheduler_lane_claim_guard"
down_revision = "0008_product_seed_jobs"
branch_labels = None
depends_on = None


_ACTIVE_LANE_OWNERSHIP_PREDICATE = sa.text(
    "state IN ('Queued', 'Claimed', 'Provisioning', 'Running', 'AwaitingApproval', 'AwaitingGitHub', 'RetryPending')"
)
_DUPLICATE_ACTIVE_LANE_CLEANUP = sa.text(
    """
    WITH ranked AS (
        SELECT
            lane_id,
            ROW_NUMBER() OVER (
                PARTITION BY work_item_id
                ORDER BY
                    CASE WHEN claimed_at IS NULL THEN 1 ELSE 0 END,
                    claimed_at,
                    created_at,
                    lane_id
            ) AS lane_rank
        FROM orchestration_lanes
        WHERE state IN ('Queued', 'Claimed', 'Provisioning', 'Running', 'AwaitingApproval', 'AwaitingGitHub', 'RetryPending')
    )
    UPDATE orchestration_lanes
    SET
        state = 'Cancelled',
        finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP),
        last_error = COALESCE(
            NULLIF(last_error, ''),
            'Auto-cancelled by migration 0009: duplicate active lane ownership existed for the same work item.'
        )
    WHERE lane_id IN (SELECT lane_id FROM ranked WHERE lane_rank > 1)
    """
)
_REMAINING_DUPLICATE_CHECK = sa.text(
    """
    SELECT COUNT(*)
    FROM (
        SELECT work_item_id
        FROM orchestration_lanes
        WHERE state IN ('Queued', 'Claimed', 'Provisioning', 'Running', 'AwaitingApproval', 'AwaitingGitHub', 'RetryPending')
        GROUP BY work_item_id
        HAVING COUNT(*) > 1
    ) AS duplicate_work_items
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(_DUPLICATE_ACTIVE_LANE_CLEANUP)
    remaining_duplicates = bind.execute(_REMAINING_DUPLICATE_CHECK).scalar_one()
    if remaining_duplicates:
        raise RuntimeError(
            "Unable to enforce unique active-lane ownership: duplicate active lanes remain after migration cleanup."
        )
    op.create_index(
        "ix_orchestration_lanes_active_work_item",
        "orchestration_lanes",
        ["work_item_id"],
        unique=True,
        sqlite_where=_ACTIVE_LANE_OWNERSHIP_PREDICATE,
        postgresql_where=_ACTIVE_LANE_OWNERSHIP_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index("ix_orchestration_lanes_active_work_item", table_name="orchestration_lanes")
