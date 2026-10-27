"""Main FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.core.logging import instrument_app, get_logger
from app.core.request_logging import RequestLoggingMiddleware
from app.api.exceptions import ChangeGuardException
from app.api.v1.router import api_router


settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting ChangeGuard API", version=settings.app_version)
    await init_db()
    yield
    logger.info("Shutting down ChangeGuard API")
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ChangeGuard - Construction Change Order Management System",
    docs_url=settings.docs_url if settings.debug else None,
    redoc_url=settings.redoc_url if settings.debug else None,
    openapi_url=f"{settings.api_prefix}/openapi.json" if settings.debug else None,
    lifespan=lifespan,
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
app.add_middleware(RequestLoggingMiddleware)


# Exception handlers
@app.exception_handler(ChangeGuardException)
async def changeguard_exception_handler(request, exc: ChangeGuardException):
    """Handle ChangeGuard custom exceptions."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


# Include API router
app.include_router(api_router, prefix=settings.api_prefix)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
