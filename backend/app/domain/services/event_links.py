"""Only authenticated, explicit event relationships can close an unlinked-delay risk."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.domain.models import RFI, AuditEvent, EventEntityLink, ProjectEvent, Risk
from app.domain.schemas.event_link import EventLinkRead, EventLinkResult, RiskResolution
from app.domain.services.evidence import EvidenceService
from app.policy.permissions import Action, has_permission

RULE = "daily_report_delay_without_link"


def entity(link):
    return (
        ("rfi", link.rfi_id) if link.rfi_id is not None else ("change_order", link.change_order_id)
    )


def resolution_data(risk, link):
    kind, record_id = entity(link)
    return RiskResolution(
        entity_type=kind,
        entity_id=record_id,
        event_link_id=link.id,
        actor_id=risk.resolved_by_id,
        resolved_at=risk.resolved_at,
        reason=risk.resolution_reason,
    )


async def visible_entity(session, user, project_id, kind, record_id):
    evidence = EvidenceService(session, user)
    if kind == "rfi":
        record = await evidence.record(RFI, project_id, record_id)
        if record.document_id:
            await evidence.source(project_id, "document", record.document_id)
    else:
        from app.domain.services.change_orders import ChangeOrderService

        record = await ChangeOrderService(session, user).load(record_id)
        if record.project_id != project_id:
            raise HTTPException(404, "Change order not found")
    return record


class EventLinkService:
    def __init__(self, session, user):
        self.session, self.user = session, user
        self.evidence = EvidenceService(session, user)

    async def link(self, project_id, event_id, payload, request_id=None):
        required = (
            Action.DOCUMENT_READ,
            Action.FINANCIAL_READ,
            Action.RISK_ACCEPT,
            Action.RFI_WRITE if payload.entity_type == "rfi" else Action.CHANGE_WRITE,
        )
        if not all(has_permission(self.user.role, action) for action in required):
            raise HTTPException(403, "Access denied")
        await self.evidence.access.project(project_id)
        # Serialize link retries and competing resolutions on the exact event.
        event = await self.session.scalar(
            select(ProjectEvent)
            .where(
                ProjectEvent.id == event_id,
                ProjectEvent.tenant_id == self.user.tenant_id,
                ProjectEvent.project_id == project_id,
            )
            .with_for_update()
        )
        if event is None:
            raise HTTPException(404, "Project event not found")
        await self.evidence.source(project_id, "project_event", event.id)
        await visible_entity(
            self.session, self.user, project_id, payload.entity_type, payload.entity_id
        )
        from app.domain.services.risks import RiskService

        risks = list(
            await self.session.scalars(
                select(Risk)
                .where(
                    Risk.tenant_id == self.user.tenant_id,
                    Risk.project_id == project_id,
                    Risk.project_event_id == event.id,
                    Risk.risk_type == RULE,
                )
                .order_by(Risk.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        # Check the complete original evidence before any writes, even if event
        # visibility alone would have allowed linking a partially hidden risk.
        for risk in risks:
            await RiskService(self.session, self.user).load(project_id, risk.id)
        field = "rfi_id" if payload.entity_type == "rfi" else "change_order_id"
        link = await self.session.scalar(
            select(EventEntityLink).where(
                EventEntityLink.tenant_id == self.user.tenant_id,
                EventEntityLink.project_id == project_id,
                EventEntityLink.event_id == event.id,
                getattr(EventEntityLink, field) == payload.entity_id,
            )
        )
        now = datetime.now(UTC)
        if link is None:
            link = EventEntityLink(
                id=uuid4(),
                tenant_id=self.user.tenant_id,
                project_id=project_id,
                event_id=event.id,
                actor_id=self.user.id,
                reason=payload.reason,
                created_at=now,
                **{field: payload.entity_id},
            )
            audit = AuditEvent(
                tenant_id=self.user.tenant_id,
                project_id=project_id,
                actor_id=self.user.id,
                action="project_event.link_entity",
                entity_type="project_event",
                entity_id=event.id,
                request_id=request_id,
                details={
                    "link_id": str(link.id),
                    "entity_type": payload.entity_type,
                    "entity_id": str(payload.entity_id),
                    "reason": payload.reason,
                },
            )
            self.session.add_all([link, audit])
            self.session.info["event_link_write"] = (link, audit)
            try:
                await self.session.flush()
            finally:
                self.session.info.pop("event_link_write", None)
        resolved = []
        for risk in risks:
            if risk.resolution_link_id is not None:
                continue  # The first resolution and its actor/reason remain historical facts.
            before = risk.status
            risk.status = "resolved"
            risk.resolution_link_id = link.id
            risk.resolved_by_id = self.user.id
            risk.resolved_at = now
            risk.resolution_reason = payload.reason
            audit = AuditEvent(
                tenant_id=self.user.tenant_id,
                project_id=project_id,
                actor_id=self.user.id,
                action="risk.resolve",
                entity_type="risk",
                entity_id=risk.id,
                request_id=request_id,
                details={
                    "from_status": before,
                    "to_status": "resolved",
                    "event_id": str(event.id),
                    "event_link_id": str(link.id),
                    "resolving_entity_type": payload.entity_type,
                    "resolving_entity_id": str(payload.entity_id),
                    "resolved_at": now.isoformat(),
                    "reason": payload.reason,
                },
            )
            self.session.add(audit)
            self.session.info["risk_resolution"] = (risk, audit, link)
            try:
                await self.session.flush()
            finally:
                self.session.info.pop("risk_resolution", None)
            resolved.append(risk.id)
        kind, record_id = entity(link)
        return EventLinkResult(
            link=EventLinkRead(
                id=link.id,
                event_id=link.event_id,
                entity_type=kind,
                entity_id=record_id,
                actor_id=link.actor_id,
                linked_at=link.created_at,
                reason=link.reason,
            ),
            resolved_risk_ids=resolved,
        )
