from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import agent_core_platform_api.github_integration as github_module
from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.github_integration import (
    GITHUB_APP_SETTING_KEY,
    GITHUB_WEBHOOK_SETTING_KEY,
    GitHubAppConfigError,
    GitHubAppAuthError,
    GitHubAppAuthService,
    GitHubPATAuthService,
    GitHubWebhookProcessingError,
)
from agent_core_platform_api.models import OperationalSignal, Organization, Secret, Setting, WebhookDelivery, WorkspaceRepo, WorkspaceRepoOrgMapping
from agent_core_platform_api.secret_crypto import decrypt_secret, encrypt_secret
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


def _generate_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _seed_github_app(session) -> None:
    session.query(Organization).filter(Organization.slug == "primary").one()
    private_key_secret = Secret(
        key="github-app-private-key",
        name="GitHub App Private Key",
        kind="signing_key",
        value_ciphertext=encrypt_secret(_generate_private_key_pem()),
    )
    webhook_secret = Secret(
        key="github-webhook-secret",
        name="GitHub Webhook Secret",
        kind="github_webhook_secret",
        value_ciphertext=encrypt_secret("shared-webhook-secret"),
    )
    session.add_all([private_key_secret, webhook_secret])
    session.add(
        Setting(
            scope_type="platform",
            scope_id="global",
            key=GITHUB_APP_SETTING_KEY,
            value_json={
                "app_id": "12345",
                "private_key_secret_key": private_key_secret.key,
                "webhook_secret_key": webhook_secret.key,
            },
        )
    )
    session.commit()


def _seed_workspace_repo(session, *, owner: str = "aegroup-io", repo: str = "orcha") -> None:
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    git_secret = Secret(
        key=f"{repo}-git-pat",
        name=f"{repo} Git PAT",
        kind="git_personal_access_token",
        value_ciphertext=encrypt_secret("ghp_test_token"),
    )
    session.add(git_secret)
    session.flush()
    workspace_repo = WorkspaceRepo(
        org_id=org.org_id,
        key=f"{owner}-{repo}",
        name=repo,
        provider="github",
        github_owner=owner,
        github_repo=repo,
        visibility="private",
        default_branch="dev",
        clone_url=f"https://github.com/{owner}/{repo}.git",
        git_auth_secret_id=git_secret.secret_id,
    )
    session.add(workspace_repo)
    session.flush()
    session.add(WorkspaceRepoOrgMapping(repo_id=workspace_repo.repo_id, org_id=org.org_id))
    session.commit()


def _signed_headers(body: bytes, *, delivery_guid: str = "delivery-1", event_name: str = "issues") -> dict[str, str]:
    signature = "sha256=" + hmac.new(b"shared-webhook-secret", body, hashlib.sha256).hexdigest()
    return {
        "X-GitHub-Delivery": delivery_guid,
        "X-GitHub-Event": event_name,
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    }


def test_github_webhook_intake_validates_signature_before_persisting() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                _seed_github_app(session)
            finally:
                session.close()

            body = b'{"action":"opened","installation":{"id":12345}}'
            accepted = client.post("/github/webhooks", content=body, headers=_signed_headers(body))
            assert accepted.status_code == 202
            payload = accepted.json()
            assert payload["duplicate"] is False
            assert payload["status"] == "processed"
            assert payload["installation_id"] == "12345"
            assert payload["delivery_attempts"] == 1

            rejected = client.post(
                "/github/webhooks",
                content=body,
                headers={
                    "X-GitHub-Delivery": "delivery-2",
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": "sha256=bad",
                    "Content-Type": "application/json",
                },
            )
            assert rejected.status_code == 401

            verify = get_session_factory()()
            try:
                deliveries = verify.query(WebhookDelivery).order_by(WebhookDelivery.github_delivery_guid.asc()).all()
                assert [item.github_delivery_guid for item in deliveries] == ["delivery-1"]
                assert deliveries[0].raw_body == body.decode("utf-8")
            finally:
                verify.close()
        _reset_env()


def test_github_pat_auth_service_creates_repository_webhook() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["AGENT_CORE_PUBLIC_API_BASE_URL"] = "https://example.com/orcha"
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _seed_github_app(session)
                _seed_workspace_repo(session, owner="aegroup-io", repo="orcha")
                service = GitHubPATAuthService(session)
                observed: dict[str, object] = {}

                def fake_get(url: str, **kwargs):
                    observed["list_url"] = url
                    return httpx.Response(200, json=[])

                def fake_post(url: str, **kwargs):
                    observed["create_url"] = url
                    observed["payload"] = kwargs["json"]
                    return httpx.Response(201, json={"id": 99})

                result = service.ensure_repository_webhook(
                    owner="aegroup-io",
                    repo="orcha",
                    http_get=fake_get,
                    http_post=fake_post,
                )

                assert observed["list_url"] == "https://api.github.com/repos/aegroup-io/orcha/hooks"
                assert observed["create_url"] == "https://api.github.com/repos/aegroup-io/orcha/hooks"
                assert observed["payload"] == {
                    "name": "web",
                    "active": True,
                    "events": ["issues", "pull_request", "push", "repository"],
                    "config": {
                        "url": "https://example.com/orcha/github/webhooks",
                        "content_type": "json",
                        "secret": "shared-webhook-secret",
                        "insecure_ssl": "0",
                    },
                }
                assert result.hook_id == 99
                assert result.delivery_url == "https://example.com/orcha/github/webhooks"
                assert result.status == "created"
            finally:
                session.close()
                os.environ.pop("AGENT_CORE_PUBLIC_API_BASE_URL", None)
        _reset_env()


