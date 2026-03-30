from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent_core_platform_api import rbac
from agent_core_platform_api.db import get_session
from agent_core_platform_api.models import (
    Organization,
    Product,
    RepositoryBinding,
    Secret,
    WorkspaceRepo,
    WorkspaceRepoOrgMapping,
)
from agent_core_platform_api.secret_crypto import SecretCryptoError, decrypt_secret
from agent_core_platform_api.schemas import (
    BranchSummary,
    RepoBranchesRequest,
    RepoCreateRequest,
    RepoLookupItem,
    RepoLookupPermissions,
    RepoLookupRequest,
    RepoOrgMappingResponse,
    RepoResponse,
    RepoUpdateRequest,
)


router = APIRouter()

_PERM_REPO_READ = getattr(rbac, "PERM_REPO_READ", "repo.read")
_PERM_REPO_MANAGE = getattr(rbac, "PERM_REPO_MANAGE", "repo.manage")
_PERM_REPO_DELETE = getattr(rbac, "PERM_REPO_DELETE", "repo.delete")
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _ensure_repo_read(permissions: rbac.PermissionContext) -> None:
    if not permissions.has(_PERM_REPO_READ):
        raise HTTPException(status_code=403, detail="Git repository access denied")


def _ensure_repo_manage(permissions: rbac.PermissionContext) -> None:
    if not permissions.has(_PERM_REPO_MANAGE):
        raise HTTPException(status_code=403, detail="Git repository updates not permitted")


def _ensure_repo_delete(permissions: rbac.PermissionContext) -> None:
    if not permissions.has(_PERM_REPO_DELETE):
        raise HTTPException(status_code=403, detail="Git repository delete not permitted")


