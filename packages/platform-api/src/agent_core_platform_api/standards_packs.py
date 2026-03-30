from __future__ import annotations

from base64 import b64encode
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
import re
from typing import Any, Callable
from urllib.parse import quote

import httpx

from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.github_integration import (
    describe_repository_content_write_error,
    GitHubAppAuthError,
    GitHubPATAuthService,
)
from agent_core_platform_api.models import (
    ManagedAsset,
    Product,
    ProductStandardsOverride,
    RepositoryBinding,
    StandardsFollowUpItem,
    StandardsPack,
    StandardsPackAsset,
    StandardsUpgradeAsset,
    StandardsUpgradeRun,
)
from agent_core_platform_api.product_contract import ALLOWED_MANAGED_ASSET_MODES


SECTION_PATTERN = re.compile(
    r"<!--\s*orcha:begin\s+(?P<key>[\w./-]+)\s*-->(?P<body>.*?)<!--\s*orcha:end\s+(?P=key)\s*-->",
    re.DOTALL,
)
UPDATE_ACTIONS = {"create-file", "update-file", "refresh-sections"}
OUTCOME_DECISIONS = {"accepted", "rejected", "deferred"}
OUTCOME_MUTATION_ACTIONS = UPDATE_ACTIONS | {"advisory-drift", "conflict", "deferred"}


@dataclass(frozen=True)
class StandardsManagedChange:
    path: str
    content_text: str


@dataclass(frozen=True)
class StandardsUpgradePullRequestResult:
    number: int
    url: str | None
    head_branch: str
    base_branch: str
    base_sha: str
    head_sha: str
    commit_shas: list[str]


class StandardsPackConflictError(ValueError):
    """Raised when standards-pack state collides with existing persisted state."""


