"""Explicit human linkage; not exposed as an investigation/model tool."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.event_link import EventLinkCreate, EventLinkResult
from app.domain.services.event_links import EventLinkService

router = APIRouter(tags=["event links"])


@router.post("/projects/{project_id}/events/{event_id}/links", response_model=EventLinkResult)
async def link_entity(
    project_id: UUID,
    event_id: UUID,
    payload: EventLinkCreate,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await EventLinkService(session, user).link(
        project_id, event_id, payload, getattr(request.state, "request_id", None)
    )
