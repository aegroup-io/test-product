from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
import yaml

from fastapi.testclient import TestClient
import httpx
import pytest

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.db import get_session_factory, reset_database_state
from agent_core_platform_api.github_integration import GitHubAppAuthError
from agent_core_platform_api.models import GitHubProjectMirror, ManagedAsset, Organization, Product, RepositoryBinding
from agent_core_platform_api.product_seeding import ProjectSeedResult, RepositorySeedResult
import agent_core_platform_api.product_seeding as product_seeding_module
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


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _create_local_bare_remote(root: Path, *, default_branch: str = "dev") -> Path:
    bare_repo = root / "remote.git"
    _git(["init", "--bare", str(bare_repo)])
    worktree = root / "seed"
    worktree.mkdir(parents=True, exist_ok=True)
    _git(["init"], cwd=worktree)
    _git(["config", "user.name", "Test Seeder"], cwd=worktree)
    _git(["config", "user.email", "test-seeder@example.com"], cwd=worktree)
    (worktree / "README.md").write_text("# Seed\n", encoding="utf-8")
    _git(["add", "README.md"], cwd=worktree)
    _git(["commit", "-m", "Initial commit"], cwd=worktree)
    _git(["branch", "-M", default_branch], cwd=worktree)
    _git(["remote", "add", "origin", str(bare_repo)], cwd=worktree)
    _git(["push", "-u", "origin", default_branch], cwd=worktree)
    _git(["symbolic-ref", "HEAD", f"refs/heads/{default_branch}"], cwd=bare_repo)
    return bare_repo


def _install_pre_receive_hook(bare_repo: Path, script: str) -> None:
    hook_path = bare_repo / "hooks" / "pre-receive"
    hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)


class _FakeSeedAdapter:
    def __init__(
        self,
        *,
        views: list[str] | None = None,
        labels: list[str] | None = None,
        apply_result: product_seeding_module.BundleApplyResult | None = None,
        mirror_refresh_result: product_seeding_module.ProductMirrorRefreshResult | None = None,
    ):
        self.bundle_paths: list[str] = []
        self.bundle_contents: dict[str, bytes] = {}
        self.views = views or ["Board", "Ready Queue"]
        self.labels = labels or ["type:feature", "type:spike"]
        self.apply_result = apply_result
        self.mirror_refresh_result = mirror_refresh_result or product_seeding_module.ProductMirrorRefreshResult()
        self.bootstrap_called = False

    def prepare_repository(self, request) -> RepositorySeedResult:
        return RepositorySeedResult(
            github_repository_node_id="R_seed_repo",
            owner=request.github_owner,
            name=request.github_repo,
            default_branch=request.github_default_branch,
            visibility=request.github_visibility,
            description=request.description,
            labels=list(self.labels),
            permissions={
                "metadata": "read",
                "contents": "write",
                "issues": "write",
                "pull_requests": "write",
                "administration": "write",
                "organization_projects": "write",
            },
            branch_protection={
                "enabled": True,
                "required_pull_request_reviews": {
                    "required_approving_review_count": 1,
                },
            },
            raw_payload={
                "node_id": "R_seed_repo",
                "owner": {"login": request.github_owner},
                "name": request.github_repo,
                "default_branch": request.github_default_branch,
                "visibility": request.github_visibility,
                "description": request.description,
                "archived": False,
                "labels": list(self.labels),
            },
        )

    def ensure_project(self, request, repository: RepositorySeedResult) -> ProjectSeedResult:
        fields = [
            {
                "node_id": "PVTF_status",
                "name": request.status_field,
                "data_type": "single_select",
                "options": [
                    {"id": "todo", "name": request.ready_status, "color": "GRAY"},
                    {"id": "progress", "name": "In Progress", "color": "BLUE"},
                    {"id": "done", "name": request.done_status, "color": "GREEN"},
                ],
            },
            {
                "node_id": "PVTF_priority",
                "name": "Priority",
                "data_type": "text",
                "options": [],
            },
            {
                "node_id": "PVTF_depends",
                "name": "Depends On",
                "data_type": "text",
                "options": [],
            },
        ]
        raw_payload = {
            "node_id": "PVT_seed_project",
            "number": 42,
            "title": request.github_project_title or request.product_name,
            "status_field_name": request.status_field,
            "status_options": [request.ready_status, "In Progress", request.done_status],
            "fields": fields,
            "items": [],
            "views": list(self.views),
            "templates": [
                ".github/pull_request_template.md",
                ".github/ISSUE_TEMPLATE/feature.yml",
            ],
        }
        return ProjectSeedResult(
            github_project_node_id="PVT_seed_project",
            number=42,
            title=request.github_project_title or request.product_name,
            status_field_name=request.status_field,
            status_options=[request.ready_status, "In Progress", request.done_status],
            fields=fields,
            views=list(self.views),
            templates=[
                ".github/pull_request_template.md",
                ".github/ISSUE_TEMPLATE/feature.yml",
            ],
            raw_payload=raw_payload,
        )

    def apply_bundle(
        self,
        request,
        repository: RepositorySeedResult,
        bundle,
    ) -> product_seeding_module.BundleApplyResult | None:
        self.bundle_paths = [item.path for item in bundle.files]
        self.bundle_contents = {item.path: item.content for item in bundle.files}
        return self.apply_result

    def bootstrap_product_mirror(self, product: Product) -> product_seeding_module.ProductMirrorRefreshResult:
        self.bootstrap_called = True
        return self.mirror_refresh_result


