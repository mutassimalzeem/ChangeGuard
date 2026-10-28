"""Mock provider boundaries; exercise durable checkpoints in disposable PostgreSQL."""

import hashlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_processing.extraction.types import ExtractionResult, TextBlock
from app.document_processing.pipeline import (
    STAGES,
    execute_stage,
    is_transient,
    run_one_stage,
)
from app.document_processing.providers import ProviderUnavailable, Services
from app.document_processing.schema import Extraction
from app.domain.models import (
    Document,
    DocumentChunk,
    DocumentReviewTask,
    ProcessingDeadLetter,
    Risk,
)


def providers(confidence=0.95):
    services = Mock(spec=Services)
    services.ocr.return_value = "Document OCR text"
    services.extraction.side_effect = lambda content, extension: ExtractionResult(
        blocks=[
            TextBlock(
                text=services.ocr(content, extension),
                page_number=1,
                location={"source": "mock_ocr"},
            )
        ]
    )
    services.classify.return_value = {"document_type": "contract", "confidence": confidence}
    services.extract.return_value = {
        "title": "Works",
        "summary": "Contract terms",
        "confidence": confidence,
        "amount": None,
        "currency": None,
        "due_date": None,
        "entities": [],
    }
    services.embed.side_effect = lambda texts: [[0.1] * 1536 for _ in texts]
    return services


