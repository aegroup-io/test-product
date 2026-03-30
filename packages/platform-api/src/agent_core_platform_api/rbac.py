from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from agent_core_platform_api.auth import UserContext, get_current_user
from agent_core_platform_api.db import get_session
from agent_core_platform_api.models import FeatureFlag, Permission, Role, role_feature_flags, role_permissions


PERM_ORG_READ = "org.read"
PERM_ORG_MANAGE = "org.manage"
PERM_ORG_MEMBERS_READ = "org.members.read"
PERM_ORG_MEMBERS_MANAGE = "org.members.manage"
PERM_PLATFORM_READ = "platform.read"
PERM_PLATFORM_MANAGE = "platform.manage"
PERM_REPO_READ = "repo.read"
PERM_REPO_MANAGE = "repo.manage"
PERM_REPO_DELETE = "repo.delete"
PERM_AI_READ = "ai.read"
PERM_AI_MANAGE = "ai.manage"
PERM_OBSERVABILITY_READ = "observability.read"
PERM_WORKER_MANAGE = "worker.manage"
RBAC_ADMIN_ROLE_SLUGS = frozenset({"admin", "org_admin"})


@dataclass(frozen=True)
class PermissionContext:
    user: UserContext
    roles: list[str]
    permissions: set[str]
    feature_flags: set[str]

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def has_any(self, permissions: Iterable[str]) -> bool:
        return any(permission in self.permissions for permission in permissions)


class RBACStore(Protocol):
    def list_permissions(self, session: Session) -> list[Permission]:
        ...

    def list_feature_flags(self, session: Session) -> list[FeatureFlag]:
        ...

    def list_roles(self, session: Session) -> list[Role]:
        ...

    def get_permissions_for_roles(self, session: Session, role_slugs: list[str]) -> set[str]:
        ...

    def get_feature_flags_for_roles(self, session: Session, role_slugs: list[str]) -> set[str]:
        ...

    def get_role(self, session: Session, role_id) -> Role | None:
        ...

    def set_role_permissions(self, session: Session, *, role: Role, permission_keys: list[str]) -> Role:
        ...

    def set_role_feature_flags(self, session: Session, *, role: Role, feature_flag_keys: list[str]) -> Role:
        ...


class DatabaseRBACStore:
    def list_permissions(self, session: Session) -> list[Permission]:
        return session.execute(select(Permission).order_by(Permission.key)).scalars().all()

    def list_feature_flags(self, session: Session) -> list[FeatureFlag]:
        return session.execute(select(FeatureFlag).order_by(FeatureFlag.key)).scalars().all()

    def list_roles(self, session: Session) -> list[Role]:
        return (
            session.execute(
                select(Role)
                .options(selectinload(Role.permissions), selectinload(Role.feature_flags))
                .order_by(Role.slug)
            )
            .scalars()
            .all()
        )

    def get_permissions_for_roles(self, session: Session, role_slugs: list[str]) -> set[str]:
        if not role_slugs:
            return set()
        return set(
            session.execute(
                select(Permission.key)
                .join(role_permissions, Permission.permission_id == role_permissions.c.permission_id)
                .join(Role, Role.role_id == role_permissions.c.role_id)
                .where(Role.slug.in_(role_slugs))
            )
            .scalars()
            .all()
        )

    def get_feature_flags_for_roles(self, session: Session, role_slugs: list[str]) -> set[str]:
        if not role_slugs:
            return set()
        return set(
            session.execute(
                select(FeatureFlag.key)
                .join(role_feature_flags, FeatureFlag.feature_flag_id == role_feature_flags.c.feature_flag_id)
                .join(Role, Role.role_id == role_feature_flags.c.role_id)
                .where(Role.slug.in_(role_slugs))
            )
            .scalars()
            .all()
        )

    def get_role(self, session: Session, role_id) -> Role | None:
        return (
            session.execute(
                select(Role)
                .options(selectinload(Role.permissions), selectinload(Role.feature_flags))
                .where(Role.role_id == role_id)
            )
            .scalar_one_or_none()
        )

    def set_role_permissions(self, session: Session, *, role: Role, permission_keys: list[str]) -> Role:
        keys = list(dict.fromkeys(permission_keys))
        permissions = session.execute(select(Permission).where(Permission.key.in_(keys))).scalars().all()
        if len(permissions) != len(keys):
            raise ValueError("Unknown permission keys")
        role.permissions = permissions
        session.commit()
        return self.get_role(session, role.role_id) or role

    def set_role_feature_flags(self, session: Session, *, role: Role, feature_flag_keys: list[str]) -> Role:
        keys = list(dict.fromkeys(feature_flag_keys))
        feature_flags = session.execute(select(FeatureFlag).where(FeatureFlag.key.in_(keys))).scalars().all()
        if len(feature_flags) != len(keys):
            raise ValueError("Unknown feature flag keys")
        role.feature_flags = feature_flags
        session.commit()
        return self.get_role(session, role.role_id) or role


def get_rbac_store() -> RBACStore:
    return DatabaseRBACStore()


def is_rbac_admin(context: PermissionContext) -> bool:
    return context.has(PERM_PLATFORM_MANAGE) or bool(set(context.roles).intersection(RBAC_ADMIN_ROLE_SLUGS))


def get_permission_context(
    session: Session = Depends(get_session),
    current_user: UserContext = Depends(get_current_user),
    rbac_store: RBACStore = Depends(get_rbac_store),
) -> PermissionContext:
    role_slugs = sorted(current_user.roles)
    permissions = rbac_store.get_permissions_for_roles(session, role_slugs)
    feature_flags = rbac_store.get_feature_flags_for_roles(session, role_slugs)
    return PermissionContext(
        user=current_user,
        roles=role_slugs,
        permissions=permissions,
        feature_flags=feature_flags,
    )
