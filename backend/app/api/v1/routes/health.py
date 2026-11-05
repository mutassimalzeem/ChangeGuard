"""Comprehensive health check endpoints for ChangeGuard.

Verifies API liveness, readiness, PostgreSQL, Redis, Object Storage, and Celery Worker.
"""

import contextlib
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Depends, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import get_session
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
settings = get_settings()
logger = get_logger(__name__)


async def _run_health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("", summary="Basic liveness check")
@router.get("/health", summary="Basic liveness check (legacy alias)", include_in_schema=False)
async def health_check() -> dict[str, str]:
    """Basic health check endpoint for container liveness."""
    return await _run_health_check()


async def _run_liveness_check() -> dict[str, str]:
    return {"status": "alive", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/live", summary="Kubernetes / container liveness probe")
@router.get("/health/live", summary="Liveness probe alias", include_in_schema=False)
async def liveness_check() -> dict[str, str]:
    """Fast liveness check verifying the HTTP event loop is alive."""
    return await _run_liveness_check()


async def _run_health_check_db(session: AsyncSession) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        result = await session.execute(text("SELECT 1"))
        _ = result.scalar()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "healthy",
            "database": "connected",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error("Database health check failed", error=str(exc))
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(exc),
            "latency_ms": latency_ms,
        }


@router.get("/db", summary="PostgreSQL database health check")
@router.get("/health/db", summary="PostgreSQL health check alias", include_in_schema=False)
async def health_check_db(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Check connectivity to PostgreSQL and pgvector extension."""
    return await _run_health_check_db(session)


async def _run_health_check_redis() -> dict[str, Any]:
    start = time.perf_counter()
    client = None
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        ping_ok = await client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "healthy" if ping_ok else "unhealthy",
            "redis": "connected" if ping_ok else "unresponsive",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error("Redis health check failed", error=str(exc))
        return {
            "status": "unhealthy",
            "redis": "disconnected",
            "error": str(exc),
            "latency_ms": latency_ms,
        }
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()


@router.get("/redis", summary="Redis health check")
@router.get("/health/redis", summary="Redis health check alias", include_in_schema=False)
async def health_check_redis() -> dict[str, Any]:
    """Check connectivity and latency to Redis."""
    return await _run_health_check_redis()


async def _run_health_check_storage() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        protocol = "https" if settings.object_storage_secure else "http"
        endpoint = f"{protocol}://{settings.object_storage_endpoint}"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
            region_name=settings.object_storage_region,
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=2,
                read_timeout=2,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )
        s3.head_bucket(Bucket=settings.object_storage_bucket)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "healthy",
            "storage": "connected",
            "bucket": settings.object_storage_bucket,
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error("Object storage health check failed", error=str(exc))
        return {
            "status": "unhealthy",
            "storage": "disconnected",
            "bucket": settings.object_storage_bucket,
            "error": str(exc),
            "latency_ms": latency_ms,
        }


@router.get("/storage", summary="Object storage health check")
@router.get("/health/storage", summary="Object storage health check alias", include_in_schema=False)
async def health_check_storage() -> dict[str, Any]:
    """Check connectivity to S3 / MinIO object storage."""
    return await _run_health_check_storage()


async def _run_health_check_worker() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        with celery_app.connection_for_read() as conn:
            conn.connect()
            conn.release()

        inspector = celery_app.control.inspect(timeout=1.5)
        ping_res = inspector.ping() if inspector else None
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if ping_res:
            return {
                "status": "healthy",
                "worker": "active",
                "active_workers": list(ping_res.keys()),
                "latency_ms": latency_ms,
            }
        return {
            "status": "healthy",
            "worker": "broker_connected",
            "note": "Broker accessible, no ping reply from active workers",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error("Celery worker health check failed", error=str(exc))
        return {
            "status": "unhealthy",
            "worker": "disconnected",
            "error": str(exc),
            "latency_ms": latency_ms,
        }


@router.get("/worker", summary="Celery worker health check")
@router.get("/health/worker", summary="Celery worker health check alias", include_in_schema=False)
async def health_check_worker() -> dict[str, Any]:
    """Check Celery worker availability and broker connection."""
    return await _run_health_check_worker()


async def _run_readiness_check(
    session: AsyncSession,
    response: Response,
    strict: bool = False,
) -> dict[str, Any]:
    checks: dict[str, str] = {}
    details: dict[str, Any] = {}

    # 1. Database check
    try:
        t0 = time.perf_counter()
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
        details["database_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # 2. Redis check
    client = None
    try:
        t0 = time.perf_counter()
        client = Redis.from_url(
            settings.redis_url,
            socket_timeout=1.5,
            socket_connect_timeout=1.5,
        )
        if await client.ping():
            checks["redis"] = "ok"
            details["redis_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        else:
            checks["redis"] = "error: ping returned false"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

    # 3. Object Storage check
    try:
        t0 = time.perf_counter()
        protocol = "https" if settings.object_storage_secure else "http"
        endpoint = f"{protocol}://{settings.object_storage_endpoint}"
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
            region_name=settings.object_storage_region,
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=1,
                read_timeout=1,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )
        s3.head_bucket(Bucket=settings.object_storage_bucket)
        checks["object_storage"] = "ok"
        details["storage_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as exc:
        checks["object_storage"] = f"error: {exc}"

    # 4. Celery Worker / Broker check
    try:
        t0 = time.perf_counter()
        with celery_app.connection_for_read() as conn:
            conn.connect()
            conn.release()
        checks["worker"] = "ok"
        details["worker_broker_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as exc:
        checks["worker"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok and strict:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ok else "not_ready",
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
        "details": details,
    }


@router.get("/ready", summary="Full readiness check")
@router.get("/health/ready", summary="Readiness check alias", include_in_schema=False)
async def readiness_check(
    response: Response,
    strict: bool = Query(default=False, description="Return HTTP 503 if any dependency fails"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Readiness check verifying all critical dependencies:

    PostgreSQL, Redis, Object Storage, and Celery Broker.
    """
    return await _run_readiness_check(session, response, strict=strict)
