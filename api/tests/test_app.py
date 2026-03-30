from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import httpx

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_engine, reset_database_state
from agent_core_platform_api.models import Permission, Product, RepositoryBinding, Role
from orcha_api.main import app


def _configure_env(
    database_url: str,
    *,
    initial_org_name: str = "Primary",
    initial_org_slug: str = "primary",
) -> None:
    os.environ["AGENT_CORE_AUTH_DISABLED"] = "1"
    os.environ["AGENT_CORE_DATABASE_URL"] = database_url
    os.environ["AGENT_CORE_CRYPTO_SEED"] = "agent-core-test-seed"
    os.environ["AGENT_CORE_INITIAL_ORG_NAME"] = initial_org_name
    os.environ["AGENT_CORE_INITIAL_ORG_SLUG"] = initial_org_slug
    get_settings.cache_clear()
    reset_database_state()


def _reset_env() -> None:
    get_settings.cache_clear()
    reset_database_state()


def test_health_and_me() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            me = client.get("/me")
            assert me.status_code == 200
            payload = me.json()
            assert payload["user_id"] == "local-dev"
            assert "admin" in payload["roles"]
            assert "org.read" in payload["permissions"]
            assert "repo.read" in payload["permissions"]
            assert "agent.chat" in payload["feature_flags"]
            assert len(payload["org_ids"]) == 1

            orgs = client.get("/orgs")
            assert orgs.status_code == 200
            assert orgs.json()[0]["name"] == "Primary"
            assert orgs.json()[0]["slug"] == "primary"

            summary = client.get("/platform/summary")
            assert summary.status_code == 200
            assert summary.json()["provider_count"] == 0
            assert summary.json()["model_count"] == 0
            assert summary.json()["agent_count"] == 0
        _reset_env()


def test_runner_launch_endpoint_accepts_internal_api_token() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        os.environ["AGENT_CORE_AUTH_DISABLED"] = "0"
        os.environ["AGENT_CORE_API_TOKEN"] = "shared-worker-token"
        os.environ["AGENT_CORE_API_TOKEN_ROLES"] = "worker"
        get_settings.cache_clear()
        reset_database_state()
        with TestClient(app) as client:
            response = client.get(
                "/v1/runner/launches/next",
                headers={"Authorization": "Bearer shared-worker-token"},
            )
            assert response.status_code == 204
        _reset_env()


def test_custom_initial_org_seeded_via_migrations() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(
            f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}",
            initial_org_name="Major Crimes",
            initial_org_slug="major-crimes",
        )
        with TestClient(app) as client:
            orgs = client.get("/orgs")
            assert orgs.status_code == 200
            assert orgs.json()[0]["name"] == "Major Crimes"
            assert orgs.json()[0]["slug"] == "major-crimes"
        _reset_env()


def test_org_member_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            created = client.post(
                "/orgs",
                json={
                    "name": "Platform",
                    "slug": "platform",
                    "documentation_visibility": "isolated",
                },
            )
            assert created.status_code == 201
            org_id = created.json()["org_id"]
            assert created.json()["documentation_visibility"] == "isolated"

            me = client.get("/me")
            assert me.status_code == 200
            assert org_id in me.json()["org_ids"]
            assert me.json()["default_org_id"] != org_id

            initial_members = client.get(f"/orgs/{org_id}/members")
            assert initial_members.status_code == 200
            assert len(initial_members.json()) == 1
            assert initial_members.json()[0]["user_id"] == "local-dev"

            member = client.post(
                f"/orgs/{org_id}/members",
                json={
                    "user_id": "user-123",
                    "email": "user-123@example.com",
                    "display_name": "User 123",
                },
            )
            assert member.status_code == 201
            assert member.json()["is_active"] is True

            members = client.get(f"/orgs/{org_id}/members")
            assert members.status_code == 200
            assert len(members.json()) == 2

            set_default = client.post(f"/orgs/{org_id}/members/user-123/default")
            assert set_default.status_code == 200
            assert set_default.json()["is_default"] is True

            removed = client.delete(f"/orgs/{org_id}/members/user-123")
            assert removed.status_code == 204

            with_inactive = client.get(f"/orgs/{org_id}/members?include_inactive=true")
            assert with_inactive.status_code == 200
            assert with_inactive.json()[0]["is_active"] is False
        _reset_env()


