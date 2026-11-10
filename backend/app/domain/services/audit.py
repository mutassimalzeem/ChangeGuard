"""Narrowly authorized user audit appends; worker audits use their own transaction."""

from app.domain.models import AuditEvent


async def record_user_action(
    session, user, project_id, action, entity_type, entity_id, request_id=None, details=None
):
    audit = AuditEvent(
        tenant_id=user.tenant_id,
        project_id=project_id,
        actor_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=request_id,
        details=details or {},
    )
    session.add(audit)
    session.info["user_action_audit"] = audit
    try:
        await session.flush()
    finally:
        session.info.pop("user_action_audit", None)
