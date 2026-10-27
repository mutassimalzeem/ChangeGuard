"""Structured logging configuration with structlog."""

import logging
import sys
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings
from app.core.redaction import redact
from app.core.request_logging import request_context


settings = get_settings()


class JSONFormatter(logging.Formatter):
    """One redaction boundary for structlog and standard library records."""

    def format(self, record: logging.LogRecord) -> str:
        # Third-party free-form messages can contain request URLs, SQL values,
        # document text, or credentials. Keep metadata, never their message text.
        fields = dict(record.msg) if isinstance(record.msg, dict) else {
            "event": "stdlib_log", "logger": record.name,
        }
        # Include structured stdlib extras, but never raw traceback/stack messages.
        reserved = logging.makeLogRecord({}).__dict__
        fields.update({k: v for k, v in record.__dict__.items() if k not in reserved and not k.startswith("_")})
        fields.pop("exc_info", None)
        fields.pop("stack_info", None)
        context = request_context.get() or {}
        fields.update({k: context[k] for k in ("tenant_id", "user_id") if context.get(k) is not None})
        fields.update(
            timestamp=datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            level=record.levelname.lower(),
            service=settings.otel_service_name,
            environment=settings.environment,
            request_id=context.get("request_id"),
        )
        if record.exc_info:
            fields["failure_type"] = record.exc_info[0].__name__
        return json.dumps(redact(fields), ensure_ascii=True, allow_nan=False)


def configure_logging() -> None:
    """Always emit JSON, including third-party logs propagated to the root."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(handlers=[handler], level=settings.log_level.upper(), force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # Our middleware replaces access logs that can expose query strings.
    logging.getLogger("uvicorn.access").disabled = True
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def configure_tracing() -> None:
    """Configure OpenTelemetry tracing."""
    if not settings.otel_endpoint:
        return

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)


def instrument_app(app: Any) -> None:
    """Instrument FastAPI app with OpenTelemetry."""
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    CeleryInstrumentor().instrument()


def get_logger(name: str) -> structlog.BoundLogger:
    """Get structured logger instance."""
    return structlog.get_logger(name)


# Initialize on import
configure_logging()
configure_tracing()

# Export tracer for manual spans
tracer = trace.get_tracer(__name__)
