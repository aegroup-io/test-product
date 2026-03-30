from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

import agent_core_platform_api.github_mirror as github_mirror_module
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.github_integration import (
    GITHUB_APP_SETTING_KEY,
    GITHUB_WEBHOOK_SETTING_KEY,
    GitHubRepositoryWebhookResult,
)
from agent_core_platform_api.models import (
    GitHubProjectFieldMirror,
    GitHubProjectFieldOptionMirror,
    GitHubProjectItemMirror,
    GitHubProjectMirror,
    OperationalSignal,
    Organization,
    Product,
    PullRequestMirror,
    RepositoryBinding,
    Secret,
    Setting,
    WebhookDelivery,
    WorkItem,
    WorkspaceRepo,
    WorkspaceRepoOrgMapping,
)
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.secret_crypto import encrypt_secret
from agent_core_platform_api.work_item_normalization import WorkItemNormalizationService
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


def _seed_product(session) -> tuple[RepositoryBinding, GitHubProjectMirror]:
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    product = store.create_product(
        org_id=org.org_id,
        key="orcha",
        name="Orcha",
        status="Active",
        baseline_channel="stable",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id="R_repo_1",
        owner="aegroup-io",
        name="orcha",
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="seeded",
    )
    project = store.create_project_mirror(
        product_id=product.product_id,
        github_project_node_id="PVT_project_1",
        number=4,
        title="Orcha",
        status_field_name="Status",
        status_options=["Todo", "In Progress", "Done"],
        mirror_version=1,
    )
    product.primary_repo_id = repo.repo_id
    product.primary_project_id = project.project_id
    session.commit()
    return repo, project


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


def _seed_existing_repair_targets(
    session,
    *,
    repo: RepositoryBinding,
    project: GitHubProjectMirror,
) -> None:
    session.add(
        WorkItem(
            repo_id=repo.repo_id,
            project_id=project.project_id,
            github_issue_node_id="I_repair_202",
            issue_number=202,
            title="Existing repair issue",
            body="Stale mirror state",
            status="Triage",
            labels=[],
            assignees=[],
            dependencies=[],
            dependency_details=[],
            linked_prs=[],
            eligibility_flags=[],
            repair_reasons=[],
            raw_payload={},
        )
    )
    session.add(
        PullRequestMirror(
            repo_id=repo.repo_id,
            github_pr_node_id="PR_repair_601",
            number=601,
            title="Existing repair pull request",
            body="Stale mirror state",
            state="open",
            linked_work_item_ids=[],
            raw_payload={},
        )
    )
    session.commit()


def _set_effective_github_config(
    repo: RepositoryBinding,
    *,
    status_field: str = "Status",
    ready_status: str = "Todo",
    done_status: str = "Done",
) -> None:
    repo.product.effective_config = {
        "github": {
            "status_field": status_field,
            "ready_status": ready_status,
            "done_status": done_status,
        }
    }


def _signed_headers(body: bytes, *, delivery_guid: str, event_name: str) -> dict[str, str]:
    signature = "sha256=" + hmac.new(b"shared-webhook-secret", body, hashlib.sha256).hexdigest()
    return {
        "X-GitHub-Delivery": delivery_guid,
        "X-GitHub-Event": event_name,
        "X-Hub-Signature-256": signature,
        "Content-Type": "application/json",
    }


def _repo_payload(*, default_branch: str = "dev") -> dict[str, object]:
    return {
        "node_id": "R_repo_1",
        "owner": {"login": "aegroup-io"},
        "name": "orcha",
        "default_branch": default_branch,
        "visibility": "private",
        "description": "Orcha mirror repo",
        "archived": False,
    }


