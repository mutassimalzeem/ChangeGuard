"""Human risk review with atomic, append-only audit events."""

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.domain.models import AuditEvent, EventEntityLink, EvidenceLink, Risk
from app.domain.services.evidence import EvidenceService
from app.policy.permissions import Action, has_permission


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "accept",
        "dismiss",
        "override",
        "request_evidence",
        "convert_to_change_order",
        "create_change_order_draft",
    ]
    reason: str = Field(min_length=1, max_length=2000)
    severity: Literal["low", "medium", "high", "critical"] | None = None
    schedule_impact_days: int | None = Field(default=None, ge=0, le=36500)
    change_order_reference: str | None = Field(default=None, max_length=64)
    change_order_title: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A reason is mandatory")
        return value.strip()

    @model_validator(mode="after")
    def override_fields(self):
        changed = self.severity is not None or self.schedule_impact_days is not None
        if changed and self.action != "override":
            raise ValueError("Only override accepts severity or schedule impact changes")
        if self.action == "override" and not changed:
            raise ValueError(
                "At least one change (severity or schedule impact) is required for override"
            )
        return self


def validate_risk_decision(
    role: str,
    risk_status: str,
    has_links: bool,
    action: str,
    resolution_link_id: UUID | None = None,
) -> None:
    """Enforce authorization and domain constraints before executing a risk decision."""
    if not has_permission(role, Action.RISK_ACCEPT):
        raise HTTPException(403, "Access denied")
    if action in {"convert_to_change_order", "create_change_order_draft"} and not has_permission(
        role, Action.CHANGE_WRITE
    ):
        raise HTTPException(403, "Access denied")
    if resolution_link_id is not None:
        raise HTTPException(409, "Resolved risk history cannot be reopened by a review decision")
    if action not in {"dismiss", "request_evidence"} and (
        not has_links or risk_status == "insufficient_evidence"
    ):
        raise HTTPException(422, "insufficient_evidence")