def test_user_search_routes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        from agent_core_platform_api import users_routes

        original_search_users = users_routes.search_users
        original_get_user = users_routes.get_user
        original_lookup_users = users_routes.lookup_users

        class _FakeGraphUser:
            def __init__(
                self,
                *,
                user_id: str,
                username: str | None,
                email: str | None,
                display_name: str | None,
                status: str | None,
            ) -> None:
                self.user_id = user_id
                self.username = username
                self.email = email
                self.display_name = display_name
                self.status = status

        def _fake_search_users(
            query: str | None,
            limit: int,
            next_token: str | None,
        ) -> tuple[list[_FakeGraphUser], str | None]:
            assert query == "ali"
            assert limit == 10
            assert next_token is None
            return (
                [
                    _FakeGraphUser(
                        user_id="user-1",
                        username="alice@example.com",
                        email="alice@example.com",
                        display_name="Alice",
                        status="Enabled",
                    )
                ],
                "next-page",
            )

        def _fake_get_user(user_id: str) -> _FakeGraphUser | None:
            if user_id != "user-1":
                return None
            return _FakeGraphUser(
                user_id="user-1",
                username="alice@example.com",
                email="alice@example.com",
                display_name="Alice",
                status="Enabled",
            )

        def _fake_lookup_users(user_ids: list[str]) -> list[_FakeGraphUser]:
            assert user_ids == ["user-1"]
            user = _fake_get_user("user-1")
            assert user is not None
            return [user]

        users_routes.search_users = _fake_search_users
        users_routes.get_user = _fake_get_user
        users_routes.lookup_users = _fake_lookup_users

        try:
            with TestClient(app) as client:
                search = client.get("/users?query=ali&limit=10")
                assert search.status_code == 200
                assert search.json() == {
                    "users": [
                        {
                            "user_id": "user-1",
                            "username": "alice@example.com",
                            "email": "alice@example.com",
                            "display_name": "Alice",
                            "status": "Enabled",
                        }
                    ],
                    "next_token": "next-page",
                }

                detail = client.get("/users/user-1")
                assert detail.status_code == 200
                assert detail.json()["display_name"] == "Alice"

                missing = client.get("/users/missing")
                assert missing.status_code == 404

                lookup = client.post("/users/lookup", json={"user_ids": ["user-1"]})
                assert lookup.status_code == 200
                assert lookup.json()["users"][0]["user_id"] == "user-1"
        finally:
            users_routes.search_users = original_search_users
            users_routes.get_user = original_get_user
            users_routes.lookup_users = original_lookup_users
            _reset_env()


def test_rbac_role_updates() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            permissions = client.get("/rbac/permissions")
            assert permissions.status_code == 200
            assert [item["key"] for item in permissions.json()] == [
                "ai.manage",
                "ai.read",
                "observability.read",
                "org.manage",
                "org.members.manage",
                "org.members.read",
                "org.read",
                "platform.manage",
                "platform.read",
                "repo.delete",
                "repo.manage",
                "repo.read",
                "worker.manage",
            ]

            feature_flags = client.get("/rbac/feature-flags")
            assert feature_flags.status_code == 200
            assert any(item["key"] == "agent.orchestration" for item in feature_flags.json())

            roles = client.get("/rbac/roles")
            assert roles.status_code == 200
            assert [role["slug"] for role in roles.json()] == ["admin", "analyst", "org_admin", "viewer", "worker"]
            analyst = next(role for role in roles.json() if role["slug"] == "analyst")
            assert "repo.read" in {item["key"] for item in analyst["permissions"]}

            updated_permissions = client.put(
                f"/rbac/roles/{analyst['role_id']}/permissions",
                json={"permission_keys": ["org.read", "platform.read", "ai.read", "observability.read"]},
            )
            assert updated_permissions.status_code == 200
            assert [item["key"] for item in updated_permissions.json()["permissions"]] == [
                "ai.read",
                "observability.read",
                "org.read",
                "platform.read",
            ]

            updated_flags = client.put(
                f"/rbac/roles/{analyst['role_id']}/feature-flags",
                json={"feature_flag_keys": ["agent.chat", "settings.advanced"]},
            )
            assert updated_flags.status_code == 200
            assert [item["key"] for item in updated_flags.json()["feature_flags"]] == [
                "agent.chat",
                "settings.advanced",
            ]
        _reset_env()


