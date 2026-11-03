"""Project-scoped risk inspection and human review."""

# ruff: noqa: B008
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import User
from app.domain.services.risks import RiskDecision, RiskService
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/risks",
    tags=["risks"],
    dependencies=[
        Depends(require_permission(Action.DOCUMENT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
    ],
)


@router.get("")
async def list_risks(
    project_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await RiskService(session, user).list(project_id, offset, limit)


@router.get("/{risk_id}")
async def read_risk(
    project_id: UUID,
    risk_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await RiskService(session, user).read(project_id, risk_id)


@router.post("/{risk_id}/decisions")
async def decide_risk(
    project_id: UUID,
    risk_id: UUID,
    payload: RiskDecision,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await RiskService(session, user).decide(
        project_id, risk_id, payload, getattr(request.state, "request_id", None)
    )
