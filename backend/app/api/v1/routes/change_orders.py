"""Explicit human actions; status PATCH cannot bypass submit/decision endpoints."""

# ruff: noqa: B008
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.change_order import (
    ActionInput,
    ChangeOrderCreate,
    ChangeOrderPatch,
    DecisionInput,
    DraftInput,
    SubmitInput,
)
from app.domain.services.change_orders import ChangeOrderService
from app.policy.permissions import Action

router = APIRouter(
    tags=["change orders"],
    dependencies=[
        Depends(require_permission(Action.DOCUMENT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
    ],
)


def request_id(request):
    return getattr(request.state, "request_id", None)


@router.post("/projects/{project_id}/change-orders", status_code=201)
async def create_order(
    project_id: UUID,
    payload: ChangeOrderCreate,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await ChangeOrderService(session, user).create(
            project_id, payload, request_id(request)
        )
    except IntegrityError:
        raise HTTPException(409, "Conflicting change-order reference or source") from None


@router.get("/change-orders/{change_order_id}")
async def get_order(
    change_order_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).read(change_order_id)


@router.patch("/change-orders/{change_order_id}")
async def patch_order(
    change_order_id: UUID,
    payload: ChangeOrderPatch,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).patch(
        change_order_id, payload, request_id(request)
    )


@router.post("/change-orders/{change_order_id}/convert")
async def convert_order(
    change_order_id: UUID,
    request: Request,
    payload: ActionInput = Body(default=ActionInput()),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).convert(
        change_order_id, payload, request_id(request)
    )


@router.post("/change-orders/{change_order_id}/draft")
async def draft_order(
    change_order_id: UUID,
    request: Request,
    payload: DraftInput = Body(default=DraftInput()),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).draft(
        change_order_id, payload, request_id(request)
    )


@router.post("/change-orders/{change_order_id}/submit")
async def submit_order(
    change_order_id: UUID,
    payload: SubmitInput,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).submit(
        change_order_id, payload, request_id(request)
    )


@router.post("/change-orders/{change_order_id}/approve")
async def approve_order(
    change_order_id: UUID,
    payload: DecisionInput,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).decide(
        change_order_id, "approved", payload, request_id(request)
    )


@router.post("/change-orders/{change_order_id}/reject")
async def reject_order(
    change_order_id: UUID,
    payload: DecisionInput,
    request: Request,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    return await ChangeOrderService(session, user).decide(
        change_order_id, "rejected", payload, request_id(request)
    )


@router.post("/change-orders/{change_order_id}/export")
async def export_order(
    change_order_id: UUID,
    request: Request,
    payload: ActionInput = Body(default=ActionInput()),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    content = await ChangeOrderService(session, user).export(
        change_order_id, payload, request_id(request)
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="change-order-{change_order_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )
