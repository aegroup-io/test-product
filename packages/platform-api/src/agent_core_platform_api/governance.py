from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from agent_core_platform_api.models import Secret
from agent_core_platform_api.secret_crypto import SecretCryptoError, decrypt_secret


DEFAULT_APPROVAL_POSTURE = "high-trust"
ALLOWED_APPROVAL_POSTURES = frozenset({"blocked", "operator-gated", "high-trust"})
ACTION_POLICY_FIELDS = {
    "repo_write": "repo_write_policy",
    "branch_creation": "branch_creation_policy",
    "issue_edit": "issue_edit_policy",
    "pr_edit": "pr_edit_policy",
    "tool_use": "tool_use_policy",
    "network_use": "network_use_policy",
}
ACTION_ALIASES = {
    "branch-create": "branch_creation",
    "branch_creation": "branch_creation",
    "branch_create": "branch_creation",
    "issue-edit": "issue_edit",
    "issue_edit": "issue_edit",
    "network": "network_use",
    "network-use": "network_use",
    "network_use": "network_use",
    "pr-edit": "pr_edit",
    "pr_edit": "pr_edit",
    "repo-write": "repo_write",
    "repo_write": "repo_write",
    "tool": "tool_use",
    "tool-use": "tool_use",
    "tool_use": "tool_use",
}
REDACTED_SECRET = "[REDACTED_SECRET]"


def normalize_approval_posture(value: Any, *, default: str = DEFAULT_APPROVAL_POSTURE) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in ALLOWED_APPROVAL_POSTURES:
        return normalized
    return default


def normalize_action_type(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower().replace("/", "_")
    return ACTION_ALIASES.get(normalized, normalized if normalized in ACTION_POLICY_FIELDS else None)


def action_policy(policy: Mapping[str, Any] | None, action_type: str | None) -> str:
    if not isinstance(policy, Mapping):
        return DEFAULT_APPROVAL_POSTURE
    default = normalize_approval_posture(policy.get("approval_posture"))
    if action_type is None:
        return default
    action_policies = policy.get("action_policies")
    if isinstance(action_policies, Mapping):
        return normalize_approval_posture(action_policies.get(action_type), default=default)
    return default


def build_runtime_identity(lane) -> str:
    return ":".join(
        (
            f"org:{lane.product.org_id}",
            f"product:{lane.product_id}",
            f"repo:{lane.repo_id}",
            f"lane:{lane.lane_id}",
        )
    )


def build_lane_policy(
    lane,
    *,
    policy_overrides: Mapping[str, Any] | None = None,
    secret_references: Sequence[str] | None = None,
    tool_permissions: Sequence[str] | None = None,
) -> dict[str, Any]:
    effective_config = lane.product.effective_config or {}
    governance = effective_config.get("governance", {}) if isinstance(effective_config, Mapping) else {}
    base_posture = normalize_approval_posture(governance.get("approval_posture"))
    action_policies = {
        action: normalize_approval_posture(governance.get(field), default=base_posture)
        for action, field in ACTION_POLICY_FIELDS.items()
    }
    action_policies["issue_edit"] = (
        "blocked" if not governance.get("allow_agent_issue_edits", True) else action_policies["issue_edit"]
    )
    action_policies["pr_edit"] = (
        "blocked" if not governance.get("allow_agent_pr_edits", True) else action_policies["pr_edit"]
    )
    policy = {
        "approval_posture": base_posture,
        "action_policies": action_policies,
        "merge_policy": {"require_human_merge": bool(governance.get("require_human_merge", True))},
        "comment_policy": "high-trust" if governance.get("allow_agent_comments", True) else "blocked",
        "tool_permissions": sorted({value for value in tool_permissions or [] if isinstance(value, str) and value.strip()}),
        "network_access": action_policies["network_use"] != "blocked",
        "secret_handling": {
            "resolution_mode": "runtime-secret-manager",
            "redact_runtime_values": True,
            "secret_references": sorted(
                {value for value in secret_references or [] if isinstance(value, str) and value.strip()}
            ),
        },
        "runtime_identity": build_runtime_identity(lane),
        "credential_scope": {
            "org_id": str(lane.product.org_id),
            "product_id": str(lane.product_id),
            "repo_id": str(lane.repo_id),
            "lane_id": str(lane.lane_id),
            "branch_name": lane.branch_name,
        },
    }
    if isinstance(policy_overrides, Mapping):
        policy.update({key: value for key, value in policy_overrides.items()})
        if isinstance(policy_overrides.get("action_policies"), Mapping):
            merged = dict(action_policies)
            merged.update(
                {
                    key: normalize_approval_posture(value, default=base_posture)
                    for key, value in policy_overrides["action_policies"].items()
                    if isinstance(key, str)
                }
            )
            policy["action_policies"] = merged
    return policy


def build_write_audit(
    *,
    actor_type: str,
    actor_id: str,
    target_kind: str,
    target_id: str,
    action: str,
    approval_context: Mapping[str, Any] | None = None,
    outcome: str,
) -> dict[str, Any]:
    return {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "action": action,
        "approval_context": dict(approval_context or {}),
        "outcome": outcome,
    }


def load_secret_plaintexts(session: Session) -> list[str]:
    secrets: list[str] = []
    for secret in session.query(Secret).all():
        if not secret.has_value or not secret.value_ciphertext:
            continue
        try:
            decrypted = decrypt_secret(secret.value_ciphertext)
        except SecretCryptoError:
            continue
        if decrypted:
            secrets.append(decrypted)
    return sorted(set(secrets), key=len, reverse=True)


def redact_value(value: Any, secret_values: Sequence[str]) -> Any:
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, REDACTED_SECRET)
        return redacted
    if isinstance(value, Mapping):
        return {key: redact_value(item, secret_values) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, secret_values) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, secret_values) for item in value)
    return value
