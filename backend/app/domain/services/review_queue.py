"""Build the queue from existing scoped findings and review tasks."""

from fastapi import HTTPException
from sqlalchemy import select

from app.domain.models import AuditEvent, DocumentReviewTask
from app.domain.schemas.review_workspace import QueueFilters
from app.domain.services.review_read import EXTRACTION_REASONS, read_review_page
from app.domain.services.risks import RiskService
from app.policy.permissions import Action, has_permission

EXTRACTION_STATUSES = {"dismiss": "dismissed", "request_evidence": "evidence_requested"}


class ReviewQueueService:
    def __init__(self, session, user):
        self.session = session
        self.user = user
        self.risks = RiskService(session, user)
        self.evidence = self.risks.evidence

    def scoped(self, model, project_id):
        return select(model).where(
            model.tenant_id == self.user.tenant_id,
            model.project_id == project_id,
        )

    def extraction_tasks(self, project_id):
        return self.scoped(DocumentReviewTask, project_id).where(
            DocumentReviewTask.reason.in_(EXTRACTION_REASONS)
        )

    async def list(self, project_id):
        result = await read_review_page(
            self.session, project_id, QueueFilters(status="all"), legacy=True
        )
        return result["items"]

    async def decide_extraction(self, project_id, task_id, action, reason, request_id):
        if not has_permission(self.user.role, Action.RISK_ACCEPT):
            raise HTTPException(403, "Access denied")
        await self.evidence.access.project(project_id)
        task = await self.session.scalar(
            self.extraction_tasks(project_id)
            .where(DocumentReviewTask.id == task_id)
            .with_for_update()
        )
        if task is None:
            raise HTTPException(404, "Extraction review task not found")
        await self.evidence.source(project_id, "document", task.document_id)
        if task.status not in {"pending", "evidence_requested"}:
            raise HTTPException(409, "This extraction review is closed")
        before = task.status
        task.status = EXTRACTION_STATUSES[action]
        audit = AuditEvent(
            tenant_id=self.user.tenant_id,
            project_id=project_id,
            actor_id=self.user.id,
            action=f"document_review_task.{action}",
            entity_type="document_review_task",
            entity_id=task.id,
            request_id=request_id,
            details={"reason": reason, "before": before, "after": task.status},
        )
        self.session.add(audit)
        self.session.info["extraction_review"] = (task, audit)
        try:
            await self.session.flush()
        finally:
            self.session.info.pop("extraction_review", None)
