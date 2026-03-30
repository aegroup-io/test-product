from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from agent_core_platform_api.component_graph import ComponentGraphService
from agent_core_platform_api.models import GitHubProjectMirror, ManagedAsset, Product, RepositoryBinding, Secret, Setting


PRODUCT_DEFAULTS_SETTING_KEY = "orcha.product_defaults"
PLATFORM_SETTINGS_SCOPE_ID = "global"
ALLOWED_MANAGED_ASSET_MODES = {"managed", "section-managed", "advisory", "local"}
ALLOWED_WORKSPACE_STRATEGIES = {"branch-per-lane"}
ALLOWED_COMPONENT_EDGE_RELATIONSHIPS = {
    "depends_on",
    "owns",
    "deploys",
    "publishes",
    "consumes",
    "calls",
}
BLOCKING = "blocking setup error"
RECOVERABLE = "recoverable drift"
ADVISORY = "advisory warning"
ADOPTION_VALIDATION_STATES = {"adopting", "adopted", "setup-needed", "drift", "advisory"}
WRITE_PERMISSION_LEVELS = {"write", "maintain", "admin"}
ALLOWED_APPROVAL_POSTURES = {"blocked", "operator-gated", "high-trust"}

PLATFORM_DEFAULTS: dict[str, Any] = {
    "product": {},
    "github": {},
    "baseline": {
        "channel": "stable",
        "agent_core_version": "0.1.0",
        "standards_pack": "default",
        "managed_assets": [],
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
        "repo_write_policy": "high-trust",
        "branch_creation_policy": "high-trust",
        "issue_edit_policy": "high-trust",
        "pr_edit_policy": "high-trust",
        "tool_use_policy": "high-trust",
        "network_use_policy": "high-trust",
        "require_human_merge": True,
        "allow_agent_comments": True,
        "allow_agent_issue_edits": True,
        "allow_agent_pr_edits": True,
    },
    "activation": {
        "required_assets": [
            "AGENTS.md",
            ".github/workflows/repo-harness.yml",
            ".github/workflows/advisory-code-review.yml",
            ".github/workflows/merge-readiness.yml",
        ],
        "recommended_assets": [
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE",
        ],
        "required_secret_keys": [],
    },
}

SUPPORTED_EXECUTION_PROFILES: dict[str, dict[str, Any]] = {
    "standard-python": {
        "container_image": "ghcr.io/aegroup/agent-core-runner:stable",
        "workspace_strategy": "branch-per-lane",
        "max_concurrent_lanes": 6,
        "required_secret_keys": [],
    }
}


class ProductSetupDiagnostic(BaseModel):
    classification: Literal[BLOCKING, RECOVERABLE, ADVISORY]
    code: str
    message: str
    path: str | None = None


class ManagedAssetContract(BaseModel):
    path: str = Field(min_length=1)
    mode: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_mode(self) -> "ManagedAssetContract":
        if self.mode not in ALLOWED_MANAGED_ASSET_MODES:
            raise ValueError(f"Unsupported managed asset mode: {self.mode}")
        return self


