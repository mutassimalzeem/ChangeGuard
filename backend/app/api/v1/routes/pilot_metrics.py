"""Project pilot metrics, dashboard payload and on-demand weekly CSV export."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission, require_rate_limit
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.pilot_metrics import Dashboard, MetricsReport
from app.domain.services.pilot_metrics import PilotMetricsService, weekly_csv
from app.policy.permissions import Action

router = APIRouter(
    prefix="/projects/{project_id}/metrics",
    tags=["pilot-metrics"],
    dependencies=[
        Depends(require_permission(Action.AUDIT_READ)),
        Depends(require_permission(Action.FINANCIAL_READ)),
        Depends(require_rate_limit(requests=20, window_seconds=60, endpoint_tag="pilot_metrics")),
    ],
)


def metrics_service(
    session: AsyncSession = Depends(get_session), user: User = Depends(require_authenticated_user)
):
    return PilotMetricsService(session, user)


@router.get("", response_model=MetricsReport)
async def metrics(
    project_id: UUID,
    response: Response,
    start: datetime | None = None,
    end: datetime | None = None,
    service=Depends(metrics_service),
):
    response.headers["Cache-Control"] = "no-store"
    return await service.report(project_id, start, end)


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    project_id: UUID,
    response: Response,
    start: datetime | None = None,
    end: datetime | None = None,
    service=Depends(metrics_service),
):
    response.headers["Cache-Control"] = "no-store"
    return Dashboard(
        report=await service.report(project_id, start, end),
        sections={
            "processing": [
                "documents_uploaded",
                "documents_processed_successfully",
                "processing_failure_rate",
                "processing_latency_seconds",
            ],
            "quality": [
                "classification_accuracy",
                "extraction_accuracy",
                "evidence_link_coverage",
                "human_override_rate",
            ],
            "commercial": [
                "risks_detected",
                "risks_accepted",
                "risks_dismissed",
                "change_orders_created",
                "approval_cycle_time",
            ],
            "review": ["time_in_review_queue", "open_review_queue_age"],
            "ai_cost": ["ai_cost_per_document", "ai_cost_per_investigation"],
        },
    )


@router.get("/weekly.csv")
async def weekly_export(project_id: UUID, week_start: date, service=Depends(metrics_service)):
    if week_start.weekday() != 0:
        raise HTTPException(422, "week_start must be a Monday (UTC)")
    start = datetime.combine(week_start, time.min, tzinfo=UTC)
    report = await service.report(project_id, start, start + timedelta(days=7))
    return Response(
        weekly_csv(report),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="pilot-metrics-{project_id}-{week_start.isoformat()}.csv"',
            "Cache-Control": "no-store",
        },
    )
