"""Transactional stages. Checkpoints and database side effects commit together."""

import hashlib
import math
from copy import deepcopy
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import structlog
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.document_processing.providers import Services
from app.document_processing.schema import Classification, Extraction
from app.domain.models import (
    RFI,
    ChangeOrder,
    Contract,
    Document,
    DocumentChunk,
    DocumentEntityLink,
    DocumentReviewTask,
    ProcessingDeadLetter,
    Risk,
)
from app.domain.services.document_files import validate_document
from app.domain.services.object_storage import get_object_storage_service

STAGES = (
    "validate_file",
    "store_original",
    "extract_text",
    "classify_document",
    "extract_fields",
    "validate_extraction",
    "create_chunks",
    "generate_embeddings",
    "index_chunks",
    "link_entities",
    "risk_checks",
    "create_review_task",
)
MAX_ATTEMPTS = 4
TERMINAL = {"completed", "review_required", "dead_letter", "quarantined"}
log = structlog.get_logger(__name__)


def scoped(model, document):
    return select(model).where(
        model.tenant_id == document.tenant_id,
        model.project_id == document.project_id,
    )


def chunks(text, size, overlap, limit):
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk configuration")
    result = []
    for offset in range(0, len(text), size - overlap):
        result.append(text[offset : offset + size])
        if offset + size >= len(text):
            break
    if not result or len(result) > limit:
        raise ValueError("Document chunk limit exceeded or no text")
    return result