class RiskService:
    def __init__(self, session, user):
        self.session, self.user = session, user
        self.evidence = EvidenceService(session, user)

    async def list(self, project_id, offset=0, limit=50):
        await self.evidence.access.project(project_id)
        ids = list(
            await self.session.scalars(
                select(Risk.id)
                .where(
                    Risk.tenant_id == self.user.tenant_id,
                    Risk.project_id == project_id,
                )
                .order_by(Risk.detected_at, Risk.id)
                .offset(offset)
                .limit(limit)
            )
        )
        results = []
        for risk_id in ids:
            try:
                results.append(await self.read(project_id, risk_id))
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        return results

    async def load(self, project_id, risk_id, *, lock=False):
        await self.evidence.access.project(project_id)
        query = select(Risk).where(
            Risk.id == risk_id, Risk.tenant_id == self.user.tenant_id, Risk.project_id == project_id
        )
        if lock:
            query = query.with_for_update()
        risk = await self.session.scalar(query)
        if risk is None:
            raise HTTPException(404, "Risk not found")
        links = list(
            await self.session.scalars(
                select(EvidenceLink).where(
                    EvidenceLink.tenant_id == self.user.tenant_id,
                    EvidenceLink.project_id == project_id,
                    EvidenceLink.subject_type == "risk",
                    EvidenceLink.subject_id == risk.id,
                )
            )
        )
        # A partial evidence view would expose descriptions/amounts derived from hidden files.
        for link in links:
            await self.evidence.source(project_id, link.source_type, link.source_id)
        if risk.document_id:
            await self.evidence.source(project_id, "document", risk.document_id)
        if risk.resolution_link_id:
            from app.domain.services.event_links import entity, visible_entity

            link = await self.session.scalar(
                select(EventEntityLink).where(
                    EventEntityLink.id == risk.resolution_link_id,
                    EventEntityLink.tenant_id == self.user.tenant_id,
                    EventEntityLink.project_id == project_id,
                )
            )
            if link is None:
                raise HTTPException(404, "Risk resolution not found")
            await visible_entity(self.session, self.user, project_id, *entity(link))
        return risk, links

    async def read(self, project_id, risk_id):
        if not has_permission(self.user.role, Action.FINANCIAL_READ):
            raise HTTPException(403, "Access denied")
        risk, links = await self.load(project_id, risk_id)
        resolution = None
        if risk.resolution_link_id:
            from app.domain.services.event_links import resolution_data

            link = await self.session.scalar(
                select(EventEntityLink).where(
                    EventEntityLink.id == risk.resolution_link_id,
                    EventEntityLink.tenant_id == self.user.tenant_id,
                    EventEntityLink.project_id == project_id,
                )
            )
            resolution = resolution_data(risk, link).model_dump(mode="json")
        evidence_details = [
            {
                "id": str(link.id),
                "source_type": link.source_type,
                "source_id": str(link.source_id),
                "document_id": str(link.source_id)
                if link.source_type == "document"
                else (str(risk.document_id) if risk.document_id else None),
                "source_page": link.source_page,
                "source_text_snippet": link.source_text_snippet,
                "confidence": float(link.confidence) if link.confidence is not None else None,
            }
            for link in links
        ]
        return {
            "id": risk.id,
            "risk_type": risk.risk_type or risk.category or "operational_risk",
            "severity": risk.severity,
            "title": risk.title,
            "description": risk.description,
            "financial_exposure": str(risk.exposure_amount)
            if risk.exposure_amount is not None
            else None,
            "currency": risk.currency if risk.exposure_amount is not None else None,
            "schedule_impact_days": risk.schedule_impact_days,
            "responsible_party": risk.responsible_party,
            "evidence_links": [link.id for link in links],
            "evidence_details": evidence_details,
            "document_id": str(risk.document_id) if risk.document_id else None,
            "original_document_url": f"/api/v1/projects/{project_id}/documents/{risk.document_id}"
            if risk.document_id
            else None,
            "change_order_id": str(risk.change_order_id) if risk.change_order_id else None,
            "recommended_action": risk.recommended_action,
            "confidence": float(risk.confidence) if risk.confidence is not None else None,
            "status": risk.status if links else "insufficient_evidence",
            "resolution": resolution,
        }

    async def decide(self, project_id: UUID, risk_id: UUID, payload: RiskDecision, request_id=None):
        risk, links = await self.load(project_id, risk_id, lock=True)
        validate_risk_decision(
            self.user.role,
            risk.status,
            bool(links),
            payload.action,
            risk.resolution_link_id,
        )
        before = {
            "status": risk.status,
            "severity": risk.severity,
            "schedule_impact_days": risk.schedule_impact_days,
        }
        status_map = {
            "accept": "accepted",
            "dismiss": "dismissed",
            "override": "overridden",
            "request_evidence": "evidence_requested",
            "convert_to_change_order": "converted",
            "create_change_order_draft": "converted",
        }
        risk.status = status_map[payload.action]
        if payload.severity is not None:
            risk.severity = payload.severity
        if payload.schedule_impact_days is not None:
            risk.schedule_impact_days = payload.schedule_impact_days
        created_change_order_id = None
        if payload.action in {"convert_to_change_order", "create_change_order_draft"}:
            from app.domain.schemas.change_order import ChangeOrderDraftFromRisk
            from app.domain.services.change_orders import ChangeOrderService

            co_service = ChangeOrderService(self.session, self.user)
            draft_order = await co_service.create_draft_from_risk(
                project_id,
                risk_id,
                ChangeOrderDraftFromRisk(
                    reference=payload.change_order_reference,
                    title=payload.change_order_title,
                    reason=payload.reason,
                ),
                request_id=request_id,
            )
            created_change_order_id = draft_order["id"]
            return await self.read(project_id, risk_id)

        audit_details = {
            "reason": payload.reason,
            "before": before,
            "after": {
                "status": risk.status,
                "severity": risk.severity,
                "schedule_impact_days": risk.schedule_impact_days,
            },
        }
        if created_change_order_id:
            audit_details["change_order_id"] = str(created_change_order_id)
        audit = AuditEvent(
            tenant_id=self.user.tenant_id,
            project_id=project_id,
            actor_id=self.user.id,
            action=f"risk.{payload.action}",
            entity_type="risk",
            entity_id=risk.id,
            request_id=request_id,
            details=audit_details,
        )
        self.session.add(audit)
        # The scope guard checks this exact object and its pending audit event.
        self.session.info["risk_review"] = (risk, audit)
        try:
            await self.session.flush()
        finally:
            self.session.info.pop("risk_review", None)
        return await self.read(project_id, risk_id)