class ProductSection(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    org: str = Field(min_length=1)
    description: str | None = None


class GitHubSection(BaseModel):
    owner: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    default_branch: str = Field(min_length=1)
    project_number: int = Field(ge=1)
    status_field: str = Field(min_length=1)
    ready_status: str = Field(min_length=1)
    done_status: str = Field(min_length=1)


class BaselineSection(BaseModel):
    channel: str = Field(min_length=1)
    agent_core_version: str | None = Field(default=None, min_length=1)
    standards_pack: str = Field(default="default", min_length=1)
    managed_assets: list[ManagedAssetContract] = Field(default_factory=list)


class ExecutionSection(BaseModel):
    profile: str = Field(min_length=1)
    container_image: str | None = Field(default=None, min_length=1)
    max_concurrent_lanes: int | None = Field(default=None, ge=1)
    workspace_strategy: str = Field(default="branch-per-lane", min_length=1)

    @model_validator(mode="after")
    def validate_strategy(self) -> "ExecutionSection":
        if self.workspace_strategy not in ALLOWED_WORKSPACE_STRATEGIES:
            raise ValueError(f"Unsupported workspace strategy: {self.workspace_strategy}")
        return self


class GraphSection(BaseModel):
    components_file: str = Field(default=".orcha/components.yaml", min_length=1)
    auto_discover: bool = True


class GovernanceSection(BaseModel):
    approval_posture: str = Field(default="high-trust", min_length=1)
    repo_write_policy: str | None = Field(default=None, min_length=1)
    branch_creation_policy: str | None = Field(default=None, min_length=1)
    issue_edit_policy: str | None = Field(default=None, min_length=1)
    pr_edit_policy: str | None = Field(default=None, min_length=1)
    tool_use_policy: str | None = Field(default=None, min_length=1)
    network_use_policy: str | None = Field(default=None, min_length=1)
    require_human_merge: bool = True
    allow_agent_comments: bool = True
    allow_agent_issue_edits: bool = True
    allow_agent_pr_edits: bool = True

    @model_validator(mode="after")
    def validate_policies(self) -> "GovernanceSection":
        for key in (
            "approval_posture",
            "repo_write_policy",
            "branch_creation_policy",
            "issue_edit_policy",
            "pr_edit_policy",
            "tool_use_policy",
            "network_use_policy",
        ):
            value = getattr(self, key)
            if value is None:
                continue
            if value not in ALLOWED_APPROVAL_POSTURES:
                raise ValueError(f"Unsupported governance policy: {key}={value}")
        return self


class ProductManifest(BaseModel):
    schema_version: int
    product: ProductSection
    github: GitHubSection
    baseline: BaselineSection
    execution: ExecutionSection
    graph: GraphSection = Field(default_factory=GraphSection)
    governance: GovernanceSection = Field(default_factory=GovernanceSection)

    @model_validator(mode="after")
    def validate_schema_version(self) -> "ProductManifest":
        if self.schema_version != 1:
            raise ValueError(f"Unsupported product manifest schema_version: {self.schema_version}")
        return self


class DeclaredComponent(BaseModel):
    key: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    owner: str | None = None
    version: str | None = None
    status: str | None = None


class DeclaredComponentEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_key: str = Field(alias="from", min_length=1)
    to_key: str = Field(alias="to", min_length=1)
    relationship: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relationship(self) -> "DeclaredComponentEdge":
        if self.relationship not in ALLOWED_COMPONENT_EDGE_RELATIONSHIPS:
            raise ValueError(f"Unsupported component edge relationship: {self.relationship}")
        return self


class ComponentsManifest(BaseModel):
    schema_version: int
    components: list[DeclaredComponent] = Field(default_factory=list)
    edges: list[DeclaredComponentEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schema_version(self) -> "ComponentsManifest":
        if self.schema_version != 1:
            raise ValueError(f"Unsupported components manifest schema_version: {self.schema_version}")
        return self


class ProductContractRefreshResult(BaseModel):
    manifest_schema_version: int | None
    setup_state: str
    diagnostics: list[ProductSetupDiagnostic]
    effective_config: dict[str, Any]


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing required manifest: {path.name}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Manifest is not valid YAML: {path.name}") from exc
    if raw is None:
        raise ValueError(f"Manifest is empty: {path.name}")
    if not isinstance(raw, dict):
        raise ValueError(f"Manifest must be a mapping: {path.name}")
    return raw


def _policy_strictness(value: Any) -> int:
    if not isinstance(value, str):
        return 1
    normalized = value.strip().lower()
    return {"blocked": 0, "operator-gated": 1, "high-trust": 2}.get(normalized, 1)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _merge_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _deep_merge(merged, layer)
    return merged


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


def _asset_kind(path: str) -> str:
    lower_path = path.lower()
    if lower_path.endswith(".md"):
        return "markdown"
    if lower_path.endswith((".yml", ".yaml")):
        return "yaml"
    return "file"


def _permission_can_write(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in WRITE_PERMISSION_LEVELS


def _resolve_repo_relative_path(repo_root: Path, configured_path: str) -> Path:
    resolved_root = repo_root.resolve()
    candidate = Path(configured_path)
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise ValueError(f"Manifest path escapes repo root: {configured_path}")
    return resolved_candidate


class ProductContractService:
    def __init__(self, session: Session):
        self.session = session

    def parse_product_manifest(self, repo_root: Path) -> ProductManifest:
        try:
            payload = _read_yaml(repo_root / ".orcha" / "product.yaml")
            return ProductManifest.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise ValueError(str(exc)) from exc

    def parse_components_manifest(self, repo_root: Path, components_path: str) -> ComponentsManifest:
        try:
            payload = _read_yaml(_resolve_repo_relative_path(repo_root, components_path))
            return ComponentsManifest.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise ValueError(str(exc)) from exc

    def refresh_product_contract(
        self,
        *,
        product_id,
        repo_root: Path,
        operator_overrides: dict[str, Any] | None = None,
    ) -> ProductContractRefreshResult:
        product = self.session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")

        repo_binding = self._resolve_primary_repo(product)
        project_mirror = self._resolve_primary_project(product)

        diagnostics: list[ProductSetupDiagnostic] = []

        try:
            platform_settings = self._load_scope_defaults("platform", PLATFORM_SETTINGS_SCOPE_ID)
        except ValueError as exc:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="settings.platform_defaults_invalid",
                    message=str(exc),
                )
            )
            platform_settings = {}
        try:
            org_settings = self._load_scope_defaults("org", str(product.org_id))
        except ValueError as exc:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="settings.org_defaults_invalid",
                    message=str(exc),
                )
            )
            org_settings = {}
        product_defaults = self._build_product_record_defaults(product, repo_binding, project_mirror)
        manifest: ProductManifest | None = None
        components_manifest: ComponentsManifest | None = None
        components_path = str(PLATFORM_DEFAULTS["graph"]["components_file"])

        try:
            manifest = self.parse_product_manifest(repo_root)
        except ValueError as exc:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="manifest.invalid",
                    message=str(exc),
                    path=".orcha/product.yaml",
                )
            )

        if manifest is not None:
            components_path = manifest.graph.components_file
            try:
                components_full_path = _resolve_repo_relative_path(repo_root, components_path)
            except ValueError as exc:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="components.invalid",
                        message=str(exc),
                        path=components_path,
                    )
                )
            else:
                if components_full_path.exists():
                    try:
                        components_manifest = self.parse_components_manifest(repo_root, components_path)
                    except ValueError as exc:
                        diagnostics.append(
                            ProductSetupDiagnostic(
                                classification=BLOCKING,
                                code="components.invalid",
                                message=str(exc),
                                path=components_path,
                            )
                        )
                else:
                    diagnostics.append(
                        ProductSetupDiagnostic(
                            classification=ADVISORY,
                            code="components.missing",
                            message=f"Declared components file is missing: {components_path}",
                            path=components_path,
                        )
                    )

        manifest_defaults = self._build_manifest_defaults(manifest) if manifest is not None else {}
        persisted_overrides = deepcopy(product.operator_overrides or {})
        if operator_overrides:
            persisted_overrides = _deep_merge(persisted_overrides, operator_overrides)

        effective_config = _merge_layers(
            PLATFORM_DEFAULTS,
            platform_settings,
            org_settings,
            product_defaults,
            manifest_defaults,
            persisted_overrides,
        )

        diagnostics.extend(self._validate_manifest_conflicts(product, repo_binding, project_mirror, manifest))
        diagnostics.extend(self._validate_execution_profile(effective_config))
        diagnostics.extend(self._validate_project_mapping(project_mirror, effective_config))
        diagnostics.extend(self._validate_repository_posture(repo_binding, effective_config))
        diagnostics.extend(self._validate_required_assets(repo_root, effective_config))
        diagnostics.extend(self._validate_required_secrets(effective_config))
        diagnostics.extend(self._validate_components_manifest(components_manifest))

        self._apply_safety_constraints(
            effective_config,
            diagnostics=diagnostics,
            lower_layers=[PLATFORM_DEFAULTS, platform_settings, org_settings, product_defaults],
        )

        setup_state = _classify_setup_state(diagnostics)
        refresh_time = datetime.now(timezone.utc)
        ComponentGraphService(self.session).refresh_product_graph(
            product=product,
            repo_binding=repo_binding,
            components_manifest=components_manifest,
            declared_source_ref=components_path,
            observed_at=refresh_time,
        )

        product.manifest_schema_version = manifest.schema_version if manifest is not None else None
        product.operator_overrides = persisted_overrides
        product.setup_state = setup_state
        product.setup_diagnostics = [item.model_dump() for item in diagnostics]
        product.last_config_refresh_at = refresh_time
        self._sync_managed_assets(product=product, repo_root=repo_root, effective_config=effective_config)

        if not _has_blocking_diagnostics(diagnostics):
            product.effective_config = effective_config
            product.last_accepted_config_at = refresh_time
            baseline = effective_config.get("baseline", {})
            execution = effective_config.get("execution", {})
            product.baseline_channel = baseline.get("channel")
            product.standards_pack_key = product.standards_pack_key or baseline.get("standards_pack")
            product.standards_pack_version = baseline.get("standards_pack_version") or product.standards_pack_version
            product.agent_core_version = baseline.get("agent_core_version")
            product.execution_profile = execution.get("profile")
            if manifest is not None:
                product.name = manifest.product.name.strip()
                product.description = manifest.product.description
            if product.status not in {"Paused", "Archived"}:
                product.status = "Active"
        elif product.status not in {"Paused", "Archived"}:
            product.status = "Draft"

        self.session.flush()
        return ProductContractRefreshResult(
            manifest_schema_version=product.manifest_schema_version,
            setup_state=product.setup_state,
            diagnostics=diagnostics,
            effective_config=product.effective_config,
        )

    def _resolve_primary_repo(self, product: Product) -> RepositoryBinding | None:
        if product.primary_repo_id is not None:
            repo = self.session.get(RepositoryBinding, product.primary_repo_id)
            if repo is not None:
                return repo
        return (
            self.session.query(RepositoryBinding)
            .filter(RepositoryBinding.product_id == product.product_id)
            .order_by(RepositoryBinding.created_at.asc())
            .first()
        )

    def _resolve_primary_project(self, product: Product) -> GitHubProjectMirror | None:
        if product.primary_project_id is not None:
            project = self.session.get(GitHubProjectMirror, product.primary_project_id)
            if project is not None:
                return project
        return (
            self.session.query(GitHubProjectMirror)
            .filter(GitHubProjectMirror.product_id == product.product_id)
            .order_by(GitHubProjectMirror.created_at.asc())
            .first()
        )

    def _load_scope_defaults(self, scope_type: str, scope_id: str) -> dict[str, Any]:
        setting = (
            self.session.query(Setting)
            .filter(
                Setting.scope_type == scope_type,
                Setting.scope_id == scope_id,
                Setting.key == PRODUCT_DEFAULTS_SETTING_KEY,
            )
            .first()
        )
        if setting is None:
            return {}
        if not isinstance(setting.value_json, dict):
            raise ValueError(f"Setting {PRODUCT_DEFAULTS_SETTING_KEY} for {scope_type}:{scope_id} must be a JSON object")
        return deepcopy(setting.value_json)

    def _build_product_record_defaults(
        self,
        product: Product,
        repo_binding: RepositoryBinding | None,
        project_mirror: GitHubProjectMirror | None,
    ) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "product": {
                "key": product.key,
                "name": product.name,
                "description": product.description,
            },
            "baseline": {
                "channel": product.baseline_channel,
                "standards_pack": product.standards_pack_key,
                "standards_pack_version": product.standards_pack_version,
                "agent_core_version": product.agent_core_version,
            },
            "execution": {
                "profile": product.execution_profile,
            },
        }
        if repo_binding is not None:
            defaults["github"] = {
                "owner": repo_binding.owner,
                "repo": repo_binding.name,
                "default_branch": repo_binding.default_branch,
            }
        if project_mirror is not None:
            defaults.setdefault("github", {})
            defaults["github"].update(
                {
                    "project_number": project_mirror.number,
                    "status_field": project_mirror.status_field_name,
                }
            )
        return defaults

    def _build_manifest_defaults(self, manifest: ProductManifest) -> dict[str, Any]:
        return manifest.model_dump(mode="python", by_alias=True)

    def _validate_manifest_conflicts(
        self,
        product: Product,
        repo_binding: RepositoryBinding | None,
        project_mirror: GitHubProjectMirror | None,
        manifest: ProductManifest | None,
    ) -> list[ProductSetupDiagnostic]:
        if manifest is None:
            return []

        diagnostics: list[ProductSetupDiagnostic] = []
        if manifest.product.key != product.key:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="manifest.product_key_conflict",
                    message=(
                        f"Manifest product key `{manifest.product.key}` conflicts with registered product key `{product.key}`."
                    ),
                    path=".orcha/product.yaml",
                )
            )

        if repo_binding is None:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.repo_binding_missing",
                    message="Primary repository binding is missing.",
                )
            )
        else:
            if manifest.github.owner != repo_binding.owner or manifest.github.repo != repo_binding.name:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="manifest.github_repo_conflict",
                        message=(
                            "Manifest GitHub repository does not match the registered repository binding "
                            f"({manifest.github.owner}/{manifest.github.repo} vs {repo_binding.owner}/{repo_binding.name})."
                        ),
                        path=".orcha/product.yaml",
                    )
                )
            if manifest.github.default_branch != repo_binding.default_branch:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="manifest.default_branch_conflict",
                        message=(
                            f"Manifest default branch `{manifest.github.default_branch}` does not match "
                            f"registered default branch `{repo_binding.default_branch}`."
                        ),
                        path=".orcha/product.yaml",
                    )
                )

        if project_mirror is None:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.project_missing",
                    message="Primary GitHub project mapping is missing.",
                )
            )
        elif manifest.github.project_number != project_mirror.number:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="manifest.project_number_conflict",
                    message=(
                        f"Manifest project number `{manifest.github.project_number}` does not match "
                        f"registered project number `{project_mirror.number}`."
                    ),
                    path=".orcha/product.yaml",
                )
            )
        return diagnostics

    def _validate_project_mapping(
        self,
        project_mirror: GitHubProjectMirror | None,
        effective_config: dict[str, Any],
    ) -> list[ProductSetupDiagnostic]:
        if project_mirror is None:
            return []

        github_config = effective_config.get("github", {})
        status_field = github_config.get("status_field")
        ready_status = github_config.get("ready_status")
        done_status = github_config.get("done_status")
        diagnostics: list[ProductSetupDiagnostic] = []

        if status_field and status_field != project_mirror.status_field_name:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.status_field_conflict",
                    message=(
                        f"Effective status field `{status_field}` does not match registered field "
                        f"`{project_mirror.status_field_name}`."
                    ),
                    path=".orcha/product.yaml",
                )
            )

        status_options = set(project_mirror.status_options or [])
        for code, candidate in (
            ("github.ready_status_missing", ready_status),
            ("github.done_status_missing", done_status),
        ):
            if candidate and candidate not in status_options:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code=code,
                        message=f"Configured project status `{candidate}` is missing from the registered project options.",
                        path=".orcha/product.yaml",
                    )
                )
        return diagnostics

    def _validate_repository_posture(
        self,
        repo_binding: RepositoryBinding | None,
        effective_config: dict[str, Any],
    ) -> list[ProductSetupDiagnostic]:
        if repo_binding is None or repo_binding.adoption_state not in ADOPTION_VALIDATION_STATES:
            return []

        diagnostics: list[ProductSetupDiagnostic] = []
        if repo_binding.is_archived:
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.repo_archived",
                    message="Adopted repository is archived and cannot enter normal dispatch.",
                )
            )

        raw_payload = repo_binding.raw_payload if isinstance(repo_binding.raw_payload, dict) else {}
        branch_protection = raw_payload.get("default_branch_protection")
        if not isinstance(branch_protection, dict):
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.branch_protection_unknown",
                    message="Default-branch protection posture is missing from the adoption snapshot.",
                )
            )
        else:
            if branch_protection.get("enabled") is not True:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="github.branch_protection_missing",
                        message="Default branch is not protected.",
                    )
                )
            governance = effective_config.get("governance", {})
            if governance.get("require_human_merge", True):
                if branch_protection.get("requires_pull_request") is not True:
                    diagnostics.append(
                        ProductSetupDiagnostic(
                            classification=BLOCKING,
                            code="github.branch_protection_pr_reviews_required",
                            message="Default branch must require pull requests before merge.",
                        )
                    )
                approval_count = branch_protection.get("required_approving_review_count")
                if not isinstance(approval_count, int) or approval_count < 1:
                    diagnostics.append(
                        ProductSetupDiagnostic(
                            classification=BLOCKING,
                            code="github.branch_protection_approvals_required",
                            message="Default branch must require at least one approving review.",
                        )
                    )
            if branch_protection.get("allows_force_pushes") is True:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=RECOVERABLE,
                        code="github.branch_protection_force_push_allowed",
                        message="Default branch still allows force pushes and should be tightened.",
                    )
                )
            if branch_protection.get("allows_deletions") is True:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=RECOVERABLE,
                        code="github.branch_protection_deletion_allowed",
                        message="Default branch still allows deletions and should be tightened.",
                    )
                )

        permissions = raw_payload.get("orcha_permissions")
        if not isinstance(permissions, dict):
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="github.permissions_unknown",
                    message="Required GitHub permission snapshot is missing from the adoption payload.",
                )
            )
            return diagnostics

        required_permissions = {
            "contents": "contents",
            "pull_requests": "pull_requests",
            "projects": "projects",
        }
        governance = effective_config.get("governance", {})
        if governance.get("allow_agent_comments", True) or governance.get("allow_agent_issue_edits", True):
            required_permissions["issues"] = "issues"

        for permission_key, code_suffix in required_permissions.items():
            if _permission_can_write(permissions.get(permission_key)):
                continue
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code=f"github.permission_{code_suffix}_write_missing",
                    message=f"GitHub access is missing `{permission_key}` write access required for adopted products.",
                )
            )
        return diagnostics

    def _validate_execution_profile(self, effective_config: dict[str, Any]) -> list[ProductSetupDiagnostic]:
        execution = effective_config.get("execution", {})
        profile = execution.get("profile")
        if profile not in SUPPORTED_EXECUTION_PROFILES:
            return [
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="execution.profile_unsupported",
                    message=f"Unsupported execution profile: {profile}",
                    path=".orcha/product.yaml",
                )
            ]

        diagnostics: list[ProductSetupDiagnostic] = []
        profile_defaults = SUPPORTED_EXECUTION_PROFILES[profile]
        if not execution.get("container_image"):
            execution["container_image"] = profile_defaults["container_image"]
        if not execution.get("workspace_strategy"):
            execution["workspace_strategy"] = profile_defaults["workspace_strategy"]
        if not execution.get("max_concurrent_lanes"):
            execution["max_concurrent_lanes"] = profile_defaults["max_concurrent_lanes"]
        return diagnostics

    def _validate_required_assets(
        self,
        repo_root: Path,
        effective_config: dict[str, Any],
    ) -> list[ProductSetupDiagnostic]:
        diagnostics: list[ProductSetupDiagnostic] = []
        activation = effective_config.get("activation", {})
        required_assets = set(activation.get("required_assets", []))
        recommended_assets = set(activation.get("recommended_assets", []))
        manifest_assets = effective_config.get("baseline", {}).get("managed_assets", [])

        skills_dir = repo_root / "skills"
        if skills_dir.exists() and any(item.name != "README.md" for item in skills_dir.iterdir()):
            required_assets.add("skills/README.md")

        for asset in sorted(required_assets):
            if not (repo_root / asset).exists():
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="asset.required_missing",
                        message=f"Required harness asset is missing: {asset}",
                        path=asset,
                    )
                )

        for asset in sorted(recommended_assets):
            if not (repo_root / asset).exists():
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=RECOVERABLE,
                        code="asset.recommended_missing",
                        message=f"Recommended baseline asset is missing: {asset}",
                        path=asset,
                    )
                )

        for item in manifest_assets:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            mode = str(item.get("mode", "")).strip()
            if not path or not mode:
                continue
            if mode in {"managed", "section-managed"} and not (repo_root / path).exists():
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=RECOVERABLE if path not in required_assets else BLOCKING,
                        code="asset.managed_missing",
                        message=f"Managed asset declared in the manifest is missing: {path}",
                        path=path,
                        )
                )
        return diagnostics

    def _sync_managed_assets(
        self,
        *,
        product: Product,
        repo_root: Path,
        effective_config: dict[str, Any],
    ) -> None:
        activation = effective_config.get("activation", {})
        baseline = effective_config.get("baseline", {})
        required_assets = set(activation.get("required_assets", []))
        recommended_assets = set(activation.get("recommended_assets", []))
        manifest_assets = baseline.get("managed_assets", [])
        skills_dir = repo_root / "skills"
        if skills_dir.exists() and any(item.name != "README.md" for item in skills_dir.iterdir()):
            required_assets.add("skills/README.md")

        expected_assets: dict[str, dict[str, Any]] = {}
        for path in sorted(required_assets):
            expected_assets[path] = {
                "management_mode": "managed",
                "required": True,
            }
        for path in sorted(recommended_assets):
            expected_assets.setdefault(
                path,
                {
                    "management_mode": "managed",
                    "required": False,
                },
            )
        for item in manifest_assets:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            mode = str(item.get("mode", "")).strip()
            if not path or not mode:
                continue
            expected_assets[path] = {
                "management_mode": mode,
                "required": path in required_assets,
            }

        existing_assets = {
            asset.path: asset
            for asset in self.session.query(ManagedAsset).filter(ManagedAsset.product_id == product.product_id).all()
        }
        bundle_version = baseline.get("agent_core_version") or baseline.get("channel")
        for path, details in expected_assets.items():
            asset = existing_assets.get(path)
            if asset is None:
                asset = ManagedAsset(
                    product_id=product.product_id,
                    path=path,
                    kind=_asset_kind(path),
                    management_mode=details["management_mode"],
                )
                self.session.add(asset)
            asset.kind = _asset_kind(path)
            asset.management_mode = details["management_mode"]
            asset.upstream_bundle_version = bundle_version

            asset_path = repo_root / path
            if asset_path.exists():
                asset.drift_status = None
            elif details["required"]:
                asset.drift_status = "missing-required"
            elif details["management_mode"] in {"managed", "section-managed"}:
                asset.drift_status = "missing-managed"
            elif details["management_mode"] == "advisory":
                asset.drift_status = "missing-advisory"
            else:
                asset.drift_status = "missing-local"

    def _validate_required_secrets(self, effective_config: dict[str, Any]) -> list[ProductSetupDiagnostic]:
        activation = effective_config.get("activation", {})
        required_secret_keys = set(activation.get("required_secret_keys", []))
        execution = effective_config.get("execution", {})
        profile = execution.get("profile")
        if profile in SUPPORTED_EXECUTION_PROFILES:
            required_secret_keys.update(SUPPORTED_EXECUTION_PROFILES[profile]["required_secret_keys"])
        if not required_secret_keys:
            return []

        existing = {
            secret.key
            for secret in self.session.query(Secret).filter(Secret.key.in_(required_secret_keys)).all()
            if secret.has_value
        }
        diagnostics: list[ProductSetupDiagnostic] = []
        for key in sorted(required_secret_keys - existing):
            diagnostics.append(
                ProductSetupDiagnostic(
                    classification=BLOCKING,
                    code="secret.required_missing",
                    message=f"Required secret is missing or has no value: {key}",
                )
            )
        return diagnostics

    def _validate_components_manifest(
        self,
        components_manifest: ComponentsManifest | None,
    ) -> list[ProductSetupDiagnostic]:
        if components_manifest is None:
            return []

        component_keys = {component.key for component in components_manifest.components}
        diagnostics: list[ProductSetupDiagnostic] = []
        for edge in components_manifest.edges:
            if edge.from_key not in component_keys or edge.to_key not in component_keys:
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=BLOCKING,
                        code="components.edge_target_missing",
                        message=(
                            f"Component edge `{edge.from_key} -> {edge.to_key}` references an undeclared component."
                        ),
                        path=".orcha/components.yaml",
                    )
                )
        return diagnostics

    def _apply_safety_constraints(
        self,
        effective_config: dict[str, Any],
        *,
        diagnostics: list[ProductSetupDiagnostic],
        lower_layers: list[dict[str, Any]],
    ) -> None:
        governance = effective_config.setdefault("governance", {})
        lower_governance = [layer.get("governance", {}) for layer in lower_layers if isinstance(layer, dict)]

        if any(layer.get("require_human_merge") is True for layer in lower_governance):
            if governance.get("require_human_merge") is False:
                governance["require_human_merge"] = True
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=ADVISORY,
                        code="governance.require_human_merge_capped",
                        message="Repo-local governance cannot disable a higher-level human-merge requirement.",
                        path=".orcha/product.yaml",
                    )
                )

        lower_postures = [layer.get("approval_posture") for layer in lower_governance if isinstance(layer.get("approval_posture"), str)]
        if lower_postures and any(_policy_strictness(value) < _policy_strictness(governance.get("approval_posture")) for value in lower_postures):
            capped_value = min((value for value in lower_postures if isinstance(value, str)), key=_policy_strictness)
            if governance.get("approval_posture") != capped_value:
                governance["approval_posture"] = capped_value
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=ADVISORY,
                        code="governance.approval_posture_capped",
                        message="Repo-local governance cannot relax a higher-level approval posture.",
                        path=".orcha/product.yaml",
                    )
                )

        for key in (
            "repo_write_policy",
            "branch_creation_policy",
            "issue_edit_policy",
            "pr_edit_policy",
            "tool_use_policy",
            "network_use_policy",
        ):
            requested = governance.get(key) or governance.get("approval_posture")
            lower_values = [
                layer.get(key) or layer.get("approval_posture")
                for layer in lower_governance
                if isinstance(layer.get(key) or layer.get("approval_posture"), str)
            ]
            if lower_values and any(_policy_strictness(value) < _policy_strictness(requested) for value in lower_values):
                capped_value = min(
                    lower_values,
                    key=_policy_strictness,
                )
                if governance.get(key) != capped_value:
                    governance[key] = capped_value
                    diagnostics.append(
                        ProductSetupDiagnostic(
                            classification=ADVISORY,
                            code=f"governance.{key}_capped",
                            message=f"Repo-local governance cannot relax higher-level `{key}` policy.",
                            path=".orcha/product.yaml",
                        )
                    )

        for key in ("allow_agent_comments", "allow_agent_issue_edits", "allow_agent_pr_edits"):
            if any(layer.get(key) is False for layer in lower_governance):
                if governance.get(key) is True:
                    governance[key] = False
                    diagnostics.append(
                        ProductSetupDiagnostic(
                            classification=ADVISORY,
                            code=f"governance.{key}_capped",
                            message=(
                                f"Repo-local governance cannot enable `{key}` when a higher-level policy disables it."
                            ),
                            path=".orcha/product.yaml",
                        )
                    )

        execution = effective_config.setdefault("execution", {})
        profile = execution.get("profile")
        if profile not in SUPPORTED_EXECUTION_PROFILES:
            return
        lower_execution = [layer.get("execution", {}) for layer in lower_layers if isinstance(layer, dict)]
        caps = [
            value
            for value in [layer.get("max_concurrent_lanes") for layer in lower_execution]
            if isinstance(value, int) and value > 0
        ]
        requested_lanes = execution.get("max_concurrent_lanes")
        if caps and isinstance(requested_lanes, int):
            allowed_cap = min(caps + [SUPPORTED_EXECUTION_PROFILES[profile]["max_concurrent_lanes"]])
            if requested_lanes > allowed_cap:
                execution["max_concurrent_lanes"] = allowed_cap
                diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=ADVISORY,
                        code="execution.max_concurrent_lanes_capped",
                        message=(
                            f"Configured max_concurrent_lanes `{requested_lanes}` exceeds the allowed cap `{allowed_cap}`."
                        ),
                        path=".orcha/product.yaml",
                    )
                )