def test_runtime_startup_backfills_repo_permissions_for_existing_db() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

        with Session(get_engine()) as session:
            for role in session.query(Role).all():
                role.permissions = [permission for permission in role.permissions if not permission.key.startswith("repo.")]
            for permission in session.query(Permission).filter(Permission.key.in_(["repo.read", "repo.manage", "repo.delete"])).all():
                session.delete(permission)
            session.commit()

        with TestClient(app) as client:
            permissions = {item["key"] for item in client.get("/rbac/permissions").json()}
            assert {"repo.read", "repo.manage", "repo.delete"}.issubset(permissions)

            me = client.get("/me")
            assert me.status_code == 200
            assert "repo.manage" in me.json()["permissions"]
            assert "repo.read" in me.json()["permissions"]
        _reset_env()


def test_settings_and_secrets() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            updated_setting = client.put(
                "/settings/user/me/shell.locale",
                json={"value": "es-MX"},
            )
            assert updated_setting.status_code == 200
            assert updated_setting.json()["value_json"] == "es-MX"
            assert updated_setting.json()["created_by"] == "local-dev"
            assert updated_setting.json()["updated_by"] == "local-dev"

            settings_response = client.get("/settings?scope_type=user&scope_id=me")
            assert settings_response.status_code == 200
            assert settings_response.json()[0]["key"] == "shell.locale"
            assert settings_response.json()[0]["updated_by"] == "local-dev"

            secret = client.post(
                "/secrets",
                json={
                    "key": "platform-signing-key",
                    "name": "Platform Signing Key",
                    "kind": "ai_api_key",
                    "value": "super-secret-value",
                },
            )
            assert secret.status_code == 201
            assert secret.json()["has_value"] is True
            assert secret.json()["kind"] == "ai_api_key"

            secrets = client.get("/secrets")
            assert secrets.status_code == 200
            assert secrets.json()[0]["key"] == "platform-signing-key"
        _reset_env()


