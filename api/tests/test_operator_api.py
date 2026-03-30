from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import uuid

from fastapi.testclient import TestClient
import yaml

import agent_core_platform_api.github_mirror as github_mirror_module
from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.github_mirror import ProductMirrorRefreshResult
from agent_core_platform_api.models import OperationalSignal, Organization, RepositoryBinding, WorkItem
from agent_core_platform_api.operator_api import OperatorAPIService
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.work_item_normalization import RUNNER_CAPABILITY_REPAIR_REASON
from orcha_api.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _write_fixture_repo(repo_root: Path) -> None:
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
    (repo_root / ".orcha" / "product.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    components = {
        "schema_version": 1,
        "components": [
            {"key": "orcha", "name": "Orcha", "type": "product", "owner": "aegroup"},
            {"key": "orcha-repo", "name": "orcha", "type": "repository", "owner": "aegroup-io"},
            {"key": "api-service", "name": "API Service", "type": "service", "owner": "platform"},
        ],
        "edges": [
            {"from": "orcha", "to": "orcha-repo", "relationship": "owns"},
            {"from": "orcha", "to": "api-service", "relationship": "depends_on"},
        ],
    }
    (repo_root / ".orcha" / "components.yaml").write_text(yaml.safe_dump(components, sort_keys=False), encoding="utf-8")


def _build_product_payload(org_id: str, repo_root: Path) -> dict[str, object]:
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


def _seed_lane_fixture(session):
    now = _now()
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    effective_config = {
        "baseline": {"channel": "stable", "managed_assets": []},
        "execution": {
            "profile": "standard-python",
            "container_image": "ghcr.io/aegroup/agent-core-runner:stable",
            "workspace_strategy": "branch-per-lane",
            "max_concurrent_lanes": 4,
        },
    }
    product = store.create_product(
        org_id=org.org_id,
        key="atlas",
        name="Atlas",
        status="Active",
        baseline_channel="stable",
        standards_pack_key="default",
        standards_pack_version="1.2.0",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
        setup_state="ready",
        effective_config=deepcopy(effective_config),
        operator_overrides={},
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id="R_kgDOAtlas",
        owner="aegroup-io",
        name="atlas",
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="adopted",
        raw_payload={"clone_url": "https://example.invalid/atlas.git"},
    )
    pack = store.create_standards_pack(
        key="default",
        channel="stable",
        version="1.2.0",
        source_bundle="bundle://default",
        description="Default standards pack",
        manifest={},
    )
    store.create_managed_asset(
        product_id=product.product_id,
        path="AGENTS.md",
        kind="file",
        management_mode="managed",
        upstream_bundle_version="1.2.0",
        drift_status="current",
    )
    store.create_managed_asset(
        product_id=product.product_id,
        path=".github/pull_request_template.md",
        kind="file",
        management_mode="managed",
        upstream_bundle_version="1.2.0",
        drift_status="update-available",
    )
    store.create_standards_upgrade_run(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        standards_pack_id=pack.standards_pack_id,
        source_bundle="bundle://default",
        source_version="1.2.0",
        outcome_kind="upgrade-pr",
        outcome_status="reviewable",
        generated_pr_number=99,
        summary_payload={"summary": "Fixture standards run."},
    )
    product.primary_repo_id = repo.repo_id
    session.flush()

    def make_lane(issue_number: int, title: str, state: str):
        work_item = store.create_work_item(
            repo_id=repo.repo_id,
            github_issue_node_id=f"I_kwDOAtlas{issue_number}",
            issue_number=issue_number,
            title=title,
            body=title,
            status="In Progress",
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
            state=state,
            claimed_at=now,
            started_at=now,
        )
        return work_item, lane

    _, approval_lane = make_lane(281, "Awaiting approval", "AwaitingApproval")
    approval_env = store.create_execution_environment(
        lane_id=approval_lane.lane_id,
        runtime_provider="test",
        container_image="ghcr.io/aegroup/agent-core-runner:stable",
        container_handle="aks://lanes/approval",
        status="Ready",
        workspace_uri="file:///tmp/approval/workspace",
        artifact_uri="file:///tmp/approval/artifacts",
        log_uri="file:///tmp/approval/logs",
        cache_uri="file:///tmp/approval/cache",
        provider_metadata={},
    )
    approval_lane.execution_environment_id = approval_env.execution_environment_id
    approval_session = store.create_agent_session(
        lane_id=approval_lane.lane_id,
        status="awaiting_approval",
        wait_reason="Need operator approval.",
        requires_human_input=False,
        capabilities=["approval-gates"],
        continuation_summary={},
    )
    approval_lane.agent_session_id = approval_session.agent_session_id

    _, input_lane = make_lane(282, "Awaiting human input", "AwaitingGitHub")
    input_session = store.create_agent_session(
        lane_id=input_lane.lane_id,
        status="awaiting_human_input",
        wait_reason="Need operator input.",
        requires_human_input=True,
        capabilities=["approval-gates"],
        continuation_summary={},
    )
    input_lane.agent_session_id = input_session.agent_session_id

    _, cancel_lane = make_lane(283, "Cancel me", "Running")
    cancel_session = store.create_agent_session(
        lane_id=cancel_lane.lane_id,
        status="running",
        wait_reason=None,
        requires_human_input=False,
        capabilities=["stream-events"],
        continuation_summary={},
    )
    cancel_lane.agent_session_id = cancel_session.agent_session_id

    _, retry_lane = make_lane(284, "Retry me", "FailedTerminal")
    retry_lane.last_error = "Runner failed."

    session.commit()
    return {
        "product": product,
        "repo": repo,
        "approval_lane": approval_lane,
        "input_lane": input_lane,
        "cancel_lane": cancel_lane,
        "retry_lane": retry_lane,
    }