def test_webhook_processing_materializes_local_github_mirror_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
                _seed_workspace_repo(session)
                _seed_existing_repair_targets(session, repo=repo, project=project)
            finally:
                session.close()

            issue_payload = {
                "action": "opened",
                "installation": {"id": 12345},
                "repository": {
                    "node_id": "R_repo_1",
                    "owner": {"login": "aegroup-io"},
                    "name": "orcha",
                    "default_branch": "dev",
                    "visibility": "private",
                    "description": "Orcha mirror repo",
                    "archived": False,
                },
                "issue": {
                    "node_id": "I_issue_101",
                    "number": 101,
                    "title": "Mirror issue",
                    "body": "Tracks mirror state",
                    "state": "open",
                    "labels": [{"name": "Type:Feature"}, {"name": "Bug"}],
                    "assignees": [{"login": "OctoCat"}],
                },
            }
            issue_body = json.dumps(issue_payload).encode("utf-8")
            issue_response = client.post(
                "/github/webhooks",
                content=issue_body,
                headers=_signed_headers(issue_body, delivery_guid="mirror-issue", event_name="issues"),
            )
            assert issue_response.status_code == 202

            pr_payload = {
                "action": "opened",
                "installation": {"id": 12345},
                "repository": issue_payload["repository"],
                "pull_request": {
                    "node_id": "PR_501",
                    "number": 501,
                    "title": "Implement mirror state",
                    "body": "Closes #101",
                    "state": "open",
                    "draft": False,
                    "head_branch": "codex/issue-11-github-mirror",
                    "base_branch": "dev",
                    "review_state": "REVIEW_REQUIRED",
                    "merge_state": "CLEAN",
                },
            }
            pr_body = json.dumps(pr_payload).encode("utf-8")
            pr_response = client.post(
                "/github/webhooks",
                content=pr_body,
                headers=_signed_headers(pr_body, delivery_guid="mirror-pr", event_name="pull_request"),
            )
            assert pr_response.status_code == 202

            project_payload = {
                "action": "edited",
                "installation": {"id": 12345},
                "project": {
                    "node_id": "PVT_project_1",
                    "number": 4,
                    "title": "Orcha",
                    "status_field_name": "Status",
                    "status_options": ["Todo", "In Progress", "Done"],
                    "fields": [
                        {
                            "node_id": "PVTF_status",
                            "name": "Status",
                            "data_type": "single_select",
                            "options": [
                                {"id": "todo", "name": "Todo", "color": "GRAY"},
                                {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                {"id": "done", "name": "Done", "color": "GREEN"},
                            ],
                        },
                        {
                            "node_id": "PVTF_notes",
                            "name": "Notes",
                            "data_type": "text",
                        },
                    ],
                    "items": [
                        {
                            "node_id": "PVTI_issue_101",
                            "content": {"__typename": "Issue", "id": "I_issue_101"},
                            "field_values": [
                                {
                                    "field": {"id": "PVTF_status", "name": "Status", "dataType": "single_select"},
                                    "name": "In Progress",
                                    "optionId": "progress",
                                    "updatedAt": "2026-03-13T21:10:00Z",
                                },
                                {
                                    "field": {"id": "PVTF_notes", "name": "Notes", "dataType": "text"},
                                    "text": "Investigating mirror sync",
                                    "updatedAt": "2026-03-13T21:10:10Z",
                                },
                            ],
                        }
                    ],
                },
            }
            project_body = json.dumps(project_payload).encode("utf-8")
            project_response = client.post(
                "/github/webhooks",
                content=project_body,
                headers=_signed_headers(project_body, delivery_guid="mirror-project", event_name="projects_v2_item"),
            )
            assert project_response.status_code == 202

            verify = get_session_factory()()
            try:
                repo = verify.query(RepositoryBinding).filter(RepositoryBinding.github_repository_node_id == "R_repo_1").one()
                assert repo.description == "Orcha mirror repo"
                assert repo.raw_payload["name"] == "orcha"

                work_item = verify.query(WorkItem).filter(WorkItem.github_issue_node_id == "I_issue_101").one()
                assert work_item.title == "Mirror issue"
                assert work_item.title_normalized == "mirror issue"
                assert work_item.labels == ["bug", "type:feature"]
                assert work_item.assignees == ["octocat"]
                assert work_item.status == "In Progress"
                assert work_item.handoff_status == "in_review"
                assert work_item.eligibility_flags == ["awaiting-review"]

                pull_request = verify.query(PullRequestMirror).filter(PullRequestMirror.github_pr_node_id == "PR_501").one()
                assert pull_request.linked_work_item_ids == [str(work_item.work_item_id)]
                assert work_item.linked_prs == ["PR_501"]

                project = verify.query(GitHubProjectMirror).filter(GitHubProjectMirror.github_project_node_id == "PVT_project_1").one()
                assert project.status_field_name == "Status"
                assert project.status_options == ["Todo", "In Progress", "Done"]

                assert verify.query(GitHubProjectFieldMirror).count() == 2
                assert verify.query(GitHubProjectFieldOptionMirror).count() == 3
                project_item = (
                    verify.query(GitHubProjectItemMirror)
                    .filter(GitHubProjectItemMirror.github_project_item_node_id == "PVTI_issue_101")
                    .one()
                )
                assert project_item.work_item_id == work_item.work_item_id
                assert project_item.status_name == "In Progress"

                deliveries = verify.query(WebhookDelivery).order_by(WebhookDelivery.github_delivery_guid.asc()).all()
                assert [delivery.status for delivery in deliveries] == ["processed", "processed", "processed"]
            finally:
                verify.close()
        _reset_env()


def test_refresh_product_mirror_backfills_existing_repository_issues() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
                _seed_workspace_repo(session, owner=repo.owner, repo=repo.name)
                product_id = repo.product_id

                service = github_mirror_module.GitHubMirrorService(session)
                service.auth.ensure_repository_webhook = lambda **kwargs: GitHubRepositoryWebhookResult(  # type: ignore[method-assign]
                    hook_id=17,
                    delivery_url="https://example.com/orcha/github/webhooks",
                    status="created",
                )

                def fake_get(url: str, **kwargs):
                    assert url.endswith("/repos/aegroup-io/orcha/issues")
                    return httpx.Response(
                        200,
                        json=[
                            {"number": 101, "title": "Mirror issue"},
                            {"number": 102, "pull_request": {"url": "https://api.github.com/repos/aegroup-io/orcha/pulls/102"}},
                        ],
                    )

                def fake_post(url: str, **kwargs):
                    body = kwargs["json"]
                    variables = body["variables"]
                    if variables.get("id") == project.github_project_node_id:
                        return httpx.Response(
                            200,
                            json={
                                "data": {
                                    "node": {
                                        "id": project.github_project_node_id,
                                        "number": project.number,
                                        "title": project.title,
                                        "fields": {
                                            "nodes": [
                                                {
                                                    "id": "PVTF_status",
                                                    "name": "Status",
                                                    "dataType": "SINGLE_SELECT",
                                                    "options": [
                                                        {"id": "todo", "name": "Todo", "color": "GRAY"},
                                                        {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                                        {"id": "done", "name": "Done", "color": "GREEN"},
                                                    ],
                                                }
                                            ],
                                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        },
                                        "items": {
                                            "nodes": [],
                                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        },
                                    }
                                }
                            },
                        )
                    if variables.get("number") == 101:
                        return httpx.Response(
                            200,
                            json={
                                "data": {
                                    "repository": {
                                        "issue": {
                                            "id": "I_issue_101",
                                            "number": 101,
                                            "title": "Mirror issue",
                                            "body": "Tracks repo backfill",
                                            "state": "OPEN",
                                            "closedAt": None,
                                            "labels": {"nodes": [{"name": "Type:Feature"}]},
                                            "assignees": {"nodes": []},
                                            "blockedBy": {"nodes": []},
                                            "issueDependenciesSummary": {
                                                "blockedBy": 0,
                                                "totalBlockedBy": 0,
                                                "blocking": 0,
                                                "totalBlocking": 0,
                                            },
                                            "closedByPullRequestsReferences": {"nodes": []},
                                            "timelineItems": {"nodes": []},
                                            "repository": {
                                                "id": "R_repo_1",
                                                "name": "orcha",
                                                "visibility": "private",
                                                "description": "Orcha mirror repo",
                                                "isArchived": False,
                                                "owner": {"login": "aegroup-io"},
                                                "defaultBranchRef": {"name": "dev"},
                                            },
                                        }
                                    }
                                }
                            },
                        )
                    raise AssertionError(f"Unexpected GraphQL request: {body}")

                result = service.refresh_product_mirror(
                    product_id=product_id,
                    ensure_webhook=True,
                    http_get=fake_get,
                    http_post=fake_post,
                )

                assert result.issue_count == 1
                assert result.project_item_count == 0
                assert result.webhook_status == "created"

                work_items = session.query(WorkItem).all()
                assert len(work_items) == 1
                assert work_items[0].issue_number == 101
                assert work_items[0].title == "Mirror issue"

                signals = (
                    session.query(OperationalSignal)
                    .filter(OperationalSignal.target_kind == "product", OperationalSignal.target_id == str(product_id))
                    .all()
                )
                assert any(signal.signal_type == "github.mirror.refresh" for signal in signals)
            finally:
                session.close()
        _reset_env()


def test_refresh_product_mirror_records_delivery_url_diagnostic_when_webhook_bootstrap_lacks_public_url() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ.pop("AGENT_CORE_PUBLIC_API_BASE_URL", None)
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, _project = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_workspace_repo(session, owner=repo.owner, repo=repo.name)
                repo.product.primary_project_id = None
                session.commit()

                service = github_mirror_module.GitHubMirrorService(session)

                def fake_get(url: str, **kwargs):
                    assert url.endswith(f"/repos/{repo.owner}/{repo.name}/issues")
                    return httpx.Response(200, json=[])

                def fake_post(url: str, **kwargs):
                    variables = kwargs["json"]["variables"]
                    assert variables.get("id") == _project.github_project_node_id
                    return httpx.Response(
                        200,
                        json={
                            "data": {
                                "node": {
                                    "id": _project.github_project_node_id,
                                    "number": _project.number,
                                    "title": _project.title,
                                    "fields": {
                                        "nodes": [],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    },
                                    "items": {
                                        "nodes": [],
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    },
                                }
                            }
                        },
                    )

                result = service.refresh_product_mirror(
                    product_id=repo.product_id,
                    ensure_webhook=True,
                    http_get=fake_get,
                    http_post=fake_post,
                )

                assert result.issue_count == 0
                assert result.webhook_status == "unavailable"
                assert len(result.diagnostics) == 1
                assert result.diagnostics[0].code == "github.webhook.unavailable"
                assert "GitHub webhook delivery URL is not configured" in result.diagnostics[0].message

                webhook_setting = (
                    session.query(Setting)
                    .filter(
                        Setting.scope_type == "platform",
                        Setting.scope_id == "global",
                        Setting.key == GITHUB_WEBHOOK_SETTING_KEY,
                    )
                    .one()
                )
                assert webhook_setting.value_json == {
                    "webhook_secret_key": "github-webhook-secret",
                    "api_base_url": "https://api.github.com",
                }
                webhook_secret = session.query(Secret).filter(Secret.key == "github-webhook-secret").one()
                assert webhook_secret.kind == "github_webhook_secret"
                assert bool(webhook_secret.value_ciphertext) is True
            finally:
                session.close()
        _reset_env()


def test_push_webhook_on_default_branch_schedules_scoped_contract_refresh() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                repo, _ = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
                repo.product.setup_state = "ready"
                repo.product.setup_diagnostics = []
                session.commit()
                product_id = repo.product.product_id
            finally:
                session.close()

            push_payload = {
                "ref": "refs/heads/dev",
                "installation": {"id": 12345},
                "repository": _repo_payload(default_branch="dev"),
            }
            body = json.dumps(push_payload).encode("utf-8")
            response = client.post(
                "/github/webhooks",
                content=body,
                headers=_signed_headers(body, delivery_guid="push-default-branch", event_name="push"),
            )
            assert response.status_code == 202

            verify = get_session_factory()()
            try:
                product = verify.get(Product, product_id)
                assert product is not None
                assert product.setup_state == "drift"
                diagnostic_codes = {item.get("code") for item in product.setup_diagnostics if isinstance(item, dict)}
                assert "github.contract_refresh_pending" in diagnostic_codes
                signal = (
                    verify.query(OperationalSignal)
                    .filter(
                        OperationalSignal.target_kind == "product",
                        OperationalSignal.target_id == str(product.product_id),
                        OperationalSignal.signal_type == "github.contract_refresh_scheduled",
                    )
                    .one()
                )
                assert signal.severity == "warning"
                assert isinstance(signal.value, dict)
                assert signal.value.get("event_name") == "push"
                assert signal.value.get("trigger") == "push.default_branch"
            finally:
                verify.close()
        _reset_env()


def test_push_webhook_on_non_default_branch_does_not_schedule_contract_refresh() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                repo, _ = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
                repo.product.setup_state = "ready"
                repo.product.setup_diagnostics = []
                session.commit()
                product_id = repo.product.product_id
            finally:
                session.close()

            push_payload = {
                "ref": "refs/heads/feature/ignore",
                "installation": {"id": 12345},
                "repository": _repo_payload(default_branch="dev"),
            }
            body = json.dumps(push_payload).encode("utf-8")
            response = client.post(
                "/github/webhooks",
                content=body,
                headers=_signed_headers(body, delivery_guid="push-non-default", event_name="push"),
            )
            assert response.status_code == 202

            verify = get_session_factory()()
            try:
                product = verify.get(Product, product_id)
                assert product is not None
                assert product.setup_state == "ready"
                diagnostic_codes = {item.get("code") for item in product.setup_diagnostics if isinstance(item, dict)}
                assert "github.contract_refresh_pending" not in diagnostic_codes
                assert (
                    verify.query(OperationalSignal)
                    .filter(
                        OperationalSignal.target_kind == "product",
                        OperationalSignal.target_id == str(product.product_id),
                        OperationalSignal.signal_type == "github.contract_refresh_scheduled",
                    )
                    .count()
                    == 0
                )
            finally:
                verify.close()
        _reset_env()


def test_repository_default_branch_change_schedules_scoped_contract_refresh() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                repo, _ = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
                repo.product.setup_state = "ready"
                repo.product.setup_diagnostics = []
                session.commit()
                product_id = repo.product.product_id
            finally:
                session.close()

            repository_payload = {
                "action": "edited",
                "installation": {"id": 12345},
                "changes": {"default_branch": {"from": "dev"}},
                "repository": _repo_payload(default_branch="main"),
            }
            body = json.dumps(repository_payload).encode("utf-8")
            response = client.post(
                "/github/webhooks",
                content=body,
                headers=_signed_headers(body, delivery_guid="repo-default-branch", event_name="repository"),
            )
            assert response.status_code == 202

            verify = get_session_factory()()
            try:
                product = verify.get(Product, product_id)
                assert product is not None
                assert product.setup_state == "drift"
                assert any(
                    isinstance(item, dict)
                    and item.get("code") == "github.contract_refresh_pending"
                    and "default branch changed" in str(item.get("message", "")).lower()
                    for item in product.setup_diagnostics
                )
                repo = (
                    verify.query(RepositoryBinding)
                    .filter(RepositoryBinding.github_repository_node_id == "R_repo_1")
                    .one()
                )
                assert repo.default_branch == "main"
            finally:
                verify.close()
        _reset_env()


def test_work_item_normalization_maps_canonical_statuses_and_priority_hints() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                _set_effective_github_config(
                    repo,
                    status_field="Delivery",
                    ready_status="Queued",
                    done_status="Shipped",
                )
                service = github_mirror_module.GitHubMirrorService(session)
                normalizer = WorkItemNormalizationService(session)

                for issue_number, title in (
                    (101, "Queued item"),
                    (102, "Working item"),
                    (103, "Review item"),
                    (104, "Blocked item"),
                    (105, "Shipped item"),
                    (106, "Triage item"),
                ):
                    service.upsert_issue(
                        repo,
                        {
                            "node_id": f"I_issue_{issue_number}",
                            "number": issue_number,
                            "title": title,
                            "body": None,
                            "state": "open",
                            "labels": [],
                            "assignees": [],
                        },
                    )

                service.upsert_project_snapshot(
                    {
                        "node_id": "PVT_project_1",
                        "number": 4,
                        "title": "Orcha",
                        "status_field_name": "Delivery",
                        "status_options": ["Queued", "Working", "Review", "Blocked", "Shipped"],
                        "fields": [
                            {
                                "node_id": "PVTF_delivery",
                                "name": "Delivery",
                                "data_type": "single_select",
                                "options": [
                                    {"id": "queued", "name": "Queued", "color": "GRAY"},
                                    {"id": "working", "name": "Working", "color": "BLUE"},
                                    {"id": "review", "name": "Review", "color": "YELLOW"},
                                    {"id": "blocked", "name": "Blocked", "color": "RED"},
                                    {"id": "shipped", "name": "Shipped", "color": "GREEN"},
                                ],
                            },
                            {
                                "node_id": "PVTF_priority",
                                "name": "Priority",
                                "data_type": "text",
                            },
                        ],
                        "items": [
                            {
                                "node_id": "PVTI_issue_101",
                                "content": {"__typename": "Issue", "id": "I_issue_101"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_delivery", "name": "Delivery", "dataType": "single_select"},
                                        "name": "Queued",
                                        "optionId": "queued",
                                    },
                                    {
                                        "field": {"id": "PVTF_priority", "name": "Priority", "dataType": "text"},
                                        "text": "High",
                                    },
                                ],
                            },
                            {
                                "node_id": "PVTI_issue_102",
                                "content": {"__typename": "Issue", "id": "I_issue_102"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_delivery", "name": "Delivery", "dataType": "single_select"},
                                        "name": "Working",
                                        "optionId": "working",
                                    }
                                ],
                            },
                            {
                                "node_id": "PVTI_issue_103",
                                "content": {"__typename": "Issue", "id": "I_issue_103"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_delivery", "name": "Delivery", "dataType": "single_select"},
                                        "name": "Review",
                                        "optionId": "review",
                                    }
                                ],
                            },
                            {
                                "node_id": "PVTI_issue_104",
                                "content": {"__typename": "Issue", "id": "I_issue_104"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_delivery", "name": "Delivery", "dataType": "single_select"},
                                        "name": "Blocked",
                                        "optionId": "blocked",
                                    }
                                ],
                            },
                            {
                                "node_id": "PVTI_issue_105",
                                "content": {"__typename": "Issue", "id": "I_issue_105"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_delivery", "name": "Delivery", "dataType": "single_select"},
                                        "name": "Shipped",
                                        "optionId": "shipped",
                                    }
                                ],
                            },
                        ],
                    }
                )
                normalizer.normalize_for_project(project, allow_repair=False)
                normalizer.normalize_work_item(
                    session.query(WorkItem).filter(WorkItem.issue_number == 106).one(),
                    allow_repair=False,
                )
                session.commit()

                items = {item.issue_number: item for item in session.query(WorkItem).all()}
                assert items[101].status == "Ready"
                assert items[101].priority_hint == "p1"
                assert items[102].status == "In Progress"
                assert items[103].status == "In Review"
                assert items[104].status == "Blocked"
                assert items[105].status == "Done"
                assert items[106].status == "Triage"
            finally:
                session.close()
        _reset_env()


