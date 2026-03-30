from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.models import FeatureFlag, OrgMembership, Organization, Permission, Role
from agent_core_platform_api.rbac import (
    PERM_AI_MANAGE,
    PERM_AI_READ,
    PERM_OBSERVABILITY_READ,
    PERM_ORG_MANAGE,
    PERM_ORG_MEMBERS_MANAGE,
    PERM_ORG_MEMBERS_READ,
    PERM_ORG_READ,
    PERM_PLATFORM_MANAGE,
    PERM_PLATFORM_READ,
    PERM_REPO_DELETE,
    PERM_REPO_MANAGE,
    PERM_REPO_READ,
    PERM_WORKER_MANAGE,
)


PERMISSION_CATALOG = (
    (PERM_ORG_READ, "Read organization metadata and current org context", "org"),
    (PERM_ORG_MANAGE, "Manage organization metadata", "org"),
    (PERM_ORG_MEMBERS_READ, "Read organization members", "org"),
    (PERM_ORG_MEMBERS_MANAGE, "Add or remove organization members", "org"),
    (PERM_PLATFORM_READ, "Read shared platform configuration and secrets metadata", "platform"),
    (PERM_PLATFORM_MANAGE, "Manage shared platform configuration, secrets, and RBAC", "platform"),
    (PERM_REPO_READ, "View workspace Git repositories and their organization mappings", "repo"),
    (PERM_REPO_MANAGE, "Manage workspace Git repositories and repository mappings", "repo"),
    (PERM_REPO_DELETE, "Archive workspace Git repositories when no active products depend on them", "repo"),
    (PERM_AI_READ, "Read shared AI registry and orchestration metadata", "ai"),
    (PERM_AI_MANAGE, "Manage shared AI registry and orchestration metadata", "ai"),
    (PERM_OBSERVABILITY_READ, "Read shared observability and platform metrics", "observability"),
    (PERM_WORKER_MANAGE, "Enqueue shared worker jobs", "worker"),
)

FEATURE_FLAG_CATALOG = (
    ("agent.chat", "Enable assistant chat surfaces", "ai", True),
    ("agent.orchestration", "Enable orchestration-oriented agent workflows", "ai", False),
    ("settings.advanced", "Enable advanced platform settings pages", "platform", False),
)

ROLE_DEFINITIONS = {
    "admin": {
        "name": "Admin",
        "description": "Full platform administration access.",
        "permissions": [item[0] for item in PERMISSION_CATALOG],
        "feature_flags": [item[0] for item in FEATURE_FLAG_CATALOG],
    },
    "org_admin": {
        "name": "Org Admin",
        "description": "Organization-level administration and platform configuration.",
        "permissions": [item[0] for item in PERMISSION_CATALOG],
        "feature_flags": [item[0] for item in FEATURE_FLAG_CATALOG],
    },
    "analyst": {
        "name": "Analyst",
        "description": "Read baseline platform, AI, and observability features.",
        "permissions": [
            PERM_ORG_READ,
            PERM_ORG_MEMBERS_READ,
            PERM_PLATFORM_READ,
            PERM_REPO_READ,
            PERM_AI_READ,
            PERM_OBSERVABILITY_READ,
        ],
        "feature_flags": ["agent.chat"],
    },
    "viewer": {
        "name": "Viewer",
        "description": "Read-only baseline access.",
        "permissions": [
            PERM_ORG_READ,
            PERM_PLATFORM_READ,
            PERM_REPO_READ,
            PERM_AI_READ,
            PERM_OBSERVABILITY_READ,
        ],
        "feature_flags": [],
    },
    "worker": {
        "name": "Worker",
        "description": "Internal service role for runner launch, handshake, and heartbeat callbacks.",
        "permissions": [
            PERM_WORKER_MANAGE,
        ],
        "feature_flags": [],
    },
}


def _ensure_permissions(session: Session) -> dict[str, Permission]:
    permissions_by_key = {
        permission.key: permission
        for permission in session.execute(select(Permission)).scalars().all()
    }
    for key, description, category in PERMISSION_CATALOG:
        permission = permissions_by_key.get(key)
        if permission is None:
            permission = Permission(key=key, description=description, category=category)
            session.add(permission)
            permissions_by_key[key] = permission
        else:
            permission.description = description
            permission.category = category
    session.flush()
    return permissions_by_key