def _seed_delivery_cockpit_fixture(session):
    now = _now()
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    product = store.create_product(
        org_id=org.org_id,
        key="nimbus",
        name="Nimbus",
        status="Active",
        baseline_channel="stable",
        standards_pack_key="default",
        standards_pack_version="1.2.0",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
        setup_state="ready",
        effective_config={},
        operator_overrides={},
    )
    repo = store.bind_repository(
        product_id=product.product_id,
        github_repository_node_id="R_kgDONimbus",
        owner="aegroup-io",
        name="nimbus",
        default_branch="dev",
        visibility="private",
        seed_source="agent-core",
        adoption_state="seeded",
        raw_payload={"clone_url": "https://example.invalid/nimbus.git"},
    )
    project = store.create_project_mirror(
        product_id=product.product_id,
        github_project_node_id="PVT_kgDONimbus",
        number=11,
        title="Nimbus Delivery",
        status_field_name="Status",
        status_options=["Todo", "In Progress", "Review", "Done"],
        raw_payload={"url": "https://github.com/orgs/aegroup-io/projects/11"},
        mirror_version=1,
        last_reconciled_at=now,
    )
    product.primary_repo_id = repo.repo_id
    product.primary_project_id = project.project_id
    session.flush()

    review_item = store.create_work_item(
        repo_id=repo.repo_id,
        project_id=project.project_id,
        github_issue_node_id="I_kgDONimbus401",
        issue_number=401,
        title="Review the first handoff",
        body="Review handoff",
        status="In Review",
        status_source="Review",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        dependency_state="clear",
        dependency_details=[],
        priority_hint="high",
        linked_prs=["PR_kgDONimbus77"],
        eligibility_flags=["awaiting-review"],
        handoff_status="in_review",
        requires_repair=False,
        repair_reasons=[],
        last_normalized_at=now,
        raw_payload={},
    )
    ambiguous_item = store.create_work_item(
        repo_id=repo.repo_id,
        project_id=project.project_id,
        github_issue_node_id="I_kgDONimbus402",
        issue_number=402,
        title="Mirror needs repair",
        body="Repair mirror state",
        status="Blocked",
        status_source="Status",
        labels=["type:bug"],
        assignees=[],
        dependencies=["issue:399"],
        dependency_state="ambiguous",
        dependency_details=[],
        priority_hint="medium",
        linked_prs=[],
        eligibility_flags=["repair-needed"],
        handoff_status="none",
        requires_repair=True,
        repair_reasons=["dependency.ambiguous", "status.unmapped"],
        last_normalized_at=now,
        raw_payload={},
    )
    ready_item = store.create_work_item(
        repo_id=repo.repo_id,
        project_id=project.project_id,
        github_issue_node_id="I_kgDONimbus403",
        issue_number=403,
        title="Ready for the first lane",
        body="Ready item",
        status="Ready",
        status_source="Todo",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        dependency_state="clear",
        dependency_details=[],
        priority_hint="high",
        linked_prs=[],
        eligibility_flags=["eligible"],
        handoff_status="none",
        requires_repair=False,
        repair_reasons=[],
        last_normalized_at=now,
        raw_payload={},
    )
    running_item = store.create_work_item(
        repo_id=repo.repo_id,
        project_id=project.project_id,
        github_issue_node_id="I_kgDONimbus404",
        issue_number=404,
        title="Running build work",
        body="Running item",
        status="In Progress",
        status_source="In Progress",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        dependency_state="clear",
        dependency_details=[],
        priority_hint="medium",
        linked_prs=[],
        eligibility_flags=[],
        handoff_status="none",
        requires_repair=False,
        repair_reasons=[],
        last_normalized_at=now,
        raw_payload={},
    )
    pull_request = store.create_pull_request_mirror(
        repo_id=repo.repo_id,
        github_pr_node_id="PR_kgDONimbus77",
        number=77,
        title="Open the first Nimbus handoff",
        state="open",
        is_draft=False,
        review_state="APPROVED",
        merge_state="CLEAN",
        linked_work_item_ids=[str(review_item.work_item_id)],
        raw_payload={},
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id="PVTI_nimbus_401",
        github_content_node_id=review_item.github_issue_node_id,
        content_type="Issue",
        work_item_id=review_item.work_item_id,
        status_name="Review",
        field_values_payload=[],
        raw_payload={},
        last_reconciled_at=now,
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id="PVTI_nimbus_402",
        github_content_node_id=ambiguous_item.github_issue_node_id,
        content_type="Issue",
        work_item_id=ambiguous_item.work_item_id,
        status_name="Blocked",
        field_values_payload=[],
        raw_payload={},
        last_reconciled_at=now,
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id="PVTI_nimbus_403",
        github_content_node_id=ready_item.github_issue_node_id,
        content_type="Issue",
        work_item_id=ready_item.work_item_id,
        status_name="Todo",
        field_values_payload=[],
        raw_payload={},
        last_reconciled_at=now,
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id="PVTI_nimbus_404",
        github_content_node_id=running_item.github_issue_node_id,
        content_type="Issue",
        work_item_id=running_item.work_item_id,
        status_name="In Progress",
        field_values_payload=[],
        raw_payload={},
        last_reconciled_at=now,
    )
    store.create_project_item_mirror(
        project_id=project.project_id,
        github_project_item_node_id="PVTI_nimbus_pr_77",
        github_content_node_id=pull_request.github_pr_node_id,
        content_type="PullRequest",
        pull_request_id=pull_request.pull_request_id,
        status_name="Review",
        field_values_payload=[],
        raw_payload={},
        last_reconciled_at=now,
    )
    lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=running_item.work_item_id,
        attempt=1,
        state="Running",
        claimed_at=now,
        started_at=now,
    )
    environment = store.create_execution_environment(
        lane_id=lane.lane_id,
        runtime_provider="test",
        container_image="ghcr.io/aegroup/agent-core-runner:stable",
        container_handle="aks://nimbus-running",
        status="Ready",
        workspace_uri="file:///tmp/nimbus/workspace",
        artifact_uri="file:///tmp/nimbus/artifacts",
        log_uri="file:///tmp/nimbus/logs",
        cache_uri="file:///tmp/nimbus/cache",
        provider_metadata={},
    )
    lane.execution_environment_id = environment.execution_environment_id
    session.commit()
    return {"product": product, "repo": repo, "project": project}