@pytest.fixture
async def pipeline(test_session, project, tenant):
    from app.domain.services.document_files import validate_document
    from tests.test_documents import pdf_bytes

    content = pdf_bytes()
    validate_document("file.pdf", content)
    document = Document(
        id=uuid4(),
        tenant_id=tenant.id,
        project_id=project.id,
        filename="file.pdf",
        storage_key=f"{tenant.id}/{project.id}/documents/original",
        file_type="pdf",
        mime_type="application/pdf",
        size_bytes=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        status="queued",
        processing_status="queued",
    )
    test_session.add(document)
    await test_session.commit()
    storage = Mock()
    storage.download_file.return_value = content

    @asynccontextmanager
    async def factory():
        async with AsyncSession(
            bind=test_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    services = providers()

    async def step():
        return await run_one_stage(
            document.id, tenant.id, factory, services=services, storage=storage
        )

    async def refresh():
        await test_session.refresh(document)
        return document

    return SimpleNamespace(
        document=document,
        storage=storage,
        services=services,
        step=step,
        refresh=refresh,
        factory=factory,
        tenant=tenant,
    )


async def finish(pipeline):
    for _ in STAGES:
        delay = await pipeline.step()
    return delay


async def test_all_stages_and_duplicate_delivery(pipeline, test_session):
    for stage in STAGES:
        await pipeline.step()
        document = await pipeline.refresh()
        assert stage in document.processing_data["results"]
        assert document.processing_status == (
            "completed" if stage == STAGES[-1] else f"{stage}_done"
        )
    assert await pipeline.step() is None
    for name in ("extraction", "ocr", "classify", "extract", "embed"):
        getattr(pipeline.services, name).assert_called_once()
    assert await test_session.scalar(select(func.count()).select_from(DocumentChunk)) == 1
    assert await test_session.scalar(select(func.count()).select_from(DocumentReviewTask)) == 0
    pipeline.storage.store_original.assert_not_called()
    pipeline.storage.delete_file.assert_not_called()


async def test_low_confidence_creates_one_review_task(pipeline, test_session):
    pipeline.services.extract.return_value["confidence"] = 0.4
    await finish(pipeline)
    await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "review_required"
    review = await test_session.scalar(select(DocumentReviewTask))
    assert review.document_id == document.id and review.reason == "low_confidence"
    assert await test_session.scalar(select(func.count()).select_from(DocumentReviewTask)) == 1


async def test_transient_failure_backoff_and_partial_resume(pipeline, test_session):
    for _ in range(7):
        await pipeline.step()
    pipeline.services.embed.side_effect = TimeoutError("secret raw document must not be stored")
    for attempt, expected_delay in enumerate((30, 60, 120, None), 1):
        assert await pipeline.step() == expected_delay
        document = await pipeline.refresh()
        assert len(document.processing_data["results"]) == 7
        assert document.processing_data["attempts"]["generate_embeddings"] == attempt
        assert "secret" not in str(document.processing_data) + document.error_message
        if expected_delay:
            assert await pipeline.step() > 0  # early duplicate cannot bypass backoff
            document.processing_data = {
                **document.processing_data,
                "retry_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            }
            await test_session.commit()
    dead = await test_session.scalar(select(ProcessingDeadLetter))
    assert dead.stage == "generate_embeddings" and dead.attempts == 4
    assert document.processing_status == "dead_letter"
    assert await test_session.scalar(select(func.count()).select_from(DocumentChunk)) == 1
    await pipeline.step()
    pipeline.services.extraction.assert_called_once()


async def test_retry_recovers_without_repeating_previous_services(pipeline, test_session):
    for _ in range(7):
        await pipeline.step()
    pipeline.services.embed.side_effect = TimeoutError()
    assert await pipeline.step() == 30
    document = await pipeline.refresh()
    document.processing_data = {
        **document.processing_data,
        "retry_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    }
    await test_session.commit()
    pipeline.services.embed.side_effect = lambda texts: [[0.1] * 1536 for _ in texts]
    for _ in range(5):
        await pipeline.step()
    assert (await pipeline.refresh()).processing_status == "completed"
    pipeline.services.ocr.assert_called_once()
    pipeline.services.classify.assert_called_once()
    pipeline.services.extract.assert_called_once()


async def test_invalid_extraction_preserved_before_validation_dead_letter(pipeline, test_session):
    pipeline.services.extract.return_value = {"confidence": 7, "untrusted": "raw response"}
    for _ in range(6):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "dead_letter"
    assert document.processing_data["results"]["extract_fields"]["untrusted"] == "raw response"
    assert "validate_extraction" not in document.processing_data["results"]
    assert (await test_session.scalar(select(ProcessingDeadLetter))).error_type == "ValidationError"
    pipeline.services.embed.assert_not_called()


@pytest.mark.parametrize("mutation", ["wrong_tenant", "deleted", "quarantined"])
async def test_scope_and_unavailable_documents_skip(pipeline, test_session, mutation):
    document = pipeline.document
    tenant_id = pipeline.tenant.id
    if mutation == "wrong_tenant":
        tenant_id = uuid4()
    elif mutation == "deleted":
        document.deleted_at = datetime.now(UTC)
    else:
        document.status = "quarantined"
    await test_session.commit()
    assert (
        await run_one_stage(
            document.id,
            tenant_id,
            pipeline.factory,
            services=pipeline.services,
            storage=pipeline.storage,
        )
        is None
    )
    pipeline.storage.download_file.assert_not_called()


async def test_risk_checks_and_entity_links(pipeline, test_session, project, tenant):
    from app.domain.models import Contract

    contract = Contract(tenant_id=tenant.id, project_id=project.id, reference="C-1", title="Works")
    test_session.add(contract)
    await test_session.commit()
    pipeline.services.extract.return_value.update(
        {
            "amount": -100,
            "due_date": "2000-01-01",
            "entities": [
                {"kind": "contract", "reference": "C-1"},
                {"kind": "contract", "reference": "MISSING"},
            ],
        }
    )
    await finish(pipeline)
    document = await pipeline.refresh()
    links = document.processing_data["results"]["link_entities"]
    assert links["links"][0]["record_id"] == str(contract.id)
    assert links["unresolved"][0]["reference"] == "MISSING"
    assert await test_session.scalar(select(func.count()).select_from(Risk)) == 4
    await pipeline.step()
    assert await test_session.scalar(select(func.count()).select_from(Risk)) == 4


async def test_dead_letter_outbox(pipeline, test_session, monkeypatch):
    from app.document_processing.tasks import publish_dead_letters

    pipeline.storage.download_file.side_effect = ValueError("invalid")
    await pipeline.step()
    monkeypatch.setattr("app.ingestion.tasks.registry_worker_session", pipeline.factory)
    send = Mock()
    monkeypatch.setattr("app.document_processing.tasks.celery_app.send_task", send)
    send.side_effect = ConnectionError()
    with pytest.raises(ConnectionError):
        await publish_dead_letters()
    send.side_effect = None
    await publish_dead_letters()
    await publish_dead_letters()
    assert send.call_count == 2
    assert send.call_args.kwargs["queue"] == "document_dead_letter"
    assert (await test_session.scalar(select(ProcessingDeadLetter))).status == "published"


async def test_concurrent_delivery_skips_locked_document(pipeline, test_engine):
    from sqlalchemy import text

    key = int.from_bytes(
        hashlib.sha256(pipeline.document.id.bytes).digest()[:8], "big", signed=True
    )
    async with test_engine.connect() as connection:
        await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        try:
            assert await pipeline.step() is None
            pipeline.storage.download_file.assert_not_called()
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


async def test_interrupted_attempt_budget_is_durable(pipeline, test_session):
    pipeline.document.processing_data = {"attempts": {"validate_file": 4}, "results": {}}
    await test_session.commit()
    await pipeline.step()
    assert (await pipeline.refresh()).processing_status == "dead_letter"
    pipeline.storage.download_file.assert_not_called()


async def test_recovery_republishes_interrupted_stage(pipeline, test_session, monkeypatch):
    from app.ingestion.tasks import recover_registry_queue

    await pipeline.step()
    await pipeline.refresh()
    pipeline.document.updated_at = datetime.now(UTC) - timedelta(minutes=10)
    await test_session.commit()
    monkeypatch.setattr("app.ingestion.tasks.registry_worker_session", pipeline.factory)
    send = Mock()
    monkeypatch.setattr("app.ingestion.tasks.process_uploaded_file.delay", send)
    await recover_registry_queue(now=datetime.now(UTC) + timedelta(minutes=10))
    send.assert_called_once_with(str(pipeline.document.id), str(pipeline.tenant.id))


async def test_stage_logs_include_scope_duration_without_text(pipeline, monkeypatch):
    logger = Mock()
    monkeypatch.setattr("app.document_processing.pipeline.log", logger)
    await pipeline.step()
    assert logger.info.call_count == 2
    fields = logger.info.call_args.kwargs
    assert fields["document_id"] == str(pipeline.document.id)
    assert fields["tenant_id"] == str(pipeline.tenant.id)
    assert fields["project_id"] == str(pipeline.document.project_id)
    assert fields["duration_ms"] >= 0
    assert fields["stage"] == "validate_file"
    assert "text" not in fields


async def test_entity_references_cannot_link_across_project(pipeline, test_session, tenant):
    from app.domain.models import Contract, DocumentEntityLink, Project

    other = Project(id=uuid4(), tenant_id=tenant.id, code="OTHER", name="Other project")
    test_session.add(other)
    await test_session.flush()
    test_session.add(
        Contract(tenant_id=tenant.id, project_id=other.id, reference="OTHER-1", title="Other")
    )
    await test_session.commit()
    pipeline.services.extract.return_value["entities"] = [
        {"kind": "contract", "reference": "OTHER-1"}
    ]
    await finish(pipeline)
    document = await pipeline.refresh()
    assert document.processing_data["results"]["link_entities"]["links"] == []
    assert await test_session.scalar(select(func.count()).select_from(DocumentEntityLink)) == 0


def test_retry_policy():
    assert is_transient(TimeoutError())
    assert is_transient(ConnectionError())
    assert not is_transient(ValueError())
    assert not is_transient(ProviderUnavailable())


async def test_ocr_classify_extract_and_embed_unit():
    """No database or network; all requested service boundaries are mocked."""
    services = providers()
    document = SimpleNamespace(
        file_type="png", checksum=hashlib.sha256(b"image").hexdigest(), storage_key="key"
    )
    storage = Mock(download_file=Mock(return_value=b"image"))
    session = Mock(add=Mock())
    text = await execute_stage("extract_text", document, {}, session, services, storage)
    data = {"extract_text": text}
    data["classify_document"] = await execute_stage(
        "classify_document", document, data, session, services, storage
    )
    data["extract_fields"] = await execute_stage(
        "extract_fields", document, data, session, services, storage
    )
    data["validate_extraction"] = await execute_stage(
        "validate_extraction", document, data, session, services, storage
    )
    data["create_chunks"] = {"count": 1}
    document.id, document.project_id, document.tenant_id = uuid4(), uuid4(), uuid4()
    row = SimpleNamespace(text="Document OCR text", embedding=None)
    session.scalars = AsyncMock(return_value=[row])
    await execute_stage("generate_embeddings", document, data, session, services, storage)
    assert len(row.embedding) == 1536
    for name in ("ocr", "classify", "extract", "embed"):
        getattr(services, name).assert_called_once()


def test_extraction_schema_rejects_nonfinite_and_extra_authority():
    valid = providers().extract.return_value
    for bad in ({"confidence": -1}, {"amount": float("nan")}, {"approved": True}):
        with pytest.raises(ValueError):
            Extraction.model_validate({**valid, **bad})
