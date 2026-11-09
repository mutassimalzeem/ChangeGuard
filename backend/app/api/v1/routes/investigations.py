"""Authenticated unresolved-case investigations with server-owned execution budgets."""

# ruff: noqa: B008
import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.context import model_scope
from app.ai.investigation.agent import InvestigationAgent, Trace
from app.ai.investigation.planner import GatewayPlanner
from app.ai.investigation.schemas import InvestigationRequest, tool_schemas
from app.api.dependencies import require_authenticated_user, require_permission, require_rate_limit
from app.core.config import get_settings
from app.core.database import get_session
from app.domain.models import User
from app.domain.services.investigation_tools import InvestigationTools
from app.domain.services.project_access import ProjectAccessService
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/investigations",
    tags=["investigations"],
    dependencies=[
        Depends(require_permission(Action.DOCUMENT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
    ],
)


@router.get("/tool-schemas")
async def schemas(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    await ProjectAccessService(session, user).project(project_id)
    return tool_schemas()


@router.post("")
async def investigate(
    project_id: UUID,
    payload: InvestigationRequest,
    request: Request,
    _rate_limit: User = Depends(
        require_rate_limit(requests=10, window_seconds=60, endpoint_tag="investigations")
    ),
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    seconds = min(payload.max_seconds, settings.investigation_max_seconds)
    depth = min(payload.max_tool_depth, settings.investigation_max_tool_depth)
    trace = Trace(user.tenant_id, project_id, user.id, getattr(request.state, "request_id", None))
    tools = InvestigationTools(
        session,
        user,
        project_id,
        payload.document_id,
        trace.run_id,
        getattr(request.state, "request_id", None),
    )
    deadline = asyncio.get_running_loop().time() + seconds
    try:
        async with asyncio.timeout_at(deadline):
            eligible, seed = await tools.prepare()
    except TimeoutError:
        await session.rollback()
        trace.record("final_recommendation", outcome="time_limit", tool_calls=0)
        return {
            "run_id": str(trace.run_id),
            "status": "time_limit",
            "conclusions": [],
            "action": None,
            "tool_calls": 0,
            "human_review_required": True,
            "trace": trace.events,
        }
    planner = GatewayPlanner(user.tenant_id, project_id) if eligible else None
    with model_scope(user.tenant_id, project_id, investigation_id=trace.run_id):
        result = await InvestigationAgent(planner, tools, trace).run(
            payload.question,
            seed,
            eligible=eligible,
            max_tool_depth=depth,
            max_seconds=seconds,
            absolute_deadline=deadline,
        )
    if result["status"] == "time_limit":
        await session.rollback()
    return result