def test_v1_products_baselines_and_graph_routes() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        original_refresh_product_mirror = github_mirror_module.GitHubMirrorService.refresh_product_mirror

        def fake_refresh_product_mirror(self, *, product_id, ensure_webhook=False, http_get=None, http_post=None, http_patch=None):
            return ProductMirrorRefreshResult(
                issue_count=2,
                project_item_count=1,
                webhook_status="created",
                webhook_delivery_url="https://example.com/orcha/github/webhooks",
            )

        github_mirror_module.GitHubMirrorService.refresh_product_mirror = fake_refresh_product_mirror
        try:

            with TestClient(app) as client:
                org_id = client.get("/orgs").json()[0]["org_id"]
                created = client.post("/v1/products", json=_build_product_payload(org_id, repo_root))
                assert created.status_code == 201
                product_id = uuid.UUID(created.json()["product_id"])
                assert created.json()["primary_repo"]["owner"] == "aegroup-io"

                products = client.get("/v1/products")
                assert products.status_code == 200
                assert products.json()[0]["product_id"] == str(product_id)

                paused = client.post(
                    f"/v1/products/{product_id}/pause",
                    json={"actor_id": "operator-1", "reason": "Pause for maintenance."},
                )
                assert paused.status_code == 200
                assert paused.json()["status"] == "Paused"

                resume_conflict = client.post(
                    f"/v1/products/{product_id}/pause",
                    json={"actor_id": "operator-1", "reason": "Pause again."},
                )
                assert resume_conflict.status_code == 409

                resumed = client.post(
                    f"/v1/products/{product_id}/resume",
                    json={"actor_id": "operator-1", "reason": "Maintenance complete."},
                )
                assert resumed.status_code == 200
                assert resumed.json()["status"] == "Active"

                refreshed = client.post(
                    f"/v1/products/{product_id}/refresh",
                    json={"actor_id": "operator-1", "reason": "Refresh contract.", "repo_root": str(repo_root)},
                )
                assert refreshed.status_code == 200
                assert refreshed.json()["setup_state"] == "ready"

                mirror_refreshed = client.post(
                    f"/v1/products/{product_id}/refresh-mirror",
                    json={"actor_id": "operator-1", "reason": "Refresh GitHub mirror."},
                )
                assert mirror_refreshed.status_code == 200

                baseline = client.get(f"/v1/baselines/{product_id}")
                assert baseline.status_code == 200
                assert baseline.json()["drift_status"] == "current"

                graph = client.get(f"/v1/graph/products/{product_id}?depth=2")
                assert graph.status_code == 200
                assert any(node["key"] == "api-service" for node in graph.json()["nodes"])
        finally:
            github_mirror_module.GitHubMirrorService.refresh_product_mirror = original_refresh_product_mirror
        _reset_env()


