"""Checked application write service; the agent never receives a database session."""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.ai.investigation.agent import digest
from app.domain.models import AuditEvent, Document, DocumentReviewTask
from app.domain.services.evidence import EvidenceService
from app.policy.permissions import Action, has_permission


class InvestigationReviewService:
    def __init__(self, session, user):
        self.session, self.user = session, user
        self.evidence = EvidenceService(session, user)

    async def request(self, project_id, document_id, run_id, evidence, request_id=None):
        if not has_permission(self.user.role, Action.DOCUMENT_WRITE) or not evidence:
            raise HTTPException(403, "Review request denied")
        await self.evidence.access.project(project_id)
        await self.evidence.source(project_id, "document", document_id)
        await self.session.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.tenant_id == self.user.tenant_id,
                Document.project_id == project_id,
            )
            .with_for_update()
        )
        task = await self.session.scalar(
            select(DocumentReviewTask).where(
                DocumentReviewTask.tenant_id == self.user.tenant_id,
                DocumentReviewTask.project_id == project_id,
                DocumentReviewTask.document_id == document_id,
            )
        )
        if task is None:
            task = DocumentReviewTask(
                id=uuid4(),
                tenant_id=self.user.tenant_id,
                project_id=project_id,
                document_id=document_id,
                reason="investigation_required",
                status="pending",
            )
            self.session.add(task)
        else:
            task.status = "pending"
        audit = AuditEvent(
            tenant_id=self.user.tenant_id,
            project_id=project_id,
            actor_id=self.user.id,
            action="investigation.request_human_review",
            entity_type="document_review_task",
            entity_id=task.id,
            request_id=request_id,
            details={
                "run_id": str(run_id),
                "evidence": [
                    {
                        "source_type": r.source_type,
                        "source_id": str(r.source_id),
                        "source_page": r.source_page,
                        "excerpt_hash": digest(r.excerpt),
                    }
                    for r in evidence
                ],
            },
        )
        self.session.add(audit)
        self.session.info["investigation_review"] = (task, audit)
        try:
            await self.session.flush()
        finally:
            self.session.info.pop("investigation_review", None)
        return {"review_task_id": str(task.id), "status": "pending"}
