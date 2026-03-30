from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    Uuid,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from agent_core_platform_api.db import Base


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid(as_uuid=True), ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permissions.permission_id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


role_feature_flags = Table(
    "role_feature_flags",
    Base.metadata,
    Column("role_id", Uuid(as_uuid=True), ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True),
    Column(
        "feature_flag_id",
        Uuid(as_uuid=True),
        ForeignKey("feature_flags.feature_flag_id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (Index("ix_organizations_slug", "slug", unique=True),)

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    documentation_visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="shared")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_memberships_org_user"),
        Index("ix_org_memberships_org_id", "org_id"),
        Index("ix_org_memberships_user_id", "user_id"),
        Index("ix_org_memberships_active", "org_id", "is_active"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIProvider(Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        Index("ix_ai_providers_key", "key", unique=True),
        Index("ix_ai_providers_type", "type"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    compliance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    models: Mapped[list["AIModel"]] = relationship("AIModel", back_populates="provider")


class AIModel(Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        Index("ix_ai_models_key", "key", unique=True),
        Index("ix_ai_models_provider_id", "provider_id"),
        Index("ix_ai_models_default_workload", "default_workload"),
        Index("ix_ai_models_active_chat", "is_active", "can_chat"),
    )

    model_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_providers.provider_id", ondelete="RESTRICT"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_model_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    can_embed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_rerank: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_chat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_audio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_workload: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    restricted_content_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    context_window_tokens: Mapped[int | None] = mapped_column(nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    cost: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    compliance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    provider: Mapped[AIProvider] = relationship("AIProvider", back_populates="models")


class AIAgent(Base):
    __tablename__ = "ai_agents"
    __table_args__ = (
        Index("ix_ai_agents_key", "key", unique=True),
        Index("ix_ai_agents_is_active", "is_active"),
        Index("ix_ai_agents_default_model_id", "default_model_id"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tool_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_models.model_id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    default_model: Mapped["AIModel | None"] = relationship("AIModel")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (Index("ix_permissions_key", "key", unique=True),)

    permission_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (Index("ix_feature_flags_key", "key", unique=True),)

    feature_flag_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("ix_roles_slug", "slug", unique=True),)

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        order_by="Permission.key",
    )
    feature_flags: Mapped[list[FeatureFlag]] = relationship(
        "FeatureFlag",
        secondary=role_feature_flags,
        lazy="selectin",
        order_by="FeatureFlag.key",
    )


class Secret(Base):
    __tablename__ = "secrets"
    __table_args__ = (
        Index("ix_secrets_key", "key", unique=True),
        Index("ix_secrets_kind", "kind"),
    )

    secret_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(128), nullable=False, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    value_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def has_value(self) -> bool:
        return bool(self.value_ciphertext)


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "key", name="uq_settings_scope_key"),
        Index("ix_settings_scope", "scope_type", "scope_id"),
    )

    setting_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkspaceRepo(Base):
    __tablename__ = "workspace_repositories"
    __table_args__ = (
        UniqueConstraint("github_owner", "github_repo", name="uq_workspace_repositories_github"),
        Index("ix_workspace_repositories_org_id", "org_id"),
        Index("ix_workspace_repositories_archived_at", "archived_at"),
    )

    repo_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    github_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    github_repo: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    default_branch: Mapped[str] = mapped_column(String(128), nullable=False)
    clone_url: Mapped[str] = mapped_column(String(255), nullable=False)
    git_auth_secret_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("secrets.secret_id", ondelete="RESTRICT"),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship("Organization")
    git_auth_secret: Mapped[Secret] = relationship("Secret")
    org_mappings: Mapped[list["WorkspaceRepoOrgMapping"]] = relationship(
        "WorkspaceRepoOrgMapping",
        back_populates="repo",
        cascade="all, delete-orphan",
    )


class WorkspaceRepoOrgMapping(Base):
    __tablename__ = "workspace_repo_org_mappings"
    __table_args__ = (Index("ix_workspace_repo_org_mappings_org_id", "org_id"),)

    repo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspace_repositories.repo_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    repo: Mapped[WorkspaceRepo] = relationship("WorkspaceRepo", back_populates="org_mappings")
    organization: Mapped[Organization] = relationship("Organization")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("org_id", "key", name="uq_products_org_key"),
        Index("ix_products_org_id", "org_id"),
        Index("ix_products_status", "status"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Draft")
    primary_repo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    primary_project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    baseline_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    standards_pack_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    standards_pack_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_core_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    component_root_node_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    manifest_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_state: Mapped[str] = mapped_column(String(32), nullable=False, default="setup-needed")
    setup_diagnostics: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    effective_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    operator_overrides: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_config_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accepted_config_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship("Organization")
    repositories: Mapped[list["RepositoryBinding"]] = relationship(
        "RepositoryBinding",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    project_mirror: Mapped["GitHubProjectMirror | None"] = relationship(
        "GitHubProjectMirror",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )
    seed_jobs: Mapped[list["ProductSeedJob"]] = relationship(
        "ProductSeedJob",
        back_populates="product",
    )
    managed_assets: Mapped[list["ManagedAsset"]] = relationship(
        "ManagedAsset",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    standards_overrides: Mapped[list["ProductStandardsOverride"]] = relationship(
        "ProductStandardsOverride",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    standards_upgrade_runs: Mapped[list["StandardsUpgradeRun"]] = relationship(
        "StandardsUpgradeRun",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    standards_follow_up_items: Mapped[list["StandardsFollowUpItem"]] = relationship(
        "StandardsFollowUpItem",
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductSeedJob(Base):
    __tablename__ = "product_seed_jobs"
    __table_args__ = (
        Index("ix_product_seed_jobs_org_id", "org_id"),
        Index("ix_product_seed_jobs_product_id", "product_id"),
        Index("ix_product_seed_jobs_status", "status"),
    )

    seed_job_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.org_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Pending")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    progress_payload: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    error_payload: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    audit_payload: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    rendered_file_paths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    repo_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    project_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    setup_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    setup_diagnostics: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped[Organization] = relationship("Organization")
    product: Mapped["Product | None"] = relationship("Product", back_populates="seed_jobs")


class RepositoryBinding(Base):
    __tablename__ = "repository_bindings"
    __table_args__ = (
        UniqueConstraint("product_id", "owner", "name", name="uq_repository_bindings_product_repo"),
        Index("ix_repository_bindings_github_repository_node_id", "github_repository_node_id", unique=True),
        Index("ix_repository_bindings_product_id", "product_id"),
    )

    repo_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    github_repository_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seed_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    adoption_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="repositories")
    work_items: Mapped[list["WorkItem"]] = relationship(
        "WorkItem",
        back_populates="repo",
        cascade="all, delete-orphan",
    )
    pull_requests: Mapped[list["PullRequestMirror"]] = relationship(
        "PullRequestMirror",
        back_populates="repo",
        cascade="all, delete-orphan",
    )
    standards_upgrade_runs: Mapped[list["StandardsUpgradeRun"]] = relationship(
        "StandardsUpgradeRun",
        back_populates="repo",
    )
    standards_follow_up_items: Mapped[list["StandardsFollowUpItem"]] = relationship(
        "StandardsFollowUpItem",
        back_populates="repo",
    )


class GitHubProjectMirror(Base):
    __tablename__ = "github_project_mirrors"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_github_project_mirrors_product"),
        Index("ix_github_project_mirrors_github_project_node_id", "github_project_node_id", unique=True),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    github_project_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status_field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status_options: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mirror_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="project_mirror")
    work_items: Mapped[list["WorkItem"]] = relationship("WorkItem", back_populates="project")
    fields: Mapped[list["GitHubProjectFieldMirror"]] = relationship(
        "GitHubProjectFieldMirror",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    items: Mapped[list["GitHubProjectItemMirror"]] = relationship(
        "GitHubProjectItemMirror",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        UniqueConstraint("repo_id", "issue_number", name="uq_work_items_repo_issue_number"),
        Index("ix_work_items_github_issue_node_id", "github_issue_node_id", unique=True),
        Index("ix_work_items_project_id", "project_id"),
        Index("ix_work_items_status", "status"),
    )

    work_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_bindings.repo_id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("github_project_mirrors.project_id", ondelete="SET NULL"),
        nullable=True,
    )
    github_issue_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="Triage")
    status_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    assignees: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dependency_state: Mapped[str] = mapped_column(String(32), nullable=False, default="clear")
    dependency_details: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    priority_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    linked_prs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    eligibility_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    handoff_status: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    requires_repair: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repair_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repo: Mapped[RepositoryBinding] = relationship("RepositoryBinding", back_populates="work_items")
    project: Mapped["GitHubProjectMirror | None"] = relationship("GitHubProjectMirror", back_populates="work_items")
    lanes: Mapped[list["OrchestrationLane"]] = relationship(
        "OrchestrationLane",
        back_populates="work_item",
        cascade="all, delete-orphan",
    )
    project_items: Mapped[list["GitHubProjectItemMirror"]] = relationship(
        "GitHubProjectItemMirror",
        back_populates="work_item",
    )


class PullRequestMirror(Base):
    __tablename__ = "pull_request_mirrors"
    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_pull_request_mirrors_repo_number"),
        Index("ix_pull_request_mirrors_github_pr_node_id", "github_pr_node_id", unique=True),
        Index("ix_pull_request_mirrors_state", "state"),
    )

    pull_request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_bindings.repo_id", ondelete="CASCADE"),
        nullable=False,
    )
    github_pr_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    head_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checks_rollup: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    review_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merge_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_work_item_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repo: Mapped[RepositoryBinding] = relationship("RepositoryBinding", back_populates="pull_requests")
    project_items: Mapped[list["GitHubProjectItemMirror"]] = relationship(
        "GitHubProjectItemMirror",
        back_populates="pull_request",
    )


class GitHubProjectFieldMirror(Base):
    __tablename__ = "github_project_field_mirrors"
    __table_args__ = (
        UniqueConstraint("project_id", "github_project_field_node_id", name="uq_project_field_mirrors_project_node"),
        Index("ix_project_field_mirrors_github_project_field_node_id", "github_project_field_node_id", unique=True),
    )

    project_field_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("github_project_mirrors.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    github_project_field_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False)
    settings_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[GitHubProjectMirror] = relationship("GitHubProjectMirror", back_populates="fields")
    options: Mapped[list["GitHubProjectFieldOptionMirror"]] = relationship(
        "GitHubProjectFieldOptionMirror",
        back_populates="project_field",
        cascade="all, delete-orphan",
    )


class GitHubProjectFieldOptionMirror(Base):
    __tablename__ = "github_project_field_option_mirrors"
    __table_args__ = (
        UniqueConstraint("project_field_id", "github_project_option_id", name="uq_project_field_option_mirrors_shape"),
        Index("ix_project_field_option_mirrors_github_project_option_id", "github_project_option_id"),
    )

    project_field_option_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_field_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("github_project_field_mirrors.project_field_id", ondelete="CASCADE"),
        nullable=False,
    )
    github_project_option_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color: Mapped[str | None] = mapped_column(String(64), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project_field: Mapped[GitHubProjectFieldMirror] = relationship("GitHubProjectFieldMirror", back_populates="options")


class GitHubProjectItemMirror(Base):
    __tablename__ = "github_project_item_mirrors"
    __table_args__ = (
        Index("ix_project_item_mirrors_github_project_item_node_id", "github_project_item_node_id", unique=True),
        Index("ix_project_item_mirrors_github_content_node_id", "github_content_node_id"),
    )

    project_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("github_project_mirrors.project_id", ondelete="CASCADE"),
        nullable=False,
    )
    github_project_item_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    github_content_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("work_items.work_item_id", ondelete="SET NULL"),
        nullable=True,
    )
    pull_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pull_request_mirrors.pull_request_id", ondelete="SET NULL"),
        nullable=True,
    )
    status_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    field_values_payload: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[GitHubProjectMirror] = relationship("GitHubProjectMirror", back_populates="items")
    work_item: Mapped["WorkItem | None"] = relationship("WorkItem", back_populates="project_items")
    pull_request: Mapped["PullRequestMirror | None"] = relationship("PullRequestMirror", back_populates="project_items")


ACTIVE_LANE_OWNERSHIP_STATES = (
    "Queued",
    "Claimed",
    "Provisioning",
    "Running",
    "AwaitingApproval",
    "AwaitingGitHub",
    "RetryPending",
)
_ACTIVE_LANE_OWNERSHIP_PREDICATE = text(
    "state IN ('Queued', 'Claimed', 'Provisioning', 'Running', 'AwaitingApproval', 'AwaitingGitHub', 'RetryPending')"
)


class OrchestrationLane(Base):
    __tablename__ = "orchestration_lanes"
    __table_args__ = (
        UniqueConstraint("work_item_id", "attempt", name="uq_orchestration_lanes_work_item_attempt"),
        Index("ix_orchestration_lanes_product_id", "product_id"),
        Index("ix_orchestration_lanes_repo_id", "repo_id"),
        Index("ix_orchestration_lanes_work_item_state", "work_item_id", "state"),
        Index(
            "ix_orchestration_lanes_active_work_item",
            "work_item_id",
            unique=True,
            sqlite_where=_ACTIVE_LANE_OWNERSHIP_PREDICATE,
            postgresql_where=_ACTIVE_LANE_OWNERSHIP_PREDICATE,
        ),
    )

    lane_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_bindings.repo_id", ondelete="CASCADE"),
        nullable=False,
    )
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("work_items.work_item_id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="Queued")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_environment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    agent_session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    retry_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handoff_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product")
    repo: Mapped[RepositoryBinding] = relationship("RepositoryBinding")
    work_item: Mapped[WorkItem] = relationship("WorkItem", back_populates="lanes")
    execution_environment: Mapped["ExecutionEnvironment | None"] = relationship(
        "ExecutionEnvironment",
        back_populates="lane",
        uselist=False,
        cascade="all, delete-orphan",
    )
    agent_session: Mapped["AgentSession | None"] = relationship(
        "AgentSession",
        back_populates="lane",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ExecutionEnvironment(Base):
    __tablename__ = "execution_environments"
    __table_args__ = (
        Index("ix_execution_environments_lane_id", "lane_id", unique=True),
        Index("ix_execution_environments_status", "status"),
    )

    execution_environment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lane_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orchestration_lanes.lane_id", ondelete="CASCADE"),
        nullable=False,
    )
    runtime_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    container_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    workspace_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    log_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cache_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checkout_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secret_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lane: Mapped[OrchestrationLane] = relationship("OrchestrationLane", back_populates="execution_environment")


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_lane_id", "lane_id", unique=True),
        Index("ix_agent_sessions_requires_human_input", "requires_human_input"),
        Index("ix_agent_sessions_status", "status"),
    )

    agent_session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lane_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orchestration_lanes.lane_id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runner_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runner_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="launching")
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    environment_identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_event: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wait_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    continuation_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    launch_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_human_input: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    lane: Mapped[OrchestrationLane] = relationship("OrchestrationLane", back_populates="agent_session")
    events: Mapped[list["AgentSessionEvent"]] = relationship(
        "AgentSessionEvent",
        back_populates="agent_session",
        cascade="all, delete-orphan",
        order_by="AgentSessionEvent.sequence.asc()",
    )