def test_work_item_normalization_computes_dependency_state_from_multiple_inputs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                _set_effective_github_config(repo)
                service = github_mirror_module.GitHubMirrorService(session)
                normalizer = WorkItemNormalizationService(session)

                done_dependency = service.upsert_issue(
                    repo,
                    {
                        "node_id": "I_issue_201",
                        "number": 201,
                        "title": "Resolved dependency",
                        "body": None,
                        "state": "closed",
                        "labels": [],
                        "assignees": [],
                    },
                )
                open_dependency = service.upsert_issue(
                    repo,
                    {
                        "node_id": "I_issue_202",
                        "number": 202,
                        "title": "Open dependency",
                        "body": None,
                        "state": "open",
                        "labels": [],
                        "assignees": [],
                    },
                )
                blocked_item = service.upsert_issue(
                    repo,
                    {
                        "node_id": "I_issue_301",
                        "number": 301,
                        "title": "Blocked issue",
                        "body": "Depends on #202",
                        "state": "open",
                        "labels": [{"name": "depends-on:#201"}],
                        "assignees": [],
                        "blockedBy": {"nodes": [{"id": "I_issue_202", "number": 202, "state": "OPEN", "closedAt": None}]},
                    },
                )

                service.upsert_project_snapshot(
                    {
                        "node_id": "PVT_project_1",
                        "number": 4,
                        "title": "Orcha",
                        "status_field_name": "Status",
                        "status_options": ["Todo", "In Progress", "Done"],
                        "fields": [
                            {
                                "node_id": "PVTF_status",
                                "name": "Status",
                                "data_type": "single_select",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                    {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                    {"id": "done", "name": "Done", "color": "GREEN"},
                                ],
                            },
                            {
                                "node_id": "PVTF_depends",
                                "name": "Depends On",
                                "data_type": "text",
                            },
                        ],
                        "items": [
                            {
                                "node_id": "PVTI_issue_202",
                                "content": {"__typename": "Issue", "id": "I_issue_202"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_status", "name": "Status", "dataType": "single_select"},
                                        "name": "Todo",
                                        "optionId": "todo",
                                    }
                                ],
                            },
                            {
                                "node_id": "PVTI_issue_301",
                                "content": {"__typename": "Issue", "id": "I_issue_301"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_status", "name": "Status", "dataType": "single_select"},
                                        "name": "In Progress",
                                        "optionId": "progress",
                                    },
                                    {
                                        "field": {"id": "PVTF_depends", "name": "Depends On", "dataType": "text"},
                                        "text": "#202",
                                    },
                                ],
                            },
                        ],
                    }
                )

                normalizer.normalize_work_item(done_dependency, allow_repair=False)
                normalizer.normalize_work_item(open_dependency, allow_repair=False)
                normalizer.normalize_work_item(blocked_item, allow_repair=False)
                normalizer.normalize_for_project(project, allow_repair=False)
                session.commit()

                blocked = session.query(WorkItem).filter(WorkItem.issue_number == 301).one()
                assert blocked.status == "Blocked"
                assert blocked.dependency_state == "blocked"
                assert blocked.dependencies == ["issue:201", "issue:202"]
                assert blocked.handoff_status == "none"
                detail_by_issue = {
                    detail["issue_number"]: detail
                    for detail in blocked.dependency_details
                    if detail.get("kind") == "issue"
                }
                assert detail_by_issue[201]["resolved"] is True
                assert detail_by_issue[202]["resolved"] is False
            finally:
                session.close()
        _reset_env()


