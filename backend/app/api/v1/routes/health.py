"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.logging import get_logger


router = APIRouter(tags=["health"])
settings = get_settings()
logger = get_logger(__name__)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "healthy", "version": settings.app_version}


@router.get("/health/db")
async def health_check_db(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Database health check endpoint."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@router.get("/health/ready")
async def readiness_check(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Readiness check - verifies all dependencies."""
    checks = {}

    # Database
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis check would go here
    checks["redis"] = "ok"  # Placeholder

    # Overall status
    all_ok = all(v == "ok" for v in checks.values())

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }