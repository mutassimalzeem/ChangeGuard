"""Project-scoped review queue for risk findings and extraction review tasks."""

# ruff: noqa: B008
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.review_workspace import Category, Kind, QueueFilters, ReviewCommand
from app.domain.services.review_queue import ReviewQueueService
from app.domain.services.review_workspace import ReviewWorkspace
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
    kind: Kind
    categories: list[Category]
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


class HistoryEntry(BaseModel):
    action: str
    actor_id: UUID | None
    at: datetime
    reason: str | None
    owner_id: UUID | None


class WorkspaceItem(ReviewItem):
    created_at: datetime
    owner_id: UUID | None = None
    deadline: datetime | None = None
    review_state: str
    history: list[HistoryEntry]
    can_decide: bool = False
    amount: str | None = None
    currency: str | None = None


class WorkspacePage(BaseModel):
    items: list[WorkspaceItem]
    total: int


class Reviewer(BaseModel):
    id: UUID
    full_name: str


@router.get("/workspace", response_model=WorkspacePage)
async def workspace_page(
    project_id: UUID,
    filters: Annotated[QueueFilters, Query()],
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ReviewWorkspace(session, user).page(project_id, filters)


@router.get("/reviewers", response_model=list[Reviewer])
async def reviewers(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ReviewWorkspace(session, user).roster(project_id)


@router.post("/{kind}/{item_id}/commands")
async def review_command(
    project_id: UUID,
    kind: Kind,
    item_id: UUID,
    payload: ReviewCommand,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ReviewWorkspace(session, user).command(
        project_id, kind, item_id, payload, getattr(request.state, "request_id", None)
    )


class NoteTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Kind
    id: UUID


class BulkNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: UUID
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    targets: list[NoteTarget] = Field(min_length=1, max_length=20)


@router.post("/notes", status_code=204)
async def add_notes(
    project_id: UUID,
    payload: BulkNote,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    workspace = ReviewWorkspace(session, user)
    # Keep batch acquisition consistent with the order -> approval lock hierarchy.
    targets = sorted(set(payload.targets), key=lambda t: (t.kind == "approval", t.kind, t.id))
    async with session.begin_nested():
        for target in targets:
            await workspace.command(
                project_id,
                target.kind,
                target.id,
                ReviewCommand(
                    action="add_note",
                    reason=payload.reason,
                    key=uuid5(payload.key, f"{target.kind}/{target.id}"),
                ),
                getattr(request.state, "request_id", None),
            )
