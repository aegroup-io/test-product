from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.models import Organization, Product, Secret, Setting
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
    schema_version: int = 1,
    managed_asset_mode: str = "managed",
    baseline_channel: str = "stable",
    max_concurrent_lanes: int = 4,
    require_human_merge: bool = True,
    approval_posture: str = "high-trust",
    include_agents: bool = True,
    include_pr_template: bool = True,
    include_issue_templates: bool = True,
    include_baseline_workflows: bool = True,
    include_components: bool = True,
    components_relationship: str = "deploys",
    components_file: str = ".orcha/components.yaml",
) -> None:
    (repo_root / ".orcha").mkdir(parents=True, exist_ok=True)
    if include_agents:
        (repo_root / "AGENTS.md").write_text("# Fixture\n", encoding="utf-8")
    if include_pr_template:
        github_dir = repo_root / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        (github_dir / "pull_request_template.md").write_text("## Summary\n", encoding="utf-8")
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
        "schema_version": schema_version,
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
            "channel": baseline_channel,
            "agent_core_version": "0.1.0",
            "standards_pack": "default",
            "managed_assets": [
                {"path": "AGENTS.md", "mode": managed_asset_mode},
                {"path": ".github/pull_request_template.md", "mode": "managed"},
            ],
        },
        "execution": {
            "profile": "standard-python",
            "container_image": "ghcr.io/aegroup/agent-core-runner:stable",
            "max_concurrent_lanes": max_concurrent_lanes,
            "workspace_strategy": "branch-per-lane",
        },
        "graph": {
            "components_file": components_file,
            "auto_discover": True,
        },
        "governance": {
            "approval_posture": approval_posture,
            "require_human_merge": require_human_merge,
            "allow_agent_comments": True,
            "allow_agent_issue_edits": True,
            "allow_agent_pr_edits": True,
        },
    }
    (repo_root / ".orcha" / "product.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    if include_components:
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
                    "relationship": components_relationship,
                }
            ],
        }
        (repo_root / ".orcha" / "components.yaml").write_text(
            yaml.safe_dump(components, sort_keys=False),
            encoding="utf-8",
        )


def _seed_product(session) -> Product:
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    product = store.create_product(
        org_id=org.org_id,
        key="orcha",
        name="Orcha",
        status="Draft",
        baseline_channel="record-default",
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
    product.primary_repo_id = repo.repo_id
    product.primary_project_id = project.project_id
    session.flush()
    return product


def test_manifest_parser_rejects_invalid_versions_and_component_relationships() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _write_fixture_repo(
            repo_root,
            schema_version=2,
            managed_asset_mode="unsupported",
            components_relationship="unknown",
        )

        with tempfile.TemporaryDirectory() as db_dir:
            _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
            with TestClient(app):
                session = get_session_factory()()
                try:
                    product = _seed_product(session)
                    service = ProductContractService(session)
                    try:
                        service.parse_product_manifest(repo_root)
                        assert False, "parse_product_manifest should reject unsupported schema versions"
                    except ValueError as exc:
                        assert "Unsupported product manifest schema_version" in str(exc) or "Unsupported managed asset mode" in str(exc)

                    _write_fixture_repo(repo_root, components_relationship="unknown")
                    try:
                        service.parse_components_manifest(repo_root, ".orcha/components.yaml")
                        assert False, "parse_components_manifest should reject unsupported relationships"
                    except ValueError as exc:
                        assert "Unsupported component edge relationship" in str(exc)

                    assert session.get(Product, product.product_id) is not None
                finally:
                    session.close()
            _reset_env()


def test_product_contract_refresh_resolves_precedence_and_preserves_higher_level_safety() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(
            repo_root,
            baseline_channel="repo-channel",
            max_concurrent_lanes=5,
            require_human_merge=False,
        )

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product.standards_pack_key = "preview"
                product.standards_pack_version = "2026.03.16"
                session.commit()
                org_defaults = Setting(
                    scope_type="org",
                    scope_id=str(product.org_id),
                    key="orcha.product_defaults",
                    value_json={
                        "execution": {"max_concurrent_lanes": 3},
                        "activation": {"required_secret_keys": ["github-app-token"]},
                    },
                )
                session.add(org_defaults)
                session.add(
                    Secret(
                        key="github-app-token",
                        name="GitHub App Token",
                        kind="github_webhook_secret",
                        value_ciphertext="ciphertext",
                    )
                )
                session.commit()

                service = ProductContractService(session)
                result = service.refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                    operator_overrides={"execution": {"max_concurrent_lanes": 2}},
                )
                session.commit()

                persisted = session.get(Product, product.product_id)
                assert persisted is not None
                assert persisted.status == "Active"
                assert persisted.standards_pack_key == "preview"
                assert persisted.standards_pack_version == "2026.03.16"
                assert result.setup_state == "advisory"
                assert result.manifest_schema_version == 1
                assert result.effective_config["baseline"]["channel"] == "repo-channel"
                assert result.effective_config["execution"]["max_concurrent_lanes"] == 2
                assert result.effective_config["governance"]["require_human_merge"] is True
                assert any(item.code == "governance.require_human_merge_capped" for item in result.diagnostics)
                assert persisted.last_accepted_config_at is not None
            finally:
                session.close()
        _reset_env()


