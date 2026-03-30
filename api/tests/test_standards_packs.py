from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
import httpx

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.models import (
    ManagedAsset,
    Organization,
    Product,
    RepositoryBinding,
    StandardsFollowUpItem,
    StandardsUpgradeRun,
)
import agent_core_platform_api.standards_packs as standards_packs_module
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
    os.environ.pop("AGENT_CORE_ALLOWED_REPO_ROOTS", None)
    get_settings.cache_clear()
    reset_database_state()


def _seed_product(session) -> Product:
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    product = store.create_product(
        org_id=org.org_id,
        key="orcha",
        name="Orcha",
        status="Active",
        baseline_channel="stable",
        standards_pack_key="default",
        standards_pack_version="0.1.0",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id="R_standards_repo",
        owner="aegroup-io",
        name="orcha",
        default_branch="dev",
        visibility="private",
        description="fixture repo",
        seed_source="agent-core",
        adoption_state="adopted",
    )
    project = store.create_project_mirror(
        product_id=product.product_id,
        github_project_node_id="PVT_standards_project",
        number=4,
        title="Orcha",
        status_field_name="Status",
        status_options=["Todo", "In Progress", "Done"],
        mirror_version=1,
    )
    product.primary_repo_id = repo.repo_id
    product.primary_project_id = project.project_id
    session.commit()
    return product


def _create_pack(client: TestClient, *, version: str = "2026.03.16", section_path: str = "docs/guide.md") -> None:
    response = client.post(
        "/standards-packs",
        json={
            "key": "default",
            "channel": "stable",
            "version": version,
            "source_bundle": "org://baseline/default",
            "description": "Fixture standards pack",
            "manifest": {"baseline": {"channel": "stable"}},
            "assets": [
                {
                    "path": "AGENTS.md",
                    "default_mode": "managed",
                    "content_text": "# Managed Agents\n",
                },
                {
                    "path": section_path,
                    "default_mode": "section-managed",
                    "content_text": (
                        "# Guide\n\n"
                        "Local intro\n\n"
                        "<!-- orcha:begin harness -->\n"
                        "Managed upgrade content\n"
                        "<!-- orcha:end harness -->\n\n"
                        "Local footer\n"
                    ),
                },
                {
                    "path": "docs/checklist.md",
                    "default_mode": "advisory",
                    "content_text": "# Checklist\n\n- upstream\n",
                },
                {
                    "path": "docs/local-notes.md",
                    "default_mode": "local",
                    "content_text": "# Local Notes\n",
                },
            ],
        },
    )
    assert response.status_code == 201


