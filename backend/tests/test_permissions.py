"""Permission and policy decisions are explicit and default-deny."""

from uuid import uuid4

import pytest

from app.policy.decisions import Decision, PolicyContext, decide
from app.policy.permissions import PERMISSIONS, Action, Role, has_permission


@pytest.mark.parametrize("role", list(Role))
def test_every_defined_role_has_read_access(role):
    assert has_permission(role, Action.PROJECT_READ)
    assert has_permission(role, Action.DOCUMENT_READ)


@pytest.mark.parametrize("role", list(Role))
def test_financial_permissions_are_limited_to_four_roles(role):
    financial = role in {Role.OWNER, Role.ADMIN, Role.PROJECT_MANAGER, Role.COMMERCIAL_MANAGER}
    assert has_permission(role, Action.FINANCIAL_READ) is financial
    assert has_permission(role, Action.FINANCIAL_WRITE) is financial


def test_unknown_roles_and_actions_deny_by_default():
    assert not has_permission("member", Action.PROJECT_READ)
    assert not has_permission(Role.OWNER, "unknown.action")
    assert set(PERMISSIONS) == set(Role)


@pytest.mark.parametrize("role", list(Role))
def test_even_owner_cannot_cross_tenants(role):
    result = decide(role, Action.PROJECT_READ, PolicyContext(uuid4(), uuid4(), project_access=True))
    assert result.decision == Decision.DENIED


def test_policy_separates_denied_allowed_and_human_approval():
    tenant = uuid4()
    allowed = PolicyContext(tenant, tenant, project_access=True)
    assert decide(Role.SITE_ENGINEER, Action.DOCUMENT_WRITE, allowed).decision == Decision.ALLOWED
    assert decide(Role.VIEWER, Action.DOCUMENT_WRITE, allowed).decision == Decision.DENIED
    assert (
        decide(Role.OWNER, Action.FINANCIAL_RELEASE, allowed).decision
        == Decision.REQUIRES_HUMAN_APPROVAL
    )
    assert decide(Role.VIEWER, Action.FINANCIAL_RELEASE, allowed).decision == Decision.DENIED
    assert (
        decide(Role.OWNER, Action.PROJECT_READ, PolicyContext(tenant, tenant)).decision
        == Decision.DENIED
    )


def test_self_approval_missing_participants_and_automation_fail_closed():
    tenant, actor = uuid4(), uuid4()
    assert (
        decide(
            Role.OWNER, Action.APPROVAL_DECIDE, PolicyContext(tenant, tenant, project_access=True)
        ).decision
        == Decision.DENIED
    )
    context = PolicyContext(
        tenant, tenant, project_access=True, actor_id=actor, requested_by_id=actor
    )
    assert decide(Role.OWNER, Action.APPROVAL_DECIDE, context).decision == Decision.DENIED
    context = PolicyContext(
        tenant, tenant, project_access=True, actor_id=actor, requested_by_id=uuid4(), automated=True
    )
    assert (
        decide(Role.OWNER, Action.APPROVAL_DECIDE, context).decision
        == Decision.REQUIRES_HUMAN_APPROVAL
    )
    context = PolicyContext(
        tenant, tenant, project_access=True, actor_id=actor, requested_by_id=uuid4()
    )
    assert decide(Role.OWNER, Action.APPROVAL_DECIDE, context).decision == Decision.ALLOWED
