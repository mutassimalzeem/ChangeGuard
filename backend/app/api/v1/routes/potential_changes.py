"""Human-review suggestions, never approved commercial commitments."""

# ruff: noqa: B008
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import EvidenceLink, ProjectEvent, User
from app.domain.services.evidence import EvidenceService
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/potential-changes",
    tags=["potential changes"],
    dependencies=[
        Depends(require_permission(Action.DOCUMENT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
    ],
)


async def read_event(session, user, project_id, event_id):
    evidence = EvidenceService(session, user)
    await evidence.access.project(project_id)
    event = await session.scalar(
        select(ProjectEvent).where(
            ProjectEvent.tenant_id == user.tenant_id,
            ProjectEvent.project_id == project_id,
            ProjectEvent.id == event_id,
            ProjectEvent.detection_key.is_not(None),
        )
    )
    if event is None:
        raise HTTPException(404, "Potential change not found")
    links = list(
        await session.scalars(
            select(EvidenceLink).where(
                EvidenceLink.tenant_id == user.tenant_id,
                EvidenceLink.project_id == project_id,
                EvidenceLink.subject_type == "project_event",
                EvidenceLink.subject_id == event.id,
            )
        )
    )
    if not links:
        raise HTTPException(404, "Potential change has no evidence")
    for link in links:
        await evidence.source(project_id, link.source_type, link.source_id)
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "detected_date": event.detected_date,
        "event_type": event.event_type,
        "evidence_links": [link.id for link in links],
        "confidence": event.confidence,
        "suggested_owner": event.suggested_owner,
        "suggested_cost_impact": str(event.suggested_cost_impact)
        if event.suggested_cost_impact is not None
        else None,
        "suggested_currency": event.suggested_currency,
        "suggested_schedule_impact": event.suggested_schedule_impact,
        "status": event.status,
        "human_review_required": True,
    }


@router.get("")
async def list_changes(
    project_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    evidence = EvidenceService(session, user)
    await evidence.access.project(project_id)
    ids = list(
        await session.scalars(
            select(ProjectEvent.id)
            .where(
                ProjectEvent.tenant_id == user.tenant_id,
                ProjectEvent.project_id == project_id,
                ProjectEvent.detection_key.is_not(None),
            )
            .order_by(ProjectEvent.created_at, ProjectEvent.id)
            .offset(offset)
            .limit(limit)
        )
    )
    results = []
    for event_id in ids:
        try:
            results.append(await read_event(session, user, project_id, event_id))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return results


@router.get("/{event_id}")
async def get_change(
    project_id: UUID,
    event_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await read_event(session, user, project_id, event_id)
