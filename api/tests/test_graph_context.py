from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import tempfile

from fastapi.testclient import TestClient

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.execution_runtime import ExecutionEnvironmentService
from agent_core_platform_api.graph_context import GraphContextService
from agent_core_platform_api.models import Organization
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.runner_protocol import RunnerProtocolService
from orcha_api.main import app


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _configure_env(database_url: str, *, remote_execution_root: Path) -> None:
    os.environ["AGENT_CORE_AUTH_DISABLED"] = "1"
    os.environ["AGENT_CORE_DATABASE_URL"] = database_url
    os.environ["AGENT_CORE_CRYPTO_SEED"] = "agent-core-test-seed"
    os.environ["AGENT_CORE_INITIAL_ORG_NAME"] = "Primary"
    os.environ["AGENT_CORE_INITIAL_ORG_SLUG"] = "primary"
    os.environ["AGENT_CORE_REMOTE_EXECUTION_ROOT"] = str(remote_execution_root)
    os.environ["AGENT_CORE_RUNTIME_PROVIDER_NAMESPACE"] = "test-namespace"
    get_settings.cache_clear()
    reset_database_state()


def _reset_env() -> None:
    get_settings.cache_clear()
    reset_database_state()


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run(*args: str) -> str:
    result = subprocess.run(list(args), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _build_remote_repo(root: Path) -> tuple[Path, str]:
    bare_repo = root / "remote.git"
    source_repo = root / "source"
    _run("git", "init", "--bare", str(bare_repo))
    _run("git", "init", "--initial-branch=dev", str(source_repo))
    _git(source_repo, "config", "user.email", "test@example.com")
    _git(source_repo, "config", "user.name", "Test User")
    (source_repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(source_repo, "add", "README.md")
    _git(source_repo, "commit", "-m", "Initial commit")
    _git(source_repo, "remote", "add", "origin", bare_repo.as_uri())
    _git(source_repo, "push", "-u", "origin", "dev")
    return source_repo, bare_repo.as_uri()


def _seed_graph_fixture(session, *, clone_url: str):
    now = _now()
    org = session.query(Organization).filter(Organization.slug == "primary").one()
    store = OrchaStateStore(session)
    effective_config = {
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
        raw_payload={"clone_url": clone_url},
    )
    peer_product = store.create_product(
        org_id=org.org_id,
        key="shared",
        name="Shared",
        status="Active",
        baseline_channel="stable",
        agent_core_version="0.1.0",
        execution_profile="standard-python",
        setup_state="ready",
        effective_config={},
        operator_overrides={},
    )

    blocked_item = store.create_work_item(
        repo_id=repo.repo_id,
        github_issue_node_id="I_kwDOAtlasBlocked",
        issue_number=271,
        title="Stabilize shared dependency",
        body="Blocked by upstream dependency health.",
        status="Blocked",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        linked_prs=[],
    )
    active_item = store.create_work_item(
        repo_id=repo.repo_id,
        github_issue_node_id="I_kwDOAtlasActive",
        issue_number=272,
        title="Refactor service-api",
        body="Active work touching the service-api component.",
        status="In Progress",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        linked_prs=["44"],
    )
    prompt_item = store.create_work_item(
        repo_id=repo.repo_id,
        github_issue_node_id="I_kwDOAtlasPrompt",
        issue_number=273,
        title="Assemble lane prompt context",
        body="Claimed lane used for prompt-context integration.",
        status="Ready",
        labels=["type:feature"],
        assignees=[],
        dependencies=[],
        linked_prs=[],
    )

    blocked_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=blocked_item.work_item_id,
        attempt=1,
        state="AwaitingApproval",
        claimed_at=now - timedelta(minutes=50),
        started_at=now - timedelta(minutes=45),
    )
    active_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=active_item.work_item_id,
        attempt=1,
        state="Running",
        claimed_at=now - timedelta(minutes=30),
        started_at=now - timedelta(minutes=25),
    )
    prompt_lane = store.create_lane(
        product_id=product.product_id,
        repo_id=repo.repo_id,
        work_item_id=prompt_item.work_item_id,
        attempt=1,
        state="Claimed",
        claimed_at=now - timedelta(minutes=10),
    )

    pull_request = store.create_pull_request_mirror(
        repo_id=repo.repo_id,
        github_pr_node_id="PR_kwDOAtlas101",
        number=101,
        title="Refactor service-api and prompt assembly",
        body="Open PR for active graph work.",
        state="open",
        is_draft=False,
        head_branch="atlas/refactor-service-api",
        base_branch="dev",
        linked_work_item_ids=[str(active_item.work_item_id)],
    )

    root_node = store.create_component_node(
        product_id=product.product_id,
        type="product",
        key="atlas",
        name="Atlas",
        owner=org.slug,
        source_kind="declared",
        source_ref="aegroup-io/atlas",
    )
    repo_node = store.create_component_node(
        product_id=product.product_id,
        type="repository",
        key="atlas-repo",
        name="atlas",
        owner="aegroup-io",
        source_kind="declared",
        source_ref="aegroup-io/atlas",
    )
    api_node = store.create_component_node(
        product_id=product.product_id,
        type="service",
        key="service-api",
        name="service-api",
        owner="platform",
        version="1.4.2",
        status="degraded",
        source_kind="declared",
        source_ref=".orcha/components.yaml",
    )
    db_node = store.create_component_node(
        product_id=product.product_id,
        type="database",
        key="service-db",
        name="service-db",
        owner="data",
        version="13.3",
        status="healthy",
        source_kind="declared",
        source_ref=".orcha/components.yaml",
    )
    shared_gateway = store.create_component_node(
        product_id=peer_product.product_id,
        type="service",
        key="shared-gateway",
        name="shared-gateway",
        owner="shared",
        version="2.1.0",
        status="degraded",
        source_kind="declared",
        source_ref=".orcha/components.yaml",
    )
    lane_cache = store.create_component_node(
        product_id=product.product_id,
        type="service",
        key="lane-cache",
        name="lane-cache",
        owner="platform",
        version="0.9.0",
        status="healthy",
        source_kind="declared",
        source_ref=".orcha/components.yaml",
    )

    store.create_component_edge(
        from_node_id=root_node.component_node_id,
        to_node_id=repo_node.component_node_id,
        relationship="owns",
        source_kind="declared",
        confidence=1.0,
    )
    store.create_component_edge(
        from_node_id=repo_node.component_node_id,
        to_node_id=api_node.component_node_id,
        relationship="deploys",
        source_kind="declared",
        confidence=1.0,
    )
    store.create_component_edge(
        from_node_id=api_node.component_node_id,
        to_node_id=db_node.component_node_id,
        relationship="depends_on",
        source_kind="declared",
        confidence=0.9,
    )
    store.create_component_edge(
        from_node_id=api_node.component_node_id,
        to_node_id=shared_gateway.component_node_id,
        relationship="depends_on",
        source_kind="declared",
        confidence=0.8,
    )

    store.record_operational_signal(
        target_kind="component_node",
        target_id=str(api_node.component_node_id),
        signal_type="component.deployment",
        severity="warning",
        value={"environment": "prod", "status": "degraded"},
        observed_at=now - timedelta(minutes=8),
        source_kind="runtime",
    )
    store.record_operational_signal(
        target_kind="component_node",
        target_id=str(api_node.component_node_id),
        signal_type="lane.assignment",
        severity="info",
        value={"lane_id": str(active_lane.lane_id), "work_item_id": str(active_item.work_item_id)},
        observed_at=now - timedelta(minutes=6),
        source_kind="scheduler",
    )
    store.record_operational_signal(
        target_kind="component_node",
        target_id=str(api_node.component_node_id),
        signal_type="lane.assignment",
        severity="info",
        value={"lane_id": str(blocked_lane.lane_id), "work_item_id": str(blocked_item.work_item_id)},
        observed_at=now - timedelta(minutes=5),
        source_kind="scheduler",
    )
    store.record_operational_signal(
        target_kind="component_node",
        target_id=str(shared_gateway.component_node_id),
        signal_type="component.incident",
        severity="error",
        value={"summary": "Shared gateway latency incident"},
        observed_at=now - timedelta(minutes=4),
        source_kind="operator",
    )
    store.record_operational_signal(
        target_kind="component_node",
        target_id=str(lane_cache.component_node_id),
        signal_type="lane.assignment",
        severity="info",
        value={"laneId": str(prompt_lane.lane_id), "workItemId": str(prompt_item.work_item_id)},
        observed_at=now - timedelta(minutes=3),
        source_kind="scheduler",
    )

    product.primary_repo_id = repo.repo_id
    product.component_root_node_id = root_node.component_node_id
    session.flush()
    return {
        "product": product,
        "repo": repo,
        "peer_product": peer_product,
        "blocked_item": blocked_item,
        "active_item": active_item,
        "prompt_item": prompt_item,
        "blocked_lane": blocked_lane,
        "active_lane": active_lane,
        "prompt_lane": prompt_lane,
        "pull_request": pull_request,
        "nodes": {
            "root": root_node,
            "repo": repo_node,
            "api": api_node,
            "db": db_node,
            "shared": shared_gateway,
            "cache": lane_cache,
        },
    }