def test_github_pat_auth_service_bootstraps_webhook_config_from_defaults() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["AGENT_CORE_PUBLIC_API_BASE_URL"] = "https://example.com/orcha"
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _seed_workspace_repo(session, owner="aegroup-io", repo="orcha")
                service = GitHubPATAuthService(session)
                observed: dict[str, object] = {}

                def fake_get(url: str, **kwargs):
                    observed["list_url"] = url
                    return httpx.Response(200, json=[])

                def fake_post(url: str, **kwargs):
                    observed["create_url"] = url
                    observed["payload"] = kwargs["json"]
                    return httpx.Response(201, json={"id": 42})

                result = service.ensure_repository_webhook(
                    owner="aegroup-io",
                    repo="orcha",
                    http_get=fake_get,
                    http_post=fake_post,
                )

                assert result.status == "created"
                assert result.delivery_url == "https://example.com/orcha/github/webhooks"

                setting = (
                    session.query(Setting)
                    .filter(
                        Setting.scope_type == "platform",
                        Setting.scope_id == "global",
                        Setting.key == GITHUB_WEBHOOK_SETTING_KEY,
                    )
                    .one()
                )
                assert setting.value_json == {
                    "webhook_secret_key": "github-webhook-secret",
                    "api_base_url": "https://api.github.com",
                }

                secret = session.query(Secret).filter(Secret.key == "github-webhook-secret").one()
                assert secret.kind == "github_webhook_secret"
                assert bool(secret.value_ciphertext) is True

                assert observed["list_url"] == "https://api.github.com/repos/aegroup-io/orcha/hooks"
                assert observed["create_url"] == "https://api.github.com/repos/aegroup-io/orcha/hooks"
                assert observed["payload"] == {
                    "name": "web",
                    "active": True,
                    "events": ["issues", "pull_request", "push", "repository"],
                    "config": {
                        "url": "https://example.com/orcha/github/webhooks",
                        "content_type": "json",
                        "secret": decrypt_secret(secret.value_ciphertext or ""),
                        "insecure_ssl": "0",
                    },
                }
            finally:
                session.close()
                os.environ.pop("AGENT_CORE_PUBLIC_API_BASE_URL", None)
        _reset_env()


def test_github_pat_auth_service_reports_missing_delivery_url_after_bootstrap() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ.pop("AGENT_CORE_PUBLIC_API_BASE_URL", None)
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _seed_workspace_repo(session, owner="aegroup-io", repo="orcha")
                service = GitHubPATAuthService(session)

                webhook_secret = service.load_webhook_secret()
                assert webhook_secret

                with pytest.raises(GitHubAppConfigError, match="GitHub webhook delivery URL is not configured"):
                    service.load_webhook_delivery_url()
            finally:
                session.close()
        _reset_env()


def test_github_webhook_duplicate_delivery_is_duplicate_safe() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                _seed_github_app(session)
            finally:
                session.close()

            body = b'{"action":"edited","installation":{"id":12345}}'
            first = client.post("/github/webhooks", content=body, headers=_signed_headers(body, delivery_guid="delivery-dup"))
            assert first.status_code == 202

            second = client.post("/github/webhooks", content=body, headers=_signed_headers(body, delivery_guid="delivery-dup"))
            assert second.status_code == 202
            assert second.json()["duplicate"] is True
            assert second.json()["delivery_attempts"] == 2
            assert second.json()["status"] == "processed"

            verify = get_session_factory()()
            try:
                deliveries = verify.query(WebhookDelivery).filter(WebhookDelivery.github_delivery_guid == "delivery-dup").all()
                assert len(deliveries) == 1
                signals = (
                    verify.query(OperationalSignal)
                    .filter(OperationalSignal.target_kind == "webhook_delivery")
                    .all()
                )
                assert any(signal.signal_type == "github.delivery.duplicate" for signal in signals)
            finally:
                verify.close()
        _reset_env()


