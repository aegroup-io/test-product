from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from agent_core_platform_api.models import GitHubProjectMirror, ManagedAsset, Organization, Product, RepositoryBinding
from agent_core_platform_api.orcha_state import OrchaStateStore
from agent_core_platform_api.product_contract import ProductContractService
from agent_core_platform_api.schemas import ProductAdoptionRequest, ProductAdoptionResponse, ProductResponse


class ProductAdoptionConflictError(ValueError):
    """Raised when the requested adoption collides with an existing product binding."""


class ProductAdoptionService:
    def __init__(self, session: Session):
        self.session = session
        self.state = OrchaStateStore(session)
        self.contracts = ProductContractService(session)

    def adopt_product(
        self,
        payload: ProductAdoptionRequest,
        *,
        dry_run: bool,
    ) -> ProductAdoptionResponse:
        repo_root = Path(payload.repo_root).expanduser().resolve()
        if not repo_root.exists() or not repo_root.is_dir():
            raise ValueError(f"Repository root does not exist or is not a directory: {repo_root}")

        org = self.session.get(Organization, payload.org_id)
        if org is None:
            raise ValueError(f"Organization not found: {payload.org_id}")

        self._ensure_unique(payload)

        product = self.state.create_product(
            org_id=payload.org_id,
            key=payload.key.strip(),
            name=payload.name.strip(),
            description=payload.description,
            status="Draft",
            baseline_channel=payload.baseline_channel,
            agent_core_version=payload.agent_core_version,
            execution_profile=payload.execution_profile,
        )
        repo = self.state.bind_repository(
            product_id=product.product_id,
            github_repository_node_id=payload.repository.github_repository_node_id,
            owner=payload.repository.owner.strip(),
            name=payload.repository.name.strip(),
            default_branch=payload.repository.default_branch.strip(),
            visibility=payload.repository.visibility,
            description=payload.repository.description,
            is_archived=payload.repository.is_archived,
            seed_source="github-adoption",
            adoption_state="adopting",
            raw_payload={
                "default_branch_protection": payload.repository.branch_protection.model_dump(mode="python"),
                "orcha_permissions": payload.repository.permissions.model_dump(mode="python"),
            },
        )
        project = self.state.create_project_mirror(
            product_id=product.product_id,
            github_project_node_id=payload.project.github_project_node_id,
            number=payload.project.number,
            title=payload.project.title.strip(),
            status_field_name=payload.project.status_field_name.strip(),
            status_options=[item.strip() for item in payload.project.status_options],
            raw_payload={
                "status_options": [item.strip() for item in payload.project.status_options],
            },
            mirror_version=1,
        )
        product.primary_repo_id = repo.repo_id
        product.primary_project_id = project.project_id
        self.session.flush()

        result = self.contracts.refresh_product_contract(
            product_id=product.product_id,
            repo_root=repo_root,
            operator_overrides=payload.operator_overrides,
        )
        repo.adoption_state = "setup-needed" if result.setup_state == "setup-needed" else "adopted"
        self.session.flush()

        if dry_run:
            response = ProductAdoptionResponse(
                dry_run=True,
                product=self._serialize_product(product),
            )
            self.session.rollback()
            return response

        self.session.commit()
        persisted_product = self.session.get(Product, product.product_id)
        if persisted_product is None:
            raise ValueError("Adopted product could not be reloaded after commit.")
        return ProductAdoptionResponse(
            dry_run=False,
            product=self._serialize_product(persisted_product),
        )

    def _ensure_unique(self, payload: ProductAdoptionRequest) -> None:
        existing_product = (
            self.session.query(Product)
            .filter(
                Product.org_id == payload.org_id,
                Product.key == payload.key.strip(),
            )
            .first()
        )
        if existing_product is not None:
            raise ProductAdoptionConflictError(f"Product key already exists in this organization: {payload.key}")

        existing_repo = (
            self.session.query(RepositoryBinding)
            .filter(
                RepositoryBinding.owner == payload.repository.owner.strip(),
                RepositoryBinding.name == payload.repository.name.strip(),
            )
            .first()
        )
        if existing_repo is not None:
            raise ProductAdoptionConflictError(
                f"Repository is already bound to product {existing_repo.product_id}: "
                f"{payload.repository.owner}/{payload.repository.name}"
            )

        if payload.repository.github_repository_node_id:
            existing_repo_node = (
                self.session.query(RepositoryBinding)
                .filter(RepositoryBinding.github_repository_node_id == payload.repository.github_repository_node_id)
                .first()
            )
            if existing_repo_node is not None:
                raise ProductAdoptionConflictError(
                    f"Repository node is already bound to product {existing_repo_node.product_id}: "
                    f"{payload.repository.github_repository_node_id}"
                )

        if payload.project.github_project_node_id:
            existing_project = (
                self.session.query(GitHubProjectMirror)
                .filter(GitHubProjectMirror.github_project_node_id == payload.project.github_project_node_id)
                .first()
            )
            if existing_project is not None:
                raise ProductAdoptionConflictError(
                    f"Project node is already bound to product {existing_project.product_id}: "
                    f"{payload.project.github_project_node_id}"
                )

    def _serialize_product(self, product: Product) -> ProductResponse:
        self.session.refresh(product)
        repo = self._resolve_primary_repo(product)
        project = self._resolve_primary_project(product)
        if repo is not None:
            self.session.refresh(repo)
        if project is not None:
            self.session.refresh(project)
        managed_assets = (
            self.session.query(ManagedAsset)
            .filter(ManagedAsset.product_id == product.product_id)
            .order_by(ManagedAsset.path.asc())
            .all()
        )
        for asset in managed_assets:
            self.session.refresh(asset)
        return ProductResponse.model_validate(
            {
                "product_id": product.product_id,
                "org_id": product.org_id,
                "key": product.key,
                "name": product.name,
                "description": product.description,
                "status": product.status,
                "baseline_channel": product.baseline_channel,
                "standards_pack_key": product.standards_pack_key,
                "standards_pack_version": product.standards_pack_version,
                "agent_core_version": product.agent_core_version,
                "execution_profile": product.execution_profile,
                "component_root_node_id": product.component_root_node_id,
                "manifest_schema_version": product.manifest_schema_version,
                "setup_state": product.setup_state,
                "setup_diagnostics": product.setup_diagnostics,
                "effective_config": product.effective_config,
                "operator_overrides": product.operator_overrides,
                "last_config_refresh_at": product.last_config_refresh_at,
                "last_accepted_config_at": product.last_accepted_config_at,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
                "primary_repo": repo,
                "primary_project": project,
                "managed_assets": managed_assets,
            }
        )

    def _resolve_primary_repo(self, product: Product) -> RepositoryBinding | None:
        if product.primary_repo_id is None:
            return None
        return self.session.get(RepositoryBinding, product.primary_repo_id)

    def _resolve_primary_project(self, product: Product) -> GitHubProjectMirror | None:
        if product.primary_project_id is None:
            return None
        return self.session.get(GitHubProjectMirror, product.primary_project_id)