class AgentSessionEvent(Base):
    __tablename__ = "agent_session_events"
    __table_args__ = (
        UniqueConstraint("agent_session_id", "sequence", name="uq_agent_session_events_session_sequence"),
        Index("ix_agent_session_events_lane_id", "lane_id"),
        Index("ix_agent_session_events_event_type", "event_type"),
    )

    agent_session_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_sessions.agent_session_id", ondelete="CASCADE"),
        nullable=False,
    )
    lane_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orchestration_lanes.lane_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    input_tokens_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent_session: Mapped[AgentSession] = relationship("AgentSession", back_populates="events")
    lane: Mapped[OrchestrationLane] = relationship("OrchestrationLane")


class ManagedAsset(Base):
    __tablename__ = "managed_assets"
    __table_args__ = (
        UniqueConstraint("product_id", "path", name="uq_managed_assets_product_path"),
        Index("ix_managed_assets_drift_status", "drift_status"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    management_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    upstream_bundle_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    drift_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="managed_assets")


class StandardsPack(Base):
    __tablename__ = "standards_packs"
    __table_args__ = (
        UniqueConstraint("key", "channel", "version", name="uq_standards_packs_identity"),
        Index("ix_standards_packs_channel", "channel"),
    )

    standards_pack_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_bundle: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    assets: Mapped[list["StandardsPackAsset"]] = relationship(
        "StandardsPackAsset",
        back_populates="standards_pack",
        cascade="all, delete-orphan",
    )
    upgrade_runs: Mapped[list["StandardsUpgradeRun"]] = relationship(
        "StandardsUpgradeRun",
        back_populates="standards_pack",
        cascade="all, delete-orphan",
    )


class StandardsPackAsset(Base):
    __tablename__ = "standards_pack_assets"
    __table_args__ = (
        UniqueConstraint("standards_pack_id", "path", name="uq_standards_pack_assets_path"),
        Index("ix_standards_pack_assets_mode", "default_mode"),
    )

    standards_pack_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    standards_pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standards_packs.standards_pack_id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    default_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    ownership_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    standards_pack: Mapped[StandardsPack] = relationship("StandardsPack", back_populates="assets")


class ProductStandardsOverride(Base):
    __tablename__ = "product_standards_overrides"
    __table_args__ = (
        UniqueConstraint("product_id", "path", name="uq_product_standards_overrides_product_path"),
        Index("ix_product_standards_overrides_deferred", "is_deferred"),
    )

    standards_override_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    override_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="standards_overrides")