def test_graph_context_service_builds_product_slice_with_overlays_and_blocked_dependencies() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                fixture = _seed_graph_fixture(session, clone_url=clone_url)
                service = GraphContextService(session)

                graph_slice = service.build_product_slice(
                    fixture["product"].product_id,
                    depth=3,
                    component_keys=["service-api"],
                )

                keys = {node["key"] for node in graph_slice["nodes"]}
                assert keys == {"atlas", "atlas-repo", "service-api", "service-db", "shared-gateway"}

                node_by_key = {node["key"]: node for node in graph_slice["nodes"]}
                repo_overlay = node_by_key["atlas-repo"]["overlay"]
                assert len(repo_overlay["active_work_items"]) == 3
                assert len(repo_overlay["open_pull_requests"]) == 1
                assert len(repo_overlay["active_lanes"]) == 3

                api_overlay = node_by_key["service-api"]["overlay"]
                assert api_overlay["hotspot_score"] == 2
                assert {item["lane_id"] for item in api_overlay["active_lanes"]} == {
                    fixture["active_lane"].lane_id,
                    fixture["blocked_lane"].lane_id,
                }
                assert api_overlay["signals"][0]["signal_type"] == "component.deployment"

                shared_overlay = node_by_key["shared-gateway"]["overlay"]
                assert shared_overlay["incidents"][0]["signal_type"] == "component.incident"
                assert shared_overlay["incidents"][0]["observed_at"] is not None

                assert any(
                    item["to_key"] == "shared-gateway" and item["cross_product"] is True and item["reason"] == "incident"
                    for item in graph_slice["blocked_dependencies"]
                )
                assert any(item["key"] == "service-api" and item["hotspot_score"] == 2 for item in graph_slice["hotspots"])
                assert graph_slice["freshness"]["status"] == "fresh"
            finally:
                session.close()
        _reset_env()