def test_v1_product_refresh_uses_bound_repository_when_repo_root_is_omitted() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        class _Snapshot:
            def __enter__(self) -> Path:
                return repo_root

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        original_materialize = OperatorAPIService._materialize_product_repo_snapshot
        OperatorAPIService._materialize_product_repo_snapshot = lambda self, product: _Snapshot()
        try:
            with TestClient(app) as client:
                org_id = client.get("/orgs").json()[0]["org_id"]
                created = client.post("/v1/products", json=_build_product_payload(org_id, repo_root))
                assert created.status_code == 201
                product_id = uuid.UUID(created.json()["product_id"])

                refreshed = client.post(
                    f"/v1/products/{product_id}/refresh",
                    json={"actor_id": "operator-1", "reason": "Refresh contract from GitHub."},
                )
                assert refreshed.status_code == 200
                assert refreshed.json()["setup_state"] == "ready"
        finally:
            OperatorAPIService._materialize_product_repo_snapshot = original_materialize
            _reset_env()


def test_v1_product_refresh_clears_runtime_repair_flags() -> None:
    with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as db_dir:
        repo_root = Path(repo_dir)
        _write_fixture_repo(repo_root)
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")

        class _Snapshot:
            def __enter__(self) -> Path:
                return repo_root

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        original_materialize = OperatorAPIService._materialize_product_repo_snapshot
        original_serialize = OperatorAPIService._serialize_product
        OperatorAPIService._materialize_product_repo_snapshot = lambda self, product: _Snapshot()
        OperatorAPIService._serialize_product = lambda self, product: product
        try:
            with TestClient(app) as client:
                org_id = client.get("/orgs").json()[0]["org_id"]
                created = client.post("/v1/products", json=_build_product_payload(org_id, repo_root))
                assert created.status_code == 201
                product_id = uuid.UUID(created.json()["product_id"])

                session = get_session_factory()()
                try:
                    repo = (
                        session.query(RepositoryBinding)
                        .filter(RepositoryBinding.product_id == product_id)
                        .one()
                    )
                    store = OrchaStateStore(session)
                    work_item = store.create_work_item(
                        repo_id=repo.repo_id,
                        github_issue_node_id="I_runtimeRepairFixture",
                        issue_number=401,
                        title="Repair gating fixture",
                        body="Fixture",
                        status="Ready",
                        labels=["type:feature"],
                        assignees=[],
                        dependencies=[],
                        linked_prs=[],
                    )
                    work_item.dependency_state = "clear"
                    work_item.handoff_status = "none"
                    work_item.requires_repair = True
                    work_item.repair_reasons = [RUNNER_CAPABILITY_REPAIR_REASON]
                    work_item.eligibility_flags = ["repair-needed"]
                    session.commit()
                finally:
                    session.close()

                session = get_session_factory()()
                try:
                    refreshed = OperatorAPIService(session).refresh_product(
                        product_id,
                        actor_id="operator-1",
                        reason="Refresh contract from GitHub.",
                        repo_root=None,
                        operator_overrides={},
                    )
                    session.commit()
                    assert refreshed.product_id == product_id
                finally:
                    session.close()

                session = get_session_factory()()
                try:
                    repaired = (
                        session.query(WorkItem)
                        .filter(WorkItem.github_issue_node_id == "I_runtimeRepairFixture")
                        .one()
                    )
                    assert repaired.requires_repair is False
                    assert repaired.repair_reasons == []
                    assert "repair-needed" not in repaired.eligibility_flags
                finally:
                    session.close()
        finally:
            OperatorAPIService._materialize_product_repo_snapshot = original_materialize
            OperatorAPIService._serialize_product = original_serialize
            _reset_env()


