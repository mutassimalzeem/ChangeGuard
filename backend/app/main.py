"""Main FastAPI application entry point with graceful shutdown and error tracking."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.error_responses import (
    ErrorEnvelope,
    error_response,
    http_exception_handler,
    request_validation_handler,
)
from app.api.exceptions import ChangeGuardException
from app.api.v1.router import api_router
from app.api.v1.routes.health import (
    _run_health_check,
    _run_liveness_check,
    _run_readiness_check,
)
from app.core.config import get_settings
from app.core.database import close_db, get_session, init_db
from app.core.logging import get_logger, instrument_app
from app.core.request_logging import RequestLoggingMiddleware
from app.core.request_timeout import RequestTimeoutMiddleware
from app.core.sentry import capture_exception, flush_sentry, init_sentry

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler with graceful initialization and teardown."""
    logger.info(
        "Starting ChangeGuard API",
        version=settings.app_version,
        environment=settings.environment,
    )
    # Initialize Sentry error tracking
    init_sentry()

    # Initialize database connection pool
    await init_db()

    yield

    logger.info("Shutting down ChangeGuard API gracefully...")
    # Close database connection pool
    await close_db()
    # Flush pending error telemetry
    flush_sentry(timeout=3.0)
    logger.info("ChangeGuard API shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ChangeGuard - Construction Change Order Management System",
    docs_url=settings.docs_url if settings.debug else None,
    redoc_url=settings.redoc_url if settings.debug else None,
    openapi_url=f"{settings.api_prefix}/openapi.json" if settings.debug else None,
    lifespan=lifespan,
    responses={422: {"model": ErrorEnvelope, "description": "Request validation failed"}},
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument with OpenTelemetry
instrument_app(app)

# Request timeout and structured request logging middlewares
app.add_middleware(
    RequestTimeoutMiddleware,
    timeout_seconds=float(settings.request_timeout_seconds),
)
app.add_middleware(RequestLoggingMiddleware)


# Exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)


@app.exception_handler(ChangeGuardException)
async def changeguard_exception_handler(request: Request, exc: ChangeGuardException):
    """Handle ChangeGuard domain exceptions."""
    return error_response(exc.status_code, exc.message, code=exc.code, details=exc.details)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions, capture in Sentry, and return standard envelope."""
    event_id = capture_exception(
        exc,
        tags={"path": request.url.path, "method": request.method},
    )
    details = {"event_id": event_id} if settings.debug else {}
    return error_response(
        500,
        "An unexpected error occurred while processing the request",
        code="INTERNAL_SERVER_ERROR",
        details=details,
    )


# Root-level health endpoints for load balancers & ingress probes
@app.get("/health", tags=["health"], include_in_schema=False)
async def root_health_check() -> dict[str, str]:
    """Root liveness check."""
    return await _run_health_check()


@app.get("/health/live", tags=["health"], include_in_schema=False)
async def root_liveness_check() -> dict[str, str]:
    """Root liveness probe."""
    return await _run_liveness_check()


@app.get("/health/ready", tags=["health"], include_in_schema=False)
async def root_readiness_check(
    response: Response,
    session=Depends(get_session),
) -> dict:
    """Root readiness probe."""
    return await _run_readiness_check(session, response)


# Include API router
app.include_router(api_router, prefix=settings.api_prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
