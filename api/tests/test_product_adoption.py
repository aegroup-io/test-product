from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.models import Organization, Product
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
    include_agents: bool = True,
    include_pr_template: bool = True,
    include_issue_templates: bool = True,
    include_baseline_workflows: bool = True,
) -> None:
    (repo_root / ".orcha").mkdir(parents=True, exist_ok=True)
    if include_agents:
        (repo_root / "AGENTS.md").write_text("# Fixture\n", encoding="utf-8")
    if include_pr_template:
        (repo_root / ".github").mkdir(parents=True, exist_ok=True)
        (repo_root / ".github" / "pull_request_template.md").write_text("## Summary\n", encoding="utf-8")
    if include_issue_templates:
        (repo_root / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True, exist_ok=True)
    if include_baseline_workflows:
        workflows_dir = repo_root / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        for workflow_name in (
            "repo-harness.yml",
            "advisory-code-review.yml",
            "merge-readiness.yml",
        ):
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
            "components_file": ".orcha/components.yaml",
            "auto_discover": True,
        },
        "governance": {
            "approval_posture": "high-trust",
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
            {"key": "orcha", "name": "Orcha", "type": "product"},
            {"key": "orcha-repo", "name": "orcha", "type": "repository"},
        ],
        "edges": [
            {
                "from": "orcha",
                "to": "orcha-repo",
                "relationship": "owns",
            }
        ],
    }
    (repo_root / ".orcha" / "components.yaml").write_text(
        yaml.safe_dump(components, sort_keys=False),
        encoding="utf-8",
    )


def _build_payload(org_id: str, repo_root: Path) -> dict[str, object]:
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


def test_product_adoption_dry_run_surfaces_setup_needed_without_persisting() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, include_baseline_workflows=False)

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org = session.query(Organization).filter(Organization.slug == "primary").one()
            finally:
                session.close()

            payload = _build_payload(str(org.org_id), repo_root)
            payload["repository"]["branch_protection"]["enabled"] = False
            payload["repository"]["permissions"]["projects"] = "read"

            response = client.post("/products/adoptions/dry-run", json=payload)
            assert response.status_code == 200
            result = response.json()
            assert result["dry_run"] is True
            assert result["product"]["setup_state"] == "setup-needed"
            diagnostic_codes = {item["code"] for item in result["product"]["setup_diagnostics"]}
            assert "github.branch_protection_missing" in diagnostic_codes
            assert "github.permission_projects_write_missing" in diagnostic_codes
            assert "asset.required_missing" in diagnostic_codes
            managed_assets = {item["path"]: item["drift_status"] for item in result["product"]["managed_assets"]}
            assert managed_assets[".github/workflows/merge-readiness.yml"] == "missing-required"

            verify_session = get_session_factory()()
            try:
                assert verify_session.query(Product).count() == 0
            finally:
                verify_session.close()
        _reset_env()


def test_product_adoption_persists_compatible_repo_with_ready_state() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root)

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org = session.query(Organization).filter(Organization.slug == "primary").one()
            finally:
                session.close()

            response = client.post("/products/adoptions", json=_build_payload(str(org.org_id), repo_root))
            assert response.status_code == 201
            result = response.json()
            assert result["dry_run"] is False
            assert result["product"]["status"] == "Active"
            assert result["product"]["setup_state"] == "ready"
            assert result["product"]["primary_repo"]["adoption_state"] == "adopted"
            managed_assets = {item["path"]: item["drift_status"] for item in result["product"]["managed_assets"]}
            assert managed_assets["AGENTS.md"] is None
            assert managed_assets[".github/workflows/repo-harness.yml"] is None

            verify_session = get_session_factory()()
            try:
                persisted = verify_session.query(Product).filter(Product.key == "orcha").one()
                assert persisted.status == "Active"
                assert persisted.setup_state == "ready"
            finally:
                verify_session.close()
        _reset_env()


def test_product_adoption_persists_recoverable_drift_without_blocking_activation() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, include_issue_templates=False)

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org = session.query(Organization).filter(Organization.slug == "primary").one()
            finally:
                session.close()

            payload = _build_payload(str(org.org_id), repo_root)
            payload["repository"]["branch_protection"]["allows_force_pushes"] = True

            response = client.post("/products/adoptions", json=payload)
            assert response.status_code == 201
            result = response.json()
            assert result["product"]["status"] == "Active"
            assert result["product"]["setup_state"] == "drift"
            diagnostic_codes = {item["code"] for item in result["product"]["setup_diagnostics"]}
            assert "asset.recommended_missing" in diagnostic_codes
            assert "github.branch_protection_force_push_allowed" in diagnostic_codes
            managed_assets = {item["path"]: item["drift_status"] for item in result["product"]["managed_assets"]}
            assert managed_assets[".github/ISSUE_TEMPLATE"] == "missing-managed"
        _reset_env()