def test_project_snapshot_prunes_deleted_fields_options_and_items() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                service = github_mirror_module.GitHubMirrorService(session)

                work_item = service.upsert_issue(
                    repo,
                    {
                        "node_id": "I_issue_101",
                        "number": 101,
                        "title": "Mirror issue",
                        "body": "Tracks mirror state",
                        "state": "open",
                        "labels": [],
                        "assignees": [],
                    },
                )
                service.upsert_project_snapshot(
                    {
                        "node_id": "PVT_project_1",
                        "number": 4,
                        "title": "Orcha",
                        "status_field_name": "Status",
                        "status_options": ["Todo", "Done"],
                        "fields": [
                            {
                                "node_id": "PVTF_status",
                                "name": "Status",
                                "data_type": "single_select",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                    {"id": "done", "name": "Done", "color": "GREEN"},
                                ],
                            },
                            {
                                "node_id": "PVTF_notes",
                                "name": "Notes",
                                "data_type": "text",
                            },
                        ],
                        "items": [
                            {
                                "node_id": "PVTI_issue_101",
                                "content": {"__typename": "Issue", "id": "I_issue_101"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_status", "name": "Status", "dataType": "single_select"},
                                        "name": "Done",
                                        "optionId": "done",
                                        "updatedAt": "2026-03-13T21:10:00Z",
                                    }
                                ],
                            }
                        ],
                    }
                )
                session.commit()

                session.refresh(work_item)
                assert work_item.project_id == project.project_id
                assert work_item.status == "Done"
                assert session.query(GitHubProjectFieldMirror).count() == 2
                assert session.query(GitHubProjectFieldOptionMirror).count() == 2
                assert session.query(GitHubProjectItemMirror).count() == 1

                service.upsert_project_snapshot(
                    {
                        "node_id": "PVT_project_1",
                        "number": 4,
                        "title": "Orcha",
                        "status_field_name": "Status",
                        "status_options": ["Todo"],
                        "fields": [
                            {
                                "node_id": "PVTF_status",
                                "name": "Status",
                                "data_type": "single_select",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                ],
                            }
                        ],
                        "items": [],
                    }
                )
                session.commit()

                session.expire_all()
                refreshed_work_item = session.query(WorkItem).filter(WorkItem.github_issue_node_id == "I_issue_101").one()
                refreshed_project = (
                    session.query(GitHubProjectMirror)
                    .filter(GitHubProjectMirror.github_project_node_id == "PVT_project_1")
                    .one()
                )
                assert refreshed_work_item.project_id is None
                assert refreshed_work_item.status == "Triage"
                assert refreshed_project.status_options == ["Todo"]
                assert session.query(GitHubProjectFieldMirror).count() == 1
                assert session.query(GitHubProjectFieldOptionMirror).count() == 1
                assert session.query(GitHubProjectItemMirror).count() == 0
            finally:
                session.close()
        _reset_env()