def test_git_repository_settings_flow() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            orgs = client.get("/orgs")
            assert orgs.status_code == 200
            primary_org_id = orgs.json()[0]["org_id"]

            secondary_org = client.post(
                "/orgs",
                json={
                    "name": "Platform",
                    "slug": "platform",
                    "documentation_visibility": "shared",
                },
            )
            assert secondary_org.status_code == 201
            secondary_org_id = secondary_org.json()["org_id"]

            secret = client.post(
                "/secrets",
                json={
                    "key": "github-pat",
                    "name": "GitHub PAT",
                    "kind": "git_personal_access_token",
                    "value": "ghp_test_token",
                },
            )
            assert secret.status_code == 201
            secret_id = secret.json()["secret_id"]

            created = client.post(
                f"/orgs/{primary_org_id}/repos",
                json={
                    "key": "atlas",
                    "name": "atlas",
                    "github_owner": "aegroup-io",
                    "github_repo": "atlas",
                    "visibility": "private",
                    "default_branch": "dev",
                    "git_auth_secret_id": secret_id,
                    "org_ids": [primary_org_id, secondary_org_id],
                },
            )
            assert created.status_code == 201
            repo = created.json()
            repo_id = repo["repo_id"]
            assert repo["org_ids"] == [secondary_org_id, primary_org_id]
            assert repo["visibility"] == "private"
            assert [mapping["org_name"] for mapping in repo["org_mappings"]] == [
                "Platform",
                "Primary",
            ]

            listed = client.get(f"/orgs/{primary_org_id}/repos")
            assert listed.status_code == 200
            assert len(listed.json()) == 1

            with Session(get_engine()) as session:
                product = Product(
                    org_id=UUID(primary_org_id),
                    key="atlas",
                    name="Atlas",
                    status="Active",
                    setup_state="ready",
                    setup_diagnostics=[],
                    effective_config={},
                    operator_overrides={},
                )
                session.add(product)
                session.flush()
                session.add(
                    RepositoryBinding(
                        product_id=product.product_id,
                        github_repository_node_id="R_atlas",
                        owner="aegroup-io",
                        name="atlas",
                        default_branch="dev",
                        visibility="private",
                        raw_payload={},
                    )
                )
                session.commit()

            refreshed = client.get(f"/orgs/{primary_org_id}/repos")
            assert refreshed.status_code == 200
            refreshed_repo = refreshed.json()[0]
            primary_mapping = next(
                mapping for mapping in refreshed_repo["org_mappings"] if mapping["org_id"] == primary_org_id
            )
            assert primary_mapping["active_product_count"] == 1

            blocked_update = client.patch(
                f"/repos/{repo_id}",
                json={"org_ids": [secondary_org_id]},
            )
            assert blocked_update.status_code == 409
            assert blocked_update.json()["detail"]["message"] == (
                "Cannot remove organization mapping while products use this repository"
            )

            blocked_delete = client.delete(f"/repos/{repo_id}")
            assert blocked_delete.status_code == 409
            assert blocked_delete.json()["detail"]["message"] == "Repo has active products"

            with Session(get_engine()) as session:
                product = session.query(Product).filter(Product.key == "atlas").one()
                product.status = "Archived"
                session.commit()

            deleted = client.delete(f"/repos/{repo_id}")
            assert deleted.status_code == 204

            relisted = client.get(f"/orgs/{primary_org_id}/repos")
            assert relisted.status_code == 200
            assert relisted.json() == []
        _reset_env()


def test_git_repository_lookup_and_branch_discovery() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            primary_org_id = client.get("/orgs").json()[0]["org_id"]
            secret = client.post(
                "/secrets",
                json={
                    "key": "github-pat",
                    "name": "GitHub PAT",
                    "kind": "git_personal_access_token",
                    "value": "ghp_test_token",
                },
            )
            assert secret.status_code == 201
            secret_id = secret.json()["secret_id"]

            def fake_get(
                url: str,
                *,
                headers: dict[str, str],
                params: dict[str, object] | None = None,
                timeout: int,
            ) -> httpx.Response:
                assert headers["Authorization"] == "token ghp_test_token"
                if url == "https://api.github.com/user/repos":
                    return httpx.Response(
                        200,
                        json=[
                            {
                                "name": "atlas",
                                "full_name": "aegroup-io/atlas",
                                "private": True,
                                "archived": False,
                                "default_branch": "dev",
                                "owner": {"login": "aegroup-io"},
                                "permissions": {"pull": True, "push": True, "admin": False},
                            }
                        ],
                    )
                if url == "https://api.github.com/repos/aegroup-io/atlas":
                    return httpx.Response(200, json={"default_branch": "dev"})
                if url == "https://api.github.com/repos/aegroup-io/atlas/branches":
                    return httpx.Response(
                        200,
                        json=[
                            {"name": "dev", "commit": {"sha": "abc123"}},
                            {"name": "main", "commit": {"sha": "def456"}},
                        ],
                    )
                raise AssertionError(f"Unexpected GitHub URL: {url}")

            with patch("agent_core_platform_api.repos_routes.httpx.get", side_effect=fake_get):
                lookup = client.post(
                    f"/orgs/{primary_org_id}/github/repos/lookup",
                    json={
                        "secret_id": secret_id,
                        "q": "atlas",
                        "limit": 50,
                    },
                )
                assert lookup.status_code == 200
                assert lookup.json() == [
                    {
                        "github_owner": "aegroup-io",
                        "github_repo": "atlas",
                        "full_name": "aegroup-io/atlas",
                        "visibility": "private",
                        "is_private": True,
                        "is_archived": False,
                        "default_branch": "dev",
                        "permissions": {"pull": True, "push": True, "admin": False},
                    }
                ]

                branches = client.post(
                    f"/orgs/{primary_org_id}/github/repos/branches",
                    json={
                        "secret_id": secret_id,
                        "github_owner": "aegroup-io",
                        "github_repo": "atlas",
                    },
                )
                assert branches.status_code == 200
                assert branches.json() == [
                    {"name": "dev", "head_sha": "abc123", "is_default": True},
                    {"name": "main", "head_sha": "def456", "is_default": False},
                ]
        _reset_env()


