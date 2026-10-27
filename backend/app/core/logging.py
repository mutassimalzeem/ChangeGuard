"""Structured logging configuration with structlog."""

import logging
import sys
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


settings = get_settings()


def configure_logging() -> None:
    """Configure structured logging with structlog."""

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if settings.log_format == "json"
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
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