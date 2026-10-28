"""Pure policy decisions; an approval result never authorizes immediate execution."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.policy.permissions import Action, has_permission


class Decision(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"


@dataclass(frozen=True)
class PolicyContext:
    actor_tenant_id: UUID
    resource_tenant_id: UUID
    project_access: bool = False
    project_scoped: bool = True
    automated: bool = False
    actor_id: UUID | None = None
    requested_by_id: UUID | None = None


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str


HUMAN_APPROVAL_ACTIONS = frozenset(
    {
        Action.PROJECT_DELETE,
        Action.CHANGE_SUBMIT,
        Action.CONTRACT_COMMIT,
        Action.RISK_ACCEPT,
        Action.FINANCIAL_RELEASE,
    }
)


def decide(role: str, action: str, context: PolicyContext) -> PolicyResult:
    if context.actor_tenant_id != context.resource_tenant_id:
        return PolicyResult(Decision.DENIED, "tenant_mismatch")
    if not has_permission(role, action):
        return PolicyResult(Decision.DENIED, "insufficient_permission")
    if context.project_scoped and not context.project_access:
        return PolicyResult(Decision.DENIED, "project_access_required")
    if action == Action.APPROVAL_DECIDE:
        if context.actor_id is None or context.requested_by_id is None:
            return PolicyResult(Decision.DENIED, "approval_participants_required")
        if context.actor_id == context.requested_by_id:
            return PolicyResult(Decision.DENIED, "self_approval_forbidden")
        if context.automated:
            return PolicyResult(Decision.REQUIRES_HUMAN_APPROVAL, "human_decision_required")
    if action in HUMAN_APPROVAL_ACTIONS:
        return PolicyResult(Decision.REQUIRES_HUMAN_APPROVAL, "human_decision_required")
    return PolicyResult(Decision.ALLOWED, "permission_granted")