def test_ai_registry_and_agents_crud() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            secret = client.post(
                "/secrets",
                json={
                    "key": "openai-api-key",
                    "name": "OpenAI API Key",
                    "kind": "ai_api_key",
                    "value": "super-secret-value",
                },
            )
            assert secret.status_code == 201
            secret_id = secret.json()["secret_id"]

            provider = client.post(
                "/ai/providers",
                json={
                    "key": "openai",
                    "type": "openai",
                    "name": "OpenAI",
                    "is_active": True,
                    "config": {"api_key_secret_id": secret_id},
                    "compliance": {"residency": "us"},
                },
            )
            assert provider.status_code == 201
            provider_id = provider.json()["provider_id"]

            model = client.post(
                f"/ai/providers/{provider_id}/models",
                json={
                    "key": "gpt-4o-mini",
                    "name": "GPT-4o Mini",
                    "provider_model_id": "gpt-4o-mini",
                    "can_chat": True,
                    "is_active": True,
                    "default_params": {"temperature": 0},
                },
            )
            assert model.status_code == 201
            model_id = model.json()["model_id"]

            agent = client.post(
                "/ai/agents",
                json={
                    "key": "core-assistant",
                    "name": "Core Assistant",
                    "description": "Starter agent",
                    "system_prompt": "Reply with concise platform guidance.",
                    "tool_policy": {"mode": "manual"},
                    "output_schema": {"type": "object"},
                    "default_model_id": model_id,
                    "is_active": True,
                },
            )
            assert agent.status_code == 201

            providers = client.get("/ai/providers")
            assert providers.status_code == 200
            assert providers.json()[0]["key"] == "openai"

            models = client.get(f"/ai/models?provider_id={provider_id}")
            assert models.status_code == 200
            assert models.json()[0]["key"] == "gpt-4o-mini"

            updated_model = client.patch(
                f"/ai/models/{model_id}",
                json={"can_vision": True, "default_workload": "agent_run"},
            )
            assert updated_model.status_code == 200
            assert updated_model.json()["can_vision"] is True
            assert updated_model.json()["default_workload"] == "agent_run"

            agents = client.get("/ai/agents")
            assert agents.status_code == 200
            assert agents.json()[0]["key"] == "core-assistant"

            updated_agent = client.patch(
                f"/ai/agents/{agent.json()['agent_id']}",
                json={"name": "Core Assistant v2", "is_active": False},
            )
            assert updated_agent.status_code == 200
            assert updated_agent.json()["name"] == "Core Assistant v2"
            assert updated_agent.json()["is_active"] is False

            summary = client.get("/platform/summary")
            assert summary.status_code == 200
            payload = summary.json()
            assert payload["provider_count"] == 1
            assert payload["model_count"] == 1
            assert payload["agent_count"] == 1
        _reset_env()
