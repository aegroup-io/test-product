from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Callable
from uuid import UUID

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from agent_core_platform_api.github_integration import (
    GitHubAppAuthError,
    GitHubAppConfigError,
    GitHubPATAuthService,
    GitHubWebhookProcessingError,
)
from agent_core_platform_api.models import (
    GitHubProjectFieldMirror,
    GitHubProjectFieldOptionMirror,
    GitHubProjectItemMirror,
    GitHubProjectMirror,
    OperationalSignal,
    Product,
    PullRequestMirror,
    RepositoryBinding,
    WorkItem,
)
from agent_core_platform_api.observability import product_signal_correlation, signal_value_with_correlation
from agent_core_platform_api.product_contract import ProductSetupDiagnostic
from agent_core_platform_api.work_item_normalization import WorkItemNormalizationService


ISSUE_REFERENCE_RE = re.compile(r"(?<![\w/])#(?P<number>\d+)\b")
CONTRACT_REFRESH_PENDING_CODE = "github.contract_refresh_pending"
RECOVERABLE = "recoverable drift"
MIRROR_WEBHOOK_UNAVAILABLE_CODE = "github.webhook.unavailable"
MIRROR_WEBHOOK_PROVISION_FAILED_CODE = "github.webhook.provision_failed"
MIRROR_DIAGNOSTIC_CODES = frozenset(
    {
        MIRROR_WEBHOOK_UNAVAILABLE_CODE,
        MIRROR_WEBHOOK_PROVISION_FAILED_CODE,
    }
)
REPOSITORY_ISSUES_PER_PAGE = 100

ISSUE_NODE_QUERY = """
query OrchaIssueNode($id: ID!) {
  node(id: $id) {
    ... on Issue {
      id
      number
      title
      body
      state
      closedAt
      labels(first: 50) { nodes { name } }
      assignees(first: 20) { nodes { login } }
      blockedBy(first: 20) {
        nodes {
          id
          number
          state
          closedAt
        }
      }
      issueDependenciesSummary {
        blockedBy
        totalBlockedBy
        blocking
        totalBlocking
      }
      closedByPullRequestsReferences(first: 20, includeClosedPrs: true, userLinkedOnly: false) {
        nodes {
          id
          number
          title
          body
          state
          isDraft
          reviewDecision
          mergeStateStatus
          headRefName
          baseRefName
          mergedAt
          closedAt
        }
      }
      timelineItems(first: 20, itemTypes: [CROSS_REFERENCED_EVENT]) {
        nodes {
          __typename
          ... on CrossReferencedEvent {
            willCloseTarget
            source {
              __typename
              ... on PullRequest {
                id
                number
                title
                body
                state
                isDraft
                reviewDecision
                mergeStateStatus
                headRefName
                baseRefName
                mergedAt
                closedAt
              }
            }
          }
        }
      }
      repository {
        id
        name
        visibility
        description
        isArchived
        owner { login }
        defaultBranchRef { name }
      }
    }
  }
}
""".strip()

ISSUE_BY_NUMBER_QUERY = """
query OrchaIssueByNumber($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      id
      number
      title
      body
      state
      closedAt
      labels(first: 50) { nodes { name } }
      assignees(first: 20) { nodes { login } }
      blockedBy(first: 20) {
        nodes {
          id
          number
          state
          closedAt
        }
      }
      issueDependenciesSummary {
        blockedBy
        totalBlockedBy
        blocking
        totalBlocking
      }
      closedByPullRequestsReferences(first: 20, includeClosedPrs: true, userLinkedOnly: false) {
        nodes {
          id
          number
          title
          body
          state
          isDraft
          reviewDecision
          mergeStateStatus
          headRefName
          baseRefName
          mergedAt
          closedAt
        }
      }
      timelineItems(first: 20, itemTypes: [CROSS_REFERENCED_EVENT]) {
        nodes {
          __typename
          ... on CrossReferencedEvent {
            willCloseTarget
            source {
              __typename
              ... on PullRequest {
                id
                number
                title
                body
                state
                isDraft
                reviewDecision
                mergeStateStatus
                headRefName
                baseRefName
                mergedAt
                closedAt
              }
            }
          }
        }
      }
      repository {
        id
        name
        visibility
        description
        isArchived
        owner { login }
        defaultBranchRef { name }
      }
    }
  }
}
""".strip()

PULL_REQUEST_NODE_QUERY = """
query OrchaPullRequestNode($id: ID!) {
  node(id: $id) {
    ... on PullRequest {
      id
      number
      title
      body
      state
      isDraft
      reviewDecision
      mergeStateStatus
      headRefName
      baseRefName
      mergedAt
      closedAt
      closingIssuesReferences(first: 20, userLinkedOnly: false) {
        nodes {
          id
          number
        }
      }
      repository {
        id
        name
        visibility
        description
        isArchived
        owner { login }
        defaultBranchRef { name }
      }
    }
  }
}
""".strip()

PROJECT_NODE_QUERY = """
query OrchaProjectNode($id: ID!, $after: String) {
  node(id: $id) {
    ... on ProjectV2 {
      id
      number
      title
      fields(first: 50, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          ... on ProjectV2SingleSelectField {
            id
            name
            dataType
            options { id name color }
          }
          ... on ProjectV2Field {
            id
            name
            dataType
          }
        }
      }
    }
  }
}
""".strip()

PROJECT_ITEMS_QUERY = """
query OrchaProjectItems($id: ID!, $after: String) {
  node(id: $id) {
    ... on ProjectV2 {
      items(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          type
          content {
            __typename
            ... on Issue { id }
            ... on PullRequest { id }
          }
          fieldValues(first: 50) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                optionId
                updatedAt
                field {
                  ... on ProjectV2FieldCommon {
                    id
                    name
                    dataType
                  }
                }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                updatedAt
                field {
                  ... on ProjectV2FieldCommon {
                    id
                    name
                    dataType
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
""".strip()