async def execute_stage(stage, document, data, session, services, storage):
    async def original():
        content = await run_in_threadpool(storage.download_file, document.storage_key)
        if hashlib.sha256(content).hexdigest() != document.checksum:
            raise ValueError("Original checksum mismatch")
        return content

    if stage == "validate_file":
        await run_in_threadpool(validate_document, document.filename, await original())
        return {"checksum": document.checksum}
    if stage == "store_original":
        # Upload has already created the immutable object before publishing the job.
        # Verify it still matches; never overwrite the upload's original.
        await original()
        return {"storage_key": document.storage_key, "checksum": document.checksum}
    if stage == "extract_text":
        text = await run_in_threadpool(services.text, await original(), document.file_type)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("No document text extracted")
        if len(text) > 2_000_000:
            raise ValueError("Extracted text exceeds processing limit")
        return text
    if stage == "classify_document":
        result = Classification.model_validate(
            await run_in_threadpool(services.classify, data["extract_text"])
        )
        document.document_type = result.document_type
        return result.model_dump(mode="json")
    if stage == "extract_fields":
        # Store raw provider output before schema validation, even if it is invalid.
        return await run_in_threadpool(
            services.extract, data["extract_text"], data["classify_document"]
        )
    if stage == "validate_extraction":
        result = Extraction.model_validate(data["extract_fields"])
        document.extraction_confidence = min(
            result.confidence, data["classify_document"]["confidence"]
        )
        return result.model_dump(mode="json")
    if stage == "create_chunks":
        settings = get_settings()
        texts = chunks(
            data["extract_text"],
            settings.chunk_size,
            settings.chunk_overlap,
            settings.max_chunks_per_document,
        )
        for index, text in enumerate(texts):
            session.add(
                DocumentChunk(
                    tenant_id=document.tenant_id,
                    project_id=document.project_id,
                    document_id=document.id,
                    chunk_index=index,
                    text=text,
                )
            )
        return {"count": len(texts)}
    if stage in {"generate_embeddings", "index_chunks"}:
        rows = list(
            await session.scalars(
                scoped(DocumentChunk, document)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        if len(rows) != data["create_chunks"]["count"]:
            raise ValueError("Chunk checkpoint mismatch")
        if stage == "generate_embeddings":
            # Small batches stay within provider limits and persist only after full validation.
            vectors = []
            for start in range(0, len(rows), 32):
                vectors.extend(
                    await run_in_threadpool(
                        services.embed, [r.text for r in rows[start : start + 32]]
                    )
                )
            if len(vectors) != len(rows) or any(
                len(v) != 1536 or any(not math.isfinite(x) for x in v) for v in vectors
            ):
                raise ValueError("Invalid embedding response")
            for row, vector in zip(rows, vectors, strict=True):
                row.embedding = vector
        elif any(row.embedding is None for row in rows):
            raise ValueError("Missing chunk embeddings")
        # PostgreSQL GIN/HNSW indexes maintain themselves transactionally.
        return {"count": len(rows)}
    if stage == "link_entities":
        links, unresolved = [], []
        for entity in data["validate_extraction"]["entities"]:
            model = {"contract": Contract, "rfi": RFI, "change_order": ChangeOrder}[entity["kind"]]
            record = await session.scalar(
                scoped(model, document).where(model.reference == entity["reference"])
            )
            if record is None:
                unresolved.append(entity)
            else:
                link = await session.scalar(
                    scoped(DocumentEntityLink, document).where(
                        DocumentEntityLink.document_id == document.id,
                        getattr(DocumentEntityLink, f"{entity['kind']}_id") == record.id,
                    )
                )
                if link is None:
                    link = DocumentEntityLink(
                        tenant_id=document.tenant_id,
                        project_id=document.project_id,
                        document_id=document.id,
                        **{f"{entity['kind']}_id": record.id},
                    )
                    session.add(link)
                    await session.flush()
                links.append(
                    {
                        "kind": entity["kind"],
                        "record_id": str(record.id),
                        "reference": entity["reference"],
                    }
                )
        # Composite foreign keys enforce ownership of both ends of each link.
        return {"links": links, "unresolved": unresolved}
    if stage == "risk_checks":
        fields = data["validate_extraction"]
        codes = []
        if fields["amount"] is not None and fields["amount"] < 0:
            codes.append("negative_amount")
        if fields["amount"] is not None and not fields["currency"]:
            codes.append("missing_currency")
        # Anchor to receipt time so replays cannot change a time-based outcome.
        if fields["due_date"] and fields["due_date"] < document.created_at.date().isoformat():
            codes.append("overdue_at_receipt")
        if data["link_entities"]["unresolved"]:
            codes.append("unresolved_entity")
        for code in codes:
            session.add(
                Risk(
                    tenant_id=document.tenant_id,
                    project_id=document.project_id,
                    document_id=document.id,
                    title=code.replace("_", " ").capitalize(),
                    category="document_processing",
                    severity="medium",
                    status="open",
                )
            )
        return codes
    if stage == "create_review_task":
        low = float(document.extraction_confidence) < get_settings().processing_review_threshold
        required = low or bool(data["risk_checks"])
        if required:
            session.add(
                DocumentReviewTask(
                    tenant_id=document.tenant_id,
                    project_id=document.project_id,
                    document_id=document.id,
                    reason="low_confidence" if low else "risk_check",
                )
            )
        return {"required": required}
    raise ValueError("Unknown stage")


async def run_one_stage(document_id, tenant_id, session_factory, *, services=None, storage=None):
    """Run one bounded stage; return seconds until next delivery or None when terminal.

    A session advisory lock spans commits on a dedicated connection, protecting
    checkpoints and side effects while making running status visible immediately.
    """
    from sqlalchemy import text

    document_id, tenant_id = UUID(str(document_id)), UUID(str(tenant_id))
    services = services or Services()
    storage = storage or get_object_storage_service()
    async with session_factory() as session:
        lock_id = int.from_bytes(hashlib.sha256(document_id.bytes).digest()[:8], "big", signed=True)
        # session_factory pins the session to one connection for the whole invocation.
        acquired = await session.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id})
        await session.commit()
        if not acquired:
            return None  # current owner or periodic recovery will publish continuation
        try:
            document = await session.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,
                    Document.deleted_at.is_(None),
                )
            )
            if (
                document is None
                or document.processing_status in TERMINAL
                or document.status in {"quarantined", "failed"}
            ):
                return None
            state = deepcopy(document.processing_data or {})
            data = state.setdefault("results", {})
            stage = next((s for s in STAGES if s not in data), None)
            if stage is None:
                return None
            retry_at = state.get("retry_at")
            if retry_at and datetime.fromisoformat(retry_at) > datetime.now(UTC):
                return max(
                    1, (datetime.fromisoformat(retry_at) - datetime.now(UTC)).total_seconds()
                )
            attempts = state.setdefault("attempts", {})
            exhausted = attempts.get(stage, 0) >= MAX_ATTEMPTS
            attempts[stage] = min(attempts.get(stage, 0) + 1, MAX_ATTEMPTS)
            document.processing_status = stage
            document.status = "processing"
            document.processing_data = deepcopy(state)
            await session.commit()  # visible start and durable attempt before external I/O
            log.info(
                "document_processing_stage",
                document_id=str(document_id),
                tenant_id=str(tenant_id),
                project_id=str(document.project_id),
                stage=stage,
                duration_ms=0,
                outcome="started",
                attempt=attempts[stage],
            )
            started = monotonic()
            outcome = "completed"
            try:
                if exhausted:
                    raise RuntimeError("Interrupted stage exhausted attempts")
                async with session.begin_nested():
                    data[stage] = await execute_stage(
                        stage, document, data, session, services, storage
                    )
                    await session.flush()
                state.pop("retry_at", None)
                document.processing_status = f"{stage}_done"
                document.error_message = None
                delay = 0
                if stage == STAGES[-1]:
                    document.processing_status = (
                        "review_required" if data[stage]["required"] else "completed"
                    )
                    document.status = "review_required" if data[stage]["required"] else "linked"
                    delay = None
            except Exception as exc:
                from datetime import timedelta

                await session.refresh(document)
                data.pop(stage, None)
                outcome = "failed"
                # Never persist exception messages: providers can echo document text/secrets.
                state["error_type"] = type(exc).__name__
                document.error_message = f"Processing stage {stage} failed ({type(exc).__name__})"
                if is_transient(exc) and attempts[stage] < MAX_ATTEMPTS:
                    delay = min(30 * 2 ** (attempts[stage] - 1), 900)
                    state["retry_at"] = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
                    document.processing_status = "retry_pending"
                else:
                    document.processing_status = "dead_letter"
                    document.status = "failed"
                    session.add(
                        ProcessingDeadLetter(
                            tenant_id=document.tenant_id,
                            project_id=document.project_id,
                            document_id=document.id,
                            stage=stage,
                            attempts=attempts[stage],
                            error_type=type(exc).__name__,
                        )
                    )
                    delay = None
            document.processing_data = deepcopy(state)
            await session.commit()
            log.info(
                "document_processing_stage",
                document_id=str(document_id),
                tenant_id=str(tenant_id),
                project_id=str(document.project_id),
                stage=stage,
                duration_ms=round((monotonic() - started) * 1000, 2),
                outcome=outcome,
                attempt=attempts[stage],
            )
            return delay
        finally:
            await session.rollback()
            await session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
            await session.commit()


def is_transient(exc):
    from botocore.exceptions import ConnectionClosedError, EndpointConnectionError
    from celery.exceptions import SoftTimeLimitExceeded
    from openai import APIConnectionError, APIStatusError, APITimeoutError
    from sqlalchemy.exc import OperationalError

    from app.domain.services.object_storage import StorageError

    return isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            ConnectionClosedError,
            EndpointConnectionError,
            APIConnectionError,
            APITimeoutError,
            OperationalError,
            SoftTimeLimitExceeded,
            StorageError,
        ),
    ) or (isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500))
