from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_engine, get_session_factory, reset_database_state
from agent_core_platform_api.models import AIProvider, Organization, Product
from agent_core_platform_api.orcha_state import OrchaStateStore
from orcha_api.main import app


def _configure_env(database_url: str) -> None:
    os.environ["AGENT_CORE_AUTH_DISABLED"] = "1"
    os.environ["AGENT_CORE_DATABASE_URL"] = database_url
    os.environ["AGENT_CORE_CRYPTO_SEED"] = "agent-core-test-seed"
    os.environ["AGENT_CORE_INITIAL_ORG_NAME"] = "Primary"
    os.environ["AGENT_CORE_INITIAL_ORG_SLUG"] = "primary"
    get_settings.cache_clear()
    reset_database_state()


def _reset_env() -> None:
    get_settings.cache_clear()
    reset_database_state()


def test_orcha_foundation_tables_exist_after_startup() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            summary = client.get("/platform/summary")
            assert summary.status_code == 200
            payload = summary.json()
            assert payload["product_count"] == 0
            assert payload["repository_binding_count"] == 0
            assert payload["lane_count"] == 0
            assert payload["component_node_count"] == 0
            assert payload["webhook_delivery_count"] == 0

            table_names = set(inspect(get_engine()).get_table_names())
            assert {
                "products",
                "repository_bindings",
                "github_project_mirrors",
                "work_items",
                "orchestration_lanes",
                "execution_environments",
                "agent_sessions",
                "agent_session_events",
                "managed_assets",
                "component_nodes",
                "component_edges",
                "operational_signals",
                "webhook_deliveries",
            }.issubset(table_names)
        _reset_env()


def test_orcha_state_store_persists_foundation_entities_without_ai_seed_data() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org = session.query(Organization).filter(Organization.slug == "primary").one()
                store = OrchaStateStore(session)

                product = store.create_product(
                    org_id=org.org_id,
                    key="orcha",
                    name="Orcha",
                    status="Draft",
                    baseline_channel="stable",
                    agent_core_version="0.1.0",
                    execution_profile="standard-python",
                )
                repo = store.bind_repository(
                    product_id=product.product_id,
                    github_repository_node_id="R_kgDOOrchaRepo",
                    owner="aegroup-io",
                    name="orcha",
                    default_branch="dev",
                    visibility="private",
                    seed_source="agent-core",
                    adoption_state="seeded",
                )
                project = store.create_project_mirror(
                    product_id=product.product_id,
                    github_project_node_id="PVT_kwHOA2LEw84BRqkM",
                    number=4,
                    title="Orcha",
                    status_field_name="Status",
                    status_options=["Todo", "In Progress", "Done"],
                    mirror_version=1,
                )
                work_item = store.create_work_item(
                    repo_id=repo.repo_id,
                    project_id=project.project_id,
                    github_issue_node_id="I_kwDOOrchaIssue8",
                    issue_number=8,
                    title="Model durable control-plane state",
                    status="Ready",
                    labels=["type:feature"],
                    assignees=[],
                    dependencies=[],
                    linked_prs=[],
                )
                lane = store.create_lane(
                    product_id=product.product_id,
                    repo_id=repo.repo_id,
                    work_item_id=work_item.work_item_id,
                    attempt=1,
                    state="Queued",
                )
                environment = store.create_execution_environment(
                    lane_id=lane.lane_id,
                    runtime_provider="aks",
                    container_image="ghcr.io/aegroup/orcha:dev",
                    status="Provisioning",
                )
                agent_session = store.create_agent_session(
                    lane_id=lane.lane_id,
                    thread_id="thread-1",
                    turn_id="turn-1",
                    runner_version="0.1.0",
                    last_event="session_started",
                )
                store.create_managed_asset(
                    product_id=product.product_id,
                    path="AGENTS.md",
                    kind="markdown",
                    management_mode="managed",
                )
                product_node = store.create_component_node(
                    product_id=product.product_id,
                    type="product",
                    key="orcha",
                    name="Orcha",
                    source_kind="declared",
                )
                repo_node = store.create_component_node(
                    product_id=product.product_id,
                    type="repository",
                    key="orcha-repo",
                    name="orcha",
                    source_kind="declared",
                )
                store.create_component_edge(
                    from_node_id=product_node.component_node_id,
                    to_node_id=repo_node.component_node_id,
                    relationship="owns",
                    source_kind="declared",
                    confidence=1.0,
                )
                store.record_operational_signal(
                    target_kind="lane",
                    target_id=str(lane.lane_id),
                    signal_type="health",
                    severity="info",
                    value={"state": "queued"},
                    source_kind="system",
                )
                store.record_webhook_delivery(
                    github_delivery_guid="delivery-1",
                    event_name="issues",
                    installation_id="12345",
                    status="received",
                    payload_hash="payload-hash-1",
                )

                product.primary_repo_id = repo.repo_id
                product.primary_project_id = project.project_id
                product.component_root_node_id = product_node.component_node_id
                lane.execution_environment_id = environment.execution_environment_id
                lane.agent_session_id = agent_session.agent_session_id
                session.commit()

                assert session.query(AIProvider).count() == 0
                assert [item.key for item in store.list_products(org_id=org.org_id)] == ["orcha"]

                persisted_product = session.get(Product, product.product_id)
                assert persisted_product is not None
                assert persisted_product.primary_repo_id == repo.repo_id
                assert persisted_product.primary_project_id == project.project_id
                assert persisted_product.component_root_node_id == product_node.component_node_id

                summary = client.get("/platform/summary")
                assert summary.status_code == 200
                payload = summary.json()
                assert payload["product_count"] == 1
                assert payload["repository_binding_count"] == 1
                assert payload["lane_count"] == 1
                assert payload["component_node_count"] == 2
                assert payload["webhook_delivery_count"] == 1
            finally:
                session.close()
        _reset_env()