PROJECT_ITEM_FIELD_VALUES_QUERY = """
query OrchaProjectItemFieldValues($id: ID!, $after: String) {
  node(id: $id) {
    ... on ProjectV2Item {
      fieldValues(first: 50, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          ... on ProjectV2ItemFieldSingleSelectValue {
            name
            optionId
            updatedAt
            field {
              ... on ProjectV2FieldCommon {
                id
                name
                dataType
              }
            }
          }
          ... on ProjectV2ItemFieldTextValue {
            text
            updatedAt
            field {
              ... on ProjectV2FieldCommon {
                id
                name
                dataType
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProductMirrorRefreshResult:
    issue_count: int = 0
    project_item_count: int = 0
    webhook_status: str = "skipped"
    webhook_delivery_url: str | None = None
    diagnostics: list[ProductSetupDiagnostic] = field(default_factory=list)


def _classify_setup_state(diagnostics_payload: list[dict[str, Any]]) -> str:
    classifications = {
        str(item.get("classification", "")).strip().lower()
        for item in diagnostics_payload
        if isinstance(item, dict)
    }
    if "blocking setup error" in classifications:
        return "setup-needed"
    if RECOVERABLE in classifications:
        return "drift"
    if "advisory warning" in classifications:
        return "advisory"
    return "ready"


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return None
    return normalized.casefold()


def _normalize_names(values: list[str]) -> list[str]:
    return sorted({value.strip().casefold() for value in values if value.strip()})


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_nodes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if isinstance(value.get("nodes"), list):
            return [item for item in value["nodes"] if isinstance(item, dict)]
        if isinstance(value.get("items"), list):
            return [item for item in value["items"] if isinstance(item, dict)]
        if isinstance(value.get("edges"), list):
            return [
                edge["node"]
                for edge in value["edges"]
                if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
            ]
    return []


def _page_info(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        page_info = value.get("pageInfo")
        if isinstance(page_info, dict):
            return page_info
    return {}


def _repository_owner(repository_payload: dict[str, Any]) -> str | None:
    owner = repository_payload.get("owner")
    if isinstance(owner, dict):
        login = owner.get("login")
        if isinstance(login, str) and login.strip():
            return login.strip()
    if isinstance(owner, str) and owner.strip():
        return owner.strip()
    return None


def _repository_default_branch(repository_payload: dict[str, Any]) -> str | None:
    default_branch = repository_payload.get("default_branch")
    if isinstance(default_branch, str) and default_branch.strip():
        return default_branch.strip()
    default_branch_ref = repository_payload.get("defaultBranchRef")
    if isinstance(default_branch_ref, dict):
        name = default_branch_ref.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _field_options(field_payload: dict[str, Any]) -> list[dict[str, Any]]:
    options = field_payload.get("options")
    if isinstance(options, list):
        return [item for item in options if isinstance(item, dict)]
    return []


def _project_status_name(status_field_name: str, field_values: list[dict[str, Any]]) -> str | None:
    for field_value in field_values:
        if field_value.get("field_name") != status_field_name:
            continue
        candidate = field_value.get("value")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _normalize_field_values(field_values_payload: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for field_value in _extract_nodes(field_values_payload):
        field_payload = field_value.get("field")
        field_name = None
        field_node_id = None
        data_type = None
        if isinstance(field_payload, dict):
            field_name = field_payload.get("name")
            field_node_id = field_payload.get("id") or field_payload.get("node_id")
            data_type = field_payload.get("dataType") or field_payload.get("data_type")
        value = field_value.get("value")
        if value is None:
            value = field_value.get("name")
        if value is None:
            value = field_value.get("text")
        normalized.append(
            {
                "field_node_id": str(field_value.get("field_node_id") or field_node_id or ""),
                "field_name": str(field_value.get("field_name") or field_name or "").strip(),
                "data_type": str(field_value.get("data_type") or data_type or "").strip(),
                "value": value,
                "option_id": field_value.get("option_id") or field_value.get("optionId"),
                "updated_at": field_value.get("updated_at") or field_value.get("updatedAt"),
            }
        )
    return [item for item in normalized if item["field_name"]]


def _linked_issue_numbers(*texts: str | None) -> list[int]:
    numbers: set[int] = set()
    for text in texts:
        if not text:
            continue
        for match in ISSUE_REFERENCE_RE.finditer(text):
            numbers.add(int(match.group("number")))
    return sorted(numbers)


def _linked_issue_numbers_from_pull_request_payload(
    title: str | None,
    body: str | None,
    pull_request_payload: dict[str, Any],
) -> list[int]:
    numbers = set(_linked_issue_numbers(title, body))
    for issue_payload in _extract_nodes(pull_request_payload.get("closingIssuesReferences")):
        issue_number = issue_payload.get("number")
        if isinstance(issue_number, int):
            numbers.add(issue_number)
    return sorted(numbers)


def _issue_pull_request_node_ids(issue_payload: dict[str, Any]) -> list[str]:
    node_ids: set[str] = set()
    for pull_request_payload in _extract_nodes(issue_payload.get("closedByPullRequestsReferences")):
        node_id = pull_request_payload.get("id") or pull_request_payload.get("node_id")
        if isinstance(node_id, str) and node_id:
            node_ids.add(node_id)
    for event in _extract_nodes(issue_payload.get("timelineItems")):
        if event.get("__typename") != "CrossReferencedEvent":
            continue
        source = event.get("source")
        if not isinstance(source, dict) or source.get("__typename") != "PullRequest":
            continue
        node_id = source.get("id") or source.get("node_id")
        if isinstance(node_id, str) and node_id:
            node_ids.add(node_id)
    return sorted(node_ids)


def _graphql_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return response.text.strip() or f"GitHub GraphQL request failed with status {response.status_code}."


def _work_item_default_status(work_item: WorkItem) -> str:
    raw_payload = work_item.raw_payload if isinstance(work_item.raw_payload, dict) else {}
    state = raw_payload.get("state")
    if work_item.closed_at is not None or str(state or "").lower() == "closed":
        return "Done"
    return "Triage"


class GitHubMirrorService:
    def __init__(self, session: Session):
        self.session = session
        self.auth = GitHubPATAuthService(session)

    def _record_rate_limit(self, *, owner: str, repo: str, response: httpx.Response) -> None:
        self.auth.record_repository_rate_limit_signal(owner=owner, repo=repo, response=response)

    def get_work_item_by_node_id(self, github_issue_node_id: str) -> WorkItem | None:
        return (
            self.session.query(WorkItem)
            .filter(WorkItem.github_issue_node_id == github_issue_node_id)
            .first()
        )

    def get_pull_request_by_node_id(self, github_pr_node_id: str) -> PullRequestMirror | None:
        return (
            self.session.query(PullRequestMirror)
            .filter(PullRequestMirror.github_pr_node_id == github_pr_node_id)
            .first()
        )

    def get_project_by_node_id(self, github_project_node_id: str) -> GitHubProjectMirror | None:
        return (
            self.session.query(GitHubProjectMirror)
            .populate_existing()
            .options(
                selectinload(GitHubProjectMirror.fields).selectinload(GitHubProjectFieldMirror.options),
                selectinload(GitHubProjectMirror.items),
            )
            .filter(GitHubProjectMirror.github_project_node_id == github_project_node_id)
            .first()
        )

    def refresh_product_mirror(
        self,
        *,
        product_id: UUID,
        ensure_webhook: bool = False,
        http_get: Callable[..., httpx.Response] | None = None,
        http_post: Callable[..., httpx.Response] | None = None,
        http_patch: Callable[..., httpx.Response] | None = None,
    ) -> ProductMirrorRefreshResult:
        http_get = http_get or httpx.get
        http_post = http_post or httpx.post
        http_patch = http_patch or httpx.patch

        product = self.session.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product not found: {product_id}")
        repository_binding = self._resolve_product_repository(product)
        if repository_binding is None:
            raise ValueError("Primary repository binding not found for the product mirror refresh.")

        result = ProductMirrorRefreshResult()
        token, api_base_url, _ = self.auth.load_repository_token(
            owner=repository_binding.owner,
            repo=repository_binding.name,
            org_id=product.org_id,
        )
        if ensure_webhook:
            try:
                webhook_result = self.auth.ensure_repository_webhook(
                    owner=repository_binding.owner,
                    repo=repository_binding.name,
                    org_id=product.org_id,
                    http_get=http_get,
                    http_post=http_post,
                    http_patch=http_patch,
                )
                result.webhook_status = webhook_result.status
                result.webhook_delivery_url = webhook_result.delivery_url
            except GitHubAppConfigError as exc:
                result.webhook_status = "unavailable"
                result.diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=RECOVERABLE,
                        code=MIRROR_WEBHOOK_UNAVAILABLE_CODE,
                        message=str(exc),
                        path=".github/webhooks",
                    )
                )
            except GitHubAppAuthError as exc:
                result.webhook_status = "failed"
                result.diagnostics.append(
                    ProductSetupDiagnostic(
                        classification=RECOVERABLE,
                        code=MIRROR_WEBHOOK_PROVISION_FAILED_CODE,
                        message=(
                            "GitHub webhook provisioning failed for "
                            f"`{repository_binding.owner}/{repository_binding.name}`: {exc}"
                        ),
                        path=".github/webhooks",
                    )
                )

        project = self._resolve_product_project(product)
        if project is not None and isinstance(project.github_project_node_id, str) and project.github_project_node_id.strip():
            project_payload = self._fetch_project_snapshot(
                github_project_node_id=project.github_project_node_id,
                token=token,
                api_base_url=api_base_url,
                http_post=http_post,
                owner=repository_binding.owner,
                repo=repository_binding.name,
            )
            result.project_item_count = len(_extract_nodes(project_payload.get("items")))
            project = self.upsert_project_snapshot(project_payload)
            WorkItemNormalizationService(self.session).normalize_for_project(
                project,
                mirror_service=self,
                allow_repair=False,
            )

        issue_numbers = self._list_repository_issue_numbers(
            owner=repository_binding.owner,
            repo=repository_binding.name,
            token=token,
            api_base_url=api_base_url,
            http_get=http_get,
        )
        normalizer = WorkItemNormalizationService(self.session)
        for issue_number in issue_numbers:
            issue_payload = self._fetch_issue_by_number(
                owner=repository_binding.owner,
                repo=repository_binding.name,
                issue_number=issue_number,
                http_post=http_post,
                token=token,
                api_base_url=api_base_url,
            )
            repository_payload = issue_payload.get("repository")
            if isinstance(repository_payload, dict):
                repository_binding = self.upsert_repository(repository_payload) or repository_binding
            work_item = self.upsert_issue(repository_binding, issue_payload)
            normalizer.normalize_work_item(work_item, mirror_service=self, allow_repair=False)
        result.issue_count = len(issue_numbers)

        self._apply_product_mirror_diagnostics(product, result.diagnostics, clear_existing=ensure_webhook)
        self._record_product_mirror_signal(product, repository_binding, result)
        self.session.flush()
        return result

    def process_delivery(self, _: Session, delivery) -> None:
        payload = delivery.payload_json
        if not isinstance(payload, dict):
            raise GitHubWebhookProcessingError("Webhook payload must decode into a JSON object.")
        normalizer = WorkItemNormalizationService(self.session)

        event_name = delivery.event_name
        if event_name == "installation":
            return

        repository_payload = payload.get("repository")
        repository_binding = None
        if isinstance(repository_payload, dict):
            repository_binding = self.upsert_repository(repository_payload)

        if event_name == "push":
            if repository_binding is not None and self._push_targets_default_branch(payload, repository_binding):
                self._schedule_contract_refresh(
                    repository_binding,
                    delivery=delivery,
                    trigger="push.default_branch",
                    message=(
                        "Default-branch push may have changed product contract or setup assets. "
                        "Run product refresh for this repository."
                    ),
                )
            return

        if event_name == "repository":
            refresh_reason = self._repository_refresh_reason(payload)
            if repository_binding is not None and refresh_reason is not None:
                self._schedule_contract_refresh(
                    repository_binding,
                    delivery=delivery,
                    trigger="repository.default_branch",
                    message=refresh_reason,
                )
            return

        if event_name == "issues":
            if repository_binding is None:
                return
            issue_payload = payload.get("issue")
            if not isinstance(issue_payload, dict):
                raise GitHubWebhookProcessingError("Issue webhook payload is missing the `issue` object.")
            work_item = self.upsert_issue(repository_binding, issue_payload)
            normalizer.normalize_work_item(
                work_item,
                mirror_service=self,
            )
            return

        if event_name == "pull_request":
            if repository_binding is None:
                return
            pull_request_payload = payload.get("pull_request")
            if not isinstance(pull_request_payload, dict):
                raise GitHubWebhookProcessingError("Pull request webhook payload is missing the `pull_request` object.")
            pull_request = self.upsert_pull_request(repository_binding, pull_request_payload)
            normalizer.normalize_for_pull_request(
                pull_request,
                mirror_service=self,
            )
            return

        if event_name == "projects_v2_item":
            project_payload = payload.get("project")
            if not isinstance(project_payload, dict):
                raise GitHubWebhookProcessingError("Project item webhook payload is missing the `project` object.")
            project = self.upsert_project_snapshot(project_payload)
            normalizer.normalize_for_project(
                project,
                mirror_service=self,
            )
            return

    def _push_targets_default_branch(self, payload: dict[str, Any], repository_binding: RepositoryBinding) -> bool:
        ref = payload.get("ref")
        if not isinstance(ref, str) or not ref.strip():
            return False
        default_branch = repository_binding.default_branch.strip()
        if not default_branch:
            return False
        return ref.strip() == f"refs/heads/{default_branch}"

    def _repository_refresh_reason(self, payload: dict[str, Any]) -> str | None:
        action = payload.get("action")
        changes = payload.get("changes")
        if (
            isinstance(changes, dict)
            and isinstance(changes.get("default_branch"), dict)
        ):
            previous = changes["default_branch"].get("from")
            if isinstance(previous, str) and previous.strip():
                return (
                    "Repository default branch changed from "
                    f"`{previous.strip()}`; product contract/setup should be refreshed."
                )
            return "Repository default branch changed; product contract/setup should be refreshed."
        if isinstance(action, str) and action.strip().lower() == "edited":
            return (
                "Repository metadata changed and may affect contract/setup projection. "
                "Run product refresh for this repository."
            )
        return None

    def _schedule_contract_refresh(
        self,
        repository_binding: RepositoryBinding,
        *,
        delivery,
        trigger: str,
        message: str,
    ) -> None:
        product = self.session.get(Product, repository_binding.product_id)
        if product is None:
            return

        diagnostics = [item for item in (product.setup_diagnostics or []) if isinstance(item, dict)]
        diagnostic_payload = {
            "classification": RECOVERABLE,
            "code": CONTRACT_REFRESH_PENDING_CODE,
            "message": message,
            "path": ".orcha/product.yaml",
        }
        replaced = False
        for index, diagnostic in enumerate(diagnostics):
            if diagnostic.get("code") != CONTRACT_REFRESH_PENDING_CODE:
                continue
            diagnostics[index] = diagnostic_payload
            replaced = True
            break
        if not replaced:
            diagnostics.append(diagnostic_payload)
        product.setup_diagnostics = diagnostics
        if product.setup_state != "setup-needed":
            product.setup_state = "drift"

        signal_value = signal_value_with_correlation(
            {
                "trigger": trigger,
                "delivery_id": str(delivery.delivery_id),
                "github_delivery_guid": delivery.github_delivery_guid,
                "event_name": delivery.event_name,
                "repository": f"{repository_binding.owner}/{repository_binding.name}",
                "default_branch": repository_binding.default_branch,
                "message": message,
            },
            product_signal_correlation(product),
        )
        self.session.add(
            OperationalSignal(
                target_kind="product",
                target_id=str(product.product_id),
                signal_type="github.contract_refresh_scheduled",
                severity="warning",
                value=signal_value,
                source_kind="github",
            )
        )
        self.session.flush()

    def upsert_repository(self, repository_payload: dict[str, Any]) -> RepositoryBinding | None:
        owner = _repository_owner(repository_payload)
        name = repository_payload.get("name")
        if not isinstance(name, str) or not name.strip() or owner is None:
            return None
        github_repository_node_id = repository_payload.get("node_id") or repository_payload.get("id")
        binding = None
        if github_repository_node_id:
            binding = (
                self.session.query(RepositoryBinding)
                .filter(RepositoryBinding.github_repository_node_id == str(github_repository_node_id))
                .first()
            )
        if binding is None:
            binding = (
                self.session.query(RepositoryBinding)
                .filter(
                    RepositoryBinding.owner == owner,
                    RepositoryBinding.name == name.strip(),
                )
                .first()
            )
        if binding is None:
            return None

        binding.github_repository_node_id = (
            str(github_repository_node_id)
            if github_repository_node_id
            else binding.github_repository_node_id
        )
        binding.owner = owner
        binding.name = name.strip()
        binding.default_branch = _repository_default_branch(repository_payload) or binding.default_branch
        visibility = repository_payload.get("visibility")
        if isinstance(visibility, str) and visibility.strip():
            binding.visibility = visibility.strip().lower()
        description = repository_payload.get("description")
        binding.description = description.strip() if isinstance(description, str) and description.strip() else None
        binding.is_archived = bool(repository_payload.get("archived") or repository_payload.get("isArchived") or False)
        binding.raw_payload = dict(repository_payload)
        self.session.flush()
        return binding

    def upsert_issue(self, repository_binding: RepositoryBinding, issue_payload: dict[str, Any]) -> WorkItem:
        github_issue_node_id = issue_payload.get("node_id") or issue_payload.get("id")
        issue_number = issue_payload.get("number")
        if not github_issue_node_id or not isinstance(issue_number, int):
            raise GitHubWebhookProcessingError("Issue payload is missing a canonical node id or issue number.")

        work_item = (
            self.session.query(WorkItem)
            .filter(
                or_(
                    WorkItem.github_issue_node_id == str(github_issue_node_id),
                    (WorkItem.repo_id == repository_binding.repo_id) & (WorkItem.issue_number == issue_number),
                )
            )
            .first()
        )
        if work_item is None:
            work_item = WorkItem(
                repo_id=repository_binding.repo_id,
                github_issue_node_id=str(github_issue_node_id),
                issue_number=issue_number,
                title="",
                status="Triage",
            )
            self.session.add(work_item)

        title = issue_payload.get("title")
        body = issue_payload.get("body")
        work_item.github_issue_node_id = str(github_issue_node_id)
        work_item.issue_number = issue_number
        work_item.title = title.strip() if isinstance(title, str) and title.strip() else f"Issue {issue_number}"
        work_item.body = body if isinstance(body, str) else None
        work_item.title_normalized = _normalize_text(work_item.title)
        work_item.body_normalized = _normalize_text(work_item.body)
        work_item.labels = _normalize_names(
            [str(label.get("name", "")).strip() for label in _extract_nodes(issue_payload.get("labels"))]
        )
        work_item.assignees = _normalize_names(
            [str(assignee.get("login", "")).strip() for assignee in _extract_nodes(issue_payload.get("assignees"))]
        )
        work_item.status = "Closed" if str(issue_payload.get("state", "")).lower() == "closed" else (work_item.status or "Triage")
        work_item.closed_at = _coerce_datetime(issue_payload.get("closed_at") or issue_payload.get("closedAt"))
        work_item.raw_payload = dict(issue_payload)
        self.session.flush()
        self._sync_issue_pull_request_links(repository_binding, work_item)

        project_items = (
            self.session.query(GitHubProjectItemMirror)
            .filter(GitHubProjectItemMirror.github_content_node_id == work_item.github_issue_node_id)
            .all()
        )
        for project_item in project_items:
            project_item.work_item = work_item
            work_item.project_id = project_item.project_id
            if project_item.status_name and str(issue_payload.get("state", "")).lower() != "closed":
                work_item.status = project_item.status_name
        self.session.flush()
        return work_item

    def upsert_pull_request(self, repository_binding: RepositoryBinding, pull_request_payload: dict[str, Any]) -> PullRequestMirror:
        github_pr_node_id = pull_request_payload.get("node_id") or pull_request_payload.get("id")
        number = pull_request_payload.get("number")
        if not github_pr_node_id or not isinstance(number, int):
            raise GitHubWebhookProcessingError("Pull request payload is missing a canonical node id or PR number.")

        pull_request = (
            self.session.query(PullRequestMirror)
            .filter(
                or_(
                    PullRequestMirror.github_pr_node_id == str(github_pr_node_id),
                    (PullRequestMirror.repo_id == repository_binding.repo_id) & (PullRequestMirror.number == number),
                )
            )
            .first()
        )
        if pull_request is None:
            pull_request = PullRequestMirror(
                repo_id=repository_binding.repo_id,
                github_pr_node_id=str(github_pr_node_id),
                number=number,
                title="",
            )
            self.session.add(pull_request)

        title = pull_request_payload.get("title")
        body = pull_request_payload.get("body")
        pull_request.github_pr_node_id = str(github_pr_node_id)
        pull_request.number = number
        pull_request.title = title.strip() if isinstance(title, str) and title.strip() else f"PR {number}"
        pull_request.body = body if isinstance(body, str) else None
        pull_request.body_normalized = _normalize_text(pull_request.body)
        state = pull_request_payload.get("state")
        if isinstance(state, str) and state.strip():
            pull_request.state = state.strip().lower()
        pull_request.is_draft = bool(pull_request_payload.get("draft") or pull_request_payload.get("isDraft") or False)
        head_branch = pull_request_payload.get("head_branch") or pull_request_payload.get("headRefName")
        base_branch = pull_request_payload.get("base_branch") or pull_request_payload.get("baseRefName")
        pull_request.head_branch = head_branch.strip() if isinstance(head_branch, str) and head_branch.strip() else None
        pull_request.base_branch = base_branch.strip() if isinstance(base_branch, str) and base_branch.strip() else None
        checks_rollup = pull_request_payload.get("checks_rollup") or pull_request_payload.get("statusCheckRollup")
        pull_request.checks_rollup = dict(checks_rollup) if isinstance(checks_rollup, dict) else {}
        review_state = pull_request_payload.get("review_state") or pull_request_payload.get("reviewDecision")
        pull_request.review_state = review_state.strip() if isinstance(review_state, str) and review_state.strip() else None
        merge_state = pull_request_payload.get("merge_state") or pull_request_payload.get("mergeStateStatus")
        pull_request.merge_state = merge_state.strip() if isinstance(merge_state, str) and merge_state.strip() else None
        pull_request.closed_at = _coerce_datetime(pull_request_payload.get("closed_at") or pull_request_payload.get("closedAt"))
        pull_request.merged_at = _coerce_datetime(pull_request_payload.get("merged_at") or pull_request_payload.get("mergedAt"))
        pull_request.raw_payload = dict(pull_request_payload)

        self._sync_pull_request_issue_links(repository_binding, pull_request)

        project_items = (
            self.session.query(GitHubProjectItemMirror)
            .filter(GitHubProjectItemMirror.github_content_node_id == pull_request.github_pr_node_id)
            .all()
        )
        for project_item in project_items:
            project_item.pull_request = pull_request

        self.session.flush()
        return pull_request

    def upsert_project_snapshot(self, project_payload: dict[str, Any]) -> GitHubProjectMirror:
        github_project_node_id = project_payload.get("node_id") or project_payload.get("id")
        number = project_payload.get("number")
        project = None
        if github_project_node_id:
            project = (
                self.session.query(GitHubProjectMirror)
                .filter(GitHubProjectMirror.github_project_node_id == str(github_project_node_id))
                .first()
            )
        if project is None and isinstance(number, int):
            matches = (
                self.session.query(GitHubProjectMirror)
                .filter(GitHubProjectMirror.number == number)
                .all()
            )
            if len(matches) == 1:
                project = matches[0]
        if project is None:
            raise GitHubWebhookProcessingError("Project payload could not be matched to a registered product project.")

        project.github_project_node_id = (
            str(github_project_node_id)
            if github_project_node_id
            else project.github_project_node_id
        )
        if isinstance(number, int):
            project.number = number
        title = project_payload.get("title")
        if isinstance(title, str) and title.strip():
            project.title = title.strip()
        project.status_field_name = self._status_field_name(project_payload) or project.status_field_name
        project.status_options = self._status_options(project_payload) or list(project.status_options or [])
        project.raw_payload = dict(project_payload)
        project.last_reconciled_at = _now()

        self._sync_project_fields(project, project_payload)
        self._sync_project_items(project, project_payload)
        self.session.flush()
        self._reconcile_project_work_items(project)
        self.session.flush()
        return project

    def repair_issue(
        self,
        *,
        github_issue_node_id: str,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> WorkItem:
        http_post = http_post or httpx.post
        existing_work_item = self.get_work_item_by_node_id(github_issue_node_id)
        if existing_work_item is None:
            raise ValueError(f"GitHub object not found for node id: {github_issue_node_id}")
        repository_binding = self.session.get(RepositoryBinding, existing_work_item.repo_id)
        if repository_binding is None:
            raise ValueError("Repository binding not found for the repaired issue.")
        token, api_base_url = self._load_repository_auth(owner=repository_binding.owner, repo=repository_binding.name)
        issue_payload = self._fetch_node(
            query=ISSUE_NODE_QUERY,
            node_id=github_issue_node_id,
            http_post=http_post,
            owner=repository_binding.owner,
            repo=repository_binding.name,
            token=token,
            api_base_url=api_base_url,
        )
        repository_payload = issue_payload.get("repository")
        if not isinstance(repository_payload, dict):
            raise ValueError("GitHub issue repair response is missing the repository object.")
        repository_binding = self.upsert_repository(repository_payload)
        if repository_binding is None:
            raise ValueError("Repository binding not found for the repaired issue.")
        work_item = self.upsert_issue(repository_binding, issue_payload)
        WorkItemNormalizationService(self.session).normalize_work_item(work_item, allow_repair=False)
        return work_item

    def repair_issue_by_number(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> WorkItem:
        http_post = http_post or httpx.post
        issue_payload = self._fetch_issue_by_number(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            http_post=http_post,
        )
        repository_payload = issue_payload.get("repository")
        if not isinstance(repository_payload, dict):
            raise ValueError("GitHub issue repair response is missing the repository object.")
        repository_binding = self.upsert_repository(repository_payload)
        if repository_binding is None:
            raise ValueError("Repository binding not found for the repaired issue.")
        work_item = self.upsert_issue(repository_binding, issue_payload)
        WorkItemNormalizationService(self.session).normalize_work_item(work_item, allow_repair=False)
        return work_item

    def repair_pull_request(
        self,
        *,
        github_pr_node_id: str,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> PullRequestMirror:
        http_post = http_post or httpx.post
        existing_pull_request = self.get_pull_request_by_node_id(github_pr_node_id)
        if existing_pull_request is None:
            raise ValueError(f"GitHub object not found for node id: {github_pr_node_id}")
        repository_binding = self.session.get(RepositoryBinding, existing_pull_request.repo_id)
        if repository_binding is None:
            raise ValueError("Repository binding not found for the repaired pull request.")
        token, api_base_url = self._load_repository_auth(owner=repository_binding.owner, repo=repository_binding.name)
        pull_request_payload = self._fetch_node(
            query=PULL_REQUEST_NODE_QUERY,
            node_id=github_pr_node_id,
            http_post=http_post,
            owner=repository_binding.owner,
            repo=repository_binding.name,
            token=token,
            api_base_url=api_base_url,
        )
        repository_payload = pull_request_payload.get("repository")
        if not isinstance(repository_payload, dict):
            raise ValueError("GitHub pull request repair response is missing the repository object.")
        repository_binding = self.upsert_repository(repository_payload)
        if repository_binding is None:
            raise ValueError("Repository binding not found for the repaired pull request.")
        pull_request = self.upsert_pull_request(repository_binding, pull_request_payload)
        WorkItemNormalizationService(self.session).normalize_for_pull_request(
            pull_request,
            mirror_service=self,
            allow_repair=False,
        )
        return pull_request

    def repair_project(
        self,
        *,
        github_project_node_id: str,
        http_post: Callable[..., httpx.Response] | None = None,
    ) -> GitHubProjectMirror:
        http_post = http_post or httpx.post
        existing_project = self.get_project_by_node_id(github_project_node_id)
        if existing_project is None:
            raise ValueError(f"GitHub object not found for node id: {github_project_node_id}")
        repository_binding = self._resolve_project_repository(existing_project)
        if repository_binding is None:
            raise ValueError("Repository binding not found for the repaired project.")
        token, api_base_url = self._load_repository_auth(owner=repository_binding.owner, repo=repository_binding.name)
        project_payload = self._fetch_project_snapshot(
            github_project_node_id=github_project_node_id,
            token=token,
            api_base_url=api_base_url,
            http_post=http_post,
            owner=repository_binding.owner,
            repo=repository_binding.name,
        )
        project = self.upsert_project_snapshot(project_payload)
        WorkItemNormalizationService(self.session).normalize_for_project(
            project,
            mirror_service=self,
            allow_repair=False,
        )
        return project

    def _load_repository_auth(self, *, owner: str, repo: str) -> tuple[str, str]:
        token, api_base_url, _ = self.auth.load_repository_token(owner=owner, repo=repo)
        return token, api_base_url

    def _resolve_product_repository(self, product: Product) -> RepositoryBinding | None:
        if product.primary_repo_id is not None:
            repository_binding = self.session.get(RepositoryBinding, product.primary_repo_id)
            if repository_binding is not None:
                return repository_binding
        return (
            self.session.query(RepositoryBinding)
            .filter(RepositoryBinding.product_id == product.product_id)
            .order_by(RepositoryBinding.created_at.asc())
            .first()
        )

    def _resolve_product_project(self, product: Product) -> GitHubProjectMirror | None:
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

    def _apply_product_mirror_diagnostics(
        self,
        product: Product,
        diagnostics: list[ProductSetupDiagnostic],
        *,
        clear_existing: bool,
    ) -> None:
        existing_payload = [
            item
            for item in (product.setup_diagnostics or [])
            if isinstance(item, dict)
        ]
        if clear_existing:
            existing_payload = [
                item
                for item in existing_payload
                if str(item.get("code") or "").strip() not in MIRROR_DIAGNOSTIC_CODES
            ]
        existing_payload.extend(item.model_dump() for item in diagnostics)
        product.setup_diagnostics = existing_payload
        product.setup_state = _classify_setup_state(existing_payload)

    def _record_product_mirror_signal(
        self,
        product: Product,
        repository_binding: RepositoryBinding,
        result: ProductMirrorRefreshResult,
    ) -> None:
        self.session.add(
            OperationalSignal(
                target_kind="product",
                target_id=str(product.product_id),
                signal_type="github.mirror.refresh",
                severity="warning" if result.diagnostics else "info",
                value=signal_value_with_correlation(
                    {
                        "repository": f"{repository_binding.owner}/{repository_binding.name}",
                        "issue_count": result.issue_count,
                        "project_item_count": result.project_item_count,
                        "webhook_status": result.webhook_status,
                        "webhook_delivery_url": result.webhook_delivery_url,
                        "diagnostics": [item.model_dump() for item in result.diagnostics],
                    },
                    product_signal_correlation(product),
                ),
                source_kind="github",
            )
        )

    def _list_repository_issue_numbers(
        self,
        *,
        owner: str,
        repo: str,
        token: str,
        api_base_url: str,
        http_get: Callable[..., httpx.Response],
    ) -> list[int]:
        issue_numbers: set[int] = set()
        page = 1
        while True:
            response = http_get(
                f"{api_base_url.rstrip('/')}/repos/{owner}/{repo}/issues",
                headers=self.auth.build_headers(token),
                params={"state": "all", "per_page": REPOSITORY_ISSUES_PER_PAGE, "page": page},
                timeout=30,
            )
            self._record_rate_limit(owner=owner, repo=repo, response=response)
            if response.status_code >= 400:
                raise GitHubAppAuthError(_graphql_error_detail(response))
            payload = response.json()
            if not isinstance(payload, list):
                raise GitHubAppAuthError("GitHub repository issues response was malformed.")
            for item in payload:
                if not isinstance(item, dict) or "pull_request" in item:
                    continue
                issue_number = item.get("number")
                if isinstance(issue_number, int):
                    issue_numbers.add(issue_number)
            if len(payload) < REPOSITORY_ISSUES_PER_PAGE:
                break
            page += 1
        return sorted(issue_numbers)

    def _resolve_project_repository(self, project: GitHubProjectMirror) -> RepositoryBinding | None:
        product = self.session.get(Product, project.product_id)
        if product is not None and product.primary_repo_id is not None:
            primary_repo = self.session.get(RepositoryBinding, product.primary_repo_id)
            if primary_repo is not None:
                return primary_repo
        return (
            self.session.query(RepositoryBinding)
            .filter(RepositoryBinding.product_id == project.product_id)
            .order_by(RepositoryBinding.created_at.asc())
            .first()
        )

    def _fetch_node(
        self,
        *,
        query: str,
        node_id: str,
        http_post: Callable[..., httpx.Response],
        owner: str,
        repo: str,
        variables: dict[str, Any] | None = None,
        token: str | None = None,
        api_base_url: str | None = None,
    ) -> dict[str, Any]:
        if token is None or api_base_url is None:
            token, api_base_url = self._load_repository_auth(owner=owner, repo=repo)
        response = http_post(
            f"{api_base_url.rstrip('/')}/graphql",
            headers=self.auth.build_headers(token),
            json={"query": query, "variables": {"id": node_id, **(variables or {})}},
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_graphql_error_detail(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubAppAuthError("GitHub GraphQL response was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise GitHubAppAuthError("GitHub GraphQL response was malformed.")
        if payload.get("errors"):
            raise GitHubAppAuthError(_graphql_error_detail(response))
        node = payload.get("data", {}).get("node")
        if not isinstance(node, dict):
            raise ValueError(f"GitHub object not found for node id: {node_id}")
        return node

    def _fetch_issue_by_number(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        http_post: Callable[..., httpx.Response],
        token: str | None = None,
        api_base_url: str | None = None,
    ) -> dict[str, Any]:
        if token is None or api_base_url is None:
            token, api_base_url = self._load_repository_auth(owner=owner, repo=repo)
        response = http_post(
            f"{api_base_url.rstrip('/')}/graphql",
            headers=self.auth.build_headers(token),
            json={
                "query": ISSUE_BY_NUMBER_QUERY,
                "variables": {
                    "owner": owner,
                    "repo": repo,
                    "number": issue_number,
                },
            },
            timeout=30,
        )
        self._record_rate_limit(owner=owner, repo=repo, response=response)
        if response.status_code >= 400:
            raise GitHubAppAuthError(_graphql_error_detail(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubAppAuthError("GitHub GraphQL response was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise GitHubAppAuthError("GitHub GraphQL response was malformed.")
        if payload.get("errors"):
            raise GitHubAppAuthError(_graphql_error_detail(response))
        repository_payload = payload.get("data", {}).get("repository")
        issue_payload = repository_payload.get("issue") if isinstance(repository_payload, dict) else None
        if not isinstance(issue_payload, dict):
            raise ValueError(f"GitHub issue not found for {owner}/{repo}#{issue_number}")
        return issue_payload

    def _fetch_project_snapshot(
        self,
        *,
        github_project_node_id: str,
        token: str,
        api_base_url: str,
        http_post: Callable[..., httpx.Response],
        owner: str,
        repo: str,
    ) -> dict[str, Any]:
        project_payload = self._fetch_paginated_project_fields(
            github_project_node_id=github_project_node_id,
            token=token,
            api_base_url=api_base_url,
            http_post=http_post,
            owner=owner,
            repo=repo,
        )
        project_payload["items"] = self._fetch_paginated_project_items(
            github_project_node_id=github_project_node_id,
            token=token,
            api_base_url=api_base_url,
            http_post=http_post,
            owner=owner,
            repo=repo,
        )
        return project_payload

    def _fetch_paginated_project_fields(
        self,
        *,
        github_project_node_id: str,
        token: str,
        api_base_url: str,
        http_post: Callable[..., httpx.Response],
        owner: str,
        repo: str,
    ) -> dict[str, Any]:
        fields: list[dict[str, Any]] = []
        after: str | None = None
        project_payload: dict[str, Any] | None = None

        while True:
            page = self._fetch_node(
                query=PROJECT_NODE_QUERY,
                node_id=github_project_node_id,
                http_post=http_post,
                owner=owner,
                repo=repo,
                variables={"after": after},
                token=token,
                api_base_url=api_base_url,
            )
            if project_payload is None:
                project_payload = dict(page)
            fields_connection = page.get("fields")
            fields.extend(_extract_nodes(fields_connection))
            page_info = _page_info(fields_connection)
            if not page_info.get("hasNextPage"):
                break
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor:
                raise GitHubAppAuthError("GitHub project field pagination response was malformed.")
            after = end_cursor

        if project_payload is None:
            raise ValueError(f"GitHub object not found for node id: {github_project_node_id}")
        project_payload["fields"] = fields
        return project_payload

    def _fetch_paginated_project_items(
        self,
        *,
        github_project_node_id: str,
        token: str,
        api_base_url: str,
        http_post: Callable[..., httpx.Response],
        owner: str,
        repo: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        after: str | None = None

        while True:
            page = self._fetch_node(
                query=PROJECT_ITEMS_QUERY,
                node_id=github_project_node_id,
                http_post=http_post,
                owner=owner,
                repo=repo,
                variables={"after": after},
                token=token,
                api_base_url=api_base_url,
            )
            items_connection = page.get("items")
            for item_payload in _extract_nodes(items_connection):
                field_values_connection = item_payload.get("fieldValues")
                field_values = list(_extract_nodes(field_values_connection))
                item_page_info = _page_info(field_values_connection)
                if item_page_info.get("hasNextPage"):
                    item_node_id = item_payload.get("id")
                    if not isinstance(item_node_id, str) or not item_node_id:
                        raise GitHubAppAuthError("GitHub project item pagination response was malformed.")
                    end_cursor = item_page_info.get("endCursor")
                    if not isinstance(end_cursor, str) or not end_cursor:
                        raise GitHubAppAuthError("GitHub project field value pagination response was malformed.")
                    field_values.extend(
                        self._fetch_paginated_project_item_field_values(
                            github_project_item_node_id=item_node_id,
                            token=token,
                            api_base_url=api_base_url,
                            http_post=http_post,
                            owner=owner,
                            repo=repo,
                            after=end_cursor,
                        )
                    )
                item_payload["fieldValues"] = field_values
                items.append(item_payload)

            page_info = _page_info(items_connection)
            if not page_info.get("hasNextPage"):
                break
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor:
                raise GitHubAppAuthError("GitHub project item pagination response was malformed.")
            after = end_cursor

        return items

    def _fetch_paginated_project_item_field_values(
        self,
        *,
        github_project_item_node_id: str,
        token: str,
        api_base_url: str,
        http_post: Callable[..., httpx.Response],
        owner: str,
        repo: str,
        after: str,
    ) -> list[dict[str, Any]]:
        field_values: list[dict[str, Any]] = []
        next_cursor: str | None = after

        while next_cursor is not None:
            page = self._fetch_node(
                query=PROJECT_ITEM_FIELD_VALUES_QUERY,
                node_id=github_project_item_node_id,
                http_post=http_post,
                owner=owner,
                repo=repo,
                variables={"after": next_cursor},
                token=token,
                api_base_url=api_base_url,
            )
            field_values_connection = page.get("fieldValues")
            field_values.extend(_extract_nodes(field_values_connection))
            page_info = _page_info(field_values_connection)
            if not page_info.get("hasNextPage"):
                break
            end_cursor = page_info.get("endCursor")
            if not isinstance(end_cursor, str) or not end_cursor:
                raise GitHubAppAuthError("GitHub project field value pagination response was malformed.")
            next_cursor = end_cursor

        return field_values

    def _status_field_name(self, project_payload: dict[str, Any]) -> str | None:
        status_field_name = project_payload.get("status_field_name")
        if isinstance(status_field_name, str) and status_field_name.strip():
            return status_field_name.strip()
        for field_payload in _extract_nodes(project_payload.get("fields")):
            name = field_payload.get("name")
            data_type = field_payload.get("data_type") or field_payload.get("dataType")
            if isinstance(name, str) and name.strip() and str(data_type).lower() in {"single_select", "singleselect", "single select"}:
                return name.strip()
        return None

    def _status_options(self, project_payload: dict[str, Any]) -> list[str]:
        explicit = project_payload.get("status_options")
        if isinstance(explicit, list):
            return [str(item).strip() for item in explicit if str(item).strip()]
        for field_payload in _extract_nodes(project_payload.get("fields")):
            if field_payload.get("name") != self._status_field_name(project_payload):
                continue
            return [
                str(option.get("name", "")).strip()
                for option in _field_options(field_payload)
                if str(option.get("name", "")).strip()
            ]
        return []

    def _sync_project_fields(self, project: GitHubProjectMirror, project_payload: dict[str, Any]) -> None:
        seen_field_ids: set[str] = set()
        for position, field_payload in enumerate(_extract_nodes(project_payload.get("fields"))):
            github_project_field_node_id = field_payload.get("node_id") or field_payload.get("id")
            name = field_payload.get("name")
            if not github_project_field_node_id or not isinstance(name, str) or not name.strip():
                continue
            seen_field_ids.add(str(github_project_field_node_id))
            project_field = (
                self.session.query(GitHubProjectFieldMirror)
                .filter(GitHubProjectFieldMirror.github_project_field_node_id == str(github_project_field_node_id))
                .first()
            )
            if project_field is None:
                project_field = GitHubProjectFieldMirror(
                    project_id=project.project_id,
                    github_project_field_node_id=str(github_project_field_node_id),
                    name=name.strip(),
                    data_type=str(field_payload.get("data_type") or field_payload.get("dataType") or "unknown"),
                )
                self.session.add(project_field)
                self.session.flush()
            project_field.project_id = project.project_id
            project_field.name = name.strip()
            project_field.data_type = str(field_payload.get("data_type") or field_payload.get("dataType") or "unknown")
            project_field.settings_payload = {
                "position": position,
                "options_count": len(_field_options(field_payload)),
            }
            project_field.raw_payload = dict(field_payload)

            seen_option_ids: set[str] = set()
            for option_position, option_payload in enumerate(_field_options(field_payload)):
                option_id = option_payload.get("id")
                option_name = option_payload.get("name")
                if not option_id or not isinstance(option_name, str) or not option_name.strip():
                    continue
                seen_option_ids.add(str(option_id))
                option = (
                    self.session.query(GitHubProjectFieldOptionMirror)
                    .filter(
                        GitHubProjectFieldOptionMirror.project_field_id == project_field.project_field_id,
                        GitHubProjectFieldOptionMirror.github_project_option_id == str(option_id),
                    )
                    .first()
                )
                if option is None:
                    option = GitHubProjectFieldOptionMirror(
                        project_field_id=project_field.project_field_id,
                        github_project_option_id=str(option_id),
                        name=option_name.strip(),
                    )
                    self.session.add(option)
                option.name = option_name.strip()
                color = option_payload.get("color")
                option.color = color.strip() if isinstance(color, str) and color.strip() else None
                option.position = option_position
                option.raw_payload = dict(option_payload)

            stale_options = (
                self.session.query(GitHubProjectFieldOptionMirror)
                .filter(GitHubProjectFieldOptionMirror.project_field_id == project_field.project_field_id)
                .all()
            )
            for stale_option in stale_options:
                if stale_option.github_project_option_id not in seen_option_ids:
                    self.session.delete(stale_option)

        stale_fields = (
            self.session.query(GitHubProjectFieldMirror)
            .filter(GitHubProjectFieldMirror.project_id == project.project_id)
            .all()
        )
        for stale_field in stale_fields:
            if stale_field.github_project_field_node_id not in seen_field_ids:
                self.session.delete(stale_field)

    def _sync_project_items(self, project: GitHubProjectMirror, project_payload: dict[str, Any]) -> None:
        seen_item_ids: set[str] = set()
        for item_payload in _extract_nodes(project_payload.get("items")):
            github_project_item_node_id = item_payload.get("node_id") or item_payload.get("id")
            if not github_project_item_node_id:
                continue
            seen_item_ids.add(str(github_project_item_node_id))
            project_item = (
                self.session.query(GitHubProjectItemMirror)
                .filter(GitHubProjectItemMirror.github_project_item_node_id == str(github_project_item_node_id))
                .first()
            )
            if project_item is None:
                project_item = GitHubProjectItemMirror(
                    project_id=project.project_id,
                    github_project_item_node_id=str(github_project_item_node_id),
                )
                self.session.add(project_item)

            content_payload = item_payload.get("content")
            content_node_id = item_payload.get("github_content_node_id")
            content_type = item_payload.get("content_type")
            if isinstance(content_payload, dict):
                content_node_id = content_node_id or content_payload.get("node_id") or content_payload.get("id")
                content_type = content_type or content_payload.get("__typename") or content_payload.get("type")

            field_values_payload = _normalize_field_values(item_payload.get("field_values") or item_payload.get("fieldValues"))
            status_name = item_payload.get("status_name")
            if not isinstance(status_name, str) or not status_name.strip():
                status_name = _project_status_name(project.status_field_name, field_values_payload)

            project_item.project_id = project.project_id
            project_item.github_project_item_node_id = str(github_project_item_node_id)
            project_item.github_content_node_id = str(content_node_id) if content_node_id else None
            project_item.content_type = str(content_type) if content_type else None
            project_item.status_name = status_name.strip() if isinstance(status_name, str) and status_name.strip() else None
            project_item.field_values_payload = field_values_payload
            project_item.raw_payload = dict(item_payload)
            project_item.last_reconciled_at = _now()

            project_item.work_item = None
            project_item.pull_request = None
            if project_item.github_content_node_id and project_item.content_type == "Issue":
                work_item = self.get_work_item_by_node_id(project_item.github_content_node_id)
                if work_item is not None:
                    project_item.work_item = work_item
                    work_item.project_id = project.project_id
                    if project_item.status_name:
                        work_item.status = project_item.status_name
            if project_item.github_content_node_id and project_item.content_type == "PullRequest":
                project_item.pull_request = self.get_pull_request_by_node_id(project_item.github_content_node_id)

        stale_items = (
            self.session.query(GitHubProjectItemMirror)
            .filter(GitHubProjectItemMirror.project_id == project.project_id)
            .all()
        )
        for stale_item in stale_items:
            if stale_item.github_project_item_node_id not in seen_item_ids:
                self.session.delete(stale_item)

    def _sync_issue_pull_request_links(self, repository_binding: RepositoryBinding, work_item: WorkItem) -> None:
        if work_item.work_item_id is None:
            self.session.flush()
        work_item_id = str(work_item.work_item_id)
        linked_pr_node_ids: set[str] = set(
            _issue_pull_request_node_ids(work_item.raw_payload if isinstance(work_item.raw_payload, dict) else {})
        )
        pull_requests = (
            self.session.query(PullRequestMirror)
            .filter(PullRequestMirror.repo_id == repository_binding.repo_id)
            .all()
        )
        for pull_request in pull_requests:
            linked_work_item_ids = set(pull_request.linked_work_item_ids or [])
            if work_item.issue_number in _linked_issue_numbers_from_pull_request_payload(
                pull_request.title,
                pull_request.body,
                pull_request.raw_payload if isinstance(pull_request.raw_payload, dict) else {},
            ):
                linked_pr_node_ids.add(pull_request.github_pr_node_id)
                linked_work_item_ids.add(work_item_id)
            else:
                linked_work_item_ids.discard(work_item_id)
            pull_request.linked_work_item_ids = sorted(linked_work_item_ids)
        work_item.linked_prs = sorted(linked_pr_node_ids)

    def _sync_pull_request_issue_links(
        self,
        repository_binding: RepositoryBinding,
        pull_request: PullRequestMirror,
    ) -> None:
        linked_issue_numbers = set(
            _linked_issue_numbers_from_pull_request_payload(
                pull_request.title,
                pull_request.body,
                pull_request.raw_payload if isinstance(pull_request.raw_payload, dict) else {},
            )
        )
        linked_work_items = (
            self.session.query(WorkItem)
            .filter(WorkItem.repo_id == repository_binding.repo_id)
            .all()
        )
        linked_work_item_ids: list[str] = []
        for work_item in linked_work_items:
            linked_prs = set(work_item.linked_prs or [])
            if work_item.issue_number in linked_issue_numbers:
                linked_prs.add(pull_request.github_pr_node_id)
                linked_work_item_ids.append(str(work_item.work_item_id))
            else:
                linked_prs.discard(pull_request.github_pr_node_id)
            work_item.linked_prs = sorted(linked_prs)
        pull_request.linked_work_item_ids = sorted(linked_work_item_ids)

    def _reconcile_project_work_items(self, project: GitHubProjectMirror) -> None:
        project_items = (
            self.session.query(GitHubProjectItemMirror)
            .options(selectinload(GitHubProjectItemMirror.work_item))
            .filter(GitHubProjectItemMirror.project_id == project.project_id)
            .all()
        )
        active_items_by_work_item_id = {
            item.work_item_id: item
            for item in project_items
            if item.work_item_id is not None and item.content_type == "Issue"
        }
        candidate_work_items = {
            work_item.work_item_id: work_item
            for work_item in self.session.query(WorkItem).filter(WorkItem.project_id == project.project_id).all()
        }
        for item in project_items:
            if item.work_item is not None:
                candidate_work_items[item.work_item.work_item_id] = item.work_item

        for work_item_id, work_item in candidate_work_items.items():
            active_item = active_items_by_work_item_id.get(work_item_id)
            if active_item is None:
                work_item.project_id = None
                work_item.status = _work_item_default_status(work_item)
                continue
            work_item.project_id = project.project_id
            if active_item.status_name and _work_item_default_status(work_item) != "Closed":
                work_item.status = active_item.status_name
            else:
                work_item.status = _work_item_default_status(work_item)
