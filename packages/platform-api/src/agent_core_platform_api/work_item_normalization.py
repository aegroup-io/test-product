from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from sqlalchemy.orm import Session

from agent_core_platform_api.models import (
    GitHubProjectItemMirror,
    GitHubProjectMirror,
    PullRequestMirror,
    RepositoryBinding,
    WorkItem,
)


ISSUE_REFERENCE_RE = re.compile(r"(?:#|/issues/)(?P<number>\d+)\b", re.IGNORECASE)
DEPENDENCY_TEXT_RE = re.compile(
    r"(?:depends\s+on|blocked\s+by|depends-on|blocked-by|dependency(?:\s+on)?)\s*:?\s*(?:#|/issues/)(?P<number>\d+)\b",
    re.IGNORECASE,
)
DEPENDENCY_FIELD_NAMES = {
    "blocked by",
    "blocked-by",
    "depends on",
    "depends-on",
    "dependencies",
    "dependency",
}
PRIORITY_FIELD_NAMES = {
    "priority",
    "priority hint",
    "severity",
}
BLOCKED_LABELS = {
    "blocked",
    "status:blocked",
    "state:blocked",
}
PRIORITY_LABEL_PREFIXES = (
    "priority:",
    "prio:",
    "p:",
    "sev:",
)
DEPENDENCY_LABEL_PREFIXES = (
    "blocked-by:",
    "depends-on:",
    "dependency:",
)
RUNTIME_REPAIR_REASON_PREFIX = "runtime."
RUNNER_CAPABILITY_REPAIR_REASON = "runtime.runner_capability_mismatch"
RUNNER_HANDSHAKE_TIMEOUT_REPAIR_REASON = "runtime.runner_handshake_timeout"
RUNNER_HEARTBEAT_TIMEOUT_REPAIR_REASON = "runtime.runner_heartbeat_timeout"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _casefold(value: str | None) -> str:
    return value.strip().casefold() if isinstance(value, str) and value.strip() else ""


def _canonical_status_name(status: str) -> str:
    normalized = _casefold(status)
    if normalized == "in progress":
        return "In Progress"
    if normalized == "in review":
        return "In Review"
    return status.title()


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
    return []


def _issue_numbers_from_text(*texts: str | None) -> set[int]:
    numbers: set[int] = set()
    for text in texts:
        if not isinstance(text, str):
            continue
        for match in ISSUE_REFERENCE_RE.finditer(text):
            numbers.add(int(match.group("number")))
    return numbers


def _dependency_issue_numbers_from_text(*texts: str | None) -> set[int]:
    numbers: set[int] = set()
    for text in texts:
        if not isinstance(text, str):
            continue
        for match in DEPENDENCY_TEXT_RE.finditer(text):
            numbers.add(int(match.group("number")))
    return numbers


def _priority_rank(priority_hint: str) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(priority_hint, 99)


def _priority_hint_from_value(value: str | None) -> str | None:
    normalized = _casefold(value)
    if normalized in {"p0", "priority 0", "critical", "urgent", "highest"}:
        return "p0"
    if normalized in {"p1", "priority 1", "high"}:
        return "p1"
    if normalized in {"p2", "priority 2", "medium", "normal"}:
        return "p2"
    if normalized in {"p3", "priority 3", "low", "backlog", "trivial"}:
        return "p3"
    return None


