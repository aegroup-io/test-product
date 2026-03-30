from __future__ import annotations

from base64 import b64encode
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable, Protocol
from urllib.parse import quote, urlparse

import httpx
import yaml
from sqlalchemy.orm import Session

from agent_core_platform_api.github_integration import (
    GitHubAppAuthError,
    GitHubPATAuthService,
)
from agent_core_platform_api.github_mirror import GitHubMirrorService, ProductMirrorRefreshResult
from agent_core_platform_api.models import (
    ComponentEdge,
    ComponentNode,
    GitHubProjectMirror,
    ManagedAsset,
    Organization,
    Product,
    ProductSeedJob,
    RepositoryBinding,
)
from agent_core_platform_api.product_contract import ADVISORY, BLOCKING, RECOVERABLE, ProductContractService, ProductSetupDiagnostic
from agent_core_platform_api.schemas import ProductSeedRequest


PRODUCT_BASELINE_PATH = ".agent-core/product-baseline.json"
PRODUCT_FACTORY_PATH = ".agent-core/product-factory.json"
RUNTIME_LOCK_PATH = ".agent-core/runtime-baseline.lock.json"
EXTRA_BUNDLE_FILES = (
    "README.md",
    PRODUCT_BASELINE_PATH,
    PRODUCT_FACTORY_PATH,
    RUNTIME_LOCK_PATH,
)
DEFAULT_PROJECT_VIEWS = ["Board", "Ready Queue"]
DEFAULT_REPOSITORY_LABELS = [
    {"name": "type:feature", "color": "0E8A16", "description": "Shippable product or platform capability"},
    {"name": "type:spike", "color": "1D76DB", "description": "Learning or investigation work"},
]
DEFAULT_TEMPLATE_PATHS = [
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/spike.yml",
    ".github/ISSUE_TEMPLATE/api.yml",
]
IGNORED_RUNTIME_MODULE_DIR_NAMES = {
    ".cache",
    ".mypy_cache",
    ".next",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
IGNORED_RUNTIME_MODULE_FILE_NAMES = {
    ".coverage",
    ".DS_Store",
}
IGNORED_RUNTIME_MODULE_FILE_SUFFIXES = {
    ".pyc",
    ".pyd",
    ".pyo",
}
REQUIRED_GITHUB_PERMISSIONS = {
    "metadata": "read",
    "contents": "write",
    "issues": "write",
    "pull_requests": "write",
    "administration": "write",
    "organization_projects": "write",
}
PERMISSION_RANK = {
    "": 0,
    "none": 0,
    "read": 1,
    "triage": 1,
    "write": 2,
    "maintain": 2,
    "admin": 3,
}

PROJECT_VIEWS_QUERY = """
query OrchaProjectViews($id: ID!) {
  node(id: $id) {
    ... on ProjectV2 {
      views(first: 20) {
        nodes {
          name
        }
      }
    }
  }
}
""".strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                first_message = first.get("message")
                if isinstance(first_message, str) and first_message.strip():
                    return first_message.strip()
    return response.text.strip() or f"GitHub request failed with status {response.status_code}."


def _classify_setup_state(diagnostics: list[ProductSetupDiagnostic]) -> str:
    classifications = {item.classification for item in diagnostics}
    if BLOCKING in classifications:
        return "setup-needed"
    if RECOVERABLE in classifications:
        return "drift"
    if ADVISORY in classifications:
        return "advisory"
    return "ready"


def _has_blocking_diagnostics(diagnostics: list[ProductSetupDiagnostic]) -> bool:
    return any(item.classification == BLOCKING for item in diagnostics)


def _normalize_path(path: str) -> str:
    normalized = Path(path).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / PRODUCT_BASELINE_PATH).exists() and (candidate / ".orcha" / "product.yaml").exists():
            return candidate
    raise RuntimeError("Unable to locate the repo root for approved baseline rendering.")


@dataclass
class RenderedBundleFile:
    path: str
    content: bytes
    source: str


@dataclass
class RenderedSeedBundle:
    files: list[RenderedBundleFile]
    manifest: dict[str, Any]
    components: dict[str, Any]
    baseline_version: str


@dataclass
class RepositorySeedResult:
    github_repository_node_id: str
    owner: str
    name: str
    default_branch: str
    visibility: str
    description: str | None
    labels: list[str]
    permissions: dict[str, Any]
    branch_protection: dict[str, Any]
    raw_payload: dict[str, Any]


@dataclass
class ProjectSeedResult:
    github_project_node_id: str
    number: int
    title: str
    status_field_name: str
    status_options: list[str]
    fields: list[dict[str, Any]]
    views: list[str]
    templates: list[str]
    raw_payload: dict[str, Any]


@dataclass
class BundleApplyResult:
    mode: str
    head_branch: str | None = None
    base_branch: str | None = None
    pull_request_number: int | None = None
    pull_request_url: str | None = None
    commit_shas: list[str] = field(default_factory=list)


class GitCommandError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ):
        self.operation = operation
        self.returncode = returncode
        self.stdout = stdout.strip()
        self.stderr = stderr.strip()
        detail = self.stderr or self.stdout or f"git {operation} failed with exit code {returncode}."
        super().__init__(detail)


class ProductSeedAdapter(Protocol):
    def prepare_repository(self, request: ProductSeedRequest) -> RepositorySeedResult:
        ...

    def ensure_project(self, request: ProductSeedRequest, repository: RepositorySeedResult) -> ProjectSeedResult:
        ...

    def apply_bundle(
        self,
        request: ProductSeedRequest,
        repository: RepositorySeedResult,
        bundle: RenderedSeedBundle,
    ) -> BundleApplyResult | None:
        ...

    def bootstrap_product_mirror(self, product: Product) -> ProductMirrorRefreshResult:
        ...


class DryRunProductSeedAdapter:
    def prepare_repository(self, request: ProductSeedRequest) -> RepositorySeedResult:
        repo_node_id = f"R_seed_{request.github_owner}_{request.github_repo}".replace("-", "_")
        return RepositorySeedResult(
            github_repository_node_id=repo_node_id,
            owner=request.github_owner,
            name=request.github_repo,
            default_branch=request.github_default_branch,
            visibility=request.github_visibility,
            description=request.description,
            labels=[item["name"] for item in DEFAULT_REPOSITORY_LABELS],
            permissions=dict(REQUIRED_GITHUB_PERMISSIONS),
            branch_protection={
                "enabled": True,
                "required_pull_request_reviews": {
                    "required_approving_review_count": 1,
                },
            },
            raw_payload={
                "node_id": repo_node_id,
                "owner": {"login": request.github_owner},
                "name": request.github_repo,
                "default_branch": request.github_default_branch,
                "visibility": request.github_visibility,
                "description": request.description,
                "archived": False,
                "labels": [item["name"] for item in DEFAULT_REPOSITORY_LABELS],
            },
        )

    def ensure_project(self, request: ProductSeedRequest, repository: RepositorySeedResult) -> ProjectSeedResult:
        number = request.github_project_number or 1
        title = request.github_project_title or request.product_name
        node_id = request.github_project_node_id or f"PVT_seed_{request.product_key}".replace("-", "_")
        fields = _default_project_fields(request)
        raw_payload = {
            "node_id": node_id,
            "number": number,
            "title": title,
            "status_field_name": request.status_field,
            "status_options": [option["name"] for option in fields[0]["options"]],
            "fields": fields,
            "items": [],
            "views": ["Table"],
            "templates": list(DEFAULT_TEMPLATE_PATHS),
        }
        return ProjectSeedResult(
            github_project_node_id=node_id,
            number=number,
            title=title,
            status_field_name=request.status_field,
            status_options=[option["name"] for option in fields[0]["options"]],
            fields=fields,
            views=["Table"],
            templates=list(DEFAULT_TEMPLATE_PATHS),
            raw_payload=raw_payload,
        )

    def apply_bundle(
        self,
        request: ProductSeedRequest,
        repository: RepositorySeedResult,
        bundle: RenderedSeedBundle,
    ) -> BundleApplyResult | None:
        return None

    def bootstrap_product_mirror(self, product: Product) -> ProductMirrorRefreshResult:
        return ProductMirrorRefreshResult()


