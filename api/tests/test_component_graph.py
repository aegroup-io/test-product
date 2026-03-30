from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.models import ComponentEdge, ComponentNode, Organization, Product
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.product_contract import ProductContractService
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


def _write_fixture_repo(
    repo_root: Path,
    *,
    components_relationship: str = "deploys",
    include_extra_service: bool = False,
    components_file: str = ".orcha/components.yaml",
    include_invalid_edge: bool = False,
) -> None:
    (repo_root / ".orcha").mkdir(parents=True, exist_ok=True)
    (repo_root / "AGENTS.md").write_text("# Fixture\n", encoding="utf-8")
    workflows_dir = repo_root / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    (repo_root / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True, exist_ok=True)
    (repo_root / ".github" / "pull_request_template.md").write_text("## Summary\n", encoding="utf-8")
    for workflow_name in ("repo-harness.yml", "advisory-code-review.yml", "merge-readiness.yml"):
        (workflows_dir / workflow_name).write_text("name: Fixture\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "product": {
            "key": "orcha",
            "name": "Orcha",
            "org": "aegroup",
            "description": "fixture repo",
        },
        "github": {
            "owner": "aegroup-io",
            "repo": "orcha",
            "default_branch": "dev",
            "project_number": 4,
            "status_field": "Status",
            "ready_status": "Todo",
            "done_status": "Done",
        },
        "baseline": {
            "channel": "stable",
            "agent_core_version": "0.1.0",
            "standards_pack": "default",
            "managed_assets": [
                {"path": "AGENTS.md", "mode": "managed"},
                {"path": ".github/pull_request_template.md", "mode": "managed"},
            ],
        },
        "execution": {
            "profile": "standard-python",
            "container_image": "ghcr.io/aegroup/agent-core-runner:stable",
            "max_concurrent_lanes": 4,
            "workspace_strategy": "branch-per-lane",
        },
        "graph": {
            "components_file": components_file,
            "auto_discover": True,
        },
        "governance": {
            "require_human_merge": True,
            "allow_agent_comments": True,
            "allow_agent_issue_edits": True,
        },
    }
    (repo_root / ".orcha" / "product.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    components = {
        "schema_version": 1,
        "components": [
            {"key": "orcha", "name": "Orcha", "type": "product", "owner": "aegroup"},
            {"key": "orcha-repo", "name": "orcha", "type": "repository", "owner": "aegroup-io"},
        ],
        "edges": [
            {
                "from": "orcha",
                "to": "orcha-repo",
                "relationship": components_relationship,
            }
        ],
    }
    if include_extra_service:
        components["components"].append(
            {"key": "api-service", "name": "API Service", "type": "service", "owner": "platform"}
        )
        components["edges"].append(
            {"from": "orcha", "to": "api-service", "relationship": "depends_on"}
        )
    if include_invalid_edge:
        components["edges"].append(
            {"from": "orcha", "to": "missing-service", "relationship": "depends_on"}
        )

    components_target = repo_root / components_file
    components_target.parent.mkdir(parents=True, exist_ok=True)
    components_target.write_text(
        yaml.safe_dump(components, sort_keys=False),
        encoding="utf-8",
    )


def _build_adoption_payload(org_id: str, repo_root: Path) -> dict[str, object]:
    return {
        "org_id": org_id,
        "key": "orcha",
        "name": "Orcha",
        "description": "fixture repo",
        "repo_root": str(repo_root),
        "baseline_channel": "stable",
        "agent_core_version": "0.1.0",
        "execution_profile": "standard-python",
        "repository": {
            "github_repository_node_id": "R_kgDOOrchaRepo",
            "owner": "aegroup-io",
            "name": "orcha",
            "default_branch": "dev",
            "visibility": "private",
            "description": "fixture repo",
            "is_archived": False,
            "branch_protection": {
                "enabled": True,
                "requires_pull_request": True,
                "required_approving_review_count": 1,
                "allows_force_pushes": False,
                "allows_deletions": False,
            },
            "permissions": {
                "contents": "write",
                "pull_requests": "write",
                "issues": "write",
                "projects": "write",
            },
        },
        "project": {
            "github_project_node_id": "PVT_kwHOA2LEw84BRqkM",
            "number": 4,
            "title": "Orcha",
            "status_field_name": "Status",
            "status_options": ["Todo", "In Progress", "Done"],
        },
        "operator_overrides": {},
    }


def _seed_product(session) -> Product:
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
        seed_source="github-adoption",
        adoption_state="adopted",
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
    product.primary_repo_id = repo.repo_id
    product.primary_project_id = project.project_id
    session.flush()
    return product


def test_product_adoption_persists_declared_topology_with_provenance() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, components_relationship="deploys")
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()

            response = client.post("/products/adoptions", json=_build_adoption_payload(org_id, repo_root))
            assert response.status_code == 201
            payload = response.json()
            assert payload["product"]["component_root_node_id"] is not None

            verify_session = get_session_factory()()
            try:
                product = verify_session.query(Product).filter(Product.key == "orcha").one()
                root_node = (
                    verify_session.query(ComponentNode)
                    .filter(ComponentNode.product_id == product.product_id, ComponentNode.key == "orcha")
                    .one()
                )
                repo_node = (
                    verify_session.query(ComponentNode)
                    .filter(ComponentNode.product_id == product.product_id, ComponentNode.key == "orcha-repo")
                    .one()
                )
                declared_edge = (
                    verify_session.query(ComponentEdge)
                    .filter(
                        ComponentEdge.from_node_id == root_node.component_node_id,
                        ComponentEdge.to_node_id == repo_node.component_node_id,
                        ComponentEdge.relationship_type == "deploys",
                        ComponentEdge.source_kind == "declared",
                    )
                    .one()
                )
                repo_edge = (
                    verify_session.query(ComponentEdge)
                    .filter(
                        ComponentEdge.from_node_id == root_node.component_node_id,
                        ComponentEdge.to_node_id == repo_node.component_node_id,
                        ComponentEdge.relationship_type == "owns",
                        ComponentEdge.source_kind == "repo-metadata",
                    )
                    .one()
                )

                assert product.component_root_node_id == root_node.component_node_id
                assert root_node.source_kind == "declared"
                assert root_node.source_ref == ".orcha/components.yaml"
                assert root_node.confidence == 1.0
                assert root_node.freshness_status == "current"
                assert root_node.last_verified_at is not None
                assert declared_edge.source_ref == ".orcha/components.yaml"
                assert declared_edge.confidence == 1.0
                assert declared_edge.freshness_status == "current"
                assert repo_edge.source_ref == "aegroup-io/orcha"
            finally:
                verify_session.close()
        _reset_env()


