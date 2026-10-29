"""Checked append and read operations with source visibility applied on every read."""

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select

from app.domain.models import (
    AIAnswer,
    BOQItem,
    ChangeOrder,
    Claim,
    Contract,
    ContractClause,
    Document,
    DocumentChunk,
    EvidenceLink,
    ProjectEvent,
    Risk,
    SitePhoto,
)
from app.domain.schemas.evidence import EvidenceRead, EvidenceResult
from app.domain.services.project_access import ProjectAccessService
from app.policy.permissions import Action, has_permission

SUBJECTS = {
    "claim": Claim,
    "risk": Risk,
    "project_event": ProjectEvent,
    "change_order": ChangeOrder,
    "ai_answer": AIAnswer,
}
SOURCES = {
    "document": Document,
    "document_chunk": DocumentChunk,
    "site_photo": SitePhoto,
    "project_event": ProjectEvent,
    "boq_item": BOQItem,
    "contract_clause": ContractClause,
}


class EvidenceService:
    def __init__(self, session, user):
        self.session, self.user = session, user
        self.access = ProjectAccessService(session, user)

    async def record(self, model, project_id, record_id):
        row = await self.session.scalar(
            select(model).where(
                model.id == record_id,
                model.project_id == project_id,
                model.tenant_id == self.user.tenant_id,
            )
        )
        if row is None:
            raise HTTPException(404, "Evidence resource not found")
        return row

    async def source(self, project_id, source_type, source_id):
        if source_type not in SOURCES:
            raise HTTPException(422, "Invalid evidence source")
        row = await self.record(SOURCES[source_type], project_id, source_id)
        document = None
        if source_type == "document":
            document = row
        elif source_type in {"document_chunk", "site_photo"} or (
            source_type == "project_event" and row.document_id
        ):
            document = await self.record(Document, project_id, row.document_id)
        elif source_type in {"contract_clause", "boq_item"}:
            if source_type == "boq_item" and not has_permission(
                self.user.role, Action.FINANCIAL_READ
            ):
                raise HTTPException(404, "Evidence resource not found")
            contract = (
                await self.record(Contract, project_id, row.contract_id)
                if row.contract_id
                else None
            )
            if contract is not None and contract.document_id:
                document = await self.record(Document, project_id, contract.document_id)
        if document is not None and (
            document.deleted_at is not None
            or (
                document.access_level == "restricted"
                and self.user.role not in {"owner", "admin"}
                and document.uploaded_by_id != self.user.id
            )
        ):
            raise HTTPException(404, "Evidence resource not found")
        if (
            source_type == "document_chunk"
            and row.access_level == "restricted"
            and self.user.role not in {"owner", "admin"}
            and document.uploaded_by_id != self.user.id
        ):
            raise HTTPException(404, "Evidence resource not found")
        return row

    async def append(self, project_id, subject_type, subject_id, payloads):
        if not has_permission(self.user.role, Action.CHANGE_WRITE):
            raise HTTPException(403, "Access denied")
        await self.access.project(project_id)
        await self.record(SUBJECTS[subject_type], project_id, subject_id)
        # Validate the entire batch before adding anything to the session.
        for payload in payloads:
            await self.source(project_id, payload.source_type, payload.source_id)
        links = [
            EvidenceLink(
                tenant_id=self.user.tenant_id,
                project_id=project_id,
                subject_type=subject_type,
                subject_id=subject_id,
                created_by=self.user.id,
                **payload.model_dump(),
            )
            for payload in payloads
        ]
        self.session.add_all(links)
        await self.session.flush()
        return links

    async def view(self, project_id, subject_type, subject_id, offset=0, limit=50):
        await self.access.project(project_id)
        await self.record(SUBJECTS[subject_type], project_id, subject_id)
        rows = await self.session.scalars(
            select(EvidenceLink)
            .where(
                EvidenceLink.project_id == project_id,
                EvidenceLink.subject_type == subject_type,
                EvidenceLink.subject_id == subject_id,
            )
            .order_by(EvidenceLink.created_at, EvidenceLink.id)
            .offset(offset)
            .limit(limit)
        )
        visible = []
        for row in rows:
            try:
                await self.source(project_id, row.source_type, row.source_id)
            except HTTPException as exc:
                if exc.status_code != status.HTTP_404_NOT_FOUND:
                    raise
                continue
            visible.append(EvidenceRead.model_validate(row))
        return EvidenceResult(
            status="supported" if visible else "insufficient_evidence", evidence=visible
        )

    async def save_claim(  # noqa: PLR0913
        self, project_id, text, evidence, *, ai_generated=True, verified=False, ai_answer_id=None
    ):
        if not has_permission(self.user.role, Action.CHANGE_WRITE):
            raise HTTPException(403, "Access denied")
        if (ai_generated or verified) and not evidence:
            raise HTTPException(422, "insufficient_evidence")
        await self.access.project(project_id)
        for item in evidence:
            await self.source(project_id, item.source_type, item.source_id)
        claim = Claim(
            id=uuid4(),
            tenant_id=self.user.tenant_id,
            project_id=project_id,
            text=text,
            ai_generated=ai_generated,
            status="verified" if verified else "draft",
            ai_answer_id=ai_answer_id,
        )
        self.session.add(claim)
        await self.session.flush()
        await self.append(project_id, "claim", claim.id, evidence)
        return claim

    async def save_answer(self, project_id, facts):
        """Persist an answer only when every supplied factual assertion is grounded.

        Generation callers supply (claim text, evidence list) pairs. Unsupported
        output is discarded, and no partial answer or partial claims are saved.
        """
        if not facts or any(not evidence for _, evidence in facts):
            return {"status": "insufficient_evidence", "answer": None}
        if not has_permission(self.user.role, Action.CHANGE_WRITE):
            raise HTTPException(403, "Access denied")
        await self.access.project(project_id)
        for _, evidence in facts:
            for item in evidence:
                await self.source(project_id, item.source_type, item.source_id)
        async with self.session.begin_nested():
            answer = AIAnswer(
                id=uuid4(),
                tenant_id=self.user.tenant_id,
                project_id=project_id,
                text="\n".join(text for text, _ in facts),
                status="supported",
                created_by=self.user.id,
            )
            self.session.add(answer)
            await self.session.flush()
            for text, evidence in facts:
                await self.save_claim(project_id, text, evidence, ai_answer_id=answer.id)
                await self.append(project_id, "ai_answer", answer.id, evidence)
        return {"status": "supported", "answer": answer}
