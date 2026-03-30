from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_core_platform_api.models import (
    AgentSession,
    ComponentEdge,
    ComponentNode,
    ExecutionEnvironment,
    GitHubProjectFieldMirror,
    GitHubProjectFieldOptionMirror,
    GitHubProjectItemMirror,
    GitHubProjectMirror,
    ManagedAsset,
    OperationalSignal,
    OrchestrationLane,
    PullRequestMirror,
    Product,
    ProductStandardsOverride,
    RepositoryBinding,
    StandardsFollowUpItem,
    StandardsPack,
    StandardsPackAsset,
    StandardsUpgradeAsset,
    StandardsUpgradeRun,
    WebhookDelivery,
    WorkItem,
)


class OrchaStateStore:
    """Thin persistence helpers for Orcha-owned durable control-plane state."""

    def __init__(self, session: Session):
        self.session = session

    def create_product(self, **kwargs) -> Product:
        return self._add(Product(**kwargs))

    def list_products(self, *, org_id=None) -> list[Product]:
        statement = select(Product).order_by(Product.key)
        if org_id is not None:
            statement = statement.where(Product.org_id == org_id)
        return list(self.session.execute(statement).scalars().all())

    def bind_repository(self, **kwargs) -> RepositoryBinding:
        return self._add(RepositoryBinding(**kwargs))

    def create_project_mirror(self, **kwargs) -> GitHubProjectMirror:
        return self._add(GitHubProjectMirror(**kwargs))

    def create_work_item(self, **kwargs) -> WorkItem:
        return self._add(WorkItem(**kwargs))

    def create_pull_request_mirror(self, **kwargs) -> PullRequestMirror:
        return self._add(PullRequestMirror(**kwargs))

    def create_project_field_mirror(self, **kwargs) -> GitHubProjectFieldMirror:
        return self._add(GitHubProjectFieldMirror(**kwargs))

    def create_project_field_option_mirror(self, **kwargs) -> GitHubProjectFieldOptionMirror:
        return self._add(GitHubProjectFieldOptionMirror(**kwargs))

    def create_project_item_mirror(self, **kwargs) -> GitHubProjectItemMirror:
        return self._add(GitHubProjectItemMirror(**kwargs))

    def create_lane(self, **kwargs) -> OrchestrationLane:
        return self._add(OrchestrationLane(**kwargs))

    def create_execution_environment(self, **kwargs) -> ExecutionEnvironment:
        return self._add(ExecutionEnvironment(**kwargs))

    def create_agent_session(self, **kwargs) -> AgentSession:
        return self._add(AgentSession(**kwargs))

    def create_managed_asset(self, **kwargs) -> ManagedAsset:
        return self._add(ManagedAsset(**kwargs))

    def create_standards_pack(self, **kwargs) -> StandardsPack:
        return self._add(StandardsPack(**kwargs))

    def create_standards_pack_asset(self, **kwargs) -> StandardsPackAsset:
        return self._add(StandardsPackAsset(**kwargs))

    def create_product_standards_override(self, **kwargs) -> ProductStandardsOverride:
        return self._add(ProductStandardsOverride(**kwargs))

    def create_standards_upgrade_run(self, **kwargs) -> StandardsUpgradeRun:
        return self._add(StandardsUpgradeRun(**kwargs))

    def create_standards_upgrade_asset(self, **kwargs) -> StandardsUpgradeAsset:
        return self._add(StandardsUpgradeAsset(**kwargs))

    def create_standards_follow_up_item(self, **kwargs) -> StandardsFollowUpItem:
        return self._add(StandardsFollowUpItem(**kwargs))

    def create_component_node(self, **kwargs) -> ComponentNode:
        return self._add(ComponentNode(**kwargs))

    def create_component_edge(self, **kwargs) -> ComponentEdge:
        if "relationship" in kwargs and "relationship_type" not in kwargs:
            kwargs["relationship_type"] = kwargs.pop("relationship")
        return self._add(ComponentEdge(**kwargs))

    def record_operational_signal(self, **kwargs) -> OperationalSignal:
        return self._add(OperationalSignal(**kwargs))

    def record_webhook_delivery(self, **kwargs) -> WebhookDelivery:
        return self._add(WebhookDelivery(**kwargs))

    def _add(self, instance):
        self.session.add(instance)
        self.session.flush()
        return instance