class GitHubPatProductSeedAdapter:
    def __init__(
        self,
        session: Session,
        *,
        http_post: Callable[..., httpx.Response] = httpx.post,
        http_put: Callable[..., httpx.Response] = httpx.put,
        http_patch: Callable[..., httpx.Response] = httpx.patch,
        http_get: Callable[..., httpx.Response] = httpx.get,
        git_bin: str = "git",
    ):
        self.session = session
        self.auth = GitHubPATAuthService(session)
        self.http_post = http_post
        self.http_put = http_put
        self.http_patch = http_patch
        self.http_get = http_get
        self.git_bin = git_bin
        self._token: str | None = None
        self._api_base_url: str | None = None
        self._repository_clone_url: str | None = None
        self._git_username: str | None = None

    def prepare_repository(self, request: ProductSeedRequest) -> RepositorySeedResult:
        token = self._token_for_request(request)
        repository_response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/repos/{request.github_owner}/{request.github_repo}",
            headers=self._headers(token),
            timeout=30,
        )
        self._record_rate_limit(owner=request.github_owner, repo=request.github_repo, response=repository_response)
        if repository_response.status_code >= 400:
            detail = _http_error_detail(repository_response)
            if repository_response.status_code == 404:
                raise GitHubAppAuthError(
                    "Connected Git repository target was not found on GitHub for "
                    f"`{request.github_owner}/{request.github_repo}`. Reconnect the target in Settings > Git Repositories "
                    "or choose an existing repository."
                )
            raise GitHubAppAuthError(detail)
        repository_payload = repository_response.json()
        if not isinstance(repository_payload, dict):
            raise GitHubAppAuthError("GitHub repository lookup response was malformed.")

        current_default_branch = str(repository_payload.get("default_branch") or request.github_default_branch)
        if current_default_branch != request.github_default_branch:
            self._create_branch_from_default(
                owner=request.github_owner,
                repo=request.github_repo,
                current_default_branch=current_default_branch,
                target_branch=request.github_default_branch,
                token=token,
            )
            patch_response = self.http_patch(
                f"{self._api_base_url.rstrip('/')}/repos/{request.github_owner}/{request.github_repo}",
                headers=self._headers(token),
                json={"default_branch": request.github_default_branch},
                timeout=30,
            )
            self._record_rate_limit(owner=request.github_owner, repo=request.github_repo, response=patch_response)
            if patch_response.status_code >= 400:
                raise GitHubAppAuthError(_http_error_detail(patch_response))

        branch_protection = self._fetch_branch_protection(
            owner=request.github_owner,
            repo=request.github_repo,
            branch=request.github_default_branch,
            token=token,
        )
        labels = self._list_repository_labels(
            owner=request.github_owner,
            repo=request.github_repo,
            token=token,
        )
        repository_payload["default_branch"] = request.github_default_branch
        repository_payload["default_branch_protection"] = branch_protection
        repository_payload["labels"] = labels
        repository_permissions = repository_payload.get("permissions")
        return RepositorySeedResult(
            github_repository_node_id=str(repository_payload.get("node_id") or f"R_{request.github_repo}"),
            owner=request.github_owner,
            name=request.github_repo,
            default_branch=request.github_default_branch,
            visibility=str(repository_payload.get("visibility") or request.github_visibility),
            description=request.description,
            labels=labels,
            permissions=dict(repository_permissions) if isinstance(repository_permissions, dict) else {},
            branch_protection=branch_protection,
            raw_payload=repository_payload,
        )

    def ensure_project(self, request: ProductSeedRequest, repository: RepositorySeedResult) -> ProjectSeedResult:
        token = self._token_for_request(request)
        mirror = GitHubMirrorService(self.session)
        project_payload: dict[str, Any]
        if request.github_project_node_id and request.github_project_number:
            project_payload = mirror._fetch_project_snapshot(  # noqa: SLF001 - shared fetch helper
                github_project_node_id=request.github_project_node_id,
                token=token,
                api_base_url=self._api_base_url or "",
                http_post=self.http_post,
                owner=repository.owner,
                repo=repository.name,
            )
            project_payload["node_id"] = str(
                project_payload.get("node_id") or project_payload.get("id") or request.github_project_node_id
            )
            project_payload["templates"] = list(DEFAULT_TEMPLATE_PATHS)
        else:
            project_payload = self._create_project_payload(request, token)
        project_id = str(project_payload.get("node_id") or request.github_project_node_id or "").strip()
        project_payload["views"] = (
            self._fetch_project_views(
                project_id=project_id,
                token=token,
                owner=repository.owner,
                repo=repository.name,
            )
            if project_id
            else []
        )
        fields = project_payload.get("fields")
        if not isinstance(fields, list):
            fields = _default_project_fields(request)
            project_payload["fields"] = fields
        status_field_name = _project_status_field_name(project_payload, preferred_name=request.status_field)
        status_options = _project_status_options(project_payload, status_field_name=status_field_name)
        project_payload.setdefault("items", [])
        project_payload.setdefault("views", [])
        project_payload.setdefault("templates", list(DEFAULT_TEMPLATE_PATHS))
        project_payload["status_field_name"] = status_field_name
        project_payload["status_options"] = status_options or [request.ready_status, "In Progress", request.done_status]
        return ProjectSeedResult(
            github_project_node_id=str(project_payload.get("node_id") or request.github_project_node_id or "PVT_missing"),
            number=int(project_payload.get("number") or request.github_project_number or 1),
            title=str(project_payload.get("title") or request.github_project_title or request.product_name),
            status_field_name=status_field_name,
            status_options=project_payload["status_options"],
            fields=list(fields),
            views=[str(view) for view in project_payload.get("views", []) if str(view).strip()],
            templates=[str(item) for item in project_payload.get("templates", []) if str(item).strip()],
            raw_payload=project_payload,
        )

    def apply_bundle(
        self,
        request: ProductSeedRequest,
        repository: RepositorySeedResult,
        bundle: RenderedSeedBundle,
    ) -> BundleApplyResult:
        token = self._token_for_request(request)
        if self._branch_requires_pull_request(repository.branch_protection):
            result = self._apply_bundle_via_pull_request(
                request=request,
                repository=repository,
                bundle=bundle,
                token=token,
            )
        else:
            try:
                result = self._apply_bundle_via_git_push(
                    request=request,
                    repository=repository,
                    bundle=bundle,
                    token=token,
                )
            except GitCommandError as error:
                if self._git_push_requires_pull_request(error):
                    result = self._apply_bundle_via_pull_request(
                        request=request,
                        repository=repository,
                        bundle=bundle,
                        token=token,
                    )
                else:
                    raise GitHubAppAuthError(self._describe_git_push_error(bundle=bundle, error=error)) from error

        repository.branch_protection = self._ensure_branch_protection(
            owner=repository.owner,
            repo=repository.name,
            branch=repository.default_branch,
            token=token,
        )
        repository.labels = self._ensure_repository_labels(
            owner=repository.owner,
            repo=repository.name,
            token=token,
        )
        repository.raw_payload["default_branch_protection"] = repository.branch_protection
        repository.raw_payload["labels"] = list(repository.labels)
        return result

    def bootstrap_product_mirror(self, product: Product) -> ProductMirrorRefreshResult:
        return GitHubMirrorService(self.session).refresh_product_mirror(
            product_id=product.product_id,
            ensure_webhook=True,
            http_get=self.http_get,
            http_post=self.http_post,
            http_patch=self.http_patch,
        )

    def _token_for_request(self, request: ProductSeedRequest) -> str:
        if self._token is not None:
            return self._token
        token, api_base_url, workspace_repo = self.auth.load_repository_token(
            owner=request.github_owner,
            repo=request.github_repo,
            org_id=request.org_id,
        )
        self._token = token
        self._api_base_url = api_base_url
        if isinstance(workspace_repo.clone_url, str) and workspace_repo.clone_url.strip():
            self._repository_clone_url = workspace_repo.clone_url.strip()
        return self._token

    def _headers(self, token: str) -> dict[str, str]:
        return self.auth.build_headers(token)

    def _record_rate_limit(self, *, owner: str, repo: str, response: httpx.Response) -> None:
        self.auth.record_repository_rate_limit_signal(owner=owner, repo=repo, response=response)

    def _create_branch_from_default(
        self,
        *,
        owner: str,
        repo: str,
        current_default_branch: str,
        target_branch: str,
        token: str,
    ) -> None:
        ref_response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/git/ref/heads/{current_default_branch}",
            headers=self._headers(token),
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=ref_response)
        if ref_response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(ref_response))
        ref_payload = ref_response.json()
        sha = ref_payload.get("object", {}).get("sha") if isinstance(ref_payload, dict) else None
        if not isinstance(sha, str) or not sha:
            raise GitHubAppAuthError("GitHub branch reference response was malformed.")
        create_ref_response = self.http_post(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/git/refs",
            headers=self._headers(token),
            json={"ref": f"refs/heads/{target_branch}", "sha": sha},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=create_ref_response)
        if create_ref_response.status_code >= 400 and create_ref_response.status_code != 422:
            raise GitHubAppAuthError(_http_error_detail(create_ref_response))

    def _ensure_branch_protection(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        token: str,
    ) -> dict[str, Any]:
        protection_response = self.http_put(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/branches/{branch}/protection",
            headers=self._headers(token),
            json={
                "required_status_checks": None,
                "enforce_admins": True,
                "required_pull_request_reviews": {
                    "dismiss_stale_reviews": False,
                    "require_code_owner_reviews": False,
                    "required_approving_review_count": 1,
                },
                "restrictions": None,
                "allow_force_pushes": False,
                "allow_deletions": False,
                "block_creations": False,
                "required_conversation_resolution": True,
            },
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=protection_response)
        if protection_response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(protection_response))
        payload = protection_response.json()
        if isinstance(payload, dict):
            return self._normalize_branch_protection(payload)
        return self._normalize_branch_protection({})

    def _fetch_branch_protection(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        token: str,
    ) -> dict[str, Any]:
        response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/branches/{branch}/protection",
            headers=self._headers(token),
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code == 404:
            return self._normalize_branch_protection({})
        if response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubAppAuthError("GitHub branch protection response was malformed.")
        return self._normalize_branch_protection(payload)

    def _normalize_branch_protection(self, payload: dict[str, Any]) -> dict[str, Any]:
        reviews = payload.get("required_pull_request_reviews")
        required_approving_review_count = 0
        if isinstance(reviews, dict):
            raw_count = reviews.get("required_approving_review_count")
            if isinstance(raw_count, int):
                required_approving_review_count = raw_count
        return {
            **payload,
            "enabled": bool(payload.get("enabled") or payload.get("url")),
            "requires_pull_request": isinstance(reviews, dict),
            "required_approving_review_count": required_approving_review_count,
            "allows_force_pushes": self._branch_protection_flag(payload, "allow_force_pushes", "allows_force_pushes"),
            "allows_deletions": self._branch_protection_flag(payload, "allow_deletions", "allows_deletions"),
        }

    @staticmethod
    def _branch_protection_flag(payload: dict[str, Any], nested_key: str, flat_key: str) -> bool:
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            enabled = nested.get("enabled")
            if isinstance(enabled, bool):
                return enabled
        return bool(payload.get(flat_key))

    def _ensure_repository_labels(
        self,
        *,
        owner: str,
        repo: str,
        token: str,
    ) -> list[str]:
        existing_labels = {
            label.casefold()
            for label in self._list_repository_labels(
                owner=owner,
                repo=repo,
                token=token,
            )
        }
        for label in DEFAULT_REPOSITORY_LABELS:
            label_name = str(label.get("name", "")).strip()
            if not label_name:
                continue
            if label_name.casefold() in existing_labels:
                continue
            response = self.http_post(
                f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/labels",
                headers=self._headers(token),
                json={
                    "name": label_name,
                    "color": label.get("color", "0E8A16"),
                    "description": label.get("description"),
                },
                timeout=30,
            )
            self._record_rate_limit(owner=owner, repo=repo, response=response)
            if response.status_code >= 400 and response.status_code != 422:
                raise GitHubAppAuthError(_http_error_detail(response))
            existing_labels.add(label_name.casefold())
        return sorted(label["name"] for label in DEFAULT_REPOSITORY_LABELS)

    def _list_repository_labels(
        self,
        *,
        owner: str,
        repo: str,
        token: str,
    ) -> list[str]:
        response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/labels",
            headers=self._headers(token),
            params={"per_page": 100},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(response))
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubAppAuthError("GitHub labels response was malformed.")
        return [
            str(item.get("name")).strip()
            for item in payload
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip()
        ]

    def _graphql(self, *, token: str, owner: str, repo: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = self.http_post(
            f"{self._api_base_url.rstrip('/')}/graphql",
            headers=self._headers(token),
            json={"query": query, "variables": variables},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubAppAuthError("GitHub GraphQL response was malformed.")
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            raise GitHubAppAuthError(_http_error_detail(response))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GitHubAppAuthError("GitHub GraphQL response was missing data.")
        return data

    def _lookup_owner_node_id(self, *, token: str, owner: str, repo: str, login: str) -> str:
        response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/users/{login}",
            headers=self._headers(token),
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(f"Unable to resolve GitHub owner `{login}`: {_http_error_detail(response)}")
        payload = response.json()
        owner_id = payload.get("node_id") if isinstance(payload, dict) else None
        if not isinstance(owner_id, str) or not owner_id:
            raise GitHubAppAuthError(f"Unable to resolve GitHub owner node id for `{login}`.")
        return owner_id

    def _create_project_payload(self, request: ProductSeedRequest, token: str) -> dict[str, Any]:
        owner_id = self._lookup_owner_node_id(
            token=token,
            owner=request.github_owner,
            repo=request.github_repo,
            login=request.github_owner,
        )
        create_data = self._graphql(
            token=token,
            owner=request.github_owner,
            repo=request.github_repo,
            query="""
                mutation OrchaCreateProject($ownerId: ID!, $title: String!) {
                  createProjectV2(input: { ownerId: $ownerId, title: $title }) {
                    projectV2 {
                      id
                      number
                      title
                    }
                  }
                }
            """,
            variables={"ownerId": owner_id, "title": request.github_project_title or request.product_name},
        )
        project = create_data.get("createProjectV2", {}).get("projectV2")
        if not isinstance(project, dict):
            raise GitHubAppAuthError("GitHub project create response was malformed.")
        project_id = project.get("id")
        project_number = project.get("number")
        if not isinstance(project_id, str) or not isinstance(project_number, int):
            raise GitHubAppAuthError("GitHub project create response was missing the project identity.")

        mirror = GitHubMirrorService(self.session)
        project_payload = mirror._fetch_project_snapshot(
            github_project_node_id=project_id,
            token=token,
            api_base_url=self._api_base_url or "",
            http_post=self.http_post,
            owner=request.github_owner,
            repo=request.github_repo,
        )
        project_payload["node_id"] = str(project_payload.get("node_id") or project_payload.get("id") or project_id)

        fields = _default_project_fields(request)
        for field in fields:
            field_name = str(field.get("name") or "").strip()
            if not field_name or _project_has_field(project_payload, field_name):
                continue
            try:
                self._create_project_field(
                    token=token,
                    owner=request.github_owner,
                    repo=request.github_repo,
                    project_id=project_id,
                    field_payload=field,
                )
            except GitHubAppAuthError as error:
                if not _is_project_field_name_conflict(error):
                    raise
                refreshed_payload = mirror._fetch_project_snapshot(
                    github_project_node_id=project_id,
                    token=token,
                    api_base_url=self._api_base_url or "",
                    http_post=self.http_post,
                    owner=request.github_owner,
                    repo=request.github_repo,
                )
                refreshed_payload["node_id"] = str(
                    refreshed_payload.get("node_id") or refreshed_payload.get("id") or project_id
                )
                if not _project_has_field(refreshed_payload, field_name):
                    raise
                project_payload = refreshed_payload

        project_payload = mirror._fetch_project_snapshot(
            github_project_node_id=project_id,
            token=token,
            api_base_url=self._api_base_url or "",
            http_post=self.http_post,
            owner=request.github_owner,
            repo=request.github_repo,
        )
        project_payload["node_id"] = str(project_payload.get("node_id") or project_payload.get("id") or project_id)
        status_field_name = _project_status_field_name(project_payload, preferred_name=request.status_field)
        status_options = _project_status_options(project_payload, status_field_name=status_field_name)
        project_payload["status_field_name"] = status_field_name
        project_payload["status_options"] = status_options or [request.ready_status, "In Progress", request.done_status]
        project_payload["templates"] = list(DEFAULT_TEMPLATE_PATHS)
        project_payload["views"] = self._fetch_project_views(
            project_id=project_id,
            token=token,
            owner=request.github_owner,
            repo=request.github_repo,
        )

        return {
            "node_id": project_payload["node_id"],
            "number": int(project_payload.get("number") or project_number),
            "title": str(project_payload.get("title") or project.get("title") or request.github_project_title or request.product_name),
            "status_field_name": status_field_name,
            "status_options": project_payload["status_options"],
            "fields": _project_fields(project_payload),
            "items": list(project_payload.get("items", [])) if isinstance(project_payload.get("items"), list) else [],
            "views": project_payload["views"],
            "templates": project_payload["templates"],
        }

    def _create_project_field(
        self,
        *,
        token: str,
        owner: str,
        repo: str,
        project_id: str,
        field_payload: dict[str, Any],
    ) -> None:
        data_type = str(field_payload.get("data_type") or field_payload.get("dataType") or "text").upper()
        mutation = """
            mutation OrchaCreateProjectField(
              $projectId: ID!,
              $name: String!,
              $dataType: ProjectV2CustomFieldType!,
              $singleSelectOptions: [ProjectV2SingleSelectFieldOptionInput!]
            ) {
              createProjectV2Field(
                input: {
                  projectId: $projectId,
                  name: $name,
                  dataType: $dataType,
                  singleSelectOptions: $singleSelectOptions
                }
              ) {
                projectV2Field {
                  ... on ProjectV2Field {
                    id
                  }
                }
              }
            }
        """
        variables: dict[str, Any] = {
            "projectId": project_id,
            "name": field_payload.get("name"),
            "dataType": "SINGLE_SELECT" if data_type in {"SINGLE_SELECT", "SINGLESELECT"} else "TEXT",
            "singleSelectOptions": None,
        }
        if variables["dataType"] == "SINGLE_SELECT":
            options = field_payload.get("options", [])
            variables["singleSelectOptions"] = [
                {
                    "name": option.get("name"),
                    "color": option.get("color", "GRAY"),
                    "description": (
                        str(option.get("description")).strip()
                        if isinstance(option.get("description"), str) and option.get("description").strip()
                        else str(option.get("name")).strip()
                    ),
                }
                for option in options
                if isinstance(option, dict) and isinstance(option.get("name"), str) and option.get("name").strip()
            ]
        self._graphql(
            token=token,
            owner=owner,
            repo=repo,
            query=mutation,
            variables=variables,
        )

    def _fetch_project_views(
        self,
        *,
        project_id: str,
        token: str,
        owner: str,
        repo: str,
    ) -> list[str]:
        data = self._graphql(
            token=token,
            owner=owner,
            repo=repo,
            query=PROJECT_VIEWS_QUERY,
            variables={"id": project_id},
        )
        node = data.get("node")
        views = node.get("views") if isinstance(node, dict) else None
        return [
            str(view.get("name")).strip()
            for view in views.get("nodes", [])
            if isinstance(view, dict) and isinstance(view.get("name"), str) and view.get("name").strip()
        ] if isinstance(views, dict) else []

    def _apply_bundle_via_pull_request(
        self,
        *,
        request: ProductSeedRequest,
        repository: RepositorySeedResult,
        bundle: RenderedSeedBundle,
        token: str,
    ) -> BundleApplyResult:
        base_branch = repository.default_branch
        head_branch = self._build_seed_branch_name(product_key=request.product_key)
        clone_url = self._repository_clone_url_for_request(request)
        commit_shas: list[str] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            checkout_path = Path(temp_dir) / repository.name
            self._clone_repository(
                clone_url=clone_url,
                token=token,
                request=request,
                branch=base_branch,
                checkout_path=checkout_path,
            )
            self._run_git(
                ["checkout", "-B", head_branch],
                cwd=checkout_path,
                clone_url=clone_url,
                token=token,
                request=request,
                operation="checkout",
            )
            _write_bundle(bundle, checkout_path)
            commit_sha = self._commit_bundle_if_changed(
                checkout_path=checkout_path,
                clone_url=clone_url,
                token=token,
                request=request,
                message=f"Seed approved baseline for {request.product_name}",
            )
            if commit_sha is None:
                return BundleApplyResult(mode="direct", base_branch=base_branch)
            self._push_branch(
                checkout_path=checkout_path,
                clone_url=clone_url,
                token=token,
                request=request,
                refspec=f"HEAD:{head_branch}",
                force=True,
            )
            commit_shas.append(commit_sha)
        pr_number, pr_url = self._create_or_lookup_pull_request(
            owner=repository.owner,
            repo=repository.name,
            base_branch=base_branch,
            head_branch=head_branch,
            title=f"Seed approved baseline for {request.product_name}",
            body=(
                "This pull request was opened by Orcha live seed because the repository default branch "
                "requires pull requests before merge.\n\n"
                "Merge this PR, then rerun product contract refresh to complete activation."
            ),
            token=token,
        )
        return BundleApplyResult(
            mode="pull_request",
            head_branch=head_branch,
            base_branch=base_branch,
            pull_request_number=pr_number,
            pull_request_url=pr_url,
            commit_shas=commit_shas,
        )

    def _branch_requires_pull_request(self, branch_protection: dict[str, Any]) -> bool:
        if branch_protection.get("requires_pull_request") is True:
            return True
        reviews = branch_protection.get("required_pull_request_reviews")
        return isinstance(reviews, dict)

    def _build_seed_branch_name(self, *, product_key: str) -> str:
        normalized_product = re.sub(r"[^a-z0-9._-]+", "-", product_key.lower()).strip("-") or "product"
        return f"orcha/seed/{normalized_product}/baseline"

    def _apply_bundle_via_git_push(
        self,
        *,
        request: ProductSeedRequest,
        repository: RepositorySeedResult,
        bundle: RenderedSeedBundle,
        token: str,
    ) -> BundleApplyResult:
        clone_url = self._repository_clone_url_for_request(request)
        with tempfile.TemporaryDirectory() as temp_dir:
            checkout_path = Path(temp_dir) / repository.name
            self._clone_repository(
                clone_url=clone_url,
                token=token,
                request=request,
                branch=repository.default_branch,
                checkout_path=checkout_path,
            )
            _write_bundle(bundle, checkout_path)
            commit_sha = self._commit_bundle_if_changed(
                checkout_path=checkout_path,
                clone_url=clone_url,
                token=token,
                request=request,
                message=f"Seed approved baseline for {request.product_name}",
            )
            if commit_sha is None:
                return BundleApplyResult(mode="direct", base_branch=repository.default_branch)
            self._push_branch(
                checkout_path=checkout_path,
                clone_url=clone_url,
                token=token,
                request=request,
                refspec=f"HEAD:{repository.default_branch}",
            )
            return BundleApplyResult(
                mode="direct",
                base_branch=repository.default_branch,
                commit_shas=[commit_sha],
            )

    def _repository_clone_url_for_request(self, request: ProductSeedRequest) -> str:
        if self._repository_clone_url and self._repository_clone_url.strip():
            return self._repository_clone_url.strip()
        return f"https://github.com/{request.github_owner}/{request.github_repo}.git"

    def _clone_repository(
        self,
        *,
        clone_url: str,
        token: str,
        request: ProductSeedRequest,
        branch: str,
        checkout_path: Path,
    ) -> None:
        self._run_git(
            ["clone", "--origin", "origin", "--branch", branch, "--single-branch", clone_url, str(checkout_path)],
            clone_url=clone_url,
            token=token,
            request=request,
            operation="clone",
        )

    def _commit_bundle_if_changed(
        self,
        *,
        checkout_path: Path,
        clone_url: str,
        token: str,
        request: ProductSeedRequest,
        message: str,
    ) -> str | None:
        status = self._run_git(
            ["status", "--porcelain", "--untracked-files=all"],
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="status",
        )
        if not status.strip():
            return None
        self._run_git(
            ["config", "user.name", "Orcha Seed"],
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="config-user-name",
        )
        self._run_git(
            ["config", "user.email", "orcha-seed@users.noreply.github.com"],
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="config-user-email",
        )
        self._run_git(
            ["add", "--force", "--all"],
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="add",
        )
        self._run_git(
            ["commit", "-m", message],
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="commit",
        )
        return self._run_git(
            ["rev-parse", "HEAD"],
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="rev-parse",
        ).strip()

    def _push_branch(
        self,
        *,
        checkout_path: Path,
        clone_url: str,
        token: str,
        request: ProductSeedRequest,
        refspec: str,
        force: bool = False,
    ) -> None:
        command = ["push", "origin", refspec]
        if force:
            command.append("--force")
        self._run_git(
            command,
            cwd=checkout_path,
            clone_url=clone_url,
            token=token,
            request=request,
            operation="push",
        )

    def _run_git(
        self,
        args: list[str],
        *,
        clone_url: str,
        token: str,
        request: ProductSeedRequest,
        operation: str,
        cwd: Path | None = None,
    ) -> str:
        command = [self.git_bin]
        command.extend(self._git_auth_args(clone_url=clone_url, token=token, request=request))
        command.extend(args)
        environment = dict(os.environ)
        environment.setdefault("GIT_TERMINAL_PROMPT", "0")
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode != 0:
            raise GitCommandError(
                operation=operation,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout

    def _git_auth_args(self, *, clone_url: str, token: str, request: ProductSeedRequest) -> list[str]:
        parsed = urlparse(clone_url)
        if parsed.scheme not in {"http", "https"}:
            return []
        username = self._authenticated_git_username(token=token, request=request)
        basic_auth = b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
        return [
            "-c",
            "credential.helper=",
            "-c",
            f"http.extraheader=AUTHORIZATION: basic {basic_auth}",
        ]

    def _authenticated_git_username(self, *, token: str, request: ProductSeedRequest) -> str:
        if self._git_username is not None:
            return self._git_username
        response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/user",
            headers=self._headers(token),
            timeout=30,
        )
        self._record_rate_limit(owner=request.github_owner, repo=request.github_repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(response))
        payload = response.json()
        login = payload.get("login") if isinstance(payload, dict) else None
        if not isinstance(login, str) or not login.strip():
            raise GitHubAppAuthError("GitHub authenticated-user response was malformed.")
        self._git_username = login.strip()
        return self._git_username

    @staticmethod
    def _git_push_requires_pull_request(error: GitCommandError) -> bool:
        detail = "\n".join(part for part in [error.stderr, error.stdout] if part).casefold()
        return any(
            marker in detail
            for marker in (
                "changes must be made through a pull request",
                "protected branch hook declined",
                "protected branch update failed",
                "pull request",
                "gh006",
            )
        )

    @staticmethod
    def _describe_git_push_error(*, bundle: RenderedSeedBundle, error: GitCommandError) -> str:
        detail = error.stderr or error.stdout or str(error)
        normalized_paths = {item.path.strip().lower() for item in bundle.files}
        if any(path.startswith(".github/workflows/") for path in normalized_paths) and "workflow" in detail.casefold():
            return (
                "Unable to push seed bundle because the connected GitHub credential cannot modify workflow files. "
                "GitHub requires workflow write access for `.github/workflows/*` updates "
                "(classic PAT: `workflow` scope; fine-grained token or app: `Workflows` repository permission set to `write`)."
            )
        return f"Unable to publish the seed bundle with git push: {detail}"

    def _create_or_lookup_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        base_branch: str,
        head_branch: str,
        title: str,
        body: str,
        token: str,
    ) -> tuple[int, str | None]:
        response = self.http_post(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/pulls",
            headers=self._headers(token),
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code == 422:
            existing = self._lookup_open_pull_request(
                owner=owner,
                repo=repo,
                base_branch=base_branch,
                head_branch=head_branch,
                token=token,
            )
            if existing is not None:
                return existing
        if response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(response))
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubAppAuthError("GitHub pull request response was malformed.")
        number = payload.get("number")
        if not isinstance(number, int):
            raise GitHubAppAuthError("GitHub pull request response was malformed.")
        url = payload.get("html_url")
        return number, url.strip() if isinstance(url, str) and url.strip() else None

    def _lookup_open_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        base_branch: str,
        head_branch: str,
        token: str,
    ) -> tuple[int, str | None] | None:
        response = self.http_get(
            f"{self._api_base_url.rstrip('/')}/repos/{owner}/{repo}/pulls",
            headers=self._headers(token),
            params={"state": "open", "head": f"{owner}:{head_branch}", "base": base_branch},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_http_error_detail(response))
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        first = payload[0]
        if not isinstance(first, dict):
            return None
        number = first.get("number")
        if not isinstance(number, int):
            return None
        url = first.get("html_url")
        return number, url.strip() if isinstance(url, str) and url.strip() else None


