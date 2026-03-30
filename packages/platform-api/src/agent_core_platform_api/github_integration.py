from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Callable, Mapping
from uuid import UUID

import httpx
from jose import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from agent_core_platform_api.config import get_settings
from agent_core_platform_api.governance import build_write_audit
from agent_core_platform_api.models import (
    OperationalSignal,
    Secret,
    Setting,
    WebhookDelivery,
    WorkspaceRepo,
    WorkspaceRepoOrgMapping,
)
from agent_core_platform_api.observability import delivery_signal_correlation, signal_value_with_correlation
from agent_core_platform_api.secret_crypto import SecretCryptoError, decrypt_secret, encrypt_secret


PLATFORM_SETTINGS_SCOPE_ID = "global"
GITHUB_APP_SETTING_KEY = "orcha.github_app"
GITHUB_WEBHOOK_SETTING_KEY = "orcha.github_webhook"
GITHUB_ACCEPT_HEADER = "application/vnd.github+json"
DEFAULT_GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_GITHUB_WEBHOOK_SECRET_KEY = "github-webhook-secret"
DEFAULT_GITHUB_WEBHOOK_SECRET_NAME = "GitHub Webhook Secret"
WEBHOOK_BOOTSTRAP_ACTOR_ID = "github_webhook_bootstrap"


class GitHubAppConfigError(RuntimeError):
    """Raised when GitHub App configuration or secrets are unavailable."""


class GitHubAppAuthError(RuntimeError):
    """Raised when GitHub App authentication fails."""


class GitHubWebhookSignatureError(RuntimeError):
    """Raised when a webhook signature cannot be validated."""


class GitHubWebhookProcessingError(RuntimeError):
    """Raised when a webhook delivery cannot be processed safely."""


class GitHubAppConfig(BaseModel):
    app_id: str = Field(min_length=1)
    webhook_secret_key: str = Field(min_length=1)
    private_key_secret_key: str = Field(min_length=1)
    api_base_url: str = Field(default=DEFAULT_GITHUB_API_BASE_URL, min_length=1)


class GitHubWebhookConfig(BaseModel):
    webhook_secret_key: str = Field(min_length=1)
    api_base_url: str = Field(default=DEFAULT_GITHUB_API_BASE_URL, min_length=1)
    delivery_url: str | None = Field(default=None, min_length=1)


class GitHubInstallationToken(BaseModel):
    token: str = Field(min_length=1)
    expires_at: str = Field(min_length=1)
    permissions: dict[str, Any] = Field(default_factory=dict)
    repositories: list[dict[str, Any]] = Field(default_factory=list)


