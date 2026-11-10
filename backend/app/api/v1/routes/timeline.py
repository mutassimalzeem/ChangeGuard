"""Permission-checked evidence timeline."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.timeline import TimelinePage
from app.domain.services.timeline import TimelineService
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/timeline",
    tags=["timeline"],
    dependencies=[
        Depends(require_permission(Action.DOCUMENT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
    ],
)


@router.get("", response_model=TimelinePage)
async def list_timeline(
    project_id: UUID,
    offset: int = Query(0, ge=0, le=10000),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await TimelineService(session, user).list(project_id, offset, limit)