def test_product_contract_refresh_caps_governance_posture_and_pr_edit_policy() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, approval_posture="high-trust")

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                session.add(
                    Setting(
                        scope_type="org",
                        scope_id=str(product.org_id),
                        key="orcha.product_defaults",
                        value_json={
                            "governance": {
                                "approval_posture": "operator-gated",
                                "pr_edit_policy": "blocked",
                            }
                        },
                    )
                )
                session.commit()

                result = ProductContractService(session).refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                )
                session.commit()

                assert result.effective_config["governance"]["approval_posture"] == "operator-gated"
                assert result.effective_config["governance"]["pr_edit_policy"] == "blocked"
                assert any(item.code == "governance.approval_posture_capped" for item in result.diagnostics)
                assert any(item.code == "governance.pr_edit_policy_capped" for item in result.diagnostics)
            finally:
                session.close()
        _reset_env()


def test_product_contract_refresh_defaults_to_high_trust_when_manifest_omits_posture() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, approval_posture="high-trust")
        manifest_path = repo_root / ".orcha" / "product.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["governance"].pop("approval_posture", None)
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)

                result = ProductContractService(session).refresh_product_contract(
                    product_id=product.product_id,
                    repo_root=repo_root,
                )
                session.commit()

                assert result.effective_config["governance"]["approval_posture"] == "high-trust"
                assert result.effective_config["governance"]["repo_write_policy"] is None
            finally:
                session.close()
        _reset_env()


def test_product_contract_refresh_blocks_activation_for_missing_assets_and_secrets() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(
            repo_root,
            include_agents=False,
            include_pr_template=False,
            include_issue_templates=False,
        )

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                session.add(
                    Setting(
                        scope_type="org",
                        scope_id=str(product.org_id),
                        key="orcha.product_defaults",
                        value_json={"activation": {"required_secret_keys": ["github-app-token"]}},
                    )
                )
                session.commit()

                service = ProductContractService(session)
                result = service.refresh_product_contract(product_id=product.product_id, repo_root=repo_root)
                session.commit()

                persisted = session.get(Product, product.product_id)
                assert persisted is not None
                assert persisted.status == "Draft"
                assert result.setup_state == "setup-needed"
                assert result.effective_config == {}
                assert any(item.code == "asset.required_missing" for item in result.diagnostics)
                assert any(item.code == "secret.required_missing" for item in result.diagnostics)
            finally:
                session.close()
        _reset_env()


def test_product_contract_refresh_records_malformed_yaml_as_blocking_diagnostics() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root)

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                service = ProductContractService(session)

                (repo_root / ".orcha" / "product.yaml").write_text("schema_version: [\n", encoding="utf-8")
                broken_manifest = service.refresh_product_contract(product_id=product.product_id, repo_root=repo_root)
                session.commit()

                assert broken_manifest.setup_state == "setup-needed"
                assert any(item.code == "manifest.invalid" for item in broken_manifest.diagnostics)

                _write_fixture_repo(repo_root)
                (repo_root / ".orcha" / "components.yaml").write_text("schema_version: [\n", encoding="utf-8")
                broken_components = service.refresh_product_contract(product_id=product.product_id, repo_root=repo_root)
                session.commit()

                assert broken_components.setup_state == "setup-needed"
                assert any(item.code == "components.invalid" for item in broken_components.diagnostics)
            finally:
                session.close()
        _reset_env()


def test_product_contract_refresh_blocks_components_paths_outside_repo_root() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, components_file="../outside-components.yaml")

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                service = ProductContractService(session)

                result = service.refresh_product_contract(product_id=product.product_id, repo_root=repo_root)
                session.commit()

                assert result.setup_state == "setup-needed"
                assert any(item.code == "components.invalid" for item in result.diagnostics)
            finally:
                session.close()
        _reset_env()


def test_product_contract_refresh_reloads_accepted_configuration_without_restart() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root, baseline_channel="stable", max_concurrent_lanes=4)

        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                service = ProductContractService(session)

                first = service.refresh_product_contract(product_id=product.product_id, repo_root=repo_root)
                session.commit()
                persisted = session.get(Product, product.product_id)
                assert persisted is not None
                first_accept_time = persisted.last_accepted_config_at
                assert first.setup_state == "ready"
                assert first.effective_config["baseline"]["channel"] == "stable"

                _write_fixture_repo(repo_root, baseline_channel="candidate", max_concurrent_lanes=2)
                second = service.refresh_product_contract(product_id=product.product_id, repo_root=repo_root)
                session.commit()

                refreshed = session.get(Product, product.product_id)
                assert refreshed is not None
                assert second.setup_state == "ready"
                assert second.effective_config["baseline"]["channel"] == "candidate"
                assert second.effective_config["execution"]["max_concurrent_lanes"] == 2
                assert refreshed.last_accepted_config_at is not None
                assert first_accept_time is not None
                assert refreshed.last_accepted_config_at != first_accept_time
            finally:
                session.close()
        _reset_env()
