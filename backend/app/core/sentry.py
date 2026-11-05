"""Sentry-compatible error tracking and exception telemetry hook."""

from collections.abc import Mapping
from typing import Any, Literal
from uuid import uuid4

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redaction import redact
from app.core.request_logging import request_context

settings = get_settings()
logger = get_logger(__name__)

SentryLevel = Literal["fatal", "critical", "error", "warning", "info", "debug"]

# State
_sentry_initialized = False


def _scrub_sentry_event(event: Any, hint: Any) -> Any:
    """Scrub sensitive credentials and PII from Sentry error events."""
    # Redact request headers if present
    request_data = event.get("request", {})
    if "headers" in request_data and isinstance(request_data["headers"], dict):
        for header in ("authorization", "cookie", "x-api-key", "set-cookie", "proxy-authorization"):
            if header in request_data["headers"]:
                request_data["headers"][header] = "[REDACTED]"

    # Attach current tenant and request ID from request context
    context = request_context.get() or {}
    tags = event.setdefault("tags", {})
    if "tenant_id" in context:
        tags["tenant_id"] = str(context["tenant_id"])
    if "request_id" in context:
        tags["request_id"] = str(context["request_id"])

    # Redact extra context
    if "extra" in event and isinstance(event["extra"], dict):
        event["extra"] = redact(event["extra"])

    return event


def init_sentry() -> bool:
    """Initialize Sentry SDK if SENTRY_DSN is configured.

    Returns True if Sentry was initialized, False otherwise.
    """
    global _sentry_initialized

    if not settings.sentry_dsn:
        logger.info("Sentry DSN not configured; using structured logging fallback for error tracking")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        traces_sample_rate = 1.0 if settings.environment == "staging" else 0.1

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            release=f"changeguard@{settings.app_version}",
            traces_sample_rate=traces_sample_rate,
            send_default_pii=False,
            before_send=_scrub_sentry_event,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                CeleryIntegration(),
                SqlalchemyIntegration(),
                RedisIntegration(),
            ],
        )
        _sentry_initialized = True
        logger.info(
            "Sentry error tracking initialized",
            environment=settings.environment,
            release=f"changeguard@{settings.app_version}",
        )
        return True
    except ImportError:
        logger.warning(
            "sentry-sdk package is not installed; error tracking will use structured logging fallback"
        )
        return False
    except Exception as exc:
        logger.error("Failed to initialize Sentry SDK", error=str(exc))
        return False


def is_sentry_active() -> bool:
    """Check if Sentry SDK is active."""
    return _sentry_initialized


def capture_exception(
    exc: BaseException,
    *,
    tags: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Capture an exception to Sentry or structured logging fallback.

    Returns the event identifier (UUID string).
    """
    event_id = str(uuid4())
    context = request_context.get() or {}

    merged_tags = {
        "environment": settings.environment,
        "service": settings.otel_service_name,
        **{k: str(v) for k, v in (tags or {}).items()},
    }
    if "tenant_id" in context:
        merged_tags["tenant_id"] = str(context["tenant_id"])
    if "request_id" in context:
        merged_tags["request_id"] = str(context["request_id"])

    safe_extra = redact(dict(extra or {}))

    if _sentry_initialized:
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                for k, v in merged_tags.items():
                    scope.set_tag(k, v)
                for k, v in safe_extra.items():
                    scope.set_extra(k, v)
                sentry_event_id = sentry_sdk.capture_exception(exc)
                if sentry_event_id:
                    event_id = str(sentry_event_id)
        except Exception as sentry_err:
            logger.error("Failed sending exception to Sentry", error=str(sentry_err))

    # Always log structured error event
    logger.error(
        "Application error captured",
        action="sentry_error_captured",
        event_id=event_id,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        tags=merged_tags,
        extra=safe_extra,
    )

    return event_id


def capture_message(
    message: str,
    *,
    level: SentryLevel = "info",
    tags: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Capture a message event to Sentry or structured logging fallback."""
    event_id = str(uuid4())
    context = request_context.get() or {}

    merged_tags = {
        "environment": settings.environment,
        "service": settings.otel_service_name,
        **{k: str(v) for k, v in (tags or {}).items()},
    }
    if "tenant_id" in context:
        merged_tags["tenant_id"] = str(context["tenant_id"])

    safe_extra = redact(dict(extra or {}))

    if _sentry_initialized:
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                for k, v in merged_tags.items():
                    scope.set_tag(k, v)
                for k, v in safe_extra.items():
                    scope.set_extra(k, v)
                sentry_event_id = sentry_sdk.capture_message(message, level=level)
                if sentry_event_id:
                    event_id = str(sentry_event_id)
        except Exception as sentry_err:
            logger.error("Failed sending message to Sentry", error=str(sentry_err))

    logger.info(
        message,
        action="sentry_message_captured",
        event_id=event_id,
        level=level,
        tags=merged_tags,
        extra=safe_extra,
    )

    return event_id


def set_user_context(user_id: str | None = None, tenant_id: str | None = None) -> None:
    """Set the authenticated user context for error tracking."""
    if _sentry_initialized:
        try:
            import sentry_sdk

            user_data: dict[str, Any] = {}
            if user_id:
                user_data["id"] = str(user_id)
            if tenant_id:
                user_data["tenant_id"] = str(tenant_id)
            sentry_sdk.set_user(user_data)
        except Exception:
            pass


def flush_sentry(timeout: float = 2.0) -> None:
    """Flush pending Sentry events on application shutdown."""
    if _sentry_initialized:
        try:
            import sentry_sdk

            sentry_sdk.flush(timeout=timeout)
        except Exception as exc:
            logger.error("Error flushing Sentry SDK", error=str(exc))
