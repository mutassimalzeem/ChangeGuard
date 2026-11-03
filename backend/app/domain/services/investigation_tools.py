"""Fixed project capabilities. Read tools query; writes delegate to application workflows."""

import asyncio
import json
import re
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.ai.investigation.agent import Observation
from app.ai.investigation.schemas import READ_TOOLS, EvidenceRef, ToolCall
from app.document_processing.structured.schemas import schema_for
from app.domain.models import (
    Approval,
    ChangeOrder,
    Document,
    DocumentChunk,
    DocumentReviewTask,
    ProjectEvent,
)
from app.domain.schemas.change_order import ActionInput, ChangeOrderCreate, DraftInput
from app.domain.schemas.evidence import EvidenceCreate
from app.domain.services.change_orders import ChangeOrderService
from app.domain.services.evidence import EvidenceService
from app.domain.services.investigation_review import InvestigationReviewService
from app.domain.services.potential_changes import classify_rules
from app.retrieval.schemas import SearchFilters, SearchRequest
from app.retrieval.service import HybridRetrieval


@dataclass
class SelectedHit:
    chunk_id: object
    document_id: object
    page_number: int | None
    text: str


@dataclass
class SelectedResult:
    results: list[SelectedHit]


class SelectedEvidenceRetrieval:
    """Replay only the already observed chunks through the normal draft workflow."""

    def __init__(self, evidence, project_id, refs):
        self.evidence, self.project_id, self.refs = evidence, project_id, refs

    async def search(self, request):
        if request.filters.project_id != self.project_id:
            raise HTTPException(403, "Project scope mismatch")
        hits = []
        for ref in self.refs:
            chunk = await self.evidence.source(self.project_id, "document_chunk", ref.source_id)
            if ref.excerpt not in chunk.text:
                raise HTTPException(422, "Evidence changed")
            hits.append(SelectedHit(chunk.id, chunk.document_id, chunk.page_number, chunk.text))
        return SelectedResult(hits)