def test_graph_slice_api_exposes_lane_context_with_overlay_timestamps() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                fixture = _seed_graph_fixture(session, clone_url=clone_url)
                lane_id = fixture["active_lane"].lane_id
                prompt_lane_id = fixture["prompt_lane"].lane_id
                product_id = fixture["product"].product_id
                session.commit()
            finally:
                session.close()

            lane_response = client.get(f"/graph/lanes/{lane_id}/slice?depth=3")
            assert lane_response.status_code == 200
            lane_payload = lane_response.json()
            assert lane_payload["scope"] == "lane"
            assert lane_payload["lane_id"] == str(lane_id)
            assert lane_payload["product_id"] == str(product_id)
            assert any(node["key"] == "shared-gateway" for node in lane_payload["nodes"])
            assert lane_payload["blocked_dependencies"][0]["observed_at"] is not None

            prompt_response = client.get(f"/graph/lanes/{prompt_lane_id}/slice?depth=3")
            assert prompt_response.status_code == 200
            prompt_payload = prompt_response.json()
            assert any(node["key"] == "lane-cache" for node in prompt_payload["nodes"])

            product_response = client.get(
                f"/graph/products/{product_id}/slice?component_key=service-api&depth=1"
            )
            assert product_response.status_code == 200
            product_payload = product_response.json()
            keys = {node["key"] for node in product_payload["nodes"]}
            assert keys == {"atlas-repo", "service-api", "service-db", "shared-gateway"}
        _reset_env()


def test_runner_protocol_launch_bundle_includes_compact_graph_context() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        remote_root = temp_path / "remote-execution"
        _configure_env(f"sqlite+pysqlite:///{temp_path / 'runtime.db'}", remote_execution_root=remote_root)
        _, clone_url = _build_remote_repo(temp_path)

        with TestClient(app):
            session = get_session_factory()()
            try:
                fixture = _seed_graph_fixture(session, clone_url=clone_url)
                environment = ExecutionEnvironmentService(session).provision_claimed_lane(fixture["prompt_lane"].lane_id)
                launch_request = RunnerProtocolService(session).prepare_lane_session(
                    fixture["prompt_lane"].lane_id,
                    instruction_bundle={"task": "Explain graph context before running."},
                    policy={"approval_posture": "operator-gated"},
                )
                session.commit()

                graph_context = launch_request.instruction_bundle["graph_context"]
                assert graph_context["scope"] == "lane"
                assert graph_context["lane_id"] == str(fixture["prompt_lane"].lane_id)
                assert graph_context["freshness"]["status"] == "fresh"
                assert environment.workspace_uri is not None
                assert any(node["key"] == "service-api" for node in graph_context["nodes"])
                assert any(item["to_key"] == "shared-gateway" for item in graph_context["blocked_dependencies"])
                assert any(item["key"] == "atlas-repo" for item in graph_context["hotspots"])
            finally:
                session.close()
        _reset_env()