def _ensure_feature_flags(session: Session) -> dict[str, FeatureFlag]:
    flags_by_key = {
        flag.key: flag
        for flag in session.execute(select(FeatureFlag)).scalars().all()
    }
    for key, description, category, is_default in FEATURE_FLAG_CATALOG:
        feature_flag = flags_by_key.get(key)
        if feature_flag is None:
            feature_flag = FeatureFlag(
                key=key,
                description=description,
                category=category,
                is_default=is_default,
            )
            session.add(feature_flag)
            flags_by_key[key] = feature_flag
        else:
            feature_flag.description = description
            feature_flag.category = category
            feature_flag.is_default = is_default
    session.flush()
    return flags_by_key


def _ensure_roles(
    session: Session,
    permissions_by_key: dict[str, Permission],
    flags_by_key: dict[str, FeatureFlag],
) -> None:
    existing_roles = {role.slug: role for role in session.execute(select(Role)).scalars().all()}
    for slug, definition in ROLE_DEFINITIONS.items():
        role = existing_roles.get(slug)
        if role is None:
            role = Role(slug=slug, name=definition["name"], description=definition["description"], is_system=True)
            session.add(role)
        role.name = definition["name"]
        role.description = definition["description"]
        role.permissions = [permissions_by_key[key] for key in definition["permissions"]]
        role.feature_flags = [flags_by_key[key] for key in definition["feature_flags"]]
    session.flush()


def _ensure_rbac_catalog(session: Session) -> None:
    permissions_by_key = _ensure_permissions(session)
    flags_by_key = _ensure_feature_flags(session)
    _ensure_roles(session, permissions_by_key, flags_by_key)


def _ensure_default_org(session: Session, *, name: str, slug: str) -> Organization:
    org = session.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()
    if org is None:
        org = Organization(name=name, slug=slug)
        session.add(org)
        session.flush()
    else:
        org.name = name
    return org


def _ensure_dev_membership(
    session: Session,
    org: Organization,
    *,
    dev_user_id: str,
    dev_username: str,
) -> None:
    membership = session.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org.org_id,
            OrgMembership.user_id == dev_user_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = OrgMembership(
            org_id=org.org_id,
            user_id=dev_user_id,
            email=dev_username,
            display_name="Local Developer",
            is_active=True,
            is_default=True,
        )
        session.add(membership)
        return
    membership.email = dev_username
    membership.display_name = "Local Developer"
    membership.is_active = True
    membership.is_default = True


def seed_baseline(
    session: Session,
    *,
    initial_org_name: str | None = None,
    initial_org_slug: str | None = None,
    dev_user_id: str | None = None,
    dev_username: str | None = None,
    commit: bool = True,
) -> None:
    settings = get_settings()
    _ensure_rbac_catalog(session)
    default_org = _ensure_default_org(
        session,
        name=initial_org_name or settings.initial_org_name,
        slug=initial_org_slug or settings.initial_org_slug,
    )
    _ensure_dev_membership(
        session,
        default_org,
        dev_user_id=dev_user_id or settings.dev_user_id,
        dev_username=dev_username or settings.dev_username,
    )
    if commit:
        session.commit()
    else:
        session.flush()


def ensure_runtime_state(
    session: Session,
    *,
    initial_org_slug: str | None = None,
    dev_user_id: str | None = None,
    dev_username: str | None = None,
    commit: bool = True,
) -> None:
    settings = get_settings()
    _ensure_rbac_catalog(session)
    slug = initial_org_slug or settings.initial_org_slug
    org = session.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()
    if org is None:
        raise RuntimeError(f"Configured default organization is missing: {slug}")
    _ensure_dev_membership(
        session,
        org,
        dev_user_id=dev_user_id or settings.dev_user_id,
        dev_username=dev_username or settings.dev_username,
    )
    if commit:
        session.commit()
    else:
        session.flush()