class GitHubWebhookEnvelope(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    github_delivery_guid: str = Field(min_length=1)
    event_name: str = Field(min_length=1)
    installation_id: str | None = None
    signature: str = Field(min_length=1)
    payload_hash: str = Field(min_length=1)
    raw_body: str
    payload_json: dict[str, Any] | list[Any] | str | int | float | bool | None = None


@dataclass
class GitHubWebhookIntakeResult:
    delivery: WebhookDelivery
    duplicate: bool


@dataclass
class GitHubRepositoryWebhookResult:
    hook_id: int
    delivery_url: str
    status: str


DeliveryProcessor = Callable[[Session, WebhookDelivery], None]

REPOSITORY_WEBHOOK_EVENTS = (
    "issues",
    "pull_request",
    "push",
    "repository",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _delivery_signal_target(delivery: WebhookDelivery) -> str:
    return str(delivery.delivery_id)


def _extract_installation_id(payload_json: Any) -> str | None:
    if not isinstance(payload_json, dict):
        return None
    installation = payload_json.get("installation")
    if not isinstance(installation, dict):
        return None
    installation_id = installation.get("id")
    if installation_id is None:
        return None
    return str(installation_id)


def _response_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return response.text.strip() or f"GitHub request failed with status {response.status_code}."


def _normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def describe_repository_content_write_error(*, path: str, response: httpx.Response) -> str:
    detail = _response_error_detail(response)
    normalized_path = path.strip().lower()
    if normalized_path.startswith(".github/workflows/") and response.status_code in {403, 404}:
        return (
            f"Unable to write `{path}` because the connected GitHub credential cannot modify workflow files. "
            "GitHub requires workflow write access for `.github/workflows/*` updates "
            "(classic PAT: `workflow` scope; fine-grained token or app: `Workflows` repository permission set to `write`)."
        )
    return f"Unable to write `{path}`: {detail}"


def _load_platform_setting(session: Session, key: str) -> Setting | None:
    return (
        session.query(Setting)
        .filter(
            Setting.scope_type == "platform",
            Setting.scope_id == PLATFORM_SETTINGS_SCOPE_ID,
            Setting.key == key,
        )
        .first()
    )


def _load_secret_value(session: Session, secret_key: str) -> str:
    secret = session.query(Secret).filter(Secret.key == secret_key).first()
    if secret is None or not secret.has_value or secret.value_ciphertext is None:
        raise GitHubAppConfigError(f"Missing secret value for key: {secret_key}")
    try:
        return decrypt_secret(secret.value_ciphertext)
    except SecretCryptoError as exc:
        raise GitHubAppConfigError(f"Unable to decrypt secret value for key: {secret_key}") from exc


class GitHubAppAuthService:
    def __init__(self, session: Session):
        self.session = session

    def load_config(self) -> GitHubAppConfig:
        setting = _load_platform_setting(self.session, GITHUB_APP_SETTING_KEY)
        if setting is None:
            raise GitHubAppConfigError(f"Missing platform setting: {GITHUB_APP_SETTING_KEY}")
        try:
            return GitHubAppConfig.model_validate(setting.value_json)
        except ValidationError as exc:
            raise GitHubAppConfigError(f"Invalid platform setting {GITHUB_APP_SETTING_KEY}: {exc}") from exc

    def _load_secret_value(self, secret_key: str) -> str:
        return _load_secret_value(self.session, secret_key)

    def load_webhook_secret(self) -> str:
        config = self.load_config()
        return self._load_secret_value(config.webhook_secret_key)

    def build_app_jwt(self, *, now: datetime | None = None) -> str:
        config = self.load_config()
        private_key = self._load_secret_value(config.private_key_secret_key)
        issued_at = now or _now()
        payload = {
            "iat": int((issued_at - timedelta(seconds=60)).timestamp()),
            "exp": int((issued_at + timedelta(minutes=9)).timestamp()),
            "iss": config.app_id,
        }
        try:
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as exc:  # pragma: no cover - jose surfaces multiple subclasses.
            raise GitHubAppAuthError("Unable to build GitHub App JWT.") from exc

    def exchange_installation_token(
        self,
        *,
        installation_id: str,
        http_post: Callable[..., httpx.Response] = httpx.post,
    ) -> GitHubInstallationToken:
        config = self.load_config()
        response = http_post(
            f"{config.api_base_url.rstrip('/')}/app/installations/{installation_id}/access_tokens",
            headers={
                "Accept": GITHUB_ACCEPT_HEADER,
                "Authorization": f"Bearer {self.build_app_jwt()}",
            },
            timeout=30,
        )
        self._record_rate_limit_signal(installation_id=installation_id, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_response_error_detail(response))
        try:
            return GitHubInstallationToken.model_validate(response.json())
        except ValidationError as exc:
            raise GitHubAppAuthError("GitHub installation token response was malformed.") from exc

    def _record_rate_limit_signal(self, *, installation_id: str, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        if response.status_code not in {403, 429} and remaining != "0":
            return
        signal = OperationalSignal(
            target_kind="github_installation",
            target_id=str(installation_id),
            signal_type="github.rate_limit",
            severity="warning",
            value=signal_value_with_correlation(
                {
                    "status_code": response.status_code,
                    "remaining": remaining,
                    "reset": response.headers.get("x-ratelimit-reset"),
                    "installation_id": installation_id,
                },
                {"installation_id": installation_id},
            ),
            source_kind="github",
        )
        self.session.add(signal)
        self.session.flush()


class GitHubPATAuthService:
    def __init__(self, session: Session):
        self.session = session

    def _ensure_bootstrap_webhook_secret(self) -> Secret:
        secret = self.session.query(Secret).filter(Secret.key == DEFAULT_GITHUB_WEBHOOK_SECRET_KEY).first()
        if secret is not None:
            if secret.kind != "github_webhook_secret":
                raise GitHubAppConfigError(
                    f"Secret `{DEFAULT_GITHUB_WEBHOOK_SECRET_KEY}` must have kind `github_webhook_secret`."
                )
            if not secret.has_value or secret.value_ciphertext is None:
                secret.value_ciphertext = encrypt_secret(secrets.token_urlsafe(48))
                secret.last_rotated_at = _now()
                self.session.flush()
            return secret

        secret = Secret(
            key=DEFAULT_GITHUB_WEBHOOK_SECRET_KEY,
            name=DEFAULT_GITHUB_WEBHOOK_SECRET_NAME,
            description="Shared GitHub repository webhook signing secret.",
            kind="github_webhook_secret",
            value_ciphertext=encrypt_secret(secrets.token_urlsafe(48)),
            last_rotated_at=_now(),
        )
        self.session.add(secret)
        self.session.flush()
        return secret

    def _persist_webhook_config(
        self,
        *,
        webhook_secret_key: str,
        api_base_url: str = DEFAULT_GITHUB_API_BASE_URL,
        delivery_url: str | None = None,
    ) -> GitHubWebhookConfig:
        payload: dict[str, str] = {
            "webhook_secret_key": webhook_secret_key,
            "api_base_url": api_base_url.strip() or DEFAULT_GITHUB_API_BASE_URL,
        }
        if isinstance(delivery_url, str) and delivery_url.strip():
            payload["delivery_url"] = _normalize_url(delivery_url)

        setting = Setting(
            scope_type="platform",
            scope_id=PLATFORM_SETTINGS_SCOPE_ID,
            key=GITHUB_WEBHOOK_SETTING_KEY,
            value_json=payload,
            created_by=WEBHOOK_BOOTSTRAP_ACTOR_ID,
            updated_by=WEBHOOK_BOOTSTRAP_ACTOR_ID,
        )
        self.session.add(setting)
        self.session.flush()
        return GitHubWebhookConfig.model_validate(payload)

    def _bootstrap_webhook_config(self) -> GitHubWebhookConfig:
        legacy_setting = _load_platform_setting(self.session, GITHUB_APP_SETTING_KEY)
        if legacy_setting is not None:
            try:
                legacy = GitHubAppConfig.model_validate(legacy_setting.value_json)
            except ValidationError as exc:
                raise GitHubAppConfigError(f"Invalid platform setting {GITHUB_APP_SETTING_KEY}: {exc}") from exc
            return self._persist_webhook_config(
                webhook_secret_key=legacy.webhook_secret_key,
                api_base_url=legacy.api_base_url,
            )

        secret = self._ensure_bootstrap_webhook_secret()
        return self._persist_webhook_config(
            webhook_secret_key=secret.key,
            api_base_url=DEFAULT_GITHUB_API_BASE_URL,
        )

    def load_webhook_config(self) -> GitHubWebhookConfig:
        setting = _load_platform_setting(self.session, GITHUB_WEBHOOK_SETTING_KEY)
        if setting is not None:
            try:
                return GitHubWebhookConfig.model_validate(setting.value_json)
            except ValidationError as exc:
                raise GitHubAppConfigError(f"Invalid platform setting {GITHUB_WEBHOOK_SETTING_KEY}: {exc}") from exc
        return self._bootstrap_webhook_config()

    def load_webhook_secret(self) -> str:
        config = self.load_webhook_config()
        return _load_secret_value(self.session, config.webhook_secret_key)

    def load_webhook_delivery_url(self) -> str:
        config = self.load_webhook_config()
        if isinstance(config.delivery_url, str) and config.delivery_url.strip():
            return _normalize_url(config.delivery_url)
        public_api_base_url = get_settings().public_api_base_url
        if public_api_base_url and public_api_base_url.strip():
            return f"{_normalize_url(public_api_base_url)}/github/webhooks"
        raise GitHubAppConfigError(
            "GitHub webhook delivery URL is not configured. "
            "Set `orcha.github_webhook.delivery_url` or `AGENT_CORE_PUBLIC_API_BASE_URL`."
        )

    def load_repository_token(
        self,
        *,
        owner: str,
        repo: str,
        org_id: UUID | None = None,
    ) -> tuple[str, str, WorkspaceRepo]:
        workspace_repo = self._resolve_workspace_repo(owner=owner, repo=repo, org_id=org_id)
        secret = self.session.get(Secret, workspace_repo.git_auth_secret_id)
        if secret is None:
            raise GitHubAppConfigError(
                "Connected Git repository settings are missing the PAT secret required for GitHub access."
            )
        if secret.kind != "git_personal_access_token":
            raise GitHubAppConfigError(
                f"Connected Git repository secret `{secret.key}` must be a git_personal_access_token."
            )
        if not secret.has_value or secret.value_ciphertext is None:
            raise GitHubAppConfigError(
                f"Connected Git repository secret `{secret.key}` does not have a stored value."
            )
        try:
            token = decrypt_secret(secret.value_ciphertext)
        except SecretCryptoError as exc:
            raise GitHubAppConfigError(
                f"Unable to decrypt connected Git repository secret `{secret.key}`."
            ) from exc
        return token, DEFAULT_GITHUB_API_BASE_URL, workspace_repo

    def record_repository_rate_limit_signal(
        self,
        *,
        owner: str,
        repo: str,
        response: httpx.Response,
    ) -> None:
        remaining = response.headers.get("x-ratelimit-remaining") or response.headers.get("X-RateLimit-Remaining")
        if response.status_code not in {403, 429} and remaining != "0":
            return
        repository = f"{owner.strip().lower()}/{repo.strip().lower()}"
        signal = OperationalSignal(
            target_kind="github_repository",
            target_id=repository,
            signal_type="github.rate_limit",
            severity="warning",
            value=signal_value_with_correlation(
                {
                    "status_code": response.status_code,
                    "remaining": remaining,
                    "reset": response.headers.get("x-ratelimit-reset") or response.headers.get("X-RateLimit-Reset"),
                    "repository": repository,
                },
                {"repository": repository},
            ),
            source_kind="github",
        )
        self.session.add(signal)
        self.session.flush()

    def ensure_repository_webhook(
        self,
        *,
        owner: str,
        repo: str,
        org_id: UUID | None = None,
        http_get: Callable[..., httpx.Response] = httpx.get,
        http_post: Callable[..., httpx.Response] = httpx.post,
        http_patch: Callable[..., httpx.Response] = httpx.patch,
    ) -> GitHubRepositoryWebhookResult:
        token, api_base_url, _ = self.load_repository_token(owner=owner, repo=repo, org_id=org_id)
        delivery_url = self.load_webhook_delivery_url()
        webhook_secret = self.load_webhook_secret()
        desired_config = {
            "url": delivery_url,
            "content_type": "json",
            "secret": webhook_secret,
            "insecure_ssl": "0",
        }

        hooks_response = http_get(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/hooks",
            headers=self.build_headers(token),
            params={"per_page": 100},
            timeout=30,
        )
        self.record_repository_rate_limit_signal(owner=owner, repo=repo, response=hooks_response)
        if hooks_response.status_code >= 400:
            raise GitHubAppAuthError(_response_error_detail(hooks_response))
        hooks_payload = hooks_response.json()
        if not isinstance(hooks_payload, list):
            raise GitHubAppAuthError("GitHub repository webhook list response was malformed.")

        matching_hook: dict[str, Any] | None = None
        for hook_payload in hooks_payload:
            if not isinstance(hook_payload, dict):
                continue
            config_payload = hook_payload.get("config")
            hook_url = config_payload.get("url") if isinstance(config_payload, dict) else None
            if not isinstance(hook_url, str):
                continue
            if _normalize_url(hook_url) != delivery_url:
                continue
            matching_hook = hook_payload
            break

        if matching_hook is None:
            create_response = http_post(
                f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/hooks",
                headers=self.build_headers(token),
                json={
                    "name": "web",
                    "active": True,
                    "events": list(REPOSITORY_WEBHOOK_EVENTS),
                    "config": desired_config,
                },
                timeout=30,
            )
            self.record_repository_rate_limit_signal(owner=owner, repo=repo, response=create_response)
            if create_response.status_code >= 400:
                raise GitHubAppAuthError(_response_error_detail(create_response))
            created_payload = create_response.json()
            hook_id = created_payload.get("id") if isinstance(created_payload, dict) else None
            if not isinstance(hook_id, int):
                raise GitHubAppAuthError("GitHub repository webhook create response was malformed.")
            return GitHubRepositoryWebhookResult(hook_id=hook_id, delivery_url=delivery_url, status="created")

        hook_id = matching_hook.get("id")
        if not isinstance(hook_id, int):
            raise GitHubAppAuthError("GitHub repository webhook payload was missing the hook id.")
        update_response = http_patch(
            f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/hooks/{hook_id}",
            headers=self.build_headers(token),
            json={
                "active": True,
                "events": list(REPOSITORY_WEBHOOK_EVENTS),
                "config": desired_config,
            },
            timeout=30,
        )
        self.record_repository_rate_limit_signal(owner=owner, repo=repo, response=update_response)
        if update_response.status_code >= 400:
            raise GitHubAppAuthError(_response_error_detail(update_response))
        return GitHubRepositoryWebhookResult(hook_id=hook_id, delivery_url=delivery_url, status="updated")

    @staticmethod
    def build_headers(token: str) -> dict[str, str]:
        return {
            "Accept": GITHUB_ACCEPT_HEADER,
            "Authorization": f"token {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _resolve_workspace_repo(
        self,
        *,
        owner: str,
        repo: str,
        org_id: UUID | None = None,
    ) -> WorkspaceRepo:
        normalized_owner = owner.strip().lower()
        normalized_repo = repo.strip().lower()
        workspace_repo = (
            self.session.query(WorkspaceRepo)
            .filter(
                WorkspaceRepo.github_owner == normalized_owner,
                WorkspaceRepo.github_repo == normalized_repo,
                WorkspaceRepo.archived_at.is_(None),
            )
            .order_by(WorkspaceRepo.created_at.asc())
            .first()
        )
        if workspace_repo is None:
            raise GitHubAppConfigError(
                "Connected Git repository settings were not found for "
                f"`{normalized_owner}/{normalized_repo}`. Add this repository in Settings > Git Repositories."
            )
        if org_id is not None:
            mapped_org_ids = {
                mapped_org_id
                for (mapped_org_id,) in self.session.query(WorkspaceRepoOrgMapping.org_id)
                .filter(WorkspaceRepoOrgMapping.repo_id == workspace_repo.repo_id)
                .all()
            }
            if mapped_org_ids and org_id not in mapped_org_ids:
                raise GitHubAppConfigError(
                    "Connected Git repository settings exist for "
                    f"`{normalized_owner}/{normalized_repo}`, but they are not mapped to the selected organization."
                )
            if not mapped_org_ids and workspace_repo.org_id != org_id:
                raise GitHubAppConfigError(
                    "Connected Git repository settings exist for "
                    f"`{normalized_owner}/{normalized_repo}`, but they are not mapped to the selected organization."
                )
        return workspace_repo


def _default_delivery_processor(_: Session, __: WebhookDelivery) -> None:
    return None


class GitHubWebhookService:
    def __init__(self, session: Session, *, processor: DeliveryProcessor | None = None):
        self.session = session
        self.auth = GitHubPATAuthService(session)
        if processor is None:
            from agent_core_platform_api.github_mirror import GitHubMirrorService

            self.processor = GitHubMirrorService(session).process_delivery
        else:
            self.processor = processor

    def load_delivery(self, delivery_id) -> WebhookDelivery:
        delivery = self.session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            raise ValueError(f"Webhook delivery not found: {delivery_id}")
        return delivery

    def intake(self, *, headers: Mapping[str, str], body: bytes) -> GitHubWebhookIntakeResult:
        signature = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        if not signature:
            raise ValueError("Missing X-Hub-Signature-256 header.")
        github_delivery_guid = headers.get("x-github-delivery") or headers.get("X-GitHub-Delivery")
        if not github_delivery_guid:
            raise ValueError("Missing X-GitHub-Delivery header.")
        event_name = headers.get("x-github-event") or headers.get("X-GitHub-Event")
        if not event_name:
            raise ValueError("Missing X-GitHub-Event header.")

        webhook_secret = self.auth.load_webhook_secret()
        expected = "sha256=" + hmac.new(webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise GitHubWebhookSignatureError("Invalid GitHub webhook signature.")

        payload_hash = hashlib.sha256(body).hexdigest()
        delivery = (
            self.session.query(WebhookDelivery)
            .filter(WebhookDelivery.github_delivery_guid == github_delivery_guid)
            .first()
        )
        if delivery is not None:
            return self._register_duplicate(delivery=delivery, github_delivery_guid=github_delivery_guid, payload_hash=payload_hash)

        raw_body = body.decode("utf-8")
        try:
            payload_json = json.loads(raw_body)
        except json.JSONDecodeError:
            payload_json = None

        envelope = GitHubWebhookEnvelope(
            github_delivery_guid=github_delivery_guid,
            event_name=event_name,
            installation_id=_extract_installation_id(payload_json),
            signature=signature,
            payload_hash=payload_hash,
            raw_body=raw_body,
            payload_json=payload_json,
        )
        delivery = WebhookDelivery(
            github_delivery_guid=envelope.github_delivery_guid,
            event_name=envelope.event_name,
            installation_id=envelope.installation_id,
            status="received",
            payload_hash=envelope.payload_hash,
            delivery_attempts=1,
            payload_json=envelope.payload_json,
            raw_body=envelope.raw_body,
        )
        self._persist_new_delivery(delivery)
        self._record_signal(
            delivery=delivery,
            signal_type="github.delivery.received",
            severity="info",
            value={"event_name": event_name},
        )

        if envelope.payload_json is None:
            self._mark_dead_letter(delivery, "Webhook payload must be valid JSON.")
            return GitHubWebhookIntakeResult(delivery=delivery, duplicate=False)

        self._process_delivery(delivery)
        return GitHubWebhookIntakeResult(delivery=delivery, duplicate=False)

    def replay(self, delivery_id) -> WebhookDelivery:
        delivery = self.load_delivery(delivery_id)
        delivery.replay_count += 1
        self._record_signal(
            delivery=delivery,
            signal_type="github.delivery.replay_requested",
            severity="info",
            value={
                "replay_count": delivery.replay_count,
                "audit": build_write_audit(
                    actor_type="system",
                    actor_id="github_webhook_service",
                    target_kind="github_delivery",
                    target_id=str(delivery.delivery_id),
                    action="github.delivery.replay_requested",
                    approval_context={"mode": "platform-manage-api"},
                    outcome="requested",
                ),
            },
        )
        self._process_delivery(delivery)
        return delivery

    def recover_duplicate(self, *, github_delivery_guid: str, body: bytes) -> GitHubWebhookIntakeResult:
        payload_hash = hashlib.sha256(body).hexdigest()
        delivery = (
            self.session.query(WebhookDelivery)
            .filter(WebhookDelivery.github_delivery_guid == github_delivery_guid)
            .first()
        )
        if delivery is None:
            raise ValueError(f"Webhook delivery not found after concurrent insert: {github_delivery_guid}")
        return self._register_duplicate(
            delivery=delivery,
            github_delivery_guid=github_delivery_guid,
            payload_hash=payload_hash,
        )

    def _process_delivery(self, delivery: WebhookDelivery) -> None:
        try:
            self.processor(self.session, delivery)
        except GitHubWebhookProcessingError as exc:
            self._mark_dead_letter(delivery, str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive guardrail for worker callbacks.
            self._mark_dead_letter(delivery, f"Unhandled delivery processor failure: {exc}")
            return

        delivery.status = "processed"
        delivery.error_detail = None
        delivery.processed_at = _now()
        self._record_signal(
            delivery=delivery,
            signal_type="github.delivery.processed",
            severity="info",
            value={"event_name": delivery.event_name},
        )
        self.session.flush()

    def _mark_dead_letter(self, delivery: WebhookDelivery, error_detail: str) -> None:
        delivery.status = "dead-letter"
        delivery.error_detail = error_detail
        delivery.processed_at = _now()
        self._record_signal(
            delivery=delivery,
            signal_type="github.delivery.dead_lettered",
            severity="warning",
            value={"error_detail": error_detail},
        )
        self.session.flush()

    def _persist_new_delivery(self, delivery: WebhookDelivery) -> None:
        self.session.add(delivery)
        self.session.flush()

    def _register_duplicate(
        self,
        *,
        delivery: WebhookDelivery,
        github_delivery_guid: str,
        payload_hash: str,
    ) -> GitHubWebhookIntakeResult:
        delivery.delivery_attempts += 1
        if delivery.payload_hash and delivery.payload_hash != payload_hash:
            delivery.status = "dead-letter"
            delivery.error_detail = "Delivery GUID was reused with a different payload hash."
            delivery.processed_at = _now()
            self._record_signal(
                delivery=delivery,
                signal_type="github.delivery.hash_mismatch",
                severity="warning",
                value={
                    "github_delivery_guid": github_delivery_guid,
                    "delivery_attempts": delivery.delivery_attempts,
                },
            )
        else:
            self._record_signal(
                delivery=delivery,
                signal_type="github.delivery.duplicate",
                severity="info",
                value={
                    "github_delivery_guid": github_delivery_guid,
                    "delivery_attempts": delivery.delivery_attempts,
                },
            )
        self.session.flush()
        return GitHubWebhookIntakeResult(delivery=delivery, duplicate=True)

    def _record_signal(
        self,
        *,
        delivery: WebhookDelivery,
        signal_type: str,
        severity: str,
        value: dict[str, Any],
    ) -> None:
        signal = OperationalSignal(
            target_kind="webhook_delivery",
            target_id=_delivery_signal_target(delivery),
            signal_type=signal_type,
            severity=severity,
            value=signal_value_with_correlation(value, delivery_signal_correlation(delivery)),
            source_kind="github",
        )
        self.session.add(signal)
        self.session.flush()
