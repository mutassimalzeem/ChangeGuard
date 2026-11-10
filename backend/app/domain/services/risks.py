"""Human risk review with atomic, append-only audit events."""

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.domain.models import AuditEvent, EvidenceLink, Risk
from app.domain.services.evidence import EvidenceService
from app.policy.permissions import Action, has_permission


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "dismiss", "override"]
    reason: str = Field(min_length=1, max_length=2000)
    severity: Literal["low", "medium", "high", "critical"] | None = None
    schedule_impact_days: int | None = Field(default=None, ge=0, le=36500)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A reason is mandatory")
        return value.strip()

    @model_validator(mode="after")
    def override_fields(self):
        changed = self.severity is not None or self.schedule_impact_days is not None
        if changed != (self.action == "override"):
            raise ValueError("Only override accepts changes, and at least one change is required")
        return self


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
        return risk, links

    async def read(self, project_id, risk_id):
        if not has_permission(self.user.role, Action.FINANCIAL_READ):
            raise HTTPException(403, "Access denied")
        risk, links = await self.load(project_id, risk_id)
        return {
            "id": risk.id,
            "risk_type": risk.risk_type or risk.category,
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
            "recommended_action": risk.recommended_action,
            "confidence": risk.confidence,
            "status": risk.status if links else "insufficient_evidence",
        }

    async def decide(self, project_id: UUID, risk_id: UUID, payload: RiskDecision, request_id=None):
        if not has_permission(self.user.role, Action.RISK_ACCEPT):
            raise HTTPException(403, "Access denied")
        risk, links = await self.load(project_id, risk_id, lock=True)
        if payload.action != "dismiss" and (not links or risk.status == "insufficient_evidence"):
            raise HTTPException(422, "insufficient_evidence")
        before = {
            "status": risk.status,
            "severity": risk.severity,
            "schedule_impact_days": risk.schedule_impact_days,
        }
        risk.status = {"accept": "accepted", "dismiss": "dismissed", "override": "overridden"}[
            payload.action
        ]
        if payload.severity is not None:
            risk.severity = payload.severity
        if payload.schedule_impact_days is not None:
            risk.schedule_impact_days = payload.schedule_impact_days
        audit = AuditEvent(
            tenant_id=self.user.tenant_id,
            project_id=project_id,
            actor_id=self.user.id,
            action=f"risk.{payload.action}",
            entity_type="risk",
            entity_id=risk.id,
            request_id=request_id,
            details={
                "reason": payload.reason,
                "before": before,
                "after": {
                    "status": risk.status,
                    "severity": risk.severity,
                    "schedule_impact_days": risk.schedule_impact_days,
                },
            },
        )
        self.session.add(audit)
        # The scope guard checks this exact object and its pending audit event.
        self.session.info["risk_review"] = (risk, audit)
        try:
            await self.session.flush()
        finally:
            self.session.info.pop("risk_review", None)
        return await self.read(project_id, risk_id)
