"""Customer pilot onboarding; reuse registry and scoped ORM boundaries."""

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import require_authenticated_user, require_permission, require_rate_limit
from app.api.v1.routes.documents import get_document_service
from app.core.database import get_session
from app.document_processing.structured.schemas import schema_for
from app.domain.models import (
    Approval,
    AuditEvent,
    ChangeOrder,
    Document,
    PilotOnboarding,
    Project,
    ProjectMembership,
    Risk,
    User,
)
from app.domain.services.pilot import CHECKLIST, inspect_archive, render_report, summarize
from app.domain.services.project_access import ProjectAccessService
from app.policy.permissions import Action, has_permission

router = APIRouter(prefix="/pilot", tags=["pilot"])


class PilotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=255)
    template: Literal["construction-v1"] = "construction-v1"
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    document_type: (
        Literal[
            "contract",
            "boq",
            "drawing",
            "rfi",
            "daily_report",
            "change_order",
            "site_photo",
            "email",
            "quotation",
            "other",
        ]
        | None
    ) = None
    fields: dict | None = None
    reason: str = Field(min_length=1, max_length=2000)
    version: int = Field(ge=1)


class ChecklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    completed: list[Literal["scope", "evidence", "upload", "review", "risks", "signoff"]] = Field(
        max_length=6
    )


def audit(session, user, project_id, action, details, request):
    event = AuditEvent(
        tenant_id=user.tenant_id,
        project_id=project_id,
        actor_id=user.id,
        action=action,
        entity_type="pilot",
        entity_id=project_id,
        details=details,
        request_id=getattr(request.state, "request_id", None),
    )
    session.add(event)
    session.info["pilot_audit"] = event


@router.get("/templates", dependencies=[Depends(require_permission(Action.PROJECT_CREATE))])
async def templates():
    return [
        dict(
            id="construction-v1",
            name="Construction pilot",
            required_evidence=["contract", "boq", "drawing"],
        )
    ]


@router.get("/projects", dependencies=[Depends(require_permission(Action.PROJECT_READ))])
async def list_pilots(
    user: User = Depends(require_authenticated_user), session: AsyncSession = Depends(get_session)
):
    rows = await session.scalars(
        select(Project)
        .join(
            PilotOnboarding,
            (PilotOnboarding.project_id == Project.id)
            & (PilotOnboarding.tenant_id == Project.tenant_id),
        )
        .where(Project.tenant_id == user.tenant_id)
        .order_by(Project.created_at.desc())
        .limit(100)
    )
    return [{"project_id": str(project.id), "name": project.name} for project in rows]