def test_pull_request_linkage_removes_stale_issue_references() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, _ = _seed_product(session)
                service = github_mirror_module.GitHubMirrorService(session)

                work_item = service.upsert_issue(
                    repo,
                    {
                        "node_id": "I_issue_101",
                        "number": 101,
                        "title": "Mirror issue",
                        "body": "Tracks mirror state",
                        "state": "open",
                        "labels": [],
                        "assignees": [],
                    },
                )
                pull_request = service.upsert_pull_request(
                    repo,
                    {
                        "node_id": "PR_501",
                        "number": 501,
                        "title": "Implement mirror state",
                        "body": "Closes #101",
                        "state": "open",
                        "draft": False,
                        "head_branch": "codex/issue-11-github-mirror",
                        "base_branch": "dev",
                        "review_state": "REVIEW_REQUIRED",
                        "merge_state": "CLEAN",
                    },
                )
                session.commit()

                session.refresh(work_item)
                session.refresh(pull_request)
                assert work_item.linked_prs == ["PR_501"]
                assert pull_request.linked_work_item_ids == [str(work_item.work_item_id)]

                service.upsert_pull_request(
                    repo,
                    {
                        "node_id": "PR_501",
                        "number": 501,
                        "title": "Implement mirror state",
                        "body": "No linked issue remains",
                        "state": "open",
                        "draft": False,
                        "head_branch": "codex/issue-11-github-mirror",
                        "base_branch": "dev",
                        "review_state": "REVIEW_REQUIRED",
                        "merge_state": "CLEAN",
                    },
                )
                session.commit()

                session.expire_all()
                refreshed_work_item = session.query(WorkItem).filter(WorkItem.github_issue_node_id == "I_issue_101").one()
                refreshed_pull_request = (
                    session.query(PullRequestMirror)
                    .filter(PullRequestMirror.github_pr_node_id == "PR_501")
                    .one()
                )
                assert refreshed_work_item.linked_prs == []
                assert refreshed_pull_request.linked_work_item_ids == []
            finally:
                session.close()
        _reset_env()