def test_product_graph_endpoint_surfaces_freshness_confidence_and_precedence() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, components_relationship="deploys")
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()

            response = client.post("/products/adoptions", json=_build_adoption_payload(org_id, repo_root))
            assert response.status_code == 201
            product_id = response.json()["product"]["product_id"]

            update_session = get_session_factory()()
            try:
                weak_edge = update_session.query(ComponentEdge).filter(ComponentEdge.source_kind == "repo-metadata").one()
                weak_edge.confidence = 0.4
                weak_edge.last_verified_at = datetime.now(timezone.utc) - timedelta(days=30)
                weak_edge.freshness_status = "current"
                update_session.commit()
            finally:
                update_session.close()

            graph_response = client.get(f"/products/{product_id}/graph")
            assert graph_response.status_code == 200
            graph = graph_response.json()
            edges = {
                (edge["source_kind"], edge["relationship"]): edge
                for edge in graph["edges"]
            }
            declared_edge = edges[("declared", "deploys")]
            repo_edge = edges[("repo-metadata", "owns")]

            assert declared_edge["precedence_state"] == "effective"
            assert declared_edge["freshness_status"] == "current"
            assert declared_edge["confidence_status"] == "confirmed"
            assert repo_edge["precedence_state"] == "shadowed"
            assert repo_edge["freshness_status"] == "stale"
            assert repo_edge["confidence_status"] == "uncertain"
        _reset_env()


def test_refresh_marks_missing_declared_topology_stale() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, include_extra_service=True)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                service = ProductContractService(session)
                service.refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                    operator_overrides={},
                )
                session.commit()

                _write_fixture_repo(repo_root, include_extra_service=False)
                service.refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                    operator_overrides={},
                )
                session.commit()

                stale_node = (
                    session.query(ComponentNode)
                    .filter(ComponentNode.product_id == product.product_id, ComponentNode.key == "api-service")
                    .one()
                )
                root_node = (
                    session.query(ComponentNode)
                    .filter(ComponentNode.product_id == product.product_id, ComponentNode.key == "orcha")
                    .one()
                )
                stale_edge = (
                    session.query(ComponentEdge)
                    .filter(
                        ComponentEdge.from_node_id == root_node.component_node_id,
                        ComponentEdge.to_node_id == stale_node.component_node_id,
                        ComponentEdge.relationship_type == "depends_on",
                        ComponentEdge.source_kind == "declared",
                    )
                    .one()
                )

                assert stale_node.source_kind == "declared"
                assert stale_node.freshness_status == "stale"
                assert stale_edge.freshness_status == "stale"
            finally:
                session.close()
        _reset_env()


def test_refresh_keeps_invalid_declared_edges_as_diagnostics_without_crashing() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, include_invalid_edge=True)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                service = ProductContractService(session)

                result = service.refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                    operator_overrides={},
                )
                session.commit()

                assert "components.edge_target_missing" in {item.code for item in result.diagnostics}
                assert (
                    session.query(ComponentEdge)
                    .filter(
                        ComponentEdge.source_kind == "declared",
                        ComponentEdge.relationship_type == "depends_on",
                    )
                    .count()
                    == 0
                )
            finally:
                session.close()
        _reset_env()


def test_refresh_stales_old_declared_topology_when_components_file_path_changes() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, include_extra_service=True)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                service = ProductContractService(session)
                service.refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                    operator_overrides={},
                )
                session.commit()

                _write_fixture_repo(
                    repo_root,
                    components_file=".orcha/topology.yaml",
                    include_extra_service=False,
                )
                old_components_path = repo_root / ".orcha" / "components.yaml"
                if old_components_path.exists():
                    old_components_path.unlink()
                service.refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                    operator_overrides={},
                )
                session.commit()

                stale_node = (
                    session.query(ComponentNode)
                    .filter(ComponentNode.product_id == product.product_id, ComponentNode.key == "api-service")
                    .one()
                )
                root_node = (
                    session.query(ComponentNode)
                    .filter(ComponentNode.product_id == product.product_id, ComponentNode.key == "orcha")
                    .one()
                )
                stale_edge = (
                    session.query(ComponentEdge)
                    .filter(
                        ComponentEdge.from_node_id == root_node.component_node_id,
                        ComponentEdge.to_node_id == stale_node.component_node_id,
                        ComponentEdge.relationship_type == "depends_on",
                        ComponentEdge.source_kind == "declared",
                    )
                    .one()
                )

                assert stale_node.source_ref == ".orcha/components.yaml"
                assert stale_node.freshness_status == "stale"
                assert stale_edge.source_ref == ".orcha/components.yaml"
                assert stale_edge.freshness_status == "stale"
            finally:
                session.close()
        _reset_env()
