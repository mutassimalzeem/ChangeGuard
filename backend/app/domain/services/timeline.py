"""Chronological union with the same all-sources-visible policy as risk reads."""

from fastapi import HTTPException
from sqlalchemy import select

from app.domain.models import EvidenceLink, ProjectEvent, Risk
from app.domain.schemas.evidence import EvidenceRead
from app.domain.schemas.timeline import TimelineItem, TimelinePage
from app.domain.services.evidence import EvidenceService
from app.domain.services.risks import RiskService


class TimelineService:
    def __init__(self, session, user):
        self.session, self.user = session, user
        self.evidence = EvidenceService(session, user)

    async def list(self, project_id, offset=0, limit=50):
        await self.evidence.access.project(project_id)

        def scoped(model):
            return (model.tenant_id == self.user.tenant_id, model.project_id == project_id)

        # Bound database work before hydrating evidence. Offset refers to candidate
        # records; inaccessible records leave a shorter page without revealing IDs.
        candidates = []
        for model, kind, timestamp in (
            (ProjectEvent, "event", ProjectEvent.occurred_at),
            (Risk, "risk", Risk.detected_at),
        ):
            rows = (
                await self.session.execute(
                    select(model.id, timestamp)
                    .where(*scoped(model))
                    .order_by(timestamp, model.id)
                    .limit(offset + limit + 1)
                )
            ).all()
            candidates.extend((row[1], kind, row[0]) for row in rows)
        rows = sorted(candidates)[offset : offset + limit + 1]
        items = []
        for occurred_at, kind, record_id in rows[:limit]:
            model = Risk if kind == "risk" else ProjectEvent
            record = await self.session.scalar(
                select(model).where(*scoped(model), model.id == record_id)
            )
            if record is None:
                continue
            subject = "risk" if kind == "risk" else "project_event"
            links = list(
                await self.session.scalars(
                    select(EvidenceLink)
                    .where(
                        *scoped(EvidenceLink),
                        EvidenceLink.subject_type == subject,
                        EvidenceLink.subject_id == record.id,
                    )
                    .order_by(EvidenceLink.created_at, EvidenceLink.id)
                )
            )
            try:
                if kind == "risk":
                    await RiskService(self.session, self.user).load(project_id, record.id)
                elif record.document_id:
                    await self.evidence.source(project_id, "document", record.document_id)
                for link in links:
                    await self.evidence.source(project_id, link.source_type, link.source_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                continue
            supported = bool(links) and record.status != "insufficient_evidence"
            items.append(
                TimelineItem(
                    id=record.id,
                    kind=kind,
                    occurred_at=occurred_at,
                    title=record.title,
                    description=record.description,
                    event_type=record.risk_type or record.category
                    if kind == "risk"
                    else record.event_type,
                    status=record.status if supported else "insufficient_evidence",
                    confidence=record.confidence,
                    severity=record.severity if kind == "risk" else None,
                    evidence=[EvidenceRead.model_validate(link) for link in links],
                    evidence_status="supported" if supported else "insufficient_evidence",
                )
            )
        return TimelinePage(items=items, offset=offset, limit=limit, has_more=len(rows) > limit)