def test_standards_evaluation_generates_reviewable_upgrade_run_and_records_acceptance() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")
        (repo_root / "docs" / "guide.md").write_text(
            (
                "# Guide\n\n"
                "Product-specific intro\n\n"
                "<!-- orcha:begin harness -->\n"
                "Old managed content\n"
                "<!-- orcha:end harness -->\n\n"
                "Product-specific footer\n"
            ),
            encoding="utf-8",
        )
        (repo_root / "docs" / "checklist.md").write_text("# Checklist\n\n- local drift\n", encoding="utf-8")
        (repo_root / "docs" / "local-notes.md").write_text("# Local Notes\n\nKeep local.\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_uuid = product.product_id
                product_id = str(product.product_id)
            finally:
                session.close()

            _create_pack(client)
            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.16",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            assert payload["outcome_kind"] == "upgrade-pr"
            assert payload["outcome_status"] == "reviewable"
            actions = {item["path"]: item["action"] for item in payload["assets"]}
            assert actions["AGENTS.md"] == "update-file"
            assert actions["docs/guide.md"] == "refresh-sections"
            assert actions["docs/checklist.md"] == "advisory-drift"
            assert actions["docs/local-notes.md"] == "local-only"
            assert payload["follow_up_items"] == []

            run_id = payload["standards_upgrade_run_id"]
            accept = client.post(
                f"/standards/runs/{run_id}/outcome",
                json={"outcome_status": "accepted", "generated_pr_number": 42},
            )
            assert accept.status_code == 200
            accepted = accept.json()
            assert accepted["generated_pr_number"] == 42
            assert accepted["outcome_status"] == "accepted"

            runs = client.get(f"/products/{product_id}/standards/runs")
            assert runs.status_code == 200
            assert len(runs.json()) == 1

            verify = get_session_factory()()
            try:
                persisted = verify.query(Product).filter(Product.product_id == product_uuid).one()
                assert persisted.standards_pack_key == "default"
                assert persisted.standards_pack_version == "2026.03.16"

                managed_assets = {
                    item.path: item
                    for item in verify.query(ManagedAsset).filter(ManagedAsset.product_id == product_uuid).all()
                }
                assert managed_assets["AGENTS.md"].drift_status == "current"
                assert managed_assets["AGENTS.md"].last_pr_number == 42
                assert managed_assets["docs/guide.md"].drift_status == "current"
                assert managed_assets["docs/checklist.md"].drift_status == "advisory-reviewed"
            finally:
                verify.close()
        _reset_env()


def test_standards_evaluation_materializes_upgrade_branch_and_pull_request(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")
        (repo_root / "docs" / "guide.md").write_text(
            (
                "# Guide\n\n"
                "Product-specific intro\n\n"
                "<!-- orcha:begin harness -->\n"
                "Old managed content\n"
                "<!-- orcha:end harness -->\n\n"
                "Product-specific footer\n"
            ),
            encoding="utf-8",
        )
        (repo_root / "docs" / "checklist.md").write_text("# Checklist\n\n- local drift\n", encoding="utf-8")
        (repo_root / "docs" / "local-notes.md").write_text("# Local Notes\n\nKeep local.\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        request_log: list[tuple[str, str]] = []
        commit_index = {"value": 0}

        def fake_get(url: str, **kwargs) -> httpx.Response:
            request_log.append(("GET", url))
            if url.endswith("/git/ref/heads/dev"):
                return httpx.Response(status_code=200, json={"object": {"sha": "base-sha"}})
            if "/contents/" in url:
                return httpx.Response(status_code=200, json={"sha": "existing-file-sha"})
            return httpx.Response(status_code=404, json={"message": "not found"})

        def fake_post(url: str, **kwargs) -> httpx.Response:
            request_log.append(("POST", url))
            if url.endswith("/git/refs"):
                return httpx.Response(status_code=201, json={"ref": kwargs.get("json", {}).get("ref")})
            if url.endswith("/pulls"):
                return httpx.Response(
                    status_code=201,
                    json={"number": 317, "html_url": "https://github.example/aegroup-io/orcha/pull/317"},
                )
            return httpx.Response(status_code=200, json={})

        def fake_put(url: str, **kwargs) -> httpx.Response:
            request_log.append(("PUT", url))
            if "/contents/" in url:
                commit_index["value"] += 1
                return httpx.Response(status_code=200, json={"commit": {"sha": f"commit-sha-{commit_index['value']}"}})
            return httpx.Response(status_code=404, json={"message": "not found"})

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_uuid = product.product_id
                product_id = str(product.product_id)
                publisher = standards_packs_module.GitHubStandardsUpgradePublisher(
                    session,
                    http_get=fake_get,
                    http_post=fake_post,
                    http_put=fake_put,
                )
                monkeypatch.setattr(
                    publisher,
                    "_load_token_and_api_base",
                    lambda installation_id: ("fake-token", "https://api.github.test"),
                )
                monkeypatch.setattr(
                    standards_packs_module,
                    "build_standards_upgrade_publisher",
                    lambda _session: publisher,
                )
            finally:
                session.close()

            _create_pack(client)
            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.16",
                    "installation_id": "12345",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            assert payload["generated_pr_number"] == 317
            provenance = payload["summary_payload"]["pr_provenance"]
            assert provenance["status"] == "created"
            assert provenance["pull_request_number"] == 317
            assert provenance["pull_request_url"] == "https://github.example/aegroup-io/orcha/pull/317"
            assert provenance["base_branch"] == "dev"
            assert provenance["head_branch"].startswith("orcha/standards/orcha/2026.03.16/")
            assert provenance["commit_shas"] == ["commit-sha-1", "commit-sha-2"]
            assert ("POST", "https://api.github.test/repos/aegroup-io/orcha/git/refs") in request_log
            assert ("POST", "https://api.github.test/repos/aegroup-io/orcha/pulls") in request_log
            assert ("PUT", "https://api.github.test/repos/aegroup-io/orcha/contents/AGENTS.md") in request_log
            assert ("PUT", "https://api.github.test/repos/aegroup-io/orcha/contents/docs/guide.md") in request_log

            verify = get_session_factory()()
            try:
                managed_assets = {
                    item.path: item
                    for item in verify.query(ManagedAsset).filter(ManagedAsset.product_id == product_uuid).all()
                }
                assert managed_assets["AGENTS.md"].last_pr_number == 317
                assert managed_assets["docs/guide.md"].last_pr_number == 317
            finally:
                verify.close()
        _reset_env()


def test_advisory_only_standards_run_remains_pr_free(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "docs" / "checklist.md").write_text("# Checklist\n\n- local drift\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        publish_calls: list[str] = []

        class _ForbiddenPublisher:
            def publish(self, **kwargs):
                publish_calls.append("called")
                raise AssertionError("advisory-only runs must not materialize pull requests")

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_id = str(product.product_id)
                monkeypatch.setattr(
                    standards_packs_module,
                    "build_standards_upgrade_publisher",
                    lambda _session: _ForbiddenPublisher(),
                )
            finally:
                session.close()

            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.26",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "docs/checklist.md",
                            "default_mode": "advisory",
                            "content_text": "# Checklist\n\n- upstream\n",
                        }
                    ],
                },
            )
            assert response.status_code == 201

            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.26",
                    "installation_id": "12345",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            assert payload["outcome_kind"] == "advisory"
            assert payload["generated_pr_number"] is None
            assert "pr_provenance" not in payload["summary_payload"]
            assert publish_calls == []
        _reset_env()


