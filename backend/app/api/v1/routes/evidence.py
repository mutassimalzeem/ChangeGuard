"""Project-scoped evidence inspection and append-only creation."""

# FastAPI dependency signatures declare path, query, body and injected arguments.
# ruff: noqa: B008, PLR0913, PLR0917
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.evidence import EvidenceCreate, EvidenceRead, EvidenceResult, SubjectType
from app.domain.services.evidence import EvidenceService
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/evidence",
    tags=["evidence"],
    dependencies=[Depends(require_permission(Action.DOCUMENT_READ))],
)


@router.get("/{subject_type}/{subject_id}", response_model=EvidenceResult)
async def view_evidence(
    project_id: UUID,
    subject_type: SubjectType,
    subject_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await EvidenceService(session, user).view(
        project_id, subject_type, subject_id, offset, limit
    )


@router.post("/{subject_type}/{subject_id}", response_model=list[EvidenceRead], status_code=201)
async def append_evidence(
    project_id: UUID,
    subject_type: SubjectType,
    subject_id: UUID,
    payload: Annotated[list[EvidenceCreate], Field(min_length=1, max_length=100)],
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await EvidenceService(session, user).append(
        project_id, subject_type, subject_id, payload
    )
