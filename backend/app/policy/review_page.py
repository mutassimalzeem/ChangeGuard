"""Fixed, authenticated read model. Scope supplies identity and capabilities at execution."""

from pathlib import Path

from sqlalchemy import text

from app.api.exceptions import AuthorizationError
from app.policy.permissions import TENANT_WIDE_ROLES, Action, has_permission

VISIBILITY = Path(__file__).with_name("project_evidence_visibility.sql").read_text(encoding="utf-8")
REVIEW_PAGE = text(VISIBILITY + Path(__file__).with_suffix(".sql").read_text(encoding="utf-8"))
PILOT_VISIBLE = text(
    VISIBILITY
    + """
, subjects AS (
    SELECT 'risk' AS kind,id FROM risks WHERE linked_order_visible
    UNION ALL SELECT 'change_order',id FROM orders WHERE full_visibility
)
SELECT 'project' AS kind,project_id AS id FROM access
UNION ALL SELECT 'document',id FROM docs
UNION ALL SELECT kind,id FROM subjects
UNION ALL SELECT 'needs_evidence',id FROM risks WHERE linked_order_visible AND NOT supported AND reviewable
UNION ALL SELECT 'approval',p.id FROM approvals p JOIN access USING (tenant_id,project_id)
    JOIN subjects s ON (s.kind='risk' AND s.id=p.risk_id) OR (s.kind='change_order' AND s.id=p.change_order_id)
UNION ALL SELECT DISTINCT 'covered',s.document_id FROM evidence_links l JOIN access USING (tenant_id,project_id)
    JOIN subjects v ON v.kind=l.subject_type AND v.id=l.subject_id
    JOIN sources s ON s.kind=l.source_type AND s.id=l.source_id
    WHERE s.document_id IS NOT NULL AND l.created_at < :end
"""
)


async def pilot_visibility(session, project_id, end):
    from collections import defaultdict

    from app.api.exceptions import NotFoundError

    rows = await session.execute(
        PILOT_VISIBLE, {"project_id": project_id, "legacy": True, "end": end}
    )
    visible = defaultdict(set)
    for kind, resource in rows:
        visible[kind].add(resource)
    if not visible["project"]:
        raise NotFoundError("Project", str(project_id))
    return visible


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