def test_targeted_repair_and_local_reads_use_scoped_github_fetches_only(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        calls = {"access_tokens": 0, "graphql": 0}

        def fake_post(url: str, **kwargs) -> httpx.Response:
            if url.endswith("/access_tokens"):
                calls["access_tokens"] += 1
                return httpx.Response(
                    201,
                    headers={"Content-Type": "application/json"},
                    json={"token": "ghs_test", "expires_at": "2026-03-13T22:00:00Z"},
                )

            if url.endswith("/graphql"):
                calls["graphql"] += 1
                payload = kwargs["json"]
                query = payload["query"]
                variables = payload["variables"]
                if "query OrchaProjectNode" in query:
                    after = variables.get("after")
                    if after is None:
                        field_nodes = [
                            {
                                "id": "PVTF_status",
                                "name": "Status",
                                "dataType": "SINGLE_SELECT",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                    {"id": "done", "name": "Done", "color": "GREEN"},
                                ],
                            }
                        ]
                        page_info = {"hasNextPage": True, "endCursor": "fields-page-2"}
                    elif after == "fields-page-2":
                        field_nodes = [
                            {
                                "id": "PVTF_notes",
                                "name": "Notes",
                                "dataType": "TEXT",
                            }
                        ]
                        page_info = {"hasNextPage": False, "endCursor": None}
                    else:
                        raise AssertionError(f"Unexpected project field cursor: {after}")
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        json={
                            "data": {
                                "node": {
                                    "id": "PVT_project_1",
                                    "number": 4,
                                    "title": "Orcha",
                                    "fields": {
                                        "pageInfo": page_info,
                                        "nodes": field_nodes,
                                    },
                                }
                            }
                        },
                    )
                if "query OrchaProjectItems" in query:
                    after = variables.get("after")
                    if after is None:
                        item_nodes = [
                            {
                                "id": "PVTI_repair_202",
                                "type": "ISSUE",
                                "content": {"__typename": "Issue", "id": "I_repair_202"},
                                "fieldValues": {
                                    "pageInfo": {"hasNextPage": True, "endCursor": "field-values-page-2"},
                                    "nodes": [
                                        {
                                            "name": "Todo",
                                            "optionId": "todo",
                                            "updatedAt": "2026-03-13T21:20:00Z",
                                            "field": {
                                                "id": "PVTF_status",
                                                "name": "Status",
                                                "dataType": "SINGLE_SELECT",
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                        page_info = {"hasNextPage": True, "endCursor": "items-page-2"}
                    elif after == "items-page-2":
                        item_nodes = [
                            {
                                "id": "PVTI_repair_601",
                                "type": "PULL_REQUEST",
                                "content": {"__typename": "PullRequest", "id": "PR_repair_601"},
                                "fieldValues": {
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    "nodes": [],
                                },
                            }
                        ]
                        page_info = {"hasNextPage": False, "endCursor": None}
                    else:
                        raise AssertionError(f"Unexpected project item cursor: {after}")
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        json={
                            "data": {
                                "node": {
                                    "items": {
                                        "pageInfo": page_info,
                                        "nodes": item_nodes,
                                    }
                                }
                            }
                        },
                    )
                if "query OrchaProjectItemFieldValues" in query:
                    if variables.get("id") != "PVTI_repair_202":
                        raise AssertionError(f"Unexpected project item node id: {variables.get('id')}")
                    if variables.get("after") != "field-values-page-2":
                        raise AssertionError(f"Unexpected project field value cursor: {variables.get('after')}")
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        json={
                            "data": {
                                "node": {
                                    "fieldValues": {
                                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        "nodes": [
                                            {
                                                "text": "Recovered from page 2",
                                                "updatedAt": "2026-03-13T21:21:00Z",
                                                "field": {
                                                    "id": "PVTF_notes",
                                                    "name": "Notes",
                                                    "dataType": "TEXT",
                                                },
                                            }
                                        ],
                                    }
                                }
                            }
                        },
                    )
                if "query OrchaIssueNode" in query:
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        json={
                            "data": {
                                "node": {
                                    "id": "I_repair_202",
                                    "number": 202,
                                    "title": "Repair issue",
                                    "body": "Recovered from targeted repair",
                                    "state": "OPEN",
                                    "closedAt": None,
                                    "labels": {"nodes": [{"name": "enhancement"}]},
                                    "assignees": {"nodes": [{"login": "RepairBot"}]},
                                    "repository": {
                                        "id": "R_repo_1",
                                        "name": "orcha",
                                        "visibility": "PRIVATE",
                                        "description": "Orcha mirror repo",
                                        "isArchived": False,
                                        "owner": {"login": "aegroup-io"},
                                        "defaultBranchRef": {"name": "dev"},
                                    },
                                }
                            }
                        },
                    )
                if "query OrchaPullRequestNode" in query:
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "application/json"},
                        json={
                            "data": {
                                "node": {
                                    "id": "PR_repair_601",
                                    "number": 601,
                                    "title": "Repair pull request",
                                    "body": "Closes #202",
                                    "state": "OPEN",
                                    "isDraft": False,
                                    "reviewDecision": "REVIEW_REQUIRED",
                                    "mergeStateStatus": "CLEAN",
                                    "headRefName": "codex/repair",
                                    "baseRefName": "dev",
                                    "mergedAt": None,
                                    "closedAt": None,
                                    "repository": {
                                        "id": "R_repo_1",
                                        "name": "orcha",
                                        "visibility": "PRIVATE",
                                        "description": "Orcha mirror repo",
                                        "isArchived": False,
                                        "owner": {"login": "aegroup-io"},
                                        "defaultBranchRef": {"name": "dev"},
                                    },
                                }
                            }
                        },
                    )
                raise AssertionError(f"Unexpected GraphQL query in fake GitHub client: {query}")

            raise AssertionError(f"Unexpected URL in fake GitHub client: {url}")

        monkeypatch.setattr(github_mirror_module.httpx, "post", fake_post)

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
                _seed_workspace_repo(session)
                _seed_existing_repair_targets(session, repo=repo, project=project)
            finally:
                session.close()

            issue_repair = client.post("/github/mirror/work-items/I_repair_202/repair?installation_id=12345")
            assert issue_repair.status_code == 200
            assert issue_repair.json()["github_issue_node_id"] == "I_repair_202"

            pr_repair = client.post("/github/mirror/pull-requests/PR_repair_601/repair?installation_id=12345")
            assert pr_repair.status_code == 200
            assert pr_repair.json()["github_pr_node_id"] == "PR_repair_601"
            assert len(pr_repair.json()["linked_work_item_ids"]) == 1

            project_repair = client.post("/github/mirror/projects/PVT_project_1/repair?installation_id=12345")
            assert project_repair.status_code == 200
            assert project_repair.json()["github_project_node_id"] == "PVT_project_1"
            assert {field["name"] for field in project_repair.json()["fields"]} == {"Notes", "Status"}
            assert {item["github_content_node_id"] for item in project_repair.json()["items"]} == {
                "I_repair_202",
                "PR_repair_601",
            }
            issue_project_item = next(
                item for item in project_repair.json()["items"] if item["github_content_node_id"] == "I_repair_202"
            )
            assert issue_project_item["status_name"] == "Todo"
            assert len(issue_project_item["field_values_payload"]) == 2

            assert calls == {"access_tokens": 0, "graphql": 7}

            work_item = client.get("/github/mirror/work-items/I_repair_202")
            pull_request = client.get("/github/mirror/pull-requests/PR_repair_601")
            project = client.get("/github/mirror/projects/PVT_project_1")
            assert work_item.status_code == 200
            assert pull_request.status_code == 200
            assert project.status_code == 200
            assert work_item.json()["status"] == "In Review"
            assert work_item.json()["handoff_status"] == "in_review"
            assert pull_request.json()["number"] == 601
            assert {field["name"] for field in project.json()["fields"]} == {"Notes", "Status"}
            assert len(project.json()["items"]) == 2
            assert calls == {"access_tokens": 0, "graphql": 7}
        _reset_env()


def test_webhook_normalization_triggers_targeted_repair_for_ambiguous_dependencies(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        repair_calls: list[tuple[str, str | None]] = []
        dependency_calls: list[tuple[str, str, int, str | None]] = []

        def fake_repair_issue(self, *, github_issue_node_id: str, installation_id: str | None = None, http_post=None):
            repair_calls.append((github_issue_node_id, installation_id))
            return self.get_work_item_by_node_id(github_issue_node_id)

        def fake_repair_issue_by_number(self, *, owner: str, repo: str, issue_number: int, installation_id: str | None = None, http_post=None):
            dependency_calls.append((owner, repo, issue_number, installation_id))
            raise ValueError("dependency not found")

        monkeypatch.setattr(github_mirror_module.GitHubMirrorService, "repair_issue", fake_repair_issue)
        monkeypatch.setattr(github_mirror_module.GitHubMirrorService, "repair_issue_by_number", fake_repair_issue_by_number)

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                repo, _ = _seed_product(session)
                _set_effective_github_config(repo)
                _seed_github_app(session)
            finally:
                session.close()

            issue_payload = {
                "action": "opened",
                "installation": {"id": 12345},
                "repository": {
                    "node_id": "R_repo_1",
                    "owner": {"login": "aegroup-io"},
                    "name": "orcha",
                    "default_branch": "dev",
                    "visibility": "private",
                    "description": "Orcha mirror repo",
                    "archived": False,
                },
                "issue": {
                    "node_id": "I_issue_404",
                    "number": 404,
                    "title": "Ambiguous dependency issue",
                    "body": "Depends on #999",
                    "state": "open",
                    "labels": [],
                    "assignees": [],
                },
            }
            issue_body = json.dumps(issue_payload).encode("utf-8")
            response = client.post(
                "/github/webhooks",
                content=issue_body,
                headers=_signed_headers(issue_body, delivery_guid="repair-needed", event_name="issues"),
            )
            assert response.status_code == 202
            assert repair_calls == [("I_issue_404", None)]
            assert dependency_calls == [("aegroup-io", "orcha", 999, None)]

            verify = get_session_factory()()
            try:
                work_item = verify.query(WorkItem).filter(WorkItem.github_issue_node_id == "I_issue_404").one()
                assert work_item.requires_repair is True
                assert "dependency.ambiguous" in work_item.repair_reasons
                assert work_item.status == "Triage"
            finally:
                verify.close()
        _reset_env()


def test_targeted_repair_hydrates_missing_dependency_issues_by_number(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        repaired_dependencies: list[int] = []

        def fake_repair_issue(self, *, github_issue_node_id: str, installation_id: str | None = None, http_post=None):
            return self.get_work_item_by_node_id(github_issue_node_id)

        def fake_repair_issue_by_number(self, *, owner: str, repo: str, issue_number: int, installation_id: str | None = None, http_post=None):
            repaired_dependencies.append(issue_number)
            repository_binding = (
                self.session.query(RepositoryBinding)
                .filter(RepositoryBinding.owner == owner, RepositoryBinding.name == repo)
                .one()
            )
            dependency = self.upsert_issue(
                repository_binding,
                {
                    "node_id": f"I_issue_{issue_number}",
                    "number": issue_number,
                    "title": f"Dependency {issue_number}",
                    "body": None,
                    "state": "closed",
                    "closedAt": "2026-03-13T12:00:00Z",
                    "labels": [],
                    "assignees": [],
                },
            )
            WorkItemNormalizationService(self.session).normalize_work_item(dependency, allow_repair=False)
            return dependency

        monkeypatch.setattr(github_mirror_module.GitHubMirrorService, "repair_issue", fake_repair_issue)
        monkeypatch.setattr(github_mirror_module.GitHubMirrorService, "repair_issue_by_number", fake_repair_issue_by_number)

        with TestClient(app):
            session = get_session_factory()()
            try:
                repo, project = _seed_product(session)
                _set_effective_github_config(repo)
                service = github_mirror_module.GitHubMirrorService(session)
                normalizer = WorkItemNormalizationService(session)

                work_item = service.upsert_issue(
                    repo,
                    {
                        "node_id": "I_issue_410",
                        "number": 410,
                        "title": "Waiting on remote dependency",
                        "body": None,
                        "state": "open",
                        "labels": [],
                        "assignees": [],
                    },
                )
                service.upsert_project_snapshot(
                    {
                        "node_id": "PVT_project_1",
                        "number": 4,
                        "title": "Orcha",
                        "status_field_name": "Status",
                        "status_options": ["Todo", "In Progress", "Done"],
                        "fields": [
                            {
                                "node_id": "PVTF_status",
                                "name": "Status",
                                "data_type": "single_select",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                    {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                    {"id": "done", "name": "Done", "color": "GREEN"},
                                ],
                            },
                            {
                                "node_id": "PVTF_depends",
                                "name": "Depends On",
                                "data_type": "text",
                            },
                        ],
                        "items": [
                            {
                                "node_id": "PVTI_issue_410",
                                "content": {"__typename": "Issue", "id": "I_issue_410"},
                                "field_values": [
                                    {
                                        "field": {"id": "PVTF_status", "name": "Status", "dataType": "single_select"},
                                        "name": "Todo",
                                        "optionId": "todo",
                                    },
                                    {
                                        "field": {"id": "PVTF_depends", "name": "Depends On", "dataType": "text"},
                                        "text": "#411",
                                    },
                                ],
                            }
                        ],
                    }
                )

                normalizer.normalize_work_item(
                    work_item,
                    installation_id="12345",
                    mirror_service=service,
                    allow_repair=True,
                )
                session.commit()

                refreshed = session.query(WorkItem).filter(WorkItem.issue_number == 410).one()
                dependency = session.query(WorkItem).filter(WorkItem.issue_number == 411).one()
                assert repaired_dependencies == [411]
                assert dependency.status == "Done"
                assert refreshed.dependency_state == "clear"
                assert refreshed.requires_repair is False
                assert refreshed.repair_reasons == []
                assert refreshed.status == "Ready"
            finally:
                session.close()
        _reset_env()