def _require_org(session: Session, org_id: UUID) -> Organization:
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _require_repo(session: Session, repo_id: UUID) -> WorkspaceRepo:
    repo = session.get(WorkspaceRepo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def _repo_org_ids(session: Session, repo_id: UUID) -> set[UUID]:
    mapped_ids = {
        org_id
        for (org_id,) in session.query(WorkspaceRepoOrgMapping.org_id)
        .filter(WorkspaceRepoOrgMapping.repo_id == repo_id)
        .all()
    }
    if mapped_ids:
        return mapped_ids
    repo = session.get(WorkspaceRepo, repo_id)
    if repo is not None:
        return {repo.org_id}
    return set()


def _normalize_org_ids(session: Session, requested_org_ids: list[UUID]) -> list[UUID]:
    org_ids: list[UUID] = []
    seen: set[UUID] = set()
    for org_id in requested_org_ids:
        if org_id in seen:
            continue
        _require_org(session, org_id)
        seen.add(org_id)
        org_ids.append(org_id)
    if not org_ids:
        raise HTTPException(status_code=400, detail="At least one organization is required")
    return org_ids


def _clone_url(owner: str, repo: str) -> str:
    return f"https://github.com/{owner}/{repo}.git"


def _validate_branch_name(name: str) -> None:
    branch_name = name.strip()
    if not branch_name:
        raise HTTPException(status_code=400, detail="default_branch is required")
    if _SHA_PATTERN.fullmatch(branch_name):
        raise HTTPException(status_code=400, detail="default_branch must be a branch name")


def _get_git_secret(session: Session, secret_id: UUID) -> Secret:
    secret = session.get(Secret, secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="Git auth secret not found")
    if secret.kind != "git_personal_access_token":
        raise HTTPException(status_code=400, detail="Git auth secret kind invalid")
    return secret


def _load_git_pat(secret: Secret) -> str:
    if not secret.value_ciphertext:
        raise HTTPException(status_code=409, detail="Git auth secret has no value")
    try:
        return decrypt_secret(secret.value_ciphertext)
    except SecretCryptoError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _rate_limited(response: httpx.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is not None and remaining.isdigit() and int(remaining) == 0:
        return True
    return "rate limit" in response.text.lower()


def _handle_github_error(response: httpx.Response, *, not_found_message: str | None = None) -> None:
    if response.status_code in (401, 403):
        if _rate_limited(response):
            raise HTTPException(status_code=429, detail="GitHub rate limit exceeded")
        raise HTTPException(status_code=403, detail="GitHub access denied")
    if response.status_code == 404 and not_found_message:
        raise HTTPException(status_code=400, detail=not_found_message)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)


def _matching_products(
    session: Session,
    *,
    github_owner: str,
    github_repo: str,
    org_ids: set[UUID] | None = None,
) -> list[tuple[UUID, UUID, str, str]]:
    if org_ids is not None and not org_ids:
        return []
    query = (
        session.query(Product.product_id, Product.org_id, Product.key, Product.name)
        .join(RepositoryBinding, RepositoryBinding.product_id == Product.product_id)
        .filter(
            Product.status != "Archived",
            func.lower(RepositoryBinding.owner) == github_owner.lower(),
            func.lower(RepositoryBinding.name) == github_repo.lower(),
        )
        .distinct()
        .order_by(Product.key.asc())
    )
    if org_ids is not None:
        query = query.filter(Product.org_id.in_(org_ids))
    return query.all()


def _build_repo_response(session: Session, repo: WorkspaceRepo) -> RepoResponse:
    rows = (
        session.query(Organization.org_id, Organization.name)
        .join(WorkspaceRepoOrgMapping, WorkspaceRepoOrgMapping.org_id == Organization.org_id)
        .filter(WorkspaceRepoOrgMapping.repo_id == repo.repo_id)
        .order_by(Organization.name.asc())
        .all()
    )
    if not rows:
        org = session.get(Organization, repo.org_id)
        rows = [(repo.org_id, org.name if org is not None else "Unknown")]
    org_ids = {org_id for org_id, _ in rows}
    matching_products = _matching_products(
        session,
        github_owner=repo.github_owner,
        github_repo=repo.github_repo,
        org_ids=org_ids,
    )
    counts_by_org = Counter(product_org_id for _, product_org_id, _, _ in matching_products)
    org_mappings = [
        RepoOrgMappingResponse(
            org_id=org_id,
            org_name=org_name,
            active_product_count=int(counts_by_org.get(org_id, 0)),
        )
        for org_id, org_name in rows
    ]
    return RepoResponse(
        repo_id=repo.repo_id,
        org_id=repo.org_id,
        key=repo.key,
        name=repo.name,
        provider=repo.provider,
        github_owner=repo.github_owner,
        github_repo=repo.github_repo,
        visibility=repo.visibility,
        default_branch=repo.default_branch,
        clone_url=repo.clone_url,
        git_auth_secret_id=repo.git_auth_secret_id,
        org_ids=[mapping.org_id for mapping in org_mappings],
        org_mappings=org_mappings,
        archived_at=repo.archived_at,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


@router.get("/orgs/{org_id}/repos", response_model=list[RepoResponse])
def list_org_repos(
    org_id: UUID,
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> list[RepoResponse]:
    _ensure_repo_read(permissions)
    _require_org(session, org_id)
    repo_ids = select(WorkspaceRepoOrgMapping.repo_id).where(WorkspaceRepoOrgMapping.org_id == org_id)
    query = session.query(WorkspaceRepo).filter(
        WorkspaceRepo.archived_at.is_(None),
        or_(WorkspaceRepo.repo_id.in_(repo_ids), WorkspaceRepo.org_id == org_id),
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                WorkspaceRepo.key.ilike(like),
                WorkspaceRepo.name.ilike(like),
                WorkspaceRepo.github_owner.ilike(like),
                WorkspaceRepo.github_repo.ilike(like),
            )
        )
    repos = query.order_by(WorkspaceRepo.key.asc()).all()
    return [_build_repo_response(session, repo) for repo in repos]


@router.get("/repos", response_model=list[RepoResponse])
def list_repos(
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> list[RepoResponse]:
    _ensure_repo_read(permissions)
    query = session.query(WorkspaceRepo).filter(WorkspaceRepo.archived_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                WorkspaceRepo.key.ilike(like),
                WorkspaceRepo.name.ilike(like),
                WorkspaceRepo.github_owner.ilike(like),
                WorkspaceRepo.github_repo.ilike(like),
            )
        )
    repos = query.order_by(WorkspaceRepo.key.asc()).all()
    return [_build_repo_response(session, repo) for repo in repos]


@router.get("/repos/{repo_id}", response_model=RepoResponse)
def get_repo(
    repo_id: UUID,
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> RepoResponse:
    _ensure_repo_read(permissions)
    repo = _require_repo(session, repo_id)
    return _build_repo_response(session, repo)


@router.post("/orgs/{org_id}/repos", response_model=RepoResponse, status_code=status.HTTP_201_CREATED)
def create_repo(
    org_id: UUID,
    payload: RepoCreateRequest,
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> RepoResponse:
    _ensure_repo_manage(permissions)
    _require_org(session, org_id)
    _get_git_secret(session, payload.git_auth_secret_id)
    _validate_branch_name(payload.default_branch)

    normalized_owner = payload.github_owner.strip().lower()
    normalized_repo = payload.github_repo.strip().lower()
    requested_org_ids = list(payload.org_ids)
    if org_id not in requested_org_ids:
        requested_org_ids.append(org_id)
    resolved_org_ids = _normalize_org_ids(session, requested_org_ids)

    existing_repo = (
        session.query(WorkspaceRepo)
        .filter(
            WorkspaceRepo.github_owner == normalized_owner,
            WorkspaceRepo.github_repo == normalized_repo,
        )
        .order_by(WorkspaceRepo.created_at.asc())
        .first()
    )
    if existing_repo is not None:
        persisted_org_ids = {
            mapped_org_id
            for (mapped_org_id,) in session.query(WorkspaceRepoOrgMapping.org_id)
            .filter(WorkspaceRepoOrgMapping.repo_id == existing_repo.repo_id)
            .all()
        }
        current_org_ids = _repo_org_ids(session, existing_repo.repo_id)
        target_org_ids = current_org_ids | set(resolved_org_ids)
        org_ids_to_add = target_org_ids - persisted_org_ids
        if not org_ids_to_add and existing_repo.archived_at is None:
            raise HTTPException(status_code=409, detail="Repo already exists")
        for add_org_id in org_ids_to_add:
            session.add(WorkspaceRepoOrgMapping(repo_id=existing_repo.repo_id, org_id=add_org_id))
        if existing_repo.archived_at is not None:
            existing_repo.archived_at = None
        session.commit()
        session.refresh(existing_repo)
        return _build_repo_response(session, existing_repo)

    repo = WorkspaceRepo(
        org_id=org_id,
        key=payload.key.strip(),
        name=payload.name.strip(),
        provider="github",
        github_owner=normalized_owner,
        github_repo=normalized_repo,
        visibility=payload.visibility.strip().lower(),
        default_branch=payload.default_branch.strip(),
        clone_url=_clone_url(normalized_owner, normalized_repo),
        git_auth_secret_id=payload.git_auth_secret_id,
    )
    session.add(repo)
    try:
        session.flush()
        for mapped_org_id in resolved_org_ids:
            session.add(WorkspaceRepoOrgMapping(repo_id=repo.repo_id, org_id=mapped_org_id))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Repo already exists") from exc
    session.refresh(repo)
    return _build_repo_response(session, repo)


@router.patch("/repos/{repo_id}", response_model=RepoResponse)
def update_repo(
    repo_id: UUID,
    payload: RepoUpdateRequest,
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> RepoResponse:
    _ensure_repo_manage(permissions)
    repo = _require_repo(session, repo_id)

    if payload.key is not None:
        repo.key = payload.key.strip()
    if payload.name is not None:
        repo.name = payload.name.strip()
    if payload.github_owner is not None:
        repo.github_owner = payload.github_owner.strip().lower()
    if payload.github_repo is not None:
        repo.github_repo = payload.github_repo.strip().lower()
    if payload.visibility is not None:
        repo.visibility = payload.visibility.strip().lower()
    if payload.default_branch is not None:
        _validate_branch_name(payload.default_branch)
        repo.default_branch = payload.default_branch.strip()
    if payload.git_auth_secret_id is not None:
        _get_git_secret(session, payload.git_auth_secret_id)
        repo.git_auth_secret_id = payload.git_auth_secret_id
    if payload.org_ids is not None:
        resolved_org_ids = _normalize_org_ids(session, list(payload.org_ids))
        current_org_ids = _repo_org_ids(session, repo.repo_id)
        persisted_org_ids = {
            mapped_org_id
            for (mapped_org_id,) in session.query(WorkspaceRepoOrgMapping.org_id)
            .filter(WorkspaceRepoOrgMapping.repo_id == repo.repo_id)
            .all()
        }
        next_org_ids = set(resolved_org_ids)
        removed_org_ids = current_org_ids - next_org_ids
        blocking_rows = _matching_products(
            session,
            github_owner=repo.github_owner,
            github_repo=repo.github_repo,
            org_ids=removed_org_ids,
        )
        if blocking_rows:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Cannot remove organization mapping while products use this repository",
                    "products": [
                        {
                            "product_id": str(product_id),
                            "org_id": str(blocking_org_id),
                            "key": key,
                            "name": name,
                        }
                        for product_id, blocking_org_id, key, name in blocking_rows
                    ],
                },
            )
        if persisted_org_ids:
            for remove_org_id in removed_org_ids & persisted_org_ids:
                session.query(WorkspaceRepoOrgMapping).filter(
                    WorkspaceRepoOrgMapping.repo_id == repo.repo_id,
                    WorkspaceRepoOrgMapping.org_id == remove_org_id,
                ).delete(synchronize_session=False)
        for add_org_id in next_org_ids - persisted_org_ids:
            session.add(WorkspaceRepoOrgMapping(repo_id=repo.repo_id, org_id=add_org_id))
        if repo.org_id in removed_org_ids:
            repo.org_id = resolved_org_ids[0]
    if payload.github_owner is not None or payload.github_repo is not None:
        repo.clone_url = _clone_url(repo.github_owner, repo.github_repo)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Repo already exists") from exc
    session.refresh(repo)
    return _build_repo_response(session, repo)


@router.delete("/repos/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(
    repo_id: UUID,
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> None:
    _ensure_repo_delete(permissions)
    repo = _require_repo(session, repo_id)
    blocking_products = _matching_products(
        session,
        github_owner=repo.github_owner,
        github_repo=repo.github_repo,
        org_ids=_repo_org_ids(session, repo.repo_id),
    )
    if blocking_products:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Repo has active products",
                "products": [
                    {
                        "product_id": str(product_id),
                        "org_id": str(org_id),
                        "key": key,
                        "name": name,
                    }
                    for product_id, org_id, key, name in blocking_products
                ],
            },
        )
    if repo.archived_at is None:
        repo.archived_at = datetime.now(timezone.utc)
        session.commit()
    return None


@router.post("/orgs/{org_id}/github/repos/lookup", response_model=list[RepoLookupItem])
def lookup_github_repos(
    org_id: UUID,
    payload: RepoLookupRequest,
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> list[RepoLookupItem]:
    _ensure_repo_manage(permissions)
    _require_org(session, org_id)
    token = _load_git_pat(_get_git_secret(session, payload.secret_id))

    limit = min(payload.limit, 200)
    per_page = min(limit, 100)
    query = payload.q.lower().strip() if payload.q else None
    repos: list[RepoLookupItem] = []
    page = 1
    while len(repos) < limit:
        try:
            response = httpx.get(
                "https://api.github.com/user/repos",
                headers=_github_headers(token),
                params={
                    "per_page": per_page,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                },
                timeout=15,
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        _handle_github_error(response)
        data = response.json()
        if not isinstance(data, list) or not data:
            break
        for item in data:
            name = str(item.get("name") or "")
            full_name = str(item.get("full_name") or "")
            if query and query not in name.lower() and query not in full_name.lower():
                continue
            owner = item.get("owner") or {}
            permission_payload = item.get("permissions") or {}
            repos.append(
                RepoLookupItem(
                    github_owner=str(owner.get("login") or "").lower(),
                    github_repo=name.lower(),
                    full_name=full_name,
                    visibility=str(item.get("visibility") or ("private" if item.get("private") else "public")).lower(),
                    is_private=bool(item.get("private")),
                    is_archived=bool(item.get("archived")),
                    default_branch=str(item.get("default_branch") or ""),
                    permissions=(
                        RepoLookupPermissions(
                            pull=bool(permission_payload.get("pull")),
                            push=bool(permission_payload.get("push")),
                            admin=bool(permission_payload.get("admin")),
                        )
                        if permission_payload
                        else None
                    ),
                )
            )
            if len(repos) >= limit:
                break
        page += 1
        if len(data) < per_page:
            break

    repos.sort(key=lambda item: item.full_name.lower())
    return repos


@router.post("/orgs/{org_id}/github/repos/branches", response_model=list[BranchSummary])
def list_github_repo_branches(
    org_id: UUID,
    payload: RepoBranchesRequest,
    session: Session = Depends(get_session),
    permissions: rbac.PermissionContext = Depends(rbac.get_permission_context),
) -> list[BranchSummary]:
    _ensure_repo_manage(permissions)
    _require_org(session, org_id)
    token = _load_git_pat(_get_git_secret(session, payload.secret_id))

    owner = payload.github_owner.strip().lower()
    repo = payload.github_repo.strip().lower()
    try:
        repo_response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=_github_headers(token),
            timeout=15,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _handle_github_error(repo_response, not_found_message="Repo not found")
    default_branch = str(repo_response.json().get("default_branch") or "")

    branches: list[BranchSummary] = []
    page = 1
    while True:
        try:
            response = httpx.get(
                f"https://api.github.com/repos/{owner}/{repo}/branches",
                headers=_github_headers(token),
                params={"per_page": 100, "page": page},
                timeout=15,
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        _handle_github_error(response, not_found_message="Repo not found")
        data = response.json()
        if not isinstance(data, list) or not data:
            break
        for item in data:
            name = str(item.get("name") or "")
            head_sha = str((item.get("commit") or {}).get("sha") or "")
            branches.append(
                BranchSummary(
                    name=name,
                    head_sha=head_sha,
                    is_default=name == default_branch,
                )
            )
        page += 1
        if len(data) < 100:
            break
    return branches