def _pr_reference_payloads_from_issue(issue_payload: dict[str, Any]) -> list[dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for payload in _extract_nodes(issue_payload.get("closedByPullRequestsReferences")):
        node_id = payload.get("id") or payload.get("node_id")
        if isinstance(node_id, str) and node_id:
            references[node_id] = dict(payload)

    for event in _extract_nodes(issue_payload.get("timelineItems")):
        if event.get("__typename") != "CrossReferencedEvent":
            continue
        source = event.get("source")
        if not isinstance(source, dict) or source.get("__typename") != "PullRequest":
            continue
        node_id = source.get("id") or source.get("node_id")
        if isinstance(node_id, str) and node_id:
            payload = dict(source)
            if event.get("willCloseTarget") is not None:
                payload["willCloseTarget"] = bool(event.get("willCloseTarget"))
            references[node_id] = payload

    return [references[node_id] for node_id in sorted(references)]


def _linked_issue_numbers_from_pull_request(
    title: str | None,
    body: str | None,
    raw_payload: dict[str, Any],
) -> set[int]:
    numbers = _issue_numbers_from_text(title, body)
    for issue_payload in _extract_nodes(raw_payload.get("closingIssuesReferences")):
        issue_number = issue_payload.get("number")
        if isinstance(issue_number, int):
            numbers.add(issue_number)
    return numbers


class WorkItemNormalizationService:
    def __init__(self, session: Session):
        self.session = session

    def normalize_work_item(
        self,
        work_item: WorkItem,
        *,
        installation_id: str | None = None,
        mirror_service: Any | None = None,
        allow_repair: bool = True,
        preserve_runtime_repairs: bool = True,
    ) -> WorkItem:
        state = self._build_state(work_item, preserve_runtime_repairs=preserve_runtime_repairs)
        self._apply_state(work_item, state)
        self.session.flush()

        if allow_repair and mirror_service is not None and state["repair_reasons"]:
            self._trigger_repairs(
                work_item=work_item,
                mirror_service=mirror_service,
                repair_reasons=state["repair_reasons"],
                dependency_details=state["dependency_details"],
                linked_pr_node_ids=[pr["github_pr_node_id"] for pr in state["linked_pr_details"]],
            )
            self.session.expire(work_item)
            state = self._build_state(work_item, preserve_runtime_repairs=preserve_runtime_repairs)
            self._apply_state(work_item, state)
            self.session.flush()

        return work_item

    def flag_runtime_repair(
        self,
        work_item: WorkItem,
        *,
        repair_reason: str,
        observed_at: datetime | None = None,
    ) -> WorkItem:
        reasons = sorted(set(work_item.repair_reasons or []) | {repair_reason})
        work_item.requires_repair = True
        work_item.repair_reasons = reasons
        work_item.eligibility_flags = self._eligibility_flags(
            status=work_item.status,
            dependency_state=work_item.dependency_state,
            handoff_status=work_item.handoff_status,
            requires_repair=True,
        )
        work_item.last_normalized_at = observed_at or _now()
        self.session.flush()
        return work_item

    def clear_runtime_repairs_for_product(self, product_id) -> None:
        work_items = (
            self.session.query(WorkItem)
            .join(RepositoryBinding, RepositoryBinding.repo_id == WorkItem.repo_id)
            .filter(RepositoryBinding.product_id == product_id)
            .all()
        )
        for work_item in work_items:
            runtime_repairs = self._runtime_repair_reasons(work_item.repair_reasons or [])
            if not runtime_repairs:
                continue
            self.normalize_work_item(work_item, allow_repair=False, preserve_runtime_repairs=False)

    def normalize_for_pull_request(
        self,
        pull_request: PullRequestMirror,
        *,
        installation_id: str | None = None,
        mirror_service: Any | None = None,
        allow_repair: bool = True,
    ) -> None:
        referenced_numbers = _linked_issue_numbers_from_pull_request(
            pull_request.title,
            pull_request.body,
            pull_request.raw_payload if isinstance(pull_request.raw_payload, dict) else {},
        )
        linked_work_item_ids = set(pull_request.linked_work_item_ids or [])
        work_items = []
        if referenced_numbers or linked_work_item_ids:
            for candidate in self.session.query(WorkItem).filter(WorkItem.repo_id == pull_request.repo_id).all():
                if str(candidate.work_item_id) in linked_work_item_ids or candidate.issue_number in referenced_numbers:
                    work_items.append(candidate)
        for work_item in work_items:
            self.normalize_work_item(
                work_item,
                installation_id=installation_id,
                mirror_service=mirror_service,
                allow_repair=allow_repair,
            )

    def normalize_for_project(
        self,
        project: GitHubProjectMirror,
        *,
        installation_id: str | None = None,
        mirror_service: Any | None = None,
        allow_repair: bool = True,
    ) -> None:
        work_items = (
            self.session.query(WorkItem)
            .join(RepositoryBinding, RepositoryBinding.repo_id == WorkItem.repo_id)
            .filter(RepositoryBinding.product_id == project.product_id)
            .all()
        )
        for work_item in work_items:
            self.normalize_work_item(
                work_item,
                installation_id=installation_id,
                mirror_service=mirror_service,
                allow_repair=allow_repair,
            )

    def _build_state(self, work_item: WorkItem, *, preserve_runtime_repairs: bool = True) -> dict[str, Any]:
        repo = self.session.get(RepositoryBinding, work_item.repo_id)
        project_item = self._select_project_item(work_item)
        raw_payload = work_item.raw_payload if isinstance(work_item.raw_payload, dict) else {}
        github_config = self._github_config(repo)

        linked_pr_details = self._linked_pull_request_details(work_item, raw_payload)
        dependency_state, dependency_refs, dependency_details, dependency_reasons = self._dependency_state(
            work_item=work_item,
            project_item=project_item,
            raw_payload=raw_payload,
        )
        priority_hint = self._priority_hint(work_item, project_item)
        handoff_status = self._handoff_status(linked_pr_details)

        status_source = project_item.status_name if project_item is not None else None
        if not status_source and work_item.closed_at is not None:
            status_source = "closed"

        canonical_status, status_reasons = self._canonical_status(
            work_item=work_item,
            status_source=status_source,
            dependency_state=dependency_state,
            handoff_status=handoff_status,
            github_config=github_config,
        )

        repair_reasons = sorted(set(status_reasons + dependency_reasons))
        if preserve_runtime_repairs:
            repair_reasons = sorted(set(repair_reasons + self._runtime_repair_reasons(work_item.repair_reasons or [])))
        requires_repair = bool(repair_reasons)
        eligibility_flags = self._eligibility_flags(
            status=canonical_status,
            dependency_state=dependency_state,
            handoff_status=handoff_status,
            requires_repair=requires_repair,
        )

        return {
            "status": canonical_status,
            "status_source": status_source,
            "dependencies": dependency_refs,
            "dependency_state": dependency_state,
            "dependency_details": dependency_details,
            "priority_hint": priority_hint,
            "linked_prs": sorted({pr["github_pr_node_id"] for pr in linked_pr_details}),
            "linked_pr_details": linked_pr_details,
            "eligibility_flags": eligibility_flags,
            "handoff_status": handoff_status,
            "requires_repair": requires_repair,
            "repair_reasons": repair_reasons,
            "last_normalized_at": _now(),
        }

    def _apply_state(self, work_item: WorkItem, state: dict[str, Any]) -> None:
        work_item.status = state["status"]
        work_item.status_source = state["status_source"]
        work_item.dependencies = state["dependencies"]
        work_item.dependency_state = state["dependency_state"]
        work_item.dependency_details = state["dependency_details"]
        work_item.priority_hint = state["priority_hint"]
        work_item.linked_prs = state["linked_prs"]
        work_item.eligibility_flags = state["eligibility_flags"]
        work_item.handoff_status = state["handoff_status"]
        work_item.requires_repair = state["requires_repair"]
        work_item.repair_reasons = state["repair_reasons"]
        work_item.last_normalized_at = state["last_normalized_at"]

    def _runtime_repair_reasons(self, repair_reasons: list[str]) -> list[str]:
        return sorted(
            {
                reason
                for reason in repair_reasons
                if isinstance(reason, str) and reason.startswith(RUNTIME_REPAIR_REASON_PREFIX)
            }
        )

    def _trigger_repairs(
        self,
        *,
        work_item: WorkItem,
        mirror_service: Any,
        repair_reasons: list[str],
        dependency_details: list[dict[str, Any]],
        linked_pr_node_ids: list[str],
    ) -> None:
        repair_targets: set[str] = set(repair_reasons)
        project = self._project_for_work_item(work_item)
        repo = self.session.get(RepositoryBinding, work_item.repo_id)

        if project is not None and project.github_project_node_id and any(reason.startswith("status.") for reason in repair_targets):
            mirror_service.repair_project(
                github_project_node_id=project.github_project_node_id,
            )

        if work_item.github_issue_node_id and any(
            reason.startswith(prefix)
            for reason in repair_targets
            for prefix in ("dependency.", "pr.", "status.")
        ):
            mirror_service.repair_issue(
                github_issue_node_id=work_item.github_issue_node_id,
            )

        if repo is not None and any(reason.startswith("dependency.") for reason in repair_targets):
            for detail in dependency_details:
                if detail.get("kind") != "issue" or detail.get("status") != "unknown":
                    continue
                issue_number = detail.get("issue_number")
                if not isinstance(issue_number, int):
                    continue
                try:
                    mirror_service.repair_issue_by_number(
                        owner=repo.owner,
                        repo=repo.name,
                        issue_number=issue_number,
                    )
                except ValueError:
                    continue

        for github_pr_node_id in linked_pr_node_ids:
            if github_pr_node_id and any(reason.startswith("pr.") for reason in repair_targets):
                try:
                    mirror_service.repair_pull_request(
                        github_pr_node_id=github_pr_node_id,
                    )
                except ValueError:
                    continue

    def _select_project_item(self, work_item: WorkItem) -> GitHubProjectItemMirror | None:
        query = self.session.query(GitHubProjectItemMirror).filter(GitHubProjectItemMirror.work_item_id == work_item.work_item_id)
        if work_item.project_id is not None:
            query = query.filter(GitHubProjectItemMirror.project_id == work_item.project_id)
        return query.order_by(GitHubProjectItemMirror.last_reconciled_at.desc().nullslast()).first()

    def _project_for_work_item(self, work_item: WorkItem) -> GitHubProjectMirror | None:
        if work_item.project_id is not None:
            project = self.session.get(GitHubProjectMirror, work_item.project_id)
            if project is not None:
                return project
        repo = self.session.get(RepositoryBinding, work_item.repo_id)
        if repo is None or repo.product is None:
            return None
        return repo.product.project_mirror

    def _github_config(self, repo: RepositoryBinding | None) -> dict[str, Any]:
        if repo is None or repo.product is None or not isinstance(repo.product.effective_config, dict):
            return {}
        github_config = repo.product.effective_config.get("github", {})
        return github_config if isinstance(github_config, dict) else {}

    def _priority_hint(self, work_item: WorkItem, project_item: GitHubProjectItemMirror | None) -> str | None:
        candidates: list[str] = []
        for label in work_item.labels or []:
            direct = _priority_hint_from_value(label)
            if direct is not None:
                candidates.append(direct)
                continue
            for prefix in PRIORITY_LABEL_PREFIXES:
                if label.startswith(prefix):
                    hinted = _priority_hint_from_value(label.split(":", 1)[1])
                    if hinted is not None:
                        candidates.append(hinted)

        for field_value in list(project_item.field_values_payload or []) if project_item is not None else []:
            field_name = _casefold(str(field_value.get("field_name") or ""))
            if field_name not in PRIORITY_FIELD_NAMES:
                continue
            hinted = _priority_hint_from_value(str(field_value.get("value") or ""))
            if hinted is not None:
                candidates.append(hinted)

        if not candidates:
            return None
        return sorted(candidates, key=_priority_rank)[0]

    def _linked_pull_request_details(self, work_item: WorkItem, raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
        details_by_node_id: dict[str, dict[str, Any]] = {}
        for pull_request in (
            self.session.query(PullRequestMirror)
            .filter(PullRequestMirror.github_pr_node_id.in_(work_item.linked_prs or []))
            .all()
            if work_item.linked_prs
            else []
        ):
            details_by_node_id[pull_request.github_pr_node_id] = {
                "github_pr_node_id": pull_request.github_pr_node_id,
                "number": pull_request.number,
                "state": pull_request.state,
                "is_draft": bool(pull_request.is_draft),
                "review_state": pull_request.review_state,
                "merge_state": pull_request.merge_state,
                "merged_at": pull_request.merged_at,
            }

        for payload in _pr_reference_payloads_from_issue(raw_payload):
            github_pr_node_id = payload.get("id") or payload.get("node_id")
            if not isinstance(github_pr_node_id, str) or not github_pr_node_id:
                continue
            existing = details_by_node_id.get(github_pr_node_id, {})
            details_by_node_id[github_pr_node_id] = {
                "github_pr_node_id": github_pr_node_id,
                "number": payload.get("number") if isinstance(payload.get("number"), int) else existing.get("number"),
                "state": str(payload.get("state") or existing.get("state") or "").lower() or None,
                "is_draft": bool(
                    payload.get("draft")
                    or payload.get("isDraft")
                    or existing.get("is_draft")
                    or False
                ),
                "review_state": payload.get("reviewDecision") or payload.get("review_state") or existing.get("review_state"),
                "merge_state": payload.get("mergeStateStatus") or payload.get("merge_state") or existing.get("merge_state"),
                "merged_at": _coerce_datetime(payload.get("mergedAt") or payload.get("merged_at")) or existing.get("merged_at"),
            }

        return [details_by_node_id[node_id] for node_id in sorted(details_by_node_id)]

    def _dependency_state(
        self,
        *,
        work_item: WorkItem,
        project_item: GitHubProjectItemMirror | None,
        raw_payload: dict[str, Any],
    ) -> tuple[str, list[str], list[dict[str, Any]], list[str]]:
        refs: dict[int, set[str]] = {}
        open_issue_payloads: dict[int, dict[str, Any]] = {}
        repair_reasons: list[str] = []

        for issue_payload in _extract_nodes(raw_payload.get("blockedBy")):
            issue_number = issue_payload.get("number")
            if isinstance(issue_number, int):
                refs.setdefault(issue_number, set()).add("issue.blocked_by")
                open_issue_payloads[issue_number] = issue_payload

        for issue_number in _dependency_issue_numbers_from_text(work_item.title, work_item.body):
            refs.setdefault(issue_number, set()).add("issue.text")

        for label in work_item.labels or []:
            if label in BLOCKED_LABELS:
                refs.setdefault(0, set()).add("label.blocked")
            for prefix in DEPENDENCY_LABEL_PREFIXES:
                if label.startswith(prefix):
                    suffix = label.split(":", 1)[1]
                    for issue_number in _issue_numbers_from_text(suffix, f"#{suffix}"):
                        refs.setdefault(issue_number, set()).add("label.dependency")

        for field_value in list(project_item.field_values_payload or []) if project_item is not None else []:
            field_name = _casefold(str(field_value.get("field_name") or ""))
            if field_name not in DEPENDENCY_FIELD_NAMES:
                continue
            for issue_number in _issue_numbers_from_text(str(field_value.get("value") or "")):
                refs.setdefault(issue_number, set()).add(f"project-field:{field_name}")

        dependency_details: list[dict[str, Any]] = []
        dependency_refs: list[str] = []
        blocked = False
        ambiguous = False

        if 0 in refs:
            blocked = True
            dependency_details.append(
                {
                    "kind": "label",
                    "label": "blocked",
                    "resolved": False,
                    "sources": sorted(refs.pop(0)),
                }
            )

        issue_numbers = sorted(refs)
        local_dependencies = {
            item.issue_number: item
            for item in (
                self.session.query(WorkItem)
                .filter(
                    WorkItem.repo_id == work_item.repo_id,
                    WorkItem.issue_number.in_(issue_numbers),
                )
                .all()
                if issue_numbers
                else []
            )
        }

        for issue_number in issue_numbers:
            dependency_refs.append(f"issue:{issue_number}")
            dependency_work_item = local_dependencies.get(issue_number)
            payload = open_issue_payloads.get(issue_number, {})
            payload_state = _casefold(str(payload.get("state") or ""))
            payload_closed_at = _coerce_datetime(payload.get("closedAt") or payload.get("closed_at"))
            resolved = False
            status = "unknown"
            github_issue_node_id = None
            if dependency_work_item is not None:
                github_issue_node_id = dependency_work_item.github_issue_node_id
                status = dependency_work_item.status
                resolved = _casefold(status) == "done"
            elif payload_state == "closed" or payload_closed_at is not None:
                resolved = True
                status = "Done"
                github_issue_node_id = str(payload.get("id") or payload.get("node_id")) if payload else None
            else:
                ambiguous = True
                repair_reasons.append("dependency.ambiguous")
                github_issue_node_id = str(payload.get("id") or payload.get("node_id")) if payload else None

            if not resolved:
                blocked = True
            dependency_details.append(
                {
                    "kind": "issue",
                    "issue_number": issue_number,
                    "github_issue_node_id": github_issue_node_id,
                    "status": status,
                    "resolved": resolved,
                    "sources": sorted(refs[issue_number]),
                }
            )

        summary = raw_payload.get("issueDependenciesSummary")
        if isinstance(summary, dict):
            total_blocked_by = summary.get("totalBlockedBy")
            if isinstance(total_blocked_by, int) and total_blocked_by > len(issue_numbers):
                ambiguous = True
                repair_reasons.append("dependency.stale")

        if ambiguous:
            dependency_state = "ambiguous"
        elif blocked:
            dependency_state = "blocked"
        else:
            dependency_state = "clear"

        return dependency_state, dependency_refs, dependency_details, sorted(set(repair_reasons))

    def _handoff_status(self, linked_pr_details: list[dict[str, Any]]) -> str:
        if not linked_pr_details:
            return "none"
        if any(pr.get("merged_at") is not None for pr in linked_pr_details):
            return "merged"
        if any(_casefold(str(pr.get("state") or "")) == "open" and not pr.get("is_draft") for pr in linked_pr_details):
            return "in_review"
        if any(_casefold(str(pr.get("state") or "")) == "open" for pr in linked_pr_details):
            return "coding"
        return "closed"

    def _canonical_status(
        self,
        *,
        work_item: WorkItem,
        status_source: str | None,
        dependency_state: str,
        handoff_status: str,
        github_config: dict[str, Any],
    ) -> tuple[str, list[str]]:
        reasons: list[str] = []
        if work_item.closed_at is not None or _casefold(str(work_item.raw_payload.get("state") if isinstance(work_item.raw_payload, dict) else "")) == "closed":
            return "Done", reasons

        ready_status = _casefold(str(github_config.get("ready_status") or ""))
        done_status = _casefold(str(github_config.get("done_status") or "done"))
        normalized_source = _casefold(status_source)

        canonical = None
        if normalized_source:
            if normalized_source == ready_status:
                canonical = "Ready"
            elif normalized_source == done_status or normalized_source in {"done", "closed"}:
                canonical = "Done"
            elif normalized_source in {"triage", "needs triage"}:
                canonical = "Triage"
            elif normalized_source in {"ready", "todo", "backlog"}:
                canonical = "Ready"
            elif "block" in normalized_source or "waiting" in normalized_source or "hold" in normalized_source:
                canonical = "Blocked"
            elif "review" in normalized_source or "qa" in normalized_source or "merge" in normalized_source:
                canonical = "In Review"
            elif (
                "progress" in normalized_source
                or "doing" in normalized_source
                or "active" in normalized_source
                or "working" in normalized_source
            ):
                canonical = "In Progress"
            else:
                reasons.append("status.unmapped")

        if dependency_state == "blocked":
            canonical = "Blocked"
        elif dependency_state == "ambiguous" and canonical is None:
            canonical = "Triage"

        if canonical in {None, "Ready", "Triage"}:
            if handoff_status == "in_review":
                canonical = "In Review"
            elif handoff_status in {"coding", "merged"}:
                canonical = "In Progress" if handoff_status == "coding" else "In Review"

        if canonical is None:
            canonical = "Triage"

        return canonical, sorted(set(reasons))

    def _eligibility_flags(
        self,
        *,
        status: str,
        dependency_state: str,
        handoff_status: str,
        requires_repair: bool,
    ) -> list[str]:
        flags: set[str] = set()
        if status == "Done":
            flags.add("done")
        if status == "Triage":
            flags.add("needs-triage")
        if status == "Ready" and dependency_state == "clear" and not requires_repair:
            flags.add("eligible")
        if dependency_state == "blocked":
            flags.add("blocked:dependencies")
        if dependency_state == "ambiguous":
            flags.add("dependencies:ambiguous")
        if handoff_status == "in_review":
            flags.add("awaiting-review")
        if handoff_status == "merged":
            flags.add("awaiting-close")
        if requires_repair:
            flags.add("repair-needed")
        return sorted(flags)
