"""Celery application configuration with graceful shutdown and error tracking."""

from celery import Celery
from celery.signals import setup_logging, task_failure, worker_shutdown, worker_shutting_down
from kombu import Queue

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


@setup_logging.connect
def configure_worker_logging(**kwargs):
    from app.core.logging import configure_logging

    configure_logging()


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
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_max_tasks_per_child=settings.celery_worker_max_tasks_per_child,
    result_expires=3600,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    worker_hijack_root_logger=False,
    broker_transport_options={"visibility_timeout": 3600},
    task_queues=tuple(
        Queue(name)
        for name in (
            "celery",
            "ingestion",
            "document_processing",
            "ai",
            "workflow",
            "document_dead_letter",
        )
    ),
    task_routes={
        "app.ingestion.tasks.*": {"queue": "ingestion"},
        "app.document_processing.tasks.*": {"queue": "document_processing"},
        "app.ai.tasks.*": {"queue": "ai"},
        "app.workflow.tasks.*": {"queue": "workflow"},
    },
    beat_schedule={
        "recover-document-queue": {
            "task": "app.ingestion.tasks.recover_document_queue",
            "schedule": 60.0,
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks()


@task_failure.connect
def on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    einfo=None,
    **kw,
):
    """Forward Celery task failures to Sentry error tracking."""
    if exception is not None:
        try:
            from app.core.sentry import capture_exception

            capture_exception(
                exception,
                tags={
                    "task_name": getattr(sender, "name", str(sender)),
                    "task_id": str(task_id),
                    "component": "celery_worker",
                },
                extra={
                    "task_args": str(args)[:500] if args else None,
                    "task_kwargs_keys": list(kwargs.keys()) if kwargs else [],
                },
            )
        except Exception as err:
            logger.error("Failed to capture Celery task exception", error=str(err))


@worker_shutting_down.connect
def on_worker_shutting_down(sig=None, how=None, exitcode=None, **kw):
    """Handle graceful shutdown signal for Celery worker."""
    logger.info(
        "Celery worker shutting down gracefully",
        signal=str(sig),
        how=str(how),
        exitcode=exitcode,
    )


@worker_shutdown.connect
def on_worker_shutdown(**kw):
    """Flush pending telemetry on worker exit."""
    try:
        from app.core.sentry import flush_sentry

        flush_sentry(timeout=3.0)
    except Exception:
        pass
    logger.info("Celery worker shutdown complete")


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing."""
    print(f"Request: {self.request!r}")
