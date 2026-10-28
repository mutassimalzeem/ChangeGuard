"""Ingestion Celery tasks."""

from contextlib import asynccontextmanager

from app.core.celery_app import celery_app


@asynccontextmanager
async def registry_worker_session():
    """Each Celery invocation owns its engine and event loop connections."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().database_url), poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        await engine.dispose()


async def process_registry_document(document_id: str, tenant_id: str):
    """Trusted worker transaction; explicit tenant boundary, row-lock idempotency."""
    import hashlib
    from uuid import UUID

    from sqlalchemy import select
    from starlette.concurrency import run_in_threadpool

    from app.domain.models import Document
    from app.domain.services.document_files import validate_document
    from app.domain.services.object_storage import get_object_storage_service

    async with registry_worker_session() as session:
        async with session.begin():
            document = await session.scalar(
                select(Document)
                .where(
                    Document.id == UUID(document_id),
                    Document.tenant_id == UUID(tenant_id),
                    Document.deleted_at.is_(None),
                    Document.status.in_(["received", "validating", "stored", "queued"]),
                )
                .with_for_update(skip_locked=True)
            )
            if document is None:
                return
            document.status = "processing"
            await session.flush()
            try:
                content = await run_in_threadpool(
                    get_object_storage_service().download_file, document.storage_key
                )
                if hashlib.sha256(content).hexdigest() != document.checksum:
                    raise ValueError("Original checksum mismatch")
                await run_in_threadpool(validate_document, document.filename, content)
                # Extraction/classification are separate features; never claim they succeeded.
                document.status = "review_required"
                document.error_message = None
            except Exception:
                document.status = "quarantined"
                document.error_message = "Processing failed; original retained for operator review"


@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def process_uploaded_file(document_id: str, tenant_id: str):
    """Start document processing outside the API process."""
    import asyncio

    asyncio.run(process_registry_document(document_id, tenant_id))


async def recover_registry_queue(*, now=None):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from starlette.concurrency import run_in_threadpool

    from app.domain.models import Document

    async with registry_worker_session() as session:
        rows = await session.scalars(
            select(Document)
            .where(
                Document.status.in_(["received", "validating", "stored", "queued"]),
                Document.deleted_at.is_(None),
                Document.updated_at < (now or datetime.now(UTC)) - timedelta(minutes=5),
            )
            .limit(100)
        )
        for document in rows:
            await run_in_threadpool(
                process_uploaded_file.delay, str(document.id), str(document.tenant_id)
            )


@celery_app.task
def recover_document_queue():
    """Republish durable queued registry rows after broker/API interruptions."""
    import asyncio

    asyncio.run(recover_registry_queue())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_email(self, email_data: dict):
    """Ingest email from IMAP/Graph API."""
    # TODO: Implement email ingestion
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_bulk_upload(self, upload_id: str):
    """Process bulk ZIP upload."""
    # TODO: Implement bulk upload processing
    pass