def test_github_webhook_duplicate_race_recovers_without_500() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        original_persist = github_module.GitHubWebhookService._persist_new_delivery
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                _seed_github_app(session)
            finally:
                session.close()

            body = b'{"action":"labeled","installation":{"id":12345}}'
            payload_hash = hashlib.sha256(body).hexdigest()

            def racing_persist(self, delivery: WebhookDelivery) -> None:
                concurrent_session = get_session_factory()()
                try:
                    concurrent_session.add(
                        WebhookDelivery(
                            github_delivery_guid=delivery.github_delivery_guid,
                            event_name=delivery.event_name,
                            installation_id=delivery.installation_id,
                            status="processed",
                            payload_hash=payload_hash,
                            delivery_attempts=1,
                            payload_json={"action": "labeled", "installation": {"id": 12345}},
                            raw_body=body.decode("utf-8"),
                        )
                    )
                    concurrent_session.commit()
                finally:
                    concurrent_session.close()
                original_persist(self, delivery)

            github_module.GitHubWebhookService._persist_new_delivery = racing_persist
            try:
                raced = client.post("/github/webhooks", content=body, headers=_signed_headers(body, delivery_guid="delivery-race"))
            finally:
                github_module.GitHubWebhookService._persist_new_delivery = original_persist

            assert raced.status_code == 202
            assert raced.json()["duplicate"] is True
            assert raced.json()["delivery_attempts"] == 2
            assert raced.json()["status"] == "processed"

            verify = get_session_factory()()
            try:
                deliveries = (
                    verify.query(WebhookDelivery)
                    .filter(WebhookDelivery.github_delivery_guid == "delivery-race")
                    .all()
                )
                assert len(deliveries) == 1
            finally:
                verify.close()
        _reset_env()


def test_github_webhook_dead_letters_and_replays() -> None:
    from agent_core_platform_api import main as main_module

    class FailingWebhookService(main_module.GitHubWebhookService):
        def __init__(self, session):
            super().__init__(
                session,
                processor=lambda _session, _delivery: (_ for _ in ()).throw(
                    GitHubWebhookProcessingError("processor failed")
                ),
            )

    class ReplayingWebhookService(main_module.GitHubWebhookService):
        def __init__(self, session):
            super().__init__(session)

    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        original_service = main_module.GitHubWebhookService
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                _seed_github_app(session)
            finally:
                session.close()

            body = b'{"action":"reopened","installation":{"id":12345}}'
            main_module.GitHubWebhookService = FailingWebhookService
            failed = client.post("/github/webhooks", content=body, headers=_signed_headers(body, delivery_guid="delivery-fail"))
            assert failed.status_code == 202
            assert failed.json()["status"] == "dead-letter"
            assert failed.json()["error_detail"] == "processor failed"
            delivery_id = failed.json()["delivery_id"]

            main_module.GitHubWebhookService = ReplayingWebhookService
            replay = client.post(f"/github/webhooks/{delivery_id}/replay")
            assert replay.status_code == 200
            assert replay.json()["status"] == "processed"
            assert replay.json()["replay_count"] == 1
            assert replay.json()["error_detail"] is None

            session = get_session_factory()()
            try:
                replay_signal = (
                    session.query(OperationalSignal)
                    .filter(
                        OperationalSignal.target_id == delivery_id,
                        OperationalSignal.signal_type == "github.delivery.replay_requested",
                    )
                    .one()
                )
                assert replay_signal.value["audit"]["actor_type"] == "system"
                assert replay_signal.value["audit"]["approval_context"]["mode"] == "platform-manage-api"
                assert replay_signal.value["audit"]["outcome"] == "requested"
            finally:
                session.close()
        main_module.GitHubWebhookService = original_service
        _reset_env()


def test_github_app_auth_exchanges_installation_token_and_records_rate_limit() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                _seed_github_app(session)
                service = GitHubAppAuthService(session)

                def fake_post(url: str, *, headers: dict[str, str], timeout: int) -> httpx.Response:
                    assert url.endswith("/app/installations/12345/access_tokens")
                    assert headers["Authorization"].startswith("Bearer ")
                    return httpx.Response(
                        201,
                        headers={"Content-Type": "application/json"},
                        json={"token": "ghs_test", "expires_at": "2026-03-13T21:00:00Z"},
                    )

                token = service.exchange_installation_token(installation_id="12345", http_post=fake_post)
                assert token.token == "ghs_test"

                def rate_limited_post(url: str, *, headers: dict[str, str], timeout: int) -> httpx.Response:
                    return httpx.Response(
                        403,
                        headers={
                            "Content-Type": "application/json",
                            "x-ratelimit-remaining": "0",
                            "x-ratelimit-reset": "1710364200",
                        },
                        json={"message": "API rate limit exceeded"},
                    )

                try:
                    service.exchange_installation_token(installation_id="12345", http_post=rate_limited_post)
                    assert False, "Expected GitHubAppAuthError on rate-limited response"
                except GitHubAppAuthError as exc:
                    assert "rate limit" in str(exc).lower()

                signals = (
                    session.query(OperationalSignal)
                    .filter(OperationalSignal.target_kind == "github_installation")
                    .all()
                )
                assert len(signals) == 1
                assert signals[0].signal_type == "github.rate_limit"
            finally:
                session.close()
        _reset_env()
