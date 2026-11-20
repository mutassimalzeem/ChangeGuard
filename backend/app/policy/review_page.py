"""Fixed, authenticated read model. Scope supplies identity and capabilities at execution."""

from pathlib import Path

from sqlalchemy import text

from app.api.exceptions import AuthorizationError
from app.policy.permissions import TENANT_WIDE_ROLES, Action, has_permission

REVIEW_PAGE = text(Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
REQUIRED = (Action.DOCUMENT_READ, Action.FINANCIAL_READ, Action.RISK_ACCEPT)


def bind_review_read(state, principal):
    if principal is None or not all(has_permission(principal.role, action) for action in REQUIRED):
        raise AuthorizationError()
    state.parameters = {
        **state.parameters,
        "actor_id": principal.user_id,
        "tenant_id": principal.tenant_id,
        "actor_role": principal.role.value,
        "tenant_wide": principal.role in TENANT_WIDE_ROLES,
        "can_approve": has_permission(principal.role, Action.APPROVAL_DECIDE),
    }
