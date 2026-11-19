"""Project-scoped review queue for risk findings and extraction review tasks."""

# ruff: noqa: B008
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import User
from app.domain.services.review_queue import ReviewQueueService
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/review-queue",
    tags=["review queue"],
    dependencies=[
        Depends(require_permission(Action.DOCUMENT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
        Depends(require_permission(Action.RISK_ACCEPT)),
    ],
)


class ExtractionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["dismiss", "request_evidence"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ReviewCitation(BaseModel):
    id: UUID
    source_type: str
    document_id: UUID | None
    document_name: str | None
    source_page: int | None
    source_text_snippet: str | None


class ReviewItem(BaseModel):
    id: UUID
    kind: Literal["risk", "extraction"]
    categories: list[
        Literal[
            "insufficient_evidence_risk",
            "low_confidence_extraction",
            "missing_required_field",
            "potential_duplicate",
            "conflicting_evidence",
            "high_severity_risk",
        ]
    ]
    title: str
    risk_type: str
    description: str | None
    severity: str | None = None
    confidence: float | None
    document_id: UUID | None
    evidence_details: list[ReviewCitation]
    evidence_supported: bool
    recommended_action: str | None
    status: str
    reviewable: bool
    change_order_id: UUID | None


@router.get("", response_model=list[ReviewItem])
async def list_review_queue(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ReviewQueueService(session, user).list(project_id)


@router.post("/extractions/{task_id}/decisions", status_code=204)
async def decide_extraction(
    project_id: UUID,
    task_id: UUID,
    payload: ExtractionDecision,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    await ReviewQueueService(session, user).decide_extraction(
        project_id,
        task_id,
        payload.action,
        payload.reason,
        getattr(request.state, "request_id", None),
    )