class InvestigationTools:
    def __init__(self, session, user, project_id, document_id, run_id, request_id=None):
        self.session, self.user = session, user
        self.project_id, self.document_id, self.run_id = project_id, document_id, run_id
        self.request_id = request_id
        self.evidence = EvidenceService(session, user)
        self.search = HybridRetrieval(session, user)
        self.eligible = False

    def scoped(self, model):
        return select(model).where(
            model.tenant_id == self.user.tenant_id, model.project_id == self.project_id
        )

    async def document(self, document_id):
        document = await self.evidence.source(self.project_id, "document", document_id)
        if document.status in {"failed", "quarantined"}:
            raise HTTPException(404, "Evidence not available")
        return document

    async def chunk(self, chunk_id):
        chunk = await self.evidence.source(self.project_id, "document_chunk", chunk_id)
        await self.document(chunk.document_id)
        return chunk

    def add(self, observation, kind, row_id, excerpt, page=None):
        if not excerpt:
            return None
        observation.evidence.append(
            EvidenceRef(
                source_type=kind, source_id=row_id, source_page=page, excerpt=excerpt[:2000]
            )
        )
        return len(observation.evidence) - 1

    def document_facts(self, document, observation):
        result = document.structured_extraction
        if not result or result.get("schema_version") != 1:
            return
        schema = schema_for(result["document_type"])
        if schema is None:
            return
        facts = schema.model_validate(result["fields"])
        identity = {
            "change_order": "co_number",
            "rfi": "rfi_number",
            "contract": "reference",
            "drawing": "drawing_number",
            "quotation": "reference",
        }.get(result["document_type"])
        if identity is None or getattr(facts, identity).missing:
            return
        subject = [
            result["document_type"],
            getattr(facts, identity).value,
            document.document_version,
        ]
        subject.extend(
            getattr(getattr(facts, name, None), "value", None)
            for name in ("revision", "issue_date", "status")
        )
        for name in ("amount", "contract_value", "stated_total", "due_date"):
            value = getattr(facts, name, None)
            if value is None or value.missing:
                continue
            recorded = value.value
            key = json.dumps(subject + [name, getattr(recorded, "currency", None)], default=str)
            normalized = (
                f"{recorded.currency}:{recorded.amount.normalize()}"
                if hasattr(recorded, "currency")
                else str(recorded)
            )
            index = self.add(
                observation, "document", document.id, value.source_text_snippet, value.source_page
            )
            observation.facts.append((key, normalized, index))

    async def chunk_observation(self, chunks):
        observation = Observation()
        visited = set()
        for chunk in chunks:
            index = self.add(observation, "document_chunk", chunk.id, chunk.text, chunk.page_number)
            # Explicit opposing instructions about the same referenced work are
            # contradictions, even when neither source has typed extraction.
            for reference in re.findall(r"\b(?:RFI|CO|SI|DRW)-[A-Za-z0-9-]+\b", chunk.text, re.I):
                for match in re.finditer(
                    r"\b(?P<negative>do not )?(?P<verb>proceed|install|excavate|construct) "
                    r"(?P<work>[^.!?\n]{3,120})",
                    chunk.text,
                    re.I,
                ):
                    key = (
                        "instruction:"
                        + reference.casefold()
                        + ":"
                        + match["verb"].casefold()
                        + ":"
                        + " ".join(match["work"].casefold().split())
                    )
                    observation.facts.append(
                        (key, "prohibited" if match["negative"] else "instructed", index)
                    )
            if chunk.document_id not in visited:
                self.document_facts(await self.document(chunk.document_id), observation)
                visited.add(chunk.document_id)
        return observation

    async def prepare(self):
        await self.evidence.access.project(self.project_id)
        document = await self.document(self.document_id)
        chunks = list(
            await self.session.scalars(
                self.scoped(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(8)
            )
        )
        visible = []
        for chunk in chunks:
            try:
                visible.append(await self.chunk(chunk.id))
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        observation = await self.chunk_observation(visible)
        known = {}
        conflict_found = False
        for key, value, _ in observation.facts:
            if key in known and known[key] != value:
                conflict_found = True
            known[key] = value
        if known:
            others = await self.session.scalars(
                self.scoped(Document)
                .where(Document.id != document.id)
                .order_by(Document.created_at.desc())
                .limit(32)
            )
            for other in others:
                if len(observation.evidence) >= 48:
                    break
                try:
                    await self.document(other.id)
                    candidate = Observation()
                    self.document_facts(other, candidate)
                except HTTPException as exc:
                    if exc.status_code == 404:
                        continue
                    raise
                for key, value, index in candidate.facts:
                    if key in known and known[key] != value and len(observation.evidence) < 48:
                        observation.evidence.append(candidate.evidence[index])
                        observation.facts.append((key, value, len(observation.evidence) - 1))
                        conflict_found = True
        clauses = [text for chunk in visible for text in re.split(r"(?<=[.!?])\s+|\n+", chunk.text)]
        self.eligible = any(classify_rules(text)[1] for text in clauses)
        review = await self.session.scalar(
            self.scoped(DocumentReviewTask).where(
                DocumentReviewTask.document_id == document.id,
                DocumentReviewTask.status == "pending",
            )
        )
        self.eligible = bool(visible) and (
            self.eligible
            or (
                review is not None
                and review.reason
                in {
                    "potential_change_classification_required",
                    "low_confidence",
                    "investigation_required",
                }
            )
        )
        if conflict_found:
            self.eligible = False
        observation.result = {
            "gate": "deterministic_conflict"
            if conflict_found
            else "unresolved_rule_classification"
            if self.eligible
            else "deterministic_only"
        }
        return self.eligible, observation

    async def execute(self, call, ledger, deadline):
        call = ToolCall.model_validate(call)
        if not self.eligible:
            raise HTTPException(403, "Deterministic gate denied investigation")
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError
        if call.name in READ_TOOLS:
            with self.session.no_autoflush:
                return await self.read(call)
        refs = ledger.selected(call.arguments.evidence_ids)
        if call.name == "request_human_review" and ledger.conflicts:
            refs = ledger.selected(
                list(
                    dict.fromkeys(
                        call.arguments.evidence_ids
                        + [label for pair in ledger.conflicts for label in pair]
                    )
                )
            )
        async with self.session.begin_nested():
            # Revalidate every selected source immediately before an application write.
            for ref in refs:
                if ref.source_type in {
                    "document",
                    "document_chunk",
                    "boq_item",
                    "contract_clause",
                    "project_event",
                }:
                    await self.evidence.source(self.project_id, ref.source_type, ref.source_id)
            if call.name == "create_draft_change_order":
                if ledger.conflicts or any(ref.source_type != "document_chunk" for ref in refs):
                    raise HTTPException(422, "Draft requires nonconflicting observed source chunks")
                all_chunks = {
                    ref.source_id
                    for ref in ledger.items.values()
                    if ref.source_type == "document_chunk"
                }
                if {ref.source_id for ref in refs} != all_chunks:
                    raise HTTPException(422, "A draft cannot omit observed source chunks")
                if any(
                    ref.source_type not in {"document", "document_chunk"}
                    for ref in ledger.items.values()
                ):
                    raise HTTPException(422, "Mixed resource evidence requires human review")
                document = await self.document(self.document_id)
                project = await self.evidence.access.project(self.project_id)
                service = ChangeOrderService(
                    self.session,
                    self.user,
                    gateway=False,
                    retrieval=SelectedEvidenceRetrieval(self.evidence, self.project_id, refs),
                )
                created = await service.create(
                    self.project_id,
                    ChangeOrderCreate(
                        reference="INV-" + self.run_id.hex[:20],
                        title="Investigation draft: " + document.filename[:220],
                        currency=project.currency,
                        evidence=[
                            EvidenceCreate(
                                source_type="document_chunk",
                                source_id=r.source_id,
                                source_page=r.source_page,
                                source_text_snippet=r.excerpt,
                            )
                            for r in refs
                        ],
                    ),
                    self.request_id,
                )
                await service.convert(created["id"], ActionInput(), self.request_id)
                drafted = await service.draft(created["id"], DraftInput(), self.request_id)
                result = {"change_order_id": str(drafted["id"]), "status": drafted["status"]}
            elif call.name == "request_human_review":
                result = await InvestigationReviewService(self.session, self.user).request(
                    self.project_id, self.document_id, self.run_id, refs, self.request_id
                )
            else:
                raise HTTPException(403, "Action denied")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError
        return Observation(result=result)

    async def read(self, call):
        args, name = call.arguments, call.name
        if name == "search_project_documents":
            result = await self.search.search(
                SearchRequest(
                    query=args.query,
                    semantic=False,
                    limit=args.limit,
                    filters=SearchFilters(project_id=self.project_id),
                )
            )
            return await self.chunk_observation(
                [await self.chunk(hit.chunk_id) for hit in result.results]
            )
        if name == "get_document_chunk":
            return await self.chunk_observation([await self.chunk(args.record_id)])
        observation = Observation()
        if name in {"get_contract_clause", "get_boq_item"}:
            kind = "contract_clause" if name == "get_contract_clause" else "boq_item"
            row = await self.evidence.source(self.project_id, kind, args.record_id)
            data = (
                {"clause_number": row.clause_number, "text": row.text}
                if kind == "contract_clause"
                else {
                    "item_code": row.item_code,
                    "description": row.description,
                    "quantity": str(row.quantity),
                    "unit": row.unit,
                    "unit_rate": str(row.unit_rate),
                    "currency": row.currency,
                }
            )
            self.add(observation, kind, row.id, json.dumps(data))
        elif name in {"get_change_order", "get_approval_history"}:
            if (
                await self.session.scalar(
                    self.scoped(ChangeOrder).where(ChangeOrder.id == args.record_id)
                )
                is None
            ):
                raise HTTPException(404, "Evidence not found")
            order = await ChangeOrderService(self.session, self.user).load(args.record_id)
            if order.project_id != self.project_id:
                raise HTTPException(404, "Evidence not found")
            if name == "get_change_order":
                self.add(
                    observation,
                    "change_order",
                    order.id,
                    json.dumps(
                        {
                            "reference": order.reference,
                            "title": order.title,
                            "description": order.description,
                            "status": order.status,
                            "recorded_amount": str(order.amount),
                            "currency": order.currency,
                        }
                    ),
                )
            else:
                approvals = await self.session.scalars(
                    self.scoped(Approval)
                    .where(Approval.change_order_id == order.id)
                    .order_by(Approval.created_at)
                    .limit(8)
                )
                for approval in approvals:
                    self.add(
                        observation,
                        "approval",
                        approval.id,
                        json.dumps(
                            {
                                "status": approval.status,
                                "reason": approval.comments,
                                "decided_at": str(approval.decided_at),
                            }
                        ),
                    )
        elif name == "get_project_timeline":
            events = await self.session.scalars(
                self.scoped(ProjectEvent)
                .order_by(ProjectEvent.occurred_at.desc(), ProjectEvent.id)
                .limit(args.limit)
            )
            for event in events:
                try:
                    await self.evidence.source(self.project_id, "project_event", event.id)
                except HTTPException as exc:
                    if exc.status_code == 404:
                        continue
                    raise
                self.add(
                    observation,
                    "project_event",
                    event.id,
                    json.dumps(
                        {
                            "title": event.title,
                            "description": event.description,
                            "occurred_at": str(event.occurred_at),
                        }
                    ),
                )
        elif name == "find_similar_past_cases":
            words = re.findall(r"[A-Za-z0-9-]+", args.query)[:5]
            if words:
                rows = await self.session.scalars(
                    self.scoped(ChangeOrder)
                    .where(
                        ChangeOrder.status.in_(["closed", "approved", "rejected", "disputed"]),
                        or_(
                            *(ChangeOrder.title.icontains(word, autoescape=True) for word in words)
                        ),
                    )
                    .order_by(ChangeOrder.created_at.desc())
                    .limit(args.limit)
                )
                for row in rows:
                    try:
                        await ChangeOrderService(self.session, self.user).load(row.id)
                    except HTTPException as exc:
                        if exc.status_code == 404:
                            continue
                        raise
                    self.add(
                        observation,
                        "change_order",
                        row.id,
                        json.dumps(
                            {"reference": row.reference, "title": row.title, "status": row.status}
                        ),
                    )
        else:
            raise HTTPException(403, "Unknown capability")
        return observation
