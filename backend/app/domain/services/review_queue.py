"""Build the queue from existing scoped findings and review tasks."""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import or_, select

from app.document_processing.structured.schemas import schema_for
from app.document_processing.structured.validation import fields
from app.domain.models import AuditEvent, DocumentReviewTask, EvidenceLink, Risk
from app.domain.services.risks import RiskService
from app.policy.permissions import Action, has_permission

EXTRACTION_REASONS = ("low_confidence", "low_classification_confidence")
RISK_CATEGORIES = {
    "missing_required_evidence": "missing_required_field",
    "duplicate_change_order_claim": "potential_duplicate",
    "conflicting_information": "conflicting_evidence",
}
EXTRACTION_STATUSES = {"dismiss": "dismissed", "request_evidence": "evidence_requested"}


def extraction_evidence(task, document):
    extraction = document.structured_extraction or {}
    schema = (
        schema_for(extraction.get("document_type"))
        if extraction.get("schema_version") == 1
        else None
    )
    if schema is None:
        return []
    try:
        facts = schema.model_validate(extraction.get("fields"))
    except ValidationError:
        return []
    citation = min(
        (field for _, field in fields(facts) if not field.missing),
        key=lambda field: field.confidence,
        default=None,
    )
    if citation is None:
        return []
    return [
        {
            "id": task.id,
            "source_type": "document",
            "document_id": document.id,
            "document_name": document.filename,
            "source_page": citation.source_page,
            "source_text_snippet": citation.source_text_snippet,
        }
    ]


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
        await self.evidence.access.project(project_id)
        linked = (
            self.scoped(EvidenceLink, project_id)
            .where(EvidenceLink.subject_type == "risk", EvidenceLink.subject_id == Risk.id)
            .exists()
        )
        items = []
        for risk_id in await self.session.scalars(
            self.scoped(Risk, project_id)
            .with_only_columns(Risk.id)
            .where(
                or_(
                    Risk.risk_type.in_(tuple(RISK_CATEGORIES)),
                    Risk.category.in_(tuple(RISK_CATEGORIES)),
                    Risk.severity.in_(("high", "critical")),
                    Risk.status == "insufficient_evidence",
                    Risk.evidence_review_required,
                    ~linked,
                )
            )
            .order_by(Risk.detected_at.desc(), Risk.id)
        ):
            try:
                risk = await self.risks.read(project_id, risk_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                continue
            categories = []
            if not risk["evidence_supported"]:
                categories.append("insufficient_evidence_risk")
            if category := RISK_CATEGORIES.get(risk["risk_type"]):
                categories.append(category)
            if risk["severity"] in {"high", "critical"}:
                categories.append("high_severity_risk")
            if categories:
                risk["document_id"] = risk["document_id"] or next(
                    (
                        link["document_id"]
                        for link in risk["evidence_details"]
                        if link["document_id"]
                    ),
                    None,
                )
                items.append(
                    {
                        **risk,
                        "kind": "risk",
                        "categories": categories,
                        "reviewable": risk["resolution"] is None
                        and risk["change_order_id"] is None
                        and risk["status"] not in {"resolved", "dismissed", "converted"},
                    }
                )

        for task in await self.session.scalars(
            self.extraction_tasks(project_id).order_by(
                DocumentReviewTask.created_at.desc(), DocumentReviewTask.id
            )
        ):
            try:
                document = await self.evidence.source(project_id, "document", task.document_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                continue
            confidence = document.extraction_confidence
            if confidence is None and task.reason == "low_classification_confidence":
                confidence = (document.classification_result or {}).get("confidence")
            items.append(
                {
                    "id": task.id,
                    "kind": "extraction",
                    "categories": ["low_confidence_extraction"],
                    "title": document.filename,
                    "risk_type": task.reason,
                    "description": None,
                    "confidence": confidence,
                    "document_id": document.id,
                    "evidence_details": extraction_evidence(task, document),
                    "evidence_supported": False,
                    "recommended_action": "Verify the extraction against the original document.",
                    "status": task.status,
                    "reviewable": task.status in {"pending", "evidence_requested"},
                    "change_order_id": None,
                }
            )
        return items

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
