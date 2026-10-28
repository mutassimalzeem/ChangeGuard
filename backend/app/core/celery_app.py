"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "changeguard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.ingestion.tasks",
        "app.document_processing.tasks",
        "app.ai.tasks",
        "app.workflow.tasks",
    ],
)

# Configuration
celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=settings.celery_accept_content,
    timezone=settings.celery_timezone,
    enable_utc=settings.celery_enable_utc,
    task_track_started=settings.celery_task_track_started,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery_worker_max_tasks_per_child,
    result_expires=3600,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        "app.ingestion.tasks.*": {"queue": "ingestion"},
        "app.document_processing.tasks.*": {"queue": "document_processing"},
        "app.ai.tasks.*": {"queue": "ai"},
        "app.workflow.tasks.*": {"queue": "workflow"},
    },
    beat_schedule={
        "recover-document-queue": {"task": "app.ingestion.tasks.recover_document_queue", "schedule": 60.0},
        # Periodic tasks can be added here
        # "cleanup-expired-tokens": {
        #     "task": "app.core.tasks.cleanup_expired_tokens",
        #     "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
        # },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks()


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing."""
    print(f"Request: {self.request!r}")