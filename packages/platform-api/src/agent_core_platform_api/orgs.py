from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.models import OrgMembership, Organization


def get_org_by_slug(session: Session, *, slug: str) -> Organization | None:
    return session.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()


def get_org(session: Session, *, org_id: UUID) -> Organization | None:
    return session.get(Organization, org_id)


def list_orgs(session: Session) -> list[Organization]:
    return session.execute(select(Organization).order_by(Organization.name)).scalars().all()


def get_default_org(session: Session) -> Organization:
    org = get_org_by_slug(session, slug=get_settings().initial_org_slug)
    if org is None:
        raise RuntimeError("Default organization not found")
    return org


def get_default_org_for_user(session: Session, *, user_id: str) -> Organization:
    membership = session.execute(
        select(OrgMembership)
        .where(
            OrgMembership.user_id == user_id,
            OrgMembership.is_active.is_(True),
            OrgMembership.is_default.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if membership is not None:
        org = get_org(session, org_id=membership.org_id)
        if org is not None:
            return org

    org = session.execute(
        select(Organization)
        .join(OrgMembership, OrgMembership.org_id == Organization.org_id)
        .where(
            OrgMembership.user_id == user_id,
            OrgMembership.is_active.is_(True),
        )
        .order_by(Organization.name)
        .limit(1)
    ).scalar_one_or_none()
    if org is not None:
        return org

    return get_default_org(session)
