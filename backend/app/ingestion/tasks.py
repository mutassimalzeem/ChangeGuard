"""Ingestion Celery tasks."""

from contextlib import asynccontextmanager

from app.core.celery_app import celery_app


@asynccontextmanager
async def registry_worker_session():
    """Each Celery invocation owns its engine and event loop connections."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings

    engine = create_async_engine(
        str(get_settings().database_url), poolclass=NullPool, hide_parameters=True
    )
    try:
        async with engine.connect() as connection:
            async with AsyncSession(connection, expire_on_commit=False) as session:
                yield session
    finally:
        await engine.dispose()


async def process_registry_document(document_id: str, tenant_id: str):
    """Compatibility entrypoint for the durable processing pipeline."""
    from app.document_processing.pipeline import run_one_stage
    from app.domain.services.object_storage import get_object_storage_service

    return await run_one_stage(
        document_id, tenant_id, registry_worker_session, storage=get_object_storage_service()
    )


@celery_app.task(bind=True, acks_late=True, reject_on_worker_lost=True)
def process_uploaded_file(self, document_id: str, tenant_id: str):
    """Run a stage; recovery republishes if continuation publication fails."""
    import asyncio

    delay = asyncio.run(process_registry_document(document_id, tenant_id))
    if delay is not None:
        self.apply_async(args=[document_id, tenant_id], countdown=delay)


async def recover_registry_queue(*, now=None):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from starlette.concurrency import run_in_threadpool

    from app.domain.models import Document

    async with registry_worker_session() as session:
        rows = await session.scalars(
            select(Document)
            .where(
                Document.status.in_(["stored", "queued", "processing"]),
                Document.processing_status.not_in(
                    ["completed", "review_required", "dead_letter", "quarantined"]
                ),
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
    from app.document_processing.tasks import publish_dead_letters

    asyncio.run(publish_dead_letters())


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