def _seed_request(
    org_id: str,
    *,
    dry_run: bool = False,
    required_secret_keys: list[str] | None = None,
) -> dict[str, object]:
    return {
        "org_id": org_id,
        "installation_id": None if dry_run else "12345",
        "product_key": "apollo",
        "product_name": "Apollo",
        "description": "Seeded product",
        "github_owner": "aegroup-io",
        "github_repo": "apollo",
        "github_visibility": "private",
        "github_default_branch": "dev",
        "github_project_title": "Apollo",
        "status_field": "Status",
        "ready_status": "Todo",
        "done_status": "Done",
        "required_secret_keys": required_secret_keys or [],
        "dry_run": dry_run,
    }


def test_seed_product_creates_repo_binding_project_mirror_and_active_product(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        fake_adapter = _FakeSeedAdapter()
        monkeypatch.setattr(
            product_seeding_module,
            "build_seed_adapter",
            lambda session, request: fake_adapter,
        )

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()
            response = client.post("/products/seed", json=_seed_request(org_id))
            assert response.status_code == 201
            payload = response.json()
            assert payload["status"] == "Succeeded"
            assert payload["product"]["status"] == "Active"
            assert payload["product"]["setup_state"] == "ready"
            assert ".orcha/product.yaml" in payload["rendered_file_paths"]
            assert "AGENTS.md" in fake_adapter.bundle_paths
            rendered_manifest = yaml.safe_load(fake_adapter.bundle_contents[".orcha/product.yaml"].decode("utf-8"))
            assert rendered_manifest["governance"]["approval_posture"] == "high-trust"
            assert fake_adapter.bootstrap_called is True

            job_detail = client.get(f"/products/seed-jobs/{payload['seed_job_id']}")
            assert job_detail.status_code == 200
            assert job_detail.json()["product"]["key"] == "apollo"

            session = get_session_factory()()
            try:
                product = session.query(Product).filter(Product.key == "apollo").one()
                repo = session.query(RepositoryBinding).filter(RepositoryBinding.product_id == product.product_id).one()
                project = session.query(GitHubProjectMirror).filter(GitHubProjectMirror.product_id == product.product_id).one()
                managed_assets = (
                    session.query(ManagedAsset)
                    .filter(ManagedAsset.product_id == product.product_id)
                    .all()
                )
                assert repo.owner == "aegroup-io"
                assert repo.default_branch == "dev"
                assert project.number == 42
                assert project.status_field_name == "Status"
                assert product.component_root_node_id is not None
                assert {asset.path for asset in managed_assets} >= {
                    "AGENTS.md",
                    ".github/pull_request_template.md",
                }
            finally:
                session.close()
        _reset_env()


def test_seed_product_blocks_activation_when_required_secret_is_missing(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        monkeypatch.setattr(
            product_seeding_module,
            "build_seed_adapter",
            lambda session, request: _FakeSeedAdapter(),
        )

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()
            response = client.post(
                "/products/seed",
                json=_seed_request(org_id, required_secret_keys=["missing-secret"]),
            )
            assert response.status_code == 201
            payload = response.json()
            assert payload["status"] == "Blocked"
            assert payload["product"]["status"] == "Draft"
            assert payload["setup_state"] == "setup-needed"
            assert "secret.required_missing" in {item["code"] for item in payload["setup_diagnostics"]}
        _reset_env()


def test_seed_product_reports_missing_views_and_labels_as_recoverable_drift(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        fake_adapter = _FakeSeedAdapter(views=["Table"], labels=["bug"])
        monkeypatch.setattr(
            product_seeding_module,
            "build_seed_adapter",
            lambda session, request: fake_adapter,
        )

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()
            response = client.post("/products/seed", json=_seed_request(org_id))
            assert response.status_code == 201
            payload = response.json()
            assert payload["status"] == "Succeeded"
            assert payload["product"]["status"] == "Active"
            assert payload["product"]["setup_state"] == "drift"
            diagnostic_codes = {item["code"] for item in payload["setup_diagnostics"]}
            assert "github.project.view_missing" in diagnostic_codes
            assert "github.repo.label_missing" in diagnostic_codes
        _reset_env()


def test_seed_product_blocks_activation_when_baseline_pr_is_pending(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        fake_adapter = _FakeSeedAdapter(
            apply_result=product_seeding_module.BundleApplyResult(
                mode="pull_request",
                base_branch="dev",
                head_branch="orcha/seed/apollo/baseline",
                pull_request_number=17,
                pull_request_url="https://github.example/aegroup-io/apollo/pull/17",
                commit_shas=["commit-sha-1"],
            )
        )
        monkeypatch.setattr(
            product_seeding_module,
            "build_seed_adapter",
            lambda session, request: fake_adapter,
        )

        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()
            response = client.post("/products/seed", json=_seed_request(org_id))
            assert response.status_code == 201
            payload = response.json()
            assert payload["status"] == "Blocked"
            assert payload["product"]["status"] == "Draft"
            assert payload["setup_state"] == "setup-needed"
            diagnostic_codes = {item["code"] for item in payload["setup_diagnostics"]}
            assert "github.repo.seed_pull_request_pending" in diagnostic_codes
            bundle_audit = next(item for item in payload["audit_payload"] if item["step"] == "github.bundle")
            assert bundle_audit["status"] == "blocked"
            assert bundle_audit["details"]["pull_request_number"] == 17
        _reset_env()


def test_seed_product_dry_run_records_bundle_outputs_without_creating_product() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app) as client:
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
            finally:
                session.close()
            response = client.post("/products/seed", json=_seed_request(org_id, dry_run=True))
            assert response.status_code == 201
            payload = response.json()
            assert payload["status"] == "DryRun"
            assert payload["product"] is None
            assert payload["setup_state"] == "ready"
            assert ".orcha/product.yaml" in payload["rendered_file_paths"]
            assert ".orcha/components.yaml" in payload["rendered_file_paths"]

            job_detail = client.get(f"/products/seed-jobs/{payload['seed_job_id']}")
            assert job_detail.status_code == 200
            assert job_detail.json()["status"] == "DryRun"

            session = get_session_factory()()
            try:
                assert session.query(Product).count() == 0
            finally:
                session.close()
        _reset_env()


def test_runtime_module_files_excludes_local_virtualenv_and_cache_artifacts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        (repo_root / "api" / "src").mkdir(parents=True, exist_ok=True)
        (repo_root / "api" / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
        (repo_root / "api" / ".pytest_cache" / "v").mkdir(parents=True, exist_ok=True)
        (repo_root / "api" / "__pycache__").mkdir(parents=True, exist_ok=True)
        (repo_root / "api" / "src" / "orcha_api.py").write_text("print('ok')\n", encoding="utf-8")
        (repo_root / "api" / ".gitignore").write_text(".venv/\n", encoding="utf-8")
        (repo_root / "api" / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
        (repo_root / "api" / ".pytest_cache" / "v" / "cache").write_text("", encoding="utf-8")
        (repo_root / "api" / "__pycache__" / "orcha_api.cpython-312.pyc").write_text("", encoding="utf-8")

        bundle = product_seeding_module._runtime_module_files(  # noqa: SLF001 - targeted unit coverage
            repo_root,
            {"modules": [{"target": "api"}]},
        )

        assert sorted(bundle) == ["api/.gitignore", "api/src/orcha_api.py"]


def test_repo_root_resolves_from_packaged_platform_api_layout(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        module_path = (
            repo_root
            / "packages"
            / "platform-api"
            / "src"
            / "agent_core_platform_api"
            / "product_seeding.py"
        )
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text("# packaged module path marker\n", encoding="utf-8")
        (repo_root / ".agent-core").mkdir(parents=True, exist_ok=True)
        (repo_root / ".orcha").mkdir(parents=True, exist_ok=True)
        (repo_root / ".agent-core" / "product-baseline.json").write_text("{}", encoding="utf-8")
        (repo_root / ".orcha" / "product.yaml").write_text("name: Orcha\n", encoding="utf-8")

        monkeypatch.setattr(product_seeding_module, "__file__", str(module_path))

        assert product_seeding_module._repo_root() == repo_root.resolve()  # noqa: SLF001 - direct regression coverage


def test_api_dockerfile_copies_seed_rendering_assets() -> None:
    dockerfile = (Path(__file__).resolve().parents[2] / "api" / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (Path(__file__).resolve().parents[2] / ".dockerignore").read_text(encoding="utf-8")
    ignored_patterns = {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "COPY . /app" in dockerfile
    assert ".github" not in ignored_patterns
    assert "**/.env.*" in dockerignore
    assert "**/backend.tf" in dockerignore
    assert "**/terraform.tfvars" in dockerignore


def test_github_seed_adapter_reads_actual_views_for_bound_projects(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)
                adapter._api_base_url = "https://api.github.com"
                monkeypatch.setattr(adapter, "_token_for_request", lambda request: "token")
                monkeypatch.setattr(
                    product_seeding_module.GitHubMirrorService,
                    "_fetch_project_snapshot",
                    lambda self, **kwargs: {
                        "id": "PVT_existing",
                        "number": 42,
                        "title": "Apollo",
                        "fields": [
                            {
                                "id": "PVTF_priority",
                                "name": "Priority",
                                "dataType": "TEXT",
                            },
                            {
                                "id": "PVTF_status",
                                "name": "Status",
                                "dataType": "SINGLE_SELECT",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                    {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                    {"id": "done", "name": "Done", "color": "GREEN"},
                                ],
                            },
                            {
                                "id": "PVTF_depends",
                                "name": "Depends On",
                                "dataType": "TEXT",
                            },
                        ],
                        "items": [],
                    },
                )
                monkeypatch.setattr(
                    adapter,
                    "_fetch_project_views",
                    lambda *, project_id, token, owner, repo: ["Table"],
                )
                request = product_seeding_module.ProductSeedRequest.model_validate(
                    {
                        **_seed_request(org_id),
                        "github_project_node_id": "PVT_existing",
                        "github_project_number": 42,
                    }
                )
                repository = _FakeSeedAdapter().prepare_repository(request)

                result = adapter.ensure_project(request, repository)

                assert result.views == ["Table"]
                assert result.status_options == ["Todo", "In Progress", "Done"]
                assert result.raw_payload["views"] == ["Table"]
            finally:
                session.close()
        _reset_env()


def test_github_seed_adapter_reads_actual_views_for_created_projects(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)
                monkeypatch.setattr(adapter, "_lookup_owner_node_id", lambda **kwargs: "O_owner")
                monkeypatch.setattr(
                    adapter,
                    "_graphql",
                    lambda **kwargs: {
                        "createProjectV2": {
                            "projectV2": {
                                "id": "PVT_created",
                                "number": 42,
                                "title": "Apollo",
                            }
                        }
                    },
                )
                monkeypatch.setattr(
                    product_seeding_module.GitHubMirrorService,
                    "_fetch_project_snapshot",
                    lambda self, **kwargs: {
                        "id": "PVT_created",
                        "number": 42,
                        "title": "Apollo",
                        "fields": [
                            {
                                "id": "PVTF_status",
                                "name": "Status",
                                "dataType": "SINGLE_SELECT",
                                "options": [
                                    {"id": "todo", "name": "Todo", "color": "GRAY"},
                                    {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                    {"id": "done", "name": "Done", "color": "GREEN"},
                                ],
                            },
                            {
                                "id": "PVTF_priority",
                                "name": "Priority",
                                "dataType": "TEXT",
                            },
                            {
                                "id": "PVTF_depends",
                                "name": "Depends On",
                                "dataType": "TEXT",
                            },
                        ],
                        "items": [],
                    },
                )
                monkeypatch.setattr(adapter, "_create_project_field", lambda **kwargs: None)
                monkeypatch.setattr(
                    adapter,
                    "_fetch_project_views",
                    lambda *, project_id, token, owner, repo: ["Table"],
                )
                request = product_seeding_module.ProductSeedRequest.model_validate(_seed_request(org_id))

                payload = adapter._create_project_payload(request, "token")  # noqa: SLF001 - targeted unit coverage

                assert payload["views"] == ["Table"]
                assert payload["status_options"] == ["Todo", "In Progress", "Done"]
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_reuses_existing_reserved_status_field(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)
                created_fields: list[str] = []
                snapshot_calls = {"count": 0}

                monkeypatch.setattr(adapter, "_lookup_owner_node_id", lambda **kwargs: "O_owner")
                monkeypatch.setattr(
                    adapter,
                    "_graphql",
                    lambda **kwargs: {
                        "createProjectV2": {
                            "projectV2": {
                                "id": "PVT_created",
                                "number": 42,
                                "title": "Apollo",
                            }
                        }
                    },
                )

                def fake_fetch_project_snapshot(self, **kwargs):
                    snapshot_calls["count"] += 1
                    fields = [
                        {
                            "id": "PVTF_title",
                            "name": "Title",
                            "dataType": "TEXT",
                        },
                        {
                            "id": "PVTF_status",
                            "name": "Status",
                            "dataType": "SINGLE_SELECT",
                            "options": [
                                {"id": "todo", "name": "Todo", "color": "GRAY"},
                                {"id": "progress", "name": "In Progress", "color": "BLUE"},
                                {"id": "done", "name": "Done", "color": "GREEN"},
                            ],
                        },
                    ]
                    if snapshot_calls["count"] > 1:
                        fields.extend(
                            [
                                {"id": "PVTF_priority", "name": "Priority", "dataType": "TEXT"},
                                {"id": "PVTF_depends", "name": "Depends On", "dataType": "TEXT"},
                            ]
                        )
                    return {
                        "id": "PVT_created",
                        "number": 42,
                        "title": "Apollo",
                        "fields": fields,
                        "items": [],
                    }

                monkeypatch.setattr(
                    product_seeding_module.GitHubMirrorService,
                    "_fetch_project_snapshot",
                    fake_fetch_project_snapshot,
                )
                monkeypatch.setattr(
                    adapter,
                    "_create_project_field",
                    lambda **kwargs: created_fields.append(str(kwargs["field_payload"]["name"])),
                )
                monkeypatch.setattr(adapter, "_fetch_project_views", lambda **kwargs: ["Table"])

                request = product_seeding_module.ProductSeedRequest.model_validate(_seed_request(org_id))

                payload = adapter._create_project_payload(request, "token")  # noqa: SLF001 - targeted unit coverage

                assert created_fields == ["Priority", "Depends On"]
                assert payload["status_field_name"] == "Status"
                assert payload["status_options"] == ["Todo", "In Progress", "Done"]
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_includes_single_select_option_descriptions() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                captured: dict[str, object] = {}

                def fake_graphql(**kwargs):
                    captured["variables"] = kwargs["variables"]
                    return {}

                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)
                adapter._graphql = fake_graphql  # type: ignore[method-assign]  # noqa: SLF001 - targeted unit coverage

                adapter._create_project_field(  # noqa: SLF001 - targeted unit coverage
                    token="token",
                    owner="aegroup-io",
                    repo="apollo",
                    project_id="PVT_created",
                    field_payload={
                        "name": "Status",
                        "data_type": "single_select",
                        "options": [
                            {"name": "Todo", "color": "GRAY"},
                            {"name": "In Progress", "color": "BLUE"},
                            {"name": "Done", "color": "GREEN", "description": "Completed work"},
                        ],
                    },
                )

                variables = captured["variables"]
                assert isinstance(variables, dict)
                assert variables["singleSelectOptions"] == [
                    {"name": "Todo", "color": "GRAY", "description": "Todo"},
                    {"name": "In Progress", "color": "BLUE", "description": "In Progress"},
                    {"name": "Done", "color": "GREEN", "description": "Completed work"},
                ]
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_prepares_existing_repository(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                observed: dict[str, str] = {}

                def fake_get(url: str, **kwargs):
                    observed["get_url"] = url
                    return httpx.Response(
                        200,
                        json={
                            "node_id": "R_existing_repo",
                            "name": "apollo",
                            "default_branch": "dev",
                            "visibility": "private",
                            "description": "Seeded product",
                            "permissions": {"contents": "write"},
                        },
                    )

                def fake_post(url: str, **kwargs):
                    observed["post_url"] = url
                    return httpx.Response(500, json={"message": "should not be called"})

                adapter = product_seeding_module.GitHubPatProductSeedAdapter(
                    session,
                    http_get=fake_get,
                    http_post=fake_post,
                )
                adapter._api_base_url = "https://api.github.com"
                monkeypatch.setattr(adapter, "_token_for_request", lambda request: "token")
                monkeypatch.setattr(
                    adapter,
                    "_fetch_branch_protection",
                    lambda **kwargs: {
                        "enabled": False,
                        "requires_pull_request": False,
                        "required_approving_review_count": 0,
                        "allows_force_pushes": False,
                        "allows_deletions": False,
                    },
                )
                monkeypatch.setattr(adapter, "_list_repository_labels", lambda **kwargs: ["type:feature"])

                request = product_seeding_module.ProductSeedRequest.model_validate(_seed_request(org_id))

                result = adapter.prepare_repository(request)

                assert observed["get_url"] == "https://api.github.com/repos/aegroup-io/apollo"
                assert "post_url" not in observed
                assert result.github_repository_node_id == "R_existing_repo"
                assert result.branch_protection["enabled"] is False
                assert result.raw_payload["default_branch_protection"]["requires_pull_request"] is False
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_bootstraps_product_mirror(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org = session.query(Organization).filter(Organization.slug == "primary").one()
                product = Product(
                    org_id=org.org_id,
                    key="apollo",
                    name="Apollo",
                    status="Active",
                    setup_state="ready",
                )
                session.add(product)
                session.commit()

                observed: dict[str, object] = {}

                def fake_refresh_product_mirror(self, **kwargs):
                    observed.update(kwargs)
                    return product_seeding_module.ProductMirrorRefreshResult(
                        issue_count=3,
                        project_item_count=2,
                        webhook_status="created",
                        webhook_delivery_url="https://example.com/orcha/github/webhooks",
                    )

                monkeypatch.setattr(
                    product_seeding_module.GitHubMirrorService,
                    "refresh_product_mirror",
                    fake_refresh_product_mirror,
                )
                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)

                result = adapter.bootstrap_product_mirror(product)

                assert observed["product_id"] == product.product_id
                assert observed["ensure_webhook"] is True
                assert result.issue_count == 3
                assert result.webhook_status == "created"
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_resolves_user_owner_node_id(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        _configure_env(f"sqlite+pysqlite:///{Path(temp_dir) / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                observed: dict[str, str] = {}

                def fake_get(url: str, **kwargs):
                    observed["get_url"] = url
                    return httpx.Response(
                        200,
                        json={
                            "login": "aegroup-io",
                            "node_id": "MDQ6VXNlcjU2ODA0NTQ3",
                            "type": "User",
                        },
                    )

                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session, http_get=fake_get)
                adapter._api_base_url = "https://api.github.com"

                owner_id = adapter._lookup_owner_node_id(  # noqa: SLF001 - targeted unit coverage
                    token="token",
                    owner="aegroup-io",
                    repo="apollo",
                    login="aegroup-io",
                )

                assert observed["get_url"] == "https://api.github.com/users/aegroup-io"
                assert owner_id == "MDQ6VXNlcjU2ODA0NTQ3"
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_publishes_bundle_with_git_push(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        bare_repo = _create_local_bare_remote(temp_root)
        _configure_env(f"sqlite+pysqlite:///{temp_root / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                protection_calls: list[dict[str, str]] = []

                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)
                monkeypatch.setattr(adapter, "_token_for_request", lambda request: "token")
                monkeypatch.setattr(adapter, "_repository_clone_url_for_request", lambda request: str(bare_repo))
                monkeypatch.setattr(
                    adapter,
                    "_ensure_branch_protection",
                    lambda **kwargs: protection_calls.append(
                        {"owner": kwargs["owner"], "repo": kwargs["repo"], "branch": kwargs["branch"]}
                    )
                    or {
                        "enabled": True,
                        "requires_pull_request": True,
                        "required_approving_review_count": 1,
                        "allows_force_pushes": False,
                        "allows_deletions": False,
                    },
                )
                monkeypatch.setattr(adapter, "_ensure_repository_labels", lambda **kwargs: ["type:feature", "type:spike"])

                request = product_seeding_module.ProductSeedRequest.model_validate(_seed_request(org_id))
                repository = RepositorySeedResult(
                    github_repository_node_id="R_seed_repo",
                    owner="aegroup-io",
                    name="apollo",
                    default_branch="dev",
                    visibility="private",
                    description="Seeded product",
                    labels=[],
                    permissions={},
                    branch_protection={},
                    raw_payload={},
                )
                bundle = product_seeding_module.RenderedSeedBundle(
                    files=[
                        product_seeding_module.RenderedBundleFile(
                            path=".agent-core/delivery-baseline-smoke.json",
                            content=b"{}\n",
                            source="rendered",
                        )
                    ],
                    manifest={},
                    components={},
                    baseline_version="test",
                )

                result = adapter.apply_bundle(request, repository, bundle)

                assert result.mode == "direct"
                assert len(result.commit_shas) == 1
                assert protection_calls == [{"owner": "aegroup-io", "repo": "apollo", "branch": "dev"}]
                assert repository.branch_protection["requires_pull_request"] is True
                seeded_content = _git(
                    ["--git-dir", str(bare_repo), "show", "dev:.agent-core/delivery-baseline-smoke.json"]
                )
                assert seeded_content == "{}"
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_falls_back_to_seed_pull_request_when_git_push_is_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        bare_repo = _create_local_bare_remote(temp_root)
        _install_pre_receive_hook(
            bare_repo,
            """#!/bin/sh
while read oldrev newrev refname
do
  if [ "$refname" = "refs/heads/dev" ]; then
    echo "remote: error: GH006: Protected branch update failed for refs/heads/dev." >&2
    echo "remote: Changes must be made through a pull request." >&2
    exit 1
  fi
done
exit 0
""",
        )
        _configure_env(f"sqlite+pysqlite:///{temp_root / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                request_log: list[tuple[str, dict[str, object] | None]] = []

                def fake_post(url: str, **kwargs):
                    request_log.append((url, kwargs.get("json")))
                    if url.endswith("/pulls"):
                        return httpx.Response(
                            201,
                            json={"number": 17, "html_url": "https://github.example/aegroup-io/apollo/pull/17"},
                        )
                    raise AssertionError(f"Unexpected POST {url}")

                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session, http_post=fake_post)
                adapter._api_base_url = "https://api.github.test"
                monkeypatch.setattr(adapter, "_token_for_request", lambda request: "token")
                monkeypatch.setattr(adapter, "_repository_clone_url_for_request", lambda request: str(bare_repo))
                monkeypatch.setattr(
                    adapter,
                    "_ensure_branch_protection",
                    lambda **kwargs: {
                        "enabled": True,
                        "requires_pull_request": True,
                        "required_approving_review_count": 1,
                        "allows_force_pushes": False,
                        "allows_deletions": False,
                    },
                )
                monkeypatch.setattr(adapter, "_ensure_repository_labels", lambda **kwargs: ["type:feature", "type:spike"])

                request = product_seeding_module.ProductSeedRequest.model_validate(_seed_request(org_id))
                repository = RepositorySeedResult(
                    github_repository_node_id="R_seed_repo",
                    owner="aegroup-io",
                    name="apollo",
                    default_branch="dev",
                    visibility="private",
                    description="Seeded product",
                    labels=[],
                    permissions={},
                    branch_protection={},
                    raw_payload={},
                )
                bundle = product_seeding_module.RenderedSeedBundle(
                    files=[
                        product_seeding_module.RenderedBundleFile(
                            path=".agent-core/delivery-baseline-smoke.json",
                            content=b"{}\n",
                            source="rendered",
                        )
                    ],
                    manifest={},
                    components={},
                    baseline_version="test",
                )

                result = adapter.apply_bundle(request, repository, bundle)

                assert result.mode == "pull_request"
                assert result.pull_request_number == 17
                assert result.head_branch == "orcha/seed/apollo/baseline"
                seeded_content = _git(
                    [
                        "--git-dir",
                        str(bare_repo),
                        "show",
                        "orcha/seed/apollo/baseline:.agent-core/delivery-baseline-smoke.json",
                    ]
                )
                assert seeded_content == "{}"
                assert request_log == [
                    (
                        "https://api.github.test/repos/aegroup-io/apollo/pulls",
                        {
                            "title": "Seed approved baseline for Apollo",
                            "body": (
                                "This pull request was opened by Orcha live seed because the repository default branch "
                                "requires pull requests before merge.\n\n"
                                "Merge this PR, then rerun product contract refresh to complete activation."
                            ),
                            "head": "orcha/seed/apollo/baseline",
                            "base": "dev",
                        },
                    )
                ]
            finally:
                session.close()
        _reset_env()


def test_github_pat_seed_adapter_reports_workflow_permission_error_for_managed_workflow_files(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        bare_repo = _create_local_bare_remote(temp_root)
        _install_pre_receive_hook(
            bare_repo,
            """#!/bin/sh
echo "remote: refusing to allow a Personal Access Token to create or update workflow '.github/workflows/advisory-code-review.yml' without 'workflow' scope" >&2
exit 1
""",
        )
        _configure_env(f"sqlite+pysqlite:///{temp_root / 'runtime.db'}")
        with TestClient(app):
            session = get_session_factory()()
            try:
                org_id = str(session.query(Organization).filter(Organization.slug == "primary").one().org_id)
                adapter = product_seeding_module.GitHubPatProductSeedAdapter(session)
                monkeypatch.setattr(adapter, "_token_for_request", lambda request: "token")
                monkeypatch.setattr(adapter, "_repository_clone_url_for_request", lambda request: str(bare_repo))

                request = product_seeding_module.ProductSeedRequest.model_validate(_seed_request(org_id))
                repository = RepositorySeedResult(
                    github_repository_node_id="R_seed_repo",
                    owner="aegroup-io",
                    name="apollo",
                    default_branch="dev",
                    visibility="private",
                    description="Seeded product",
                    labels=["type:feature", "type:spike"],
                    permissions={},
                    branch_protection={},
                    raw_payload={},
                )
                bundle = product_seeding_module.RenderedSeedBundle(
                    files=[
                        product_seeding_module.RenderedBundleFile(
                            path=".github/workflows/advisory-code-review.yml",
                            content=b"name: Advisory Code Review\n",
                            source="rendered",
                        )
                    ],
                    manifest={},
                    components={},
                    baseline_version="test",
                )

                with pytest.raises(GitHubAppAuthError) as exc_info:
                    adapter.apply_bundle(request, repository, bundle)

                message = str(exc_info.value)
                assert "cannot modify workflow files" in message
                assert "`workflow` scope" in message
                assert "`Workflows` repository permission" in message
            finally:
                session.close()
        _reset_env()
