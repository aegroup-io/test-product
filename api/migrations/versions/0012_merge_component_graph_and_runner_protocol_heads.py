"""Merge component-graph and runner-protocol migration heads."""

from __future__ import annotations


revision = "0012_merge_component_graph_and_runner_protocol_heads"
down_revision = (
    "0011_component_graph_provenance_and_freshness",
    "0011_runner_protocol_session_events",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