def test_standards_override_can_defer_a_pack_change() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "docs" / "guide.md").write_text(
            (
                "# Guide\n\n"
                "Local intro\n\n"
                "<!-- orcha:begin harness -->\n"
                "Managed upgrade content\n"
                "<!-- orcha:end harness -->\n\n"
                "Local footer\n"
            ),
            encoding="utf-8",
        )
        (repo_root / "docs" / "checklist.md").write_text("# Checklist\n\n- upstream\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_uuid = product.product_id
                product_id = str(product.product_id)
            finally:
                session.close()

            _create_pack(client, version="2026.03.17")
            override = client.post(
                f"/products/{product_id}/standards/overrides",
                json={
                    "path": "AGENTS.md",
                    "is_deferred": True,
                    "reason": "Repo-owned instructions still being rewritten.",
                },
            )
            assert override.status_code == 200

            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.17",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            actions = {item["path"]: item["action"] for item in payload["assets"]}
            assert actions["AGENTS.md"] == "deferred"
            assert actions["docs/guide.md"] == "noop"
            assert actions["docs/checklist.md"] == "noop"
            assert payload["outcome_status"] == "deferred"
            run_id = payload["standards_upgrade_run_id"]

            outcome = client.post(
                f"/standards/runs/{run_id}/outcome",
                json={"outcome_status": "deferred"},
            )
            assert outcome.status_code == 200

            verify = get_session_factory()()
            try:
                run = verify.query(StandardsUpgradeRun).filter(StandardsUpgradeRun.product_id == product_uuid).one()
                assert run.summary_payload["counts"]["deferred"] == 1
                managed_assets = {
                    item.path: item
                    for item in verify.query(ManagedAsset).filter(ManagedAsset.product_id == product_uuid).all()
                }
                assert managed_assets["AGENTS.md"].drift_status == "deferred"
                assert managed_assets["docs/guide.md"].drift_status == "current"
                assert managed_assets["docs/checklist.md"].drift_status == "current"
            finally:
                verify.close()
        _reset_env()


def test_section_managed_conflict_creates_follow_up_item() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")
        (repo_root / "docs" / "guide.md").write_text("# Guide without markers\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_id = str(product.product_id)
            finally:
                session.close()

            _create_pack(client, version="2026.03.18")
            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.18",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            assert payload["outcome_status"] == "conflict"
            follow_ups = payload["follow_up_items"]
            assert len(follow_ups) == 1
            assert follow_ups[0]["path"] == "docs/guide.md"

            verify = get_session_factory()()
            try:
                stored_follow_up = verify.query(StandardsFollowUpItem).one()
                assert stored_follow_up.path == "docs/guide.md"
                assert "ownership delimiters" in stored_follow_up.detail.lower()

                repo_binding = verify.query(RepositoryBinding).one()
                verify.delete(repo_binding)
                verify.commit()

                persisted_run = verify.query(StandardsUpgradeRun).one()
                persisted_follow_up = verify.query(StandardsFollowUpItem).one()
                assert persisted_run.repo_id is None
                assert persisted_follow_up.repo_id is None
            finally:
                verify.close()
        _reset_env()


def test_section_managed_conflict_when_local_has_removed_upstream_section() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")
        (repo_root / "docs" / "guide.md").write_text(
            (
                "# Guide\n\n"
                "<!-- orcha:begin harness -->\n"
                "Current section\n"
                "<!-- orcha:end harness -->\n\n"
                "<!-- orcha:begin legacy -->\n"
                "Stale section\n"
                "<!-- orcha:end legacy -->\n"
            ),
            encoding="utf-8",
        )

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_id = str(product.product_id)
            finally:
                session.close()

            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.23",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "docs/guide.md",
                            "default_mode": "section-managed",
                            "content_text": (
                                "# Guide\n\n"
                                "<!-- orcha:begin harness -->\n"
                                "Current section\n"
                                "<!-- orcha:end harness -->\n"
                            ),
                        }
                    ],
                },
            )
            assert response.status_code == 201

            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.23",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            assert payload["outcome_status"] == "conflict"
            assert "no longer present upstream" in payload["assets"][0]["detail"]
        _reset_env()