@router.post(
    "/projects", status_code=201, dependencies=[Depends(require_permission(Action.PROJECT_CREATE))]
)
async def create(
    payload: PilotCreate,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    project = Project(
        tenant_id=user.tenant_id,
        code="PILOT-" + uuid4().hex[:12].upper(),
        name=payload.name,
        currency=payload.currency,
        description="Construction pilot (construction-v1)",
        status="active",
    )
    session.add(project)
    await session.flush()
    session.info["pilot_created_project"] = project
    session.add(
        PilotOnboarding(
            tenant_id=user.tenant_id, project_id=project.id, template=payload.template, completed=[]
        )
    )
    membership = ProjectMembership(
        tenant_id=user.tenant_id, project_id=project.id, user_id=user.id, is_active=True
    )
    session.add(membership)
    session.info["pilot_membership"] = membership
    audit(session, user, project.id, "pilot.create", {"template": payload.template}, request)
    await session.commit()
    return {"project_id": str(project.id)}


async def pilot_project(project_id, session, user):
    project = await ProjectAccessService(session, user).project(project_id)
    marker = await session.scalar(
        select(PilotOnboarding).where(
            PilotOnboarding.tenant_id == user.tenant_id, PilotOnboarding.project_id == project_id
        )
    )
    if marker is None:
        raise HTTPException(404, "Pilot not found")
    return project


@router.post(
    "/projects/{project_id}/zip",
    dependencies=[
        Depends(require_rate_limit(requests=5, window_seconds=60, endpoint_tag="pilot_zip"))
    ],
)
async def upload_zip(
    project_id: UUID, file: UploadFile = File(...), service=Depends(get_document_service)
):
    service.permission(True)
    await pilot_project(project_id, service.session, service.user)
    content = await file.read(50 * 1024 * 1024 + 1)
    entries = await run_in_threadpool(inspect_archive, content)
    outcomes = []
    for name, data in entries:
        member = UploadFile(filename=name, file=BytesIO(data))
        try:
            document, status = await service.upload(
                project_id, member, "pilot_zip", None, "project"
            )
            outcomes.append(dict(file_name=name, document_id=str(document.id), status=status))
        except HTTPException as exc:
            outcomes.append(dict(file_name=name, status=exc.status_code, error=exc.detail))
        finally:
            await member.close()
    return {"items": outcomes}


@router.get("/projects/{project_id}/documents")
async def progress(project_id: UUID, service=Depends(get_document_service)):
    service.permission()
    await pilot_project(project_id, service.session, service.user)
    docs = list(
        await service.session.scalars(
            service.visible(select(Document).where(Document.project_id == project_id)).order_by(
                Document.created_at, Document.id
            )
        )
    )
    return [
        dict(
            document_id=str(d.id),
            file_name=d.filename,
            status=d.status,
            document_type=d.document_type,
            version=d.document_version,
            extraction=d.attributes.get("pilot_review", {}).get(
                "extraction", d.structured_extraction
            )
            if has_permission(service.user.role, Action.FINANCIAL_READ)
            else None,
            reviewed=bool(d.attributes.get("pilot_review")),
            error=d.error_message,
        )
        for d in docs
    ]


@router.patch("/documents/{document_id}/review")
async def review(
    document_id: UUID, payload: Review, request: Request, service=Depends(get_document_service)
):
    doc = await service.get(document_id, write=True)
    await pilot_project(doc.project_id, service.session, service.user)
    doc = await service.session.scalar(
        service.visible(select(Document).where(Document.id == document_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payload.version != doc.document_version:
        raise HTTPException(409, "Document changed; refresh before saving")
    if doc.status not in {"linked", "review_required"}:
        raise HTTPException(409, "Wait until processing finishes before reviewing")
    if not payload.reason.strip() or (payload.document_type is None and payload.fields is None):
        raise HTTPException(422, "Provide a correction and reason")
    before_review = dict(doc.attributes.get("pilot_review", {}))
    previous = dict(before_review)
    if payload.document_type is not None:
        previous["document_type"] = payload.document_type
        doc.document_type = payload.document_type
    if payload.fields is not None:
        if not has_permission(service.user.role, Action.FINANCIAL_READ):
            raise HTTPException(403, "Financial read permission required for extraction review")
        original = doc.structured_extraction
        if not original or original.get("document_type") != doc.document_type:
            raise HTTPException(409, "Extraction schema does not match document type")
        try:
            facts = schema_for(doc.document_type).model_validate(payload.fields)
        except (ValueError, KeyError):
            raise HTTPException(422, "Invalid extraction fields or evidence envelope") from None
        previous["extraction"] = {**original, "fields": facts.model_dump(mode="json")}
    previous.update(actor_id=str(service.user.id), reviewed_at=datetime.now(UTC).isoformat())
    doc.attributes = {**doc.attributes, "pilot_review": previous}
    doc.document_version += 1
    audit(
        service.session,
        service.user,
        doc.project_id,
        "pilot.review",
        {
            "document_id": str(doc.id),
            "version": doc.document_version,
            "reason": payload.reason,
            "type_reviewed": payload.document_type is not None,
            "extraction_reviewed": payload.fields is not None,
            "before": before_review,
            "after": previous,
        },
        request,
    )
    await service.session.commit()
    return {"version": doc.document_version}


@router.get(
    "/projects/{project_id}/checklist",
    dependencies=[Depends(require_permission(Action.DOCUMENT_READ))],
)
async def checklist(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    await pilot_project(project_id, session, user)
    state = await session.scalar(
        select(PilotOnboarding).where(
            PilotOnboarding.project_id == project_id, PilotOnboarding.tenant_id == user.tenant_id
        )
    )
    if state is None:
        raise HTTPException(404, "Pilot not found")
    return {"steps": CHECKLIST, "completed": state.completed}


@router.put(
    "/projects/{project_id}/checklist",
    dependencies=[Depends(require_permission(Action.DOCUMENT_WRITE))],
)
async def save_checklist(
    project_id: UUID,
    payload: ChecklistUpdate,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    await pilot_project(project_id, session, user)
    state = await session.scalar(
        select(PilotOnboarding)
        .where(
            PilotOnboarding.project_id == project_id, PilotOnboarding.tenant_id == user.tenant_id
        )
        .with_for_update()
    )
    if state is None:
        raise HTTPException(404, "Pilot not found")
    state.completed = payload.completed
    audit(session, user, project_id, "pilot.checklist", payload.model_dump(), request)
    await session.commit()
    return payload


async def readiness(project_id, service):
    service.permission()
    project = await pilot_project(project_id, service.session, service.user)
    docs = list(
        await service.session.scalars(
            service.visible(select(Document).where(Document.project_id == project_id))
        )
    )

    async def rows(model):
        return list(
            await service.session.scalars(
                select(model).where(
                    model.tenant_id == service.user.tenant_id, model.project_id == project_id
                )
            )
        )

    risks, approvals, changes = await rows(Risk), await rows(Approval), await rows(ChangeOrder)
    exposure, unknown = {}, 0
    for change in changes:
        if change.status not in {"potential", "under_review", "drafted", "submitted", "disputed"}:
            continue
        if change.amount is None:
            unknown += 1
        else:
            exposure[change.currency] = exposure.get(change.currency, Decimal(0)) + change.amount
    now = datetime.now(UTC)
    return {
        **summarize(
            [
                dict(
                    status=d.status,
                    document_type=d.document_type,
                    attributes=d.attributes,
                    classification_result=d.classification_result,
                    extraction_confidence=d.extraction_confidence,
                )
                for d in docs
            ]
        ),
        "project_name": project.name,
        "project_id": str(project_id),
        "generated_at": now.isoformat(),
        "risks_detected": sum(r.status == "open" for r in risks),
        "overdue_approvals": sum(
            a.status == "pending" and a.due_at is not None and a.due_at < now for a in approvals
        ),
        "pending_exposure": {currency: str(amount) for currency, amount in exposure.items()},
        "unknown_exposure_count": unknown,
        "notes": "Accuracy uses human-reviewed original predictions only. Confidence remains model confidence. Extraction edits are human overlays; downstream records require separate review.",
    }


@router.get(
    "/projects/{project_id}/readiness",
    dependencies=[Depends(require_permission(Action.FINANCIAL_READ))],
)
async def report(project_id: UUID, service=Depends(get_document_service)):
    return await readiness(project_id, service)


@router.get(
    "/projects/{project_id}/readiness.pdf",
    dependencies=[Depends(require_permission(Action.FINANCIAL_READ))],
)
async def pdf(project_id: UUID, service=Depends(get_document_service)):
    snapshot = await readiness(project_id, service)
    content = await run_in_threadpool(render_report, snapshot)
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="pilot-readiness.pdf"',
            "Cache-Control": "no-store",
        },
    )
