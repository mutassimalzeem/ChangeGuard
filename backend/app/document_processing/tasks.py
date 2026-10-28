"""Dead-letter outbox dispatch. The operator queue has no automatic consumer."""

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.domain.models import ProcessingDeadLetter


async def publish_dead_letters():
    from app.ingestion.tasks import registry_worker_session

    async with registry_worker_session() as session, session.begin():
        rows = await session.scalars(
            select(ProcessingDeadLetter)
            .where(ProcessingDeadLetter.status == "pending")
            .with_for_update(skip_locked=True)
            .limit(100)
        )
        for row in rows:
            celery_app.send_task(
                "app.document_processing.dead_letter",
                kwargs={
                    "dead_letter_id": str(row.id),
                    "document_id": str(row.document_id),
                    "tenant_id": str(row.tenant_id),
                    "project_id": str(row.project_id),
                    "stage": row.stage,
                    "attempts": row.attempts,
                },
                queue="document_dead_letter",
                task_id=str(row.id),
            )
            row.status = "published"