def test_v1_product_reads_include_delivery_cockpit_summary() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                fixture = _seed_delivery_cockpit_fixture(session)
                product_id = fixture["product"].product_id
            finally:
                session.close()

            products = client.get("/v1/products")
            assert products.status_code == 200
            payload = products.json()[0]
            cockpit = payload["delivery_cockpit"]
            assert cockpit["mirror_state"] == "ambiguous"
            assert cockpit["work_pressure"]["total_open_count"] == 4
            assert cockpit["work_pressure"]["in_review_count"] == 1
            assert cockpit["project"]["url"] == "https://github.com/orgs/aegroup-io/projects/11"

            review_item = next(item for item in cockpit["work_items"] if item["issue_number"] == 401)
            assert review_item["handoff_status"] == "in_review"
            assert review_item["linked_pull_requests"][0]["number"] == 77
            assert review_item["linked_pull_requests"][0]["url"] == "https://github.com/aegroup-io/nimbus/pull/77"

            ambiguous_item = next(item for item in cockpit["work_items"] if item["issue_number"] == 402)
            assert ambiguous_item["mirror_state"] == "ambiguous"
            assert "dependency.ambiguous" in ambiguous_item["repair_reasons"]

            detail = client.get(f"/v1/products/{product_id}")
            assert detail.status_code == 200
            assert detail.json()["delivery_cockpit"]["project"]["item_count"] == 5
        _reset_env()


def test_v1_lane_reads_and_interventions() -> None:
    with tempfile.TemporaryDirectory() as db_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(db_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                fixture = _seed_lane_fixture(session)
                product_id = fixture["product"].product_id
                approval_lane_id = fixture["approval_lane"].lane_id
                input_lane_id = fixture["input_lane"].lane_id
                cancel_lane_id = fixture["cancel_lane"].lane_id
                retry_lane_id = fixture["retry_lane"].lane_id
            finally:
                session.close()

            lanes = client.get(f"/v1/lanes?product_id={product_id}")
            assert lanes.status_code == 200
            assert len(lanes.json()) == 4

            approval_lane = client.get(f"/v1/lanes/{approval_lane_id}")
            assert approval_lane.status_code == 200
            assert approval_lane.json()["agent_session"]["wait_reason"] == "Need operator approval."
            assert approval_lane.json()["execution_environment"]["workspace_uri"] == "file:///tmp/approval/workspace"

            approved = client.post(
                f"/v1/lanes/{approval_lane_id}/approve",
                json={"actor_id": "operator-1", "reason": "Approved for execution.", "approval_payload": {"ticket": "CAB-7"}},
            )
            assert approved.status_code == 200
            assert approved.json()["state"] == "Running"
            assert approved.json()["agent_session"]["last_event"] == "operator_approved"

            human_input = client.post(
                f"/v1/lanes/{input_lane_id}/human-input",
                json={"actor_id": "operator-1", "reason": "Provided context.", "input_payload": {"answer": "Proceed with fallback."}},
            )
            assert human_input.status_code == 200
            assert human_input.json()["state"] == "Running"
            assert human_input.json()["agent_session"]["last_event"] == "operator_human_input"

            cancelled = client.post(
                f"/v1/lanes/{cancel_lane_id}/cancel",
                json={"actor_id": "operator-1", "reason": "Stop this run.", "disposition": "terminate"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "Cancelled"

            retried = client.post(
                f"/v1/lanes/{retry_lane_id}/retry",
                json={"actor_id": "operator-1", "reason": "Retry after fix."},
            )
            assert retried.status_code == 200
            assert retried.json()["attempt"] == 2
            assert retried.json()["state"] == "Claimed"

            retry_conflict = client.post(
                f"/v1/lanes/{approval_lane_id}/retry",
                json={"actor_id": "operator-1", "reason": "Should fail."},
            )
            assert retry_conflict.status_code == 409

            baselines = client.get(f"/v1/baselines?org_id={product_id}")
            assert baselines.status_code == 200

            session = get_session_factory()()
            try:
                approval_signal = (
                    session.query(OperationalSignal)
                    .filter(
                        OperationalSignal.signal_type == "operator.lane.approve",
                        OperationalSignal.target_id == str(approval_lane_id),
                    )
                    .one()
                )
                assert approval_signal.value["audit"]["actor_type"] == "human"
                assert approval_signal.value["audit"]["approval_context"]["mode"] == "human-operated"
                assert approval_signal.value["audit"]["target_kind"] == "lane"
            finally:
                session.close()
        _reset_env()