def test_standards_pack_rejects_paths_outside_repo_root() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.19",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "../outside.md",
                            "default_mode": "managed",
                            "content_text": "bad",
                        }
                    ],
                },
            )
            assert response.status_code == 400
            assert "escapes repo root" in response.json()["detail"]
        _reset_env()


def test_standards_pack_rejects_duplicate_asset_paths() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.22",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "AGENTS.md",
                            "default_mode": "managed",
                            "content_text": "one",
                        },
                        {
                            "path": "AGENTS.md",
                            "default_mode": "managed",
                            "content_text": "two",
                        },
                    ],
                },
            )
            assert response.status_code == 409
            assert "duplicate asset path" in response.json()["detail"]
        _reset_env()


def test_standards_pack_rejects_duplicate_canonical_asset_paths() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.24",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "AGENTS.md",
                            "default_mode": "managed",
                            "content_text": "one",
                        },
                        {
                            "path": "./AGENTS.md",
                            "default_mode": "managed",
                            "content_text": "two",
                        },
                    ],
                },
            )
            assert response.status_code == 409
            assert "duplicate asset path" in response.json()["detail"]
        _reset_env()


def test_standards_pack_rejects_invalid_section_managed_content() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.25",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "docs/guide.md",
                            "default_mode": "section-managed",
                            "content_text": "# Guide without markers\n",
                        }
                    ],
                },
            )
            assert response.status_code == 400
            assert "ownership delimiters" in response.json()["detail"].lower()
        _reset_env()


def test_standards_evaluation_rejects_repo_roots_outside_allowlist() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root / "allowed")
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_id = str(product.product_id)
            finally:
                session.close()

            _create_pack(client, version="2026.03.20")
            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.20",
                },
            )
            assert evaluate.status_code == 400
            assert "outside the configured evaluation roots" in evaluate.json()["detail"]
        _reset_env()


def test_standards_override_rejects_invalid_paths() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "AGENTS.md").write_text("# Local Agents\n", encoding="utf-8")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_id = str(product.product_id)
            finally:
                session.close()

            response = client.post(
                f"/products/{product_id}/standards/overrides",
                json={"path": "   "},
            )
            assert response.status_code == 400
            assert "path is required" in response.json()["detail"].lower()
        _reset_env()


def test_standards_evaluation_handles_non_utf8_files_as_conflicts() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        (repo_root / "AGENTS.md").write_bytes(b"\xff\xfe\x00\x00")

        os.environ["AGENT_CORE_ALLOWED_REPO_ROOTS"] = str(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                product = _seed_product(session)
                product_id = str(product.product_id)
            finally:
                session.close()

            response = client.post(
                "/standards-packs",
                json={
                    "key": "default",
                    "channel": "stable",
                    "version": "2026.03.21",
                    "source_bundle": "org://baseline/default",
                    "assets": [
                        {
                            "path": "AGENTS.md",
                            "default_mode": "managed",
                            "content_text": "# Managed Agents\n",
                        }
                    ],
                },
            )
            assert response.status_code == 201

            evaluate = client.post(
                f"/products/{product_id}/standards/evaluations",
                json={
                    "repo_root": str(repo_root),
                    "pack_key": "default",
                    "channel": "stable",
                    "version": "2026.03.21",
                },
            )
            assert evaluate.status_code == 200
            payload = evaluate.json()
            assert payload["outcome_status"] == "conflict"
            assert payload["assets"][0]["action"] == "conflict"
            assert "utf-8" in payload["assets"][0]["detail"].lower()
        _reset_env()