class StandardsUpgradeRun(Base):
    __tablename__ = "standards_upgrade_runs"
    __table_args__ = (
        Index("ix_standards_upgrade_runs_product_id", "product_id"),
        Index("ix_standards_upgrade_runs_outcome_status", "outcome_status"),
    )

    standards_upgrade_run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_bindings.repo_id", ondelete="SET NULL"),
        nullable=True,
    )
    standards_pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standards_packs.standards_pack_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_bundle: Mapped[str] = mapped_column(String(255), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome_status: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product", back_populates="standards_upgrade_runs")
    repo: Mapped["RepositoryBinding | None"] = relationship("RepositoryBinding", back_populates="standards_upgrade_runs")
    standards_pack: Mapped[StandardsPack] = relationship("StandardsPack", back_populates="upgrade_runs")
    assets: Mapped[list["StandardsUpgradeAsset"]] = relationship(
        "StandardsUpgradeAsset",
        back_populates="upgrade_run",
        cascade="all, delete-orphan",
    )
    follow_up_items: Mapped[list["StandardsFollowUpItem"]] = relationship(
        "StandardsFollowUpItem",
        back_populates="upgrade_run",
        cascade="all, delete-orphan",
    )


class StandardsUpgradeAsset(Base):
    __tablename__ = "standards_upgrade_assets"
    __table_args__ = (
        UniqueConstraint("standards_upgrade_run_id", "path", name="uq_standards_upgrade_assets_run_path"),
        Index("ix_standards_upgrade_assets_action", "action"),
    )

    standards_upgrade_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    standards_upgrade_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standards_upgrade_runs.standards_upgrade_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    management_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    drift_status: Mapped[str] = mapped_column(String(64), nullable=False)
    patch_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    upgrade_run: Mapped[StandardsUpgradeRun] = relationship("StandardsUpgradeRun", back_populates="assets")


class StandardsFollowUpItem(Base):
    __tablename__ = "standards_follow_up_items"
    __table_args__ = (
        Index("ix_standards_follow_up_items_status", "status"),
        Index("ix_standards_follow_up_items_product_path", "product_id", "path"),
    )

    standards_follow_up_item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    standards_upgrade_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("standards_upgrade_runs.standards_upgrade_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_bindings.repo_id", ondelete="SET NULL"),
        nullable=True,
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    upgrade_run: Mapped[StandardsUpgradeRun] = relationship("StandardsUpgradeRun", back_populates="follow_up_items")
    product: Mapped[Product] = relationship("Product", back_populates="standards_follow_up_items")
    repo: Mapped["RepositoryBinding | None"] = relationship("RepositoryBinding", back_populates="standards_follow_up_items")


class ComponentNode(Base):
    __tablename__ = "component_nodes"
    __table_args__ = (
        UniqueConstraint("product_id", "key", name="uq_component_nodes_product_key"),
        Index("ix_component_nodes_type", "type"),
        Index("ix_component_nodes_status", "status"),
    )

    component_node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    product: Mapped[Product] = relationship("Product")
    outgoing_edges: Mapped[list["ComponentEdge"]] = relationship(
        "ComponentEdge",
        foreign_keys="ComponentEdge.from_node_id",
        back_populates="from_node",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["ComponentEdge"]] = relationship(
        "ComponentEdge",
        foreign_keys="ComponentEdge.to_node_id",
        back_populates="to_node",
        cascade="all, delete-orphan",
    )


class ComponentEdge(Base):
    __tablename__ = "component_edges"
    __table_args__ = (
        UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "relationship",
            "source_kind",
            name="uq_component_edges_shape",
        ),
        Index("ix_component_edges_to_node_id", "to_node_id"),
    )

    component_edge_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("component_nodes.component_node_id", ondelete="CASCADE"),
        nullable=False,
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("component_nodes.component_node_id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column("relationship", String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    from_node: Mapped[ComponentNode] = relationship(
        "ComponentNode",
        foreign_keys=[from_node_id],
        back_populates="outgoing_edges",
    )
    to_node: Mapped[ComponentNode] = relationship(
        "ComponentNode",
        foreign_keys=[to_node_id],
        back_populates="incoming_edges",
    )


class OperationalSignal(Base):
    __tablename__ = "operational_signals"
    __table_args__ = (
        Index("ix_operational_signals_target", "target_kind", "target_id"),
        Index("ix_operational_signals_observed_at", "observed_at"),
    )

    signal_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_github_delivery_guid", "github_delivery_guid", unique=True),
        Index("ix_webhook_deliveries_status", "status"),
        Index("ix_webhook_deliveries_received_at", "received_at"),
    )

    delivery_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_delivery_guid: Mapped[str] = mapped_column(String(128), nullable=False)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    installation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