def build_seed_adapter(session: Session, request: ProductSeedRequest) -> ProductSeedAdapter:
    if request.dry_run:
        return DryRunProductSeedAdapter()
    return GitHubPatProductSeedAdapter(session)


def _default_project_fields(request: ProductSeedRequest) -> list[dict[str, Any]]:
    return [
        {
            "node_id": "PVTF_status",
            "name": request.status_field,
            "data_type": "single_select",
            "options": [
                {"id": "status_ready", "name": request.ready_status, "color": "GRAY", "description": request.ready_status},
                {"id": "status_progress", "name": "In Progress", "color": "BLUE", "description": "In Progress"},
                {"id": "status_done", "name": request.done_status, "color": "GREEN", "description": request.done_status},
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


def _project_fields(project_payload: dict[str, Any]) -> list[dict[str, Any]]:
    fields = project_payload.get("fields")
    return [field for field in fields if isinstance(field, dict)] if isinstance(fields, list) else []


def _field_name_matches(field_payload: dict[str, Any], target_name: str) -> bool:
    name = field_payload.get("name")
    return isinstance(name, str) and name.strip().casefold() == target_name.strip().casefold()


def _project_has_field(project_payload: dict[str, Any], field_name: str) -> bool:
    return any(_field_name_matches(field, field_name) for field in _project_fields(project_payload))


def _field_options(field_payload: dict[str, Any]) -> list[dict[str, Any]]:
    options = field_payload.get("options")
    return [option for option in options if isinstance(option, dict)] if isinstance(options, list) else []


def _project_status_field_name(project_payload: dict[str, Any], *, preferred_name: str) -> str:
    explicit = project_payload.get("status_field_name")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    for field in _project_fields(project_payload):
        if _field_name_matches(field, preferred_name):
            name = field.get("name")
            return str(name).strip()
    for field in _project_fields(project_payload):
        data_type = str(field.get("data_type") or field.get("dataType") or "").strip().lower()
        name = field.get("name")
        if isinstance(name, str) and name.strip() and data_type in {"single_select", "singleselect", "single select"}:
            return name.strip()
    return preferred_name


def _project_status_options(project_payload: dict[str, Any], *, status_field_name: str) -> list[str]:
    explicit = project_payload.get("status_options")
    if isinstance(explicit, list):
        return [str(item).strip() for item in explicit if str(item).strip()]
    fallback_options: list[str] = []
    for field in _project_fields(project_payload):
        data_type = str(field.get("data_type") or field.get("dataType") or "").strip().lower()
        if data_type not in {"single_select", "singleselect", "single select"}:
            continue
        options = [
            str(option.get("name", "")).strip()
            for option in _field_options(field)
            if str(option.get("name", "")).strip()
        ]
        if _field_name_matches(field, status_field_name):
            return options
        if not fallback_options:
            fallback_options = options
    return fallback_options


def _is_project_field_name_conflict(error: GitHubAppAuthError) -> bool:
    message = str(error).casefold()
    return "name has already been taken" in message or "name cannot have a reserved value" in message


def _json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml_file(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _bundle_file_contents(repo_root: Path, *, source: str, target: str) -> bytes:
    source_path = repo_root / source
    fallback_path = repo_root / target
    resolved_path = source_path if source_path.exists() else fallback_path
    if not resolved_path.exists():
        raise FileNotFoundError(f"Approved baseline asset is missing: {target}")
    return resolved_path.read_bytes()


def _runtime_module_files(repo_root: Path, runtime_lock: dict[str, Any]) -> dict[str, RenderedBundleFile]:
    bundle: dict[str, RenderedBundleFile] = {}
    for module in runtime_lock.get("modules", []):
        if not isinstance(module, dict):
            continue
        target = module.get("target")
        if not isinstance(target, str) or not target.strip():
            continue
        source_dir = repo_root / target
        if not source_dir.exists() or not source_dir.is_dir():
            continue
        for root, dir_names, file_names in os.walk(source_dir, topdown=True):
            root_path = Path(root)
            dir_names[:] = [
                name
                for name in dir_names
                if name not in IGNORED_RUNTIME_MODULE_DIR_NAMES and not name.endswith(".egg-info")
            ]
            for file_name in file_names:
                if (
                    file_name in IGNORED_RUNTIME_MODULE_FILE_NAMES
                    or Path(file_name).suffix in IGNORED_RUNTIME_MODULE_FILE_SUFFIXES
                ):
                    continue
                path = root_path / file_name
                relative_path = path.relative_to(repo_root).as_posix()
                bundle[relative_path] = RenderedBundleFile(
                    path=relative_path,
                    content=path.read_bytes(),
                    source=relative_path,
                )
    return bundle


def _render_seed_bundle(org: Organization, request: ProductSeedRequest, project: ProjectSeedResult) -> RenderedSeedBundle:
    repo_root = _repo_root()
    baseline_manifest = _json_file(repo_root / PRODUCT_BASELINE_PATH)
    runtime_lock = _json_file(repo_root / RUNTIME_LOCK_PATH)
    template_manifest = _yaml_file(repo_root / ".orcha" / "product.yaml")

    bundle_files: dict[str, RenderedBundleFile] = {}
    for item in baseline_manifest.get("managed_files", []):
        if not isinstance(item, dict):
            continue
        target = item.get("target")
        source = item.get("source")
        if not isinstance(target, str) or not isinstance(source, str):
            continue
        normalized_target = _normalize_path(target)
        bundle_files[normalized_target] = RenderedBundleFile(
            path=normalized_target,
            content=_bundle_file_contents(repo_root, source=source, target=normalized_target),
            source=source,
        )

    for extra_path in EXTRA_BUNDLE_FILES:
        normalized_target = _normalize_path(extra_path)
        if normalized_target in bundle_files:
            continue
        extra_file = repo_root / normalized_target
        if not extra_file.exists():
            continue
        bundle_files[normalized_target] = RenderedBundleFile(
            path=normalized_target,
            content=extra_file.read_bytes(),
            source=normalized_target,
        )

    bundle_files.update(_runtime_module_files(repo_root, runtime_lock))

    manifest = dict(template_manifest)
    manifest["product"] = {
        "key": request.product_key,
        "name": request.product_name,
        "org": org.slug,
        "description": request.description or manifest.get("product", {}).get("description"),
    }
    manifest["github"] = {
        "owner": request.github_owner,
        "repo": request.github_repo,
        "default_branch": request.github_default_branch,
        "project_number": project.number,
        "status_field": request.status_field,
        "ready_status": request.ready_status,
        "done_status": request.done_status,
    }
    baseline_section = dict(manifest.get("baseline", {}))
    baseline_section["channel"] = request.baseline_channel or baseline_section.get("channel") or "stable"
    baseline_section["agent_core_version"] = baseline_manifest.get("core_version") or baseline_section.get("agent_core_version")
    if request.standards_pack:
        baseline_section["standards_pack"] = request.standards_pack
    manifest["baseline"] = baseline_section
    execution_section = dict(manifest.get("execution", {}))
    if request.execution_profile:
        execution_section["profile"] = request.execution_profile
    if request.max_concurrent_lanes is not None:
        execution_section["max_concurrent_lanes"] = request.max_concurrent_lanes
    manifest["execution"] = execution_section

    components = {
        "schema_version": 1,
        "components": [
            {
                "key": request.product_key,
                "name": request.product_name,
                "type": "product",
                "owner": org.slug,
            },
            {
                "key": f"{request.product_key}-repo",
                "name": request.github_repo,
                "type": "repository",
                "owner": request.github_owner,
            },
        ],
        "edges": [
            {
                "from": request.product_key,
                "to": f"{request.product_key}-repo",
                "relationship": "owns",
            }
        ],
    }

    bundle_files[".orcha/product.yaml"] = RenderedBundleFile(
        path=".orcha/product.yaml",
        content=yaml.safe_dump(manifest, sort_keys=False).encode("utf-8"),
        source="rendered",
    )
    bundle_files[".orcha/components.yaml"] = RenderedBundleFile(
        path=".orcha/components.yaml",
        content=yaml.safe_dump(components, sort_keys=False).encode("utf-8"),
        source="rendered",
    )

    return RenderedSeedBundle(
        files=[bundle_files[path] for path in sorted(bundle_files)],
        manifest=manifest,
        components=components,
        baseline_version=str(baseline_manifest.get("core_version") or "unknown"),
    )


def _write_bundle(bundle: RenderedSeedBundle, repo_root: Path) -> None:
    for item in bundle.files:
        target = repo_root / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)


class ProductSeedService:
    def __init__(
        self,
        session: Session,
        *,
        adapter_factory: Callable[[Session, ProductSeedRequest], ProductSeedAdapter] | None = None,
    ):
        self.session = session
        self.adapter_factory = adapter_factory or build_seed_adapter

    def seed_product(self, request: ProductSeedRequest, *, requested_by: str | None = None) -> ProductSeedJob:
        organization = self.session.get(Organization, request.org_id)
        if organization is None:
            raise ValueError(f"Organization not found: {request.org_id}")

        job = ProductSeedJob(
            org_id=request.org_id,
            requested_by=requested_by,
            status="Running",
            dry_run=request.dry_run,
            request_payload=request.model_dump(mode="json"),
            started_at=_now(),
        )
        self.session.add(job)
        self.session.flush()

        self._append_progress(job, "seed", "running", "Seed workflow started.")
        adapter = self.adapter_factory(self.session, request)
        try:
            if request.dry_run:
                self._run_dry_run(job, organization, request, adapter)
            else:
                self._run_live_seed(job, organization, request, adapter)
        except Exception as exc:  # pragma: no cover - defensive persistence around external failures.
            self._append_error(job, "seed.failed", str(exc))
            self._append_audit(job, "seed.failed", "failed", "Seed workflow failed.", {"error": str(exc)})
            job.status = "Failed"
            job.finished_at = _now()
            self.session.flush()
        return job

    def _run_dry_run(
        self,
        job: ProductSeedJob,
        organization: Organization,
        request: ProductSeedRequest,
        adapter: ProductSeedAdapter,
    ) -> None:
        repository = adapter.prepare_repository(request)
        self._record_repository(job, repository)
        project = adapter.ensure_project(request, repository)
        self._record_project(job, project)
        bundle = _render_seed_bundle(organization, request, project)
        job.rendered_file_paths = [item.path for item in bundle.files]

        diagnostics: list[ProductSetupDiagnostic] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            _write_bundle(bundle, repo_root)
            contract_service = ProductContractService(self.session)
            try:
                contract_service.parse_product_manifest(repo_root)
                contract_service.parse_components_manifest(repo_root, ".orcha/components.yaml")
            except ValueError as exc:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="seed.bundle.invalid",
                        message=str(exc),
                    )
                )

        self._append_audit(
            job,
            "bundle.rendered",
            "succeeded",
            "Rendered approved baseline bundle for dry-run inspection.",
            {"rendered_file_count": len(bundle.files)},
        )
        job.setup_state = _classify_setup_state(diagnostics)
        job.setup_diagnostics = [item.model_dump() for item in diagnostics]
        job.status = "DryRun"
        job.finished_at = _now()
        self._append_progress(job, "seed", "completed", "Dry-run completed.")
        self.session.flush()

    def _run_live_seed(
        self,
        job: ProductSeedJob,
        organization: Organization,
        request: ProductSeedRequest,
        adapter: ProductSeedAdapter,
    ) -> None:
        repository = adapter.prepare_repository(request)
        self._record_repository(job, repository)
        self._append_audit(
            job,
            "github.repo",
            "succeeded",
            "Resolved the repository target and prepared the default branch.",
            {"repository": f"{repository.owner}/{repository.name}", "default_branch": repository.default_branch},
        )

        project = adapter.ensure_project(request, repository)
        self._record_project(job, project)
        self._append_audit(
            job,
            "github.project",
            "succeeded",
            "Created or bound the primary GitHub Project.",
            {"project_number": project.number, "title": project.title},
        )

        bundle = _render_seed_bundle(organization, request, project)
        job.rendered_file_paths = [item.path for item in bundle.files]
        apply_result = adapter.apply_bundle(request, repository, bundle)
        if isinstance(apply_result, BundleApplyResult) and apply_result.mode == "pull_request":
            self._append_audit(
                job,
                "github.bundle",
                "blocked",
                "Staged the approved baseline bundle on a pull request because the default branch requires merge review.",
                {
                    "rendered_file_count": len(bundle.files),
                    "base_branch": apply_result.base_branch,
                    "head_branch": apply_result.head_branch,
                    "pull_request_number": apply_result.pull_request_number,
                    "pull_request_url": apply_result.pull_request_url,
                    "commit_shas": list(apply_result.commit_shas),
                },
            )
        else:
            self._append_audit(
                job,
                "github.bundle",
                "succeeded",
                "Applied the approved baseline bundle to the repository.",
                {"rendered_file_count": len(bundle.files)},
            )

        product = self._register_product(
            job=job,
            organization=organization,
            request=request,
            repository=repository,
            project=project,
            bundle=bundle,
        )
        job.product_id = product.product_id
        self._append_audit(
            job,
            "registry.product",
            "succeeded",
            "Registered the product, repository binding, graph root, and project mirror.",
            {"product_id": str(product.product_id)},
        )

        mirror_refresh = adapter.bootstrap_product_mirror(product)
        self._append_audit(
            job,
            "github.mirror",
            "succeeded" if not mirror_refresh.diagnostics else "warning",
            "Bootstrapped the seeded product mirror from GitHub and checked webhook delivery.",
            {
                "issue_count": mirror_refresh.issue_count,
                "project_item_count": mirror_refresh.project_item_count,
                "webhook_status": mirror_refresh.webhook_status,
                "webhook_delivery_url": mirror_refresh.webhook_delivery_url,
                "diagnostic_count": len(mirror_refresh.diagnostics),
            },
        )

        diagnostics = self._refresh_preflight(product=product, bundle=bundle)
        diagnostics.extend(mirror_refresh.diagnostics)
        diagnostics.extend(self._validate_branch_protection(repository.branch_protection))
        diagnostics.extend(self._validate_repository_labels(repository.labels))
        diagnostics.extend(self._validate_project_shape(project, request))
        if isinstance(apply_result, BundleApplyResult) and apply_result.mode == "pull_request":
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.repo.seed_pull_request_pending",
                    message=(
                        "Baseline seed changes were opened on "
                        f"pull request #{apply_result.pull_request_number} and must be merged into "
                        f"`{apply_result.base_branch or repository.default_branch}` before activation can complete."
                    ),
                )
            )
        product.setup_state = _classify_setup_state(diagnostics)
        product.setup_diagnostics = [item.model_dump() for item in diagnostics]
        product.status = "Active" if not _has_blocking_diagnostics(diagnostics) else "Draft"
        job.setup_state = product.setup_state
        job.setup_diagnostics = list(product.setup_diagnostics)
        job.status = "Succeeded" if product.status == "Active" else "Blocked"
        job.finished_at = _now()
        self._append_progress(job, "seed", "completed", "Seed workflow completed.")
        self._append_audit(
            job,
            "activation.preflight",
            "succeeded" if product.status == "Active" else "blocked",
            "Completed activation preflight for the seeded product.",
            {"setup_state": product.setup_state, "blocking": _has_blocking_diagnostics(diagnostics)},
        )
        self.session.flush()

    def _register_product(
        self,
        *,
        job: ProductSeedJob,
        organization: Organization,
        request: ProductSeedRequest,
        repository: RepositorySeedResult,
        project: ProjectSeedResult,
        bundle: RenderedSeedBundle,
    ) -> Product:
        product = Product(
            org_id=organization.org_id,
            key=request.product_key,
            name=request.product_name,
            description=request.description,
            status="Draft",
            baseline_channel=str(bundle.manifest.get("baseline", {}).get("channel") or "stable"),
            standards_pack_key=str(bundle.manifest.get("baseline", {}).get("standards_pack") or "default"),
            standards_pack_version=bundle.baseline_version,
            agent_core_version=bundle.baseline_version,
            execution_profile=str(bundle.manifest.get("execution", {}).get("profile") or "standard-python"),
            operator_overrides={
                "activation": {
                    "required_secret_keys": list(request.required_secret_keys),
                }
            }
            if request.required_secret_keys
            else {},
        )
        self.session.add(product)
        self.session.flush()

        repo_binding = RepositoryBinding(
            product_id=product.product_id,
            github_repository_node_id=repository.github_repository_node_id,
            owner=repository.owner,
            name=repository.name,
            default_branch=repository.default_branch,
            visibility=repository.visibility,
            description=repository.description,
            is_archived=False,
            seed_source=f"approved-baseline:{bundle.baseline_version}",
            adoption_state="seeded",
            raw_payload=repository.raw_payload,
        )
        self.session.add(repo_binding)
        self.session.flush()

        project_mirror = GitHubProjectMirror(
            product_id=product.product_id,
            github_project_node_id=project.github_project_node_id,
            number=project.number,
            title=project.title,
            status_field_name=project.status_field_name,
            status_options=list(project.status_options),
            raw_payload=project.raw_payload,
        )
        self.session.add(project_mirror)
        self.session.flush()

        product.primary_repo_id = repo_binding.repo_id
        product.primary_project_id = project_mirror.project_id

        root_node = ComponentNode(
            product_id=product.product_id,
            type="product",
            key=request.product_key,
            name=request.product_name,
            owner=organization.slug,
            source_kind="seed",
            source_ref=f"{repository.owner}/{repository.name}",
        )
        self.session.add(root_node)
        self.session.flush()
        repo_node = ComponentNode(
            product_id=product.product_id,
            type="repository",
            key=f"{request.product_key}-repo",
            name=request.github_repo,
            owner=request.github_owner,
            source_kind="seed",
            source_ref=f"{repository.owner}/{repository.name}",
        )
        self.session.add(repo_node)
        self.session.flush()
        self.session.add(
            ComponentEdge(
                from_node_id=root_node.component_node_id,
                to_node_id=repo_node.component_node_id,
                relationship_type="owns",
                source_kind="seed",
                confidence=1.0,
            )
        )
        product.component_root_node_id = root_node.component_node_id

        for asset in bundle.manifest.get("baseline", {}).get("managed_assets", []):
            if not isinstance(asset, dict):
                continue
            path = asset.get("path")
            mode = asset.get("mode")
            if not isinstance(path, str) or not isinstance(mode, str):
                continue
            self.session.add(
                ManagedAsset(
                    product_id=product.product_id,
                    path=path,
                    kind="file" if "." in Path(path).name else "directory",
                    management_mode=mode,
                    upstream_bundle_version=bundle.baseline_version,
                    drift_status="current",
                    last_applied_at=_now(),
                )
            )

        project_payload = dict(project.raw_payload)
        project_payload.setdefault("node_id", project.github_project_node_id)
        project_payload.setdefault("number", project.number)
        project_payload.setdefault("title", project.title)
        project_payload.setdefault("status_field_name", project.status_field_name)
        project_payload.setdefault("status_options", list(project.status_options))
        project_payload.setdefault("fields", list(project.fields))
        project_payload.setdefault("items", [])
        GitHubMirrorService(self.session).upsert_project_snapshot(project_payload)
        self.session.flush()
        return product

    def _refresh_preflight(self, *, product: Product, bundle: RenderedSeedBundle) -> list[ProductSetupDiagnostic]:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            _write_bundle(bundle, repo_root)
            result = ProductContractService(self.session).refresh_product_contract(
                product_id=product.product_id,
                repo_root=repo_root,
                operator_overrides=product.operator_overrides,
            )
        return list(result.diagnostics)

    def _validate_github_permissions(self, permissions: dict[str, Any]) -> list[ProductSetupDiagnostic]:
        diagnostics: list[ProductSetupDiagnostic] = []
        for permission_key, required_level in REQUIRED_GITHUB_PERMISSIONS.items():
            actual_level = str(permissions.get(permission_key, "")).strip().lower()
            if PERMISSION_RANK.get(actual_level, 0) >= PERMISSION_RANK.get(required_level, 0):
                continue
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.permission.missing",
                    message=(
                        f"GitHub access permission `{permission_key}` must be at least "
                        f"`{required_level}` but is `{actual_level or 'missing'}`."
                    ),
                )
            )
        return diagnostics

    def _validate_branch_protection(self, branch_protection: dict[str, Any]) -> list[ProductSetupDiagnostic]:
        diagnostics: list[ProductSetupDiagnostic] = []
        enabled = bool(branch_protection.get("enabled") or branch_protection.get("url"))
        reviews = branch_protection.get("required_pull_request_reviews")
        required_approvals = 0
        if isinstance(reviews, dict):
            raw_count = reviews.get("required_approving_review_count")
            if isinstance(raw_count, int):
                required_approvals = raw_count
        if not enabled:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.branch_protection.missing",
                    message="Default branch protection is not enabled.",
                )
            )
        elif required_approvals < 1:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.branch_protection.reviews",
                    message="Default branch protection must require at least one approving review.",
                )
            )
        return diagnostics

    def _validate_project_shape(
        self,
        project: ProjectSeedResult,
        request: ProductSeedRequest,
    ) -> list[ProductSetupDiagnostic]:
        diagnostics: list[ProductSetupDiagnostic] = []
        if project.status_field_name != request.status_field:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.project.status_field",
                    message=(
                        f"Primary project status field `{project.status_field_name}` does not match "
                        f"the required field `{request.status_field}`."
                    ),
                )
            )
        required_options = {request.ready_status, "In Progress", request.done_status}
        missing_options = sorted(required_options - set(project.status_options))
        if missing_options:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.project.status_option_missing",
                    message=f"Primary project is missing required status options: {', '.join(missing_options)}.",
                )
            )
        field_names = {str(field.get("name")) for field in project.fields if isinstance(field, dict)}
        for field_name in {"Priority", "Depends On"}:
            if field_name not in field_names:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="github.project.field_missing",
                        message=f"Primary project is missing the required `{field_name}` field.",
                    )
                )
        available_views = {view.strip().casefold() for view in project.views if view.strip()}
        missing_views = [view for view in DEFAULT_PROJECT_VIEWS if view.casefold() not in available_views]
        if missing_views:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=RECOVERABLE,
                    code="github.project.view_missing",
                    message=(
                        "Primary project is missing seed-time default views: "
                        f"{', '.join(missing_views)}."
                    ),
                )
            )
        return diagnostics

    def _validate_repository_labels(self, labels: list[str]) -> list[ProductSetupDiagnostic]:
        observed = {label.strip().casefold() for label in labels if label.strip()}
        missing = [
            item["name"]
            for item in DEFAULT_REPOSITORY_LABELS
            if item["name"].casefold() not in observed
        ]
        if not missing:
            return []
        return [
            ProductSetupDiagnostic(
                classification=RECOVERABLE,
                code="github.repo.label_missing",
                message=f"Repository is missing baseline labels: {', '.join(missing)}.",
            )
        ]

    def _record_repository(self, job: ProductSeedJob, repository: RepositorySeedResult) -> None:
        job.repo_summary = asdict(repository)
        self._append_progress(
            job,
            "github.repo",
            "completed",
            f"Prepared repository {repository.owner}/{repository.name}.",
        )

    def _record_project(self, job: ProductSeedJob, project: ProjectSeedResult) -> None:
        job.project_summary = asdict(project)
        self._append_progress(
            job,
            "github.project",
            "completed",
            f"Prepared project {project.title} (#{project.number}).",
        )

    def _append_progress(self, job: ProductSeedJob, step: str, status: str, message: str) -> None:
        progress = list(job.progress_payload or [])
        progress.append(
            {
                "step": step,
                "status": status,
                "message": message,
                "recorded_at": _now().isoformat(),
            }
        )
        job.progress_payload = progress

    def _append_audit(
        self,
        job: ProductSeedJob,
        step: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        audit = list(job.audit_payload or [])
        audit.append(
            {
                "step": step,
                "status": status,
                "message": message,
                "details": details or {},
                "recorded_at": _now().isoformat(),
            }
        )
        job.audit_payload = audit

    def _append_error(self, job: ProductSeedJob, code: str, message: str) -> None:
        errors = list(job.error_payload or [])
        errors.append(
            {
                "code": code,
                "message": message,
                "recorded_at": _now().isoformat(),
            }
        )
        job.error_payload = errors