class GitHubStandardsUpgradePublisher:
    def __init__(
        self,
        session: Session,
        *,
        http_get: Callable[..., httpx.Response] = httpx.get,
        http_post: Callable[..., httpx.Response] = httpx.post,
        http_put: Callable[..., httpx.Response] = httpx.put,
    ):
        self.session = session
        self.auth = GitHubPATAuthService(session)
        self.http_get = http_get
        self.http_post = http_post
        self.http_put = http_put

    def publish(
        self,
        *,
        repo: RepositoryBinding,
        run_id: str,
        product_key: str,
        source_version: str,
        pr_title: str,
        pr_body: str,
        changes: list[StandardsManagedChange],
    ) -> StandardsUpgradePullRequestResult:
        token, api_base_url = self._load_token_and_api_base(repo=repo)
        base_sha = self._lookup_branch_sha(
            api_base_url=api_base_url,
            owner=repo.owner,
            repo=repo.name,
            branch=repo.default_branch,
            token=token,
        )
        head_branch = self._build_branch_name(product_key=product_key, source_version=source_version, run_id=run_id)
        self._create_branch(
            api_base_url=api_base_url,
            owner=repo.owner,
            repo=repo.name,
            branch=head_branch,
            sha=base_sha,
            token=token,
        )
        commit_shas: list[str] = []
        for change in sorted(changes, key=lambda item: item.path):
            existing_sha = self._lookup_file_sha(
                api_base_url=api_base_url,
                owner=repo.owner,
                repo=repo.name,
                branch=head_branch,
                path=change.path,
                token=token,
            )
            commit_sha = self._upsert_file(
                api_base_url=api_base_url,
                owner=repo.owner,
                repo=repo.name,
                branch=head_branch,
                path=change.path,
                content_text=change.content_text,
                existing_sha=existing_sha,
                token=token,
            )
            if commit_sha not in commit_shas:
                commit_shas.append(commit_sha)
        pr_number, pr_url = self._create_or_lookup_pull_request(
            api_base_url=api_base_url,
            owner=repo.owner,
            repo=repo.name,
            base_branch=repo.default_branch,
            head_branch=head_branch,
            title=pr_title,
            body=pr_body,
            token=token,
        )
        head_sha = commit_shas[-1] if commit_shas else base_sha
        return StandardsUpgradePullRequestResult(
            number=pr_number,
            url=pr_url,
            head_branch=head_branch,
            base_branch=repo.default_branch,
            base_sha=base_sha,
            head_sha=head_sha,
            commit_shas=commit_shas,
        )

    def _load_token_and_api_base(self, *, repo: RepositoryBinding) -> tuple[str, str]:
        token, api_base_url, _ = self.auth.load_repository_token(owner=repo.owner, repo=repo.name)
        return token, api_base_url

    def _headers(self, token: str) -> dict[str, str]:
        return self.auth.build_headers(token)

    def _record_rate_limit(self, *, owner: str, repo: str, response: httpx.Response) -> None:
        self.auth.record_repository_rate_limit_signal(owner=owner, repo=repo, response=response)

    def _build_branch_name(self, *, product_key: str, source_version: str, run_id: str) -> str:
        normalized_product = re.sub(r"[^a-z0-9._-]+", "-", product_key.lower()).strip("-") or "product"
        normalized_version = re.sub(r"[^a-zA-Z0-9._-]+", "-", source_version).strip("-") or "standards"
        run_token = re.sub(r"[^a-zA-Z0-9]+", "", run_id)[:12] or "run"
        return f"orcha/standards/{normalized_product}/{normalized_version}/{run_token}"

    def _lookup_branch_sha(
        self,
        *,
        api_base_url: str,
        owner: str,
        repo: str,
        branch: str,
        token: str,
    ) -> str:
        response = self.http_get(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/git/ref/heads/{branch}",
            headers=self._headers(token),
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_github_error_detail(response))
        payload = _parse_dict_payload(response, "GitHub branch reference response was malformed.")
        sha = payload.get("object", {}).get("sha") if isinstance(payload.get("object"), dict) else None
        if not isinstance(sha, str) or not sha:
            raise GitHubAppAuthError("GitHub branch reference response was malformed.")
        return sha

    def _create_branch(
        self,
        *,
        api_base_url: str,
        owner: str,
        repo: str,
        branch: str,
        sha: str,
        token: str,
    ) -> None:
        response = self.http_post(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/git/refs",
            headers=self._headers(token),
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400 and response.status_code != 422:
            raise GitHubAppAuthError(_github_error_detail(response))

    def _lookup_file_sha(
        self,
        *,
        api_base_url: str,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        token: str,
    ) -> str | None:
        response = self.http_get(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/contents/{quote(path, safe='/')}",
            headers=self._headers(token),
            params={"ref": branch},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise GitHubAppAuthError(_github_error_detail(response))
        payload = _parse_dict_payload(response, "GitHub content response was malformed.")
        sha = payload.get("sha")
        if not isinstance(sha, str) or not sha:
            raise GitHubAppAuthError(f"GitHub content response was malformed for `{path}`.")
        return sha

    def _upsert_file(
        self,
        *,
        api_base_url: str,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        content_text: str,
        existing_sha: str | None,
        token: str,
    ) -> str:
        payload: dict[str, Any] = {
            "message": f"Apply standards update: {path}",
            "content": b64encode(content_text.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if existing_sha is not None:
            payload["sha"] = existing_sha
        response = self.http_put(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/contents/{quote(path, safe='/')}",
            headers=self._headers(token),
            json=payload,
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(describe_repository_content_write_error(path=path, response=response))
        response_payload = _parse_dict_payload(response, "GitHub content update response was malformed.")
        commit_payload = response_payload.get("commit")
        commit_sha = commit_payload.get("sha") if isinstance(commit_payload, dict) else None
        if not isinstance(commit_sha, str) or not commit_sha:
            raise GitHubAppAuthError(f"GitHub content update response was malformed for `{path}`.")
        return commit_sha

    def _create_or_lookup_pull_request(
        self,
        *,
        api_base_url: str,
        owner: str,
        repo: str,
        base_branch: str,
        head_branch: str,
        title: str,
        body: str,
        token: str,
    ) -> tuple[int, str | None]:
        response = self.http_post(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/pulls",
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
                api_base_url=api_base_url,
                owner=owner,
                repo=repo,
                base_branch=base_branch,
                head_branch=head_branch,
                token=token,
            )
            if existing is not None:
                return existing
        if response.status_code >= 400:
            raise GitHubAppAuthError(_github_error_detail(response))
        payload = _parse_dict_payload(response, "GitHub pull request response was malformed.")
        number = payload.get("number")
        if not isinstance(number, int):
            raise GitHubAppAuthError("GitHub pull request response was malformed.")
        url = payload.get("html_url")
        return number, url.strip() if isinstance(url, str) and url.strip() else None

    def _lookup_open_pull_request(
        self,
        *,
        api_base_url: str,
        owner: str,
        repo: str,
        base_branch: str,
        head_branch: str,
        token: str,
    ) -> tuple[int, str | None] | None:
        response = self.http_get(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/pulls",
            headers=self._headers(token),
            params={"state": "open", "head": f"{owner}:{head_branch}", "base": base_branch},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_github_error_detail(response))
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


def build_standards_upgrade_publisher(session: Session) -> GitHubStandardsUpgradePublisher:
    return GitHubStandardsUpgradePublisher(session)


class StandardsPackService:
    def __init__(
        self,
        session: Session,
        *,
        upgrade_publisher: GitHubStandardsUpgradePublisher | None = None,
    ):
        self.session = session
        self.upgrade_publisher = upgrade_publisher

    def create_pack(
        self,
        *,
        key: str,
        channel: str,
        version: str,
        source_bundle: str,
        description: str | None,
        manifest: dict,
        assets: list[dict],
    ) -> StandardsPack:
        existing = (
            self.session.query(StandardsPack)
            .filter(
                StandardsPack.key == key.strip(),
                StandardsPack.channel == channel.strip(),
                StandardsPack.version == version.strip(),
            )
            .first()
        )
        if existing is not None:
            raise StandardsPackConflictError(f"Standards pack already exists: {key}@{channel}:{version}")

        pack = StandardsPack(
            key=key.strip(),
            channel=channel.strip(),
            version=version.strip(),
            source_bundle=source_bundle.strip(),
            description=description,
            manifest=dict(manifest or {}),
        )
        self.session.add(pack)
        self.session.flush()

        seen_paths: set[str] = set()
        for asset in assets:
            default_mode = str(asset.get("default_mode", "")).strip()
            if default_mode not in ALLOWED_MANAGED_ASSET_MODES:
                raise ValueError(f"Unsupported managed asset mode: {default_mode}")
            path = _validate_asset_path(str(asset.get("path", "")).strip())
            if path in seen_paths:
                raise StandardsPackConflictError(f"Standards pack request contains duplicate asset path: {path}")
            seen_paths.add(path)
            content_text = str(asset.get("content_text", ""))
            if default_mode == "section-managed":
                _extract_sections(content_text)
            self.session.add(
                StandardsPackAsset(
                    standards_pack_id=pack.standards_pack_id,
                    path=path,
                    kind=str(asset.get("kind", "")).strip() or _infer_asset_kind(path),
                    default_mode=default_mode,
                    content_text=content_text,
                    ownership_metadata=dict(asset.get("ownership_metadata") or {}),
                )
            )
        self.session.flush()
        return pack

    def list_runs(self, *, product_id) -> list[StandardsUpgradeRun]:
        return (
            self.session.query(StandardsUpgradeRun)
            .filter(StandardsUpgradeRun.product_id == product_id)
            .order_by(StandardsUpgradeRun.created_at.desc())
            .all()
        )

    def upsert_override(
        self,
        *,
        product_id,
        path: str,
        override_mode: str | None,
        is_deferred: bool,
        reason: str | None,
        override_payload: dict,
    ) -> ProductStandardsOverride:
        product = self.session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        validated_path = _validate_asset_path(path)
        if override_mode is not None and override_mode not in ALLOWED_MANAGED_ASSET_MODES:
            raise ValueError(f"Unsupported managed asset mode: {override_mode}")

        override = (
            self.session.query(ProductStandardsOverride)
            .filter(
                ProductStandardsOverride.product_id == product_id,
                ProductStandardsOverride.path == validated_path,
            )
            .first()
        )
        if override is None:
            override = ProductStandardsOverride(product_id=product_id, path=validated_path)
            self.session.add(override)
        override.override_mode = override_mode
        override.is_deferred = is_deferred
        override.reason = reason
        override.override_payload = dict(override_payload or {})
        self.session.flush()
        return override

    def evaluate_product(
        self,
        *,
        product_id,
        repo_root: Path,
        pack_key: str,
        channel: str,
        version: str,
        installation_id: str | None = None,
        materialize_pr: bool = True,
        generated_pr_number: int | None = None,
    ) -> StandardsUpgradeRun:
        repo_root = repo_root.expanduser().resolve()
        if not repo_root.exists() or not repo_root.is_dir():
            raise ValueError(f"Repository root does not exist or is not a directory: {repo_root}")
        _validate_allowed_repo_root(repo_root)

        product = self.session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        repo = self._resolve_primary_repo(product)
        pack = self._resolve_pack(pack_key=pack_key, channel=channel, version=version)
        overrides = {
            item.path: item
            for item in self.session.query(ProductStandardsOverride)
            .filter(ProductStandardsOverride.product_id == product_id)
            .all()
        }

        product.standards_pack_key = pack.key
        product.standards_pack_version = pack.version
        if product.baseline_channel is None:
            product.baseline_channel = pack.channel

        run = StandardsUpgradeRun(
            product_id=product.product_id,
            repo_id=repo.repo_id if repo is not None else None,
            standards_pack_id=pack.standards_pack_id,
            source_bundle=pack.source_bundle,
            source_version=pack.version,
            outcome_kind="no-op",
            outcome_status="current",
            generated_pr_number=generated_pr_number,
        )
        self.session.add(run)
        self.session.flush()

        counts: Counter[str] = Counter()
        changed_paths: list[str] = []
        managed_changes: list[StandardsManagedChange] = []
        managed_assets_by_path: dict[str, ManagedAsset] = {}
        advisory_paths: list[str] = []
        follow_ups = 0

        for definition in sorted(pack.assets, key=lambda item: item.path):
            override = overrides.get(definition.path)
            evaluation = self._evaluate_asset(
                repo_root=repo_root,
                definition=definition,
                override=override,
            )
            counts[evaluation["action"]] += 1
            if evaluation["action"] in UPDATE_ACTIONS:
                changed_paths.append(definition.path)
                rendered_content = evaluation.get("rendered_content")
                if isinstance(rendered_content, str):
                    managed_changes.append(
                        StandardsManagedChange(
                            path=definition.path,
                            content_text=rendered_content,
                        )
                    )
            if evaluation["action"] == "advisory-drift":
                advisory_paths.append(definition.path)

            self.session.add(
                StandardsUpgradeAsset(
                    standards_upgrade_run_id=run.standards_upgrade_run_id,
                    path=definition.path,
                    management_mode=evaluation["management_mode"],
                    action=evaluation["action"],
                    drift_status=evaluation["drift_status"],
                    patch_text=evaluation["patch_text"],
                    detail=evaluation["detail"],
                    metadata_payload=evaluation["metadata_payload"],
                )
            )
            managed_assets_by_path[definition.path] = self._sync_managed_asset(
                product=product,
                definition=definition,
                evaluation=evaluation,
                generated_pr_number=generated_pr_number,
            )

            if evaluation["action"] == "conflict":
                follow_ups += 1
                self.session.add(
                    StandardsFollowUpItem(
                        standards_upgrade_run_id=run.standards_upgrade_run_id,
                        product_id=product.product_id,
                        repo_id=repo.repo_id if repo is not None else None,
                        path=definition.path,
                        title=f"Resolve standards conflict for {definition.path}",
                        detail=evaluation["detail"] or "Managed section refresh could not be applied cleanly.",
                        status="open",
                    )
                )

        run.outcome_kind, run.outcome_status = self._resolve_run_outcome(counts)
        if run.outcome_kind != "no-op":
            run.pr_title = self._build_pr_title(product=product, pack=pack, outcome_kind=run.outcome_kind)
            run.pr_body = self._build_pr_body(
                product=product,
                pack=pack,
                changed_paths=changed_paths,
                advisory_paths=advisory_paths,
                follow_ups=follow_ups,
            )
        run.summary_payload = {
            "source_bundle": pack.source_bundle,
            "pack_key": pack.key,
            "channel": pack.channel,
            "version": pack.version,
            "counts": dict(counts),
            "changed_paths": changed_paths,
            "advisory_paths": advisory_paths,
            "follow_up_count": follow_ups,
        }
        if (
            materialize_pr
            and run.outcome_kind == "upgrade-pr"
            and run.pr_title
            and run.pr_body
            and repo is not None
            and managed_changes
        ):
            publisher = self.upgrade_publisher or build_standards_upgrade_publisher(self.session)
            result = publisher.publish(
                repo=repo,
                run_id=str(run.standards_upgrade_run_id),
                product_key=product.key,
                source_version=pack.version,
                pr_title=run.pr_title,
                pr_body=run.pr_body,
                changes=managed_changes,
            )
            run.generated_pr_number = result.number
            self._sync_generated_pr_number_for_updates(
                managed_changes=managed_changes,
                managed_assets_by_path=managed_assets_by_path,
                generated_pr_number=result.number,
            )
            run.summary_payload["pr_provenance"] = {
                "provider": "github",
                "status": "created",
                "auth_source": "workspace-repo-pat",
                "owner": repo.owner,
                "repo": repo.name,
                "pull_request_number": result.number,
                "pull_request_url": result.url,
                "head_branch": result.head_branch,
                "base_branch": result.base_branch,
                "base_sha": result.base_sha,
                "head_sha": result.head_sha,
                "commit_shas": result.commit_shas,
            }
        self.session.flush()
        return run

    def record_outcome(
        self,
        *,
        standards_upgrade_run_id,
        outcome_status: str,
        generated_pr_number: int | None = None,
    ) -> StandardsUpgradeRun:
        if outcome_status not in OUTCOME_DECISIONS:
            raise ValueError(f"Unsupported standards run outcome: {outcome_status}")

        run = self.session.get(StandardsUpgradeRun, standards_upgrade_run_id)
        if run is None:
            raise ValueError(f"Standards upgrade run not found: {standards_upgrade_run_id}")

        now = datetime.now(timezone.utc)
        if generated_pr_number is not None:
            run.generated_pr_number = generated_pr_number
        run.outcome_status = outcome_status
        for item in run.assets:
            managed_asset = self._get_or_create_managed_asset(
                product_id=run.product_id,
                path=item.path,
                kind=_infer_asset_kind(item.path),
                management_mode=item.management_mode,
                upstream_bundle_version=run.source_version,
            )
            if run.generated_pr_number is not None and item.action in UPDATE_ACTIONS:
                managed_asset.last_pr_number = run.generated_pr_number
            if outcome_status == "accepted":
                if item.action in UPDATE_ACTIONS:
                    managed_asset.drift_status = "current"
                    managed_asset.last_applied_at = now
                elif item.action == "advisory-drift":
                    managed_asset.drift_status = "advisory-reviewed"
            elif outcome_status == "rejected":
                if item.action in OUTCOME_MUTATION_ACTIONS:
                    managed_asset.drift_status = "rejected"
            elif outcome_status == "deferred":
                if item.action in OUTCOME_MUTATION_ACTIONS:
                    managed_asset.drift_status = "deferred"
        for follow_up in run.follow_up_items:
            follow_up.status = outcome_status
        self.session.flush()
        return run

    def _resolve_pack(self, *, pack_key: str, channel: str, version: str) -> StandardsPack:
        pack = (
            self.session.query(StandardsPack)
            .filter(
                StandardsPack.key == pack_key.strip(),
                StandardsPack.channel == channel.strip(),
                StandardsPack.version == version.strip(),
            )
            .first()
        )
        if pack is None:
            raise ValueError(f"Standards pack not found: {pack_key}@{channel}:{version}")
        return pack

    def _resolve_primary_repo(self, product: Product) -> RepositoryBinding | None:
        if product.primary_repo_id is None:
            return None
        return self.session.get(RepositoryBinding, product.primary_repo_id)

    def _evaluate_asset(
        self,
        *,
        repo_root: Path,
        definition: StandardsPackAsset,
        override: ProductStandardsOverride | None,
    ) -> dict[str, object]:
        management_mode = override.override_mode if override and override.override_mode else definition.default_mode
        local_path = _resolve_repo_path(repo_root, definition.path)
        local_exists = local_path.exists()
        try:
            local_content = local_path.read_text(encoding="utf-8") if local_exists else ""
        except (UnicodeDecodeError, OSError) as exc:
            return {
                "management_mode": management_mode,
                "action": "conflict",
                "drift_status": "conflict",
                "rendered_content": None,
                "patch_text": None,
                "detail": f"Local asset could not be read as UTF-8 text: {exc}",
                "metadata_payload": {"exists": local_exists},
            }
        upstream_content = definition.content_text

        if override and override.is_deferred:
            return {
                "management_mode": management_mode,
                "action": "deferred",
                "drift_status": "deferred",
                "rendered_content": None,
                "patch_text": None,
                "detail": override.reason or "Product override deferred this standards change.",
                "metadata_payload": {"override_payload": dict(override.override_payload or {})},
            }

        if management_mode == "local":
            return {
                "management_mode": management_mode,
                "action": "local-only",
                "drift_status": "local-only",
                "rendered_content": None,
                "patch_text": None,
                "detail": "Tracked for visibility only; Orcha will not edit this asset.",
                "metadata_payload": {"exists": local_exists},
            }

        if management_mode == "section-managed":
            try:
                _extract_sections(upstream_content)
                rendered_content = upstream_content if not local_exists else _refresh_managed_sections(local_content, upstream_content)
            except ValueError as exc:
                return {
                    "management_mode": management_mode,
                    "action": "conflict",
                    "drift_status": "conflict",
                    "rendered_content": None,
                    "patch_text": None,
                    "detail": str(exc),
                    "metadata_payload": {"exists": local_exists},
                }
            if rendered_content == local_content:
                return {
                    "management_mode": management_mode,
                    "action": "noop",
                    "drift_status": "current",
                    "rendered_content": None,
                    "patch_text": None,
                    "detail": None,
                    "metadata_payload": {"exists": local_exists},
                }
            return {
                "management_mode": management_mode,
                "action": "create-file" if not local_exists else "refresh-sections",
                "drift_status": "update-available",
                "rendered_content": rendered_content,
                "patch_text": _build_patch(path=definition.path, before=local_content, after=rendered_content),
                "detail": None,
                "metadata_payload": {"exists": local_exists},
            }

        if upstream_content == local_content:
            return {
                "management_mode": management_mode,
                "action": "noop",
                "drift_status": "current",
                "rendered_content": None,
                "patch_text": None,
                "detail": None,
                "metadata_payload": {"exists": local_exists},
            }

        if management_mode == "advisory":
            return {
                "management_mode": management_mode,
                "action": "advisory-drift",
                "drift_status": "advisory-drift",
                "rendered_content": None,
                "patch_text": _build_patch(path=definition.path, before=local_content, after=upstream_content),
                "detail": "Local file diverges from the adopted standards pack.",
                "metadata_payload": {"exists": local_exists},
            }

        return {
            "management_mode": management_mode,
            "action": "create-file" if not local_exists else "update-file",
            "drift_status": "update-available",
            "rendered_content": upstream_content,
            "patch_text": _build_patch(path=definition.path, before=local_content, after=upstream_content),
            "detail": None,
            "metadata_payload": {"exists": local_exists},
        }

    def _sync_managed_asset(
        self,
        *,
        product: Product,
        definition: StandardsPackAsset,
        evaluation: dict[str, object],
        generated_pr_number: int | None,
    ) -> ManagedAsset:
        managed_asset = self._get_or_create_managed_asset(
            product_id=product.product_id,
            path=definition.path,
            kind=definition.kind,
            management_mode=str(evaluation["management_mode"]),
            upstream_bundle_version=definition.standards_pack.version,
        )
        managed_asset.management_mode = str(evaluation["management_mode"])
        managed_asset.kind = definition.kind
        managed_asset.upstream_bundle_version = definition.standards_pack.version
        managed_asset.drift_status = str(evaluation["drift_status"])
        if generated_pr_number is not None and str(evaluation["action"]) in UPDATE_ACTIONS:
            managed_asset.last_pr_number = generated_pr_number
        return managed_asset

    def _sync_generated_pr_number_for_updates(
        self,
        *,
        managed_changes: list[StandardsManagedChange],
        managed_assets_by_path: dict[str, ManagedAsset],
        generated_pr_number: int,
    ) -> None:
        for item in managed_changes:
            managed_asset = managed_assets_by_path.get(item.path)
            if managed_asset is None:
                continue
            managed_asset.last_pr_number = generated_pr_number

    def _get_or_create_managed_asset(
        self,
        *,
        product_id,
        path: str,
        kind: str,
        management_mode: str,
        upstream_bundle_version: str,
    ) -> ManagedAsset:
        managed_asset = (
            self.session.query(ManagedAsset)
            .filter(
                ManagedAsset.product_id == product_id,
                ManagedAsset.path == path,
            )
            .first()
        )
        if managed_asset is None:
            managed_asset = ManagedAsset(
                product_id=product_id,
                path=path,
                kind=kind,
                management_mode=management_mode,
            )
            self.session.add(managed_asset)
        managed_asset.kind = kind
        managed_asset.management_mode = management_mode
        managed_asset.upstream_bundle_version = upstream_bundle_version
        return managed_asset

    def _resolve_run_outcome(self, counts: Counter[str]) -> tuple[str, str]:
        if counts["conflict"]:
            return "upgrade-pr" if counts["create-file"] or counts["update-file"] or counts["refresh-sections"] else "advisory", "conflict"
        if counts["create-file"] or counts["update-file"] or counts["refresh-sections"]:
            return "upgrade-pr", "reviewable"
        if counts["advisory-drift"]:
            return "advisory", "reviewable"
        if counts["deferred"]:
            return "advisory", "deferred"
        return "no-op", "current"

    def _build_pr_title(self, *, product: Product, pack: StandardsPack, outcome_kind: str) -> str:
        action = "Refresh" if outcome_kind == "upgrade-pr" else "Review"
        return f"{action} {pack.key} {pack.version} for {product.key}"

    def _build_pr_body(
        self,
        *,
        product: Product,
        pack: StandardsPack,
        changed_paths: list[str],
        advisory_paths: list[str],
        follow_ups: int,
    ) -> str:
        lines = [
            f"Standards pack: `{pack.key}`",
            f"Channel: `{pack.channel}`",
            f"Version: `{pack.version}`",
            f"Source bundle: `{pack.source_bundle}`",
            "",
            f"Product: `{product.key}`",
        ]
        if changed_paths:
            lines.append(f"Managed updates: {', '.join(f'`{path}`' for path in changed_paths)}")
        if advisory_paths:
            lines.append(f"Advisory drift: {', '.join(f'`{path}`' for path in advisory_paths)}")
        if follow_ups:
            lines.append(f"Follow-up items: {follow_ups}")
        return "\n".join(lines)

def _github_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return response.text.strip() or f"GitHub request failed with status {response.status_code}."


def _parse_dict_payload(response: httpx.Response, error_message: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubAppAuthError(error_message) from exc
    if not isinstance(payload, dict):
        raise GitHubAppAuthError(error_message)
    return payload


def _infer_asset_kind(path: str) -> str:
    lower_path = path.lower()
    if lower_path.endswith(".md"):
        return "markdown"
    if lower_path.endswith((".yml", ".yaml")):
        return "yaml"
    return "file"


def _validate_asset_path(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        raise ValueError("Standards pack asset path is required")
    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Standards pack asset path escapes repo root: {path}")
    canonical = candidate.as_posix()
    if canonical in {"", "."}:
        raise ValueError("Standards pack asset path is required")
    return canonical


def _resolve_repo_path(repo_root: Path, configured_path: str) -> Path:
    validated = _validate_asset_path(configured_path)
    resolved_root = repo_root.resolve()
    resolved_candidate = (resolved_root / validated).resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise ValueError(f"Standards pack asset path escapes repo root: {configured_path}")
    return resolved_candidate


def _validate_allowed_repo_root(repo_root: Path) -> None:
    allowed_roots = [Path(root).expanduser().resolve() for root in get_settings().allowed_repo_roots]
    if not allowed_roots:
        raise ValueError("Standards evaluation requires AGENT_CORE_ALLOWED_REPO_ROOTS or AGENT_CORE_LOCAL_DEV_ROOT.")
    if any(repo_root.is_relative_to(root) for root in allowed_roots):
        return
    raise ValueError(f"Repository root is outside the configured evaluation roots: {repo_root}")


def _extract_sections(content: str) -> dict[str, str]:
    matches = list(SECTION_PATTERN.finditer(content))
    if not matches:
        raise ValueError("Section-managed asset is missing Orcha ownership delimiters.")
    sections: dict[str, str] = {}
    for match in matches:
        key = match.group("key")
        if key in sections:
            raise ValueError(f"Section-managed asset declares duplicate section `{key}`.")
        sections[key] = match.group(0)
    return sections


def _refresh_managed_sections(local_content: str, upstream_content: str) -> str:
    upstream_sections = _extract_sections(upstream_content)
    local_sections = _extract_sections(local_content)
    extra_local_sections = sorted(set(local_sections) - set(upstream_sections))
    if extra_local_sections:
        raise ValueError(
            "Local file contains managed sections that are no longer present upstream: "
            + ", ".join(f"`{section}`" for section in extra_local_sections)
        )
    refreshed = local_content
    for key, block in upstream_sections.items():
        local_pattern = re.compile(
            rf"<!--\s*orcha:begin\s+{re.escape(key)}\s*-->.*?<!--\s*orcha:end\s+{re.escape(key)}\s*-->",
            re.DOTALL,
        )
        local_matches = list(local_pattern.finditer(refreshed))
        if len(local_matches) != 1:
            raise ValueError(f"Local file is missing a unique managed section for `{key}`.")
        refreshed = local_pattern.sub(block, refreshed, count=1)
    return refreshed


def _build_patch(*, path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
