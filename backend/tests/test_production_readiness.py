"""Unit tests for Phase 7.4 Production Readiness components:

- Health checks (API, database, Redis, object storage, Celery worker)
- Worker health probe
- Request timeout middleware
- Sentry-compatible error tracking hook
- Worker concurrency & timeout configuration
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.request_timeout import RequestTimeoutMiddleware
from app.core.sentry import (
    capture_exception,
    capture_message,
    flush_sentry,
    init_sentry,
    is_sentry_active,
    set_user_context,
)
from app.core.worker_health import check_worker_health


def test_production_readiness_settings():
    """Verify new concurrency and timeout settings are loaded and validated."""
    settings = get_settings()
    assert hasattr(settings, "celery_worker_concurrency")
    assert settings.celery_worker_concurrency >= 1
    assert hasattr(settings, "request_timeout_seconds")
    assert settings.request_timeout_seconds >= 1

    # Custom settings validation
    custom = Settings(
        CELERY_WORKER_CONCURRENCY=8,
        REQUEST_TIMEOUT_SECONDS=45,
    )
    assert custom.celery_worker_concurrency == 8
    assert custom.request_timeout_seconds == 45


def test_sentry_fallback_without_dsn(caplog):
    """When SENTRY_DSN is None, Sentry falls back to structured logging without crashing."""
    with patch("app.core.sentry.settings.sentry_dsn", None):
        initialized = init_sentry()
        assert not initialized
        assert not is_sentry_active()

        # Capture exception should return event_id and not raise
        event_id = capture_exception(
            ValueError("Test production error"),
            tags={"tenant_id": "test-tenant", "component": "unit_test"},
            extra={"details": "rehearsal"},
        )
        assert event_id is not None
        assert len(event_id) == 36  # UUID length

        # Capture message should return event_id
        msg_id = capture_message(
            "System warning message",
            level="warning",
            tags={"env": "test"},
        )
        assert msg_id is not None

        # User context and flush shouldn't error
        set_user_context("usr-123", "ten-456")
        flush_sentry()


def test_sentry_active_delegation():
    """When sentry_sdk is present and DSN is set, calls are delegated to sentry_sdk."""
    mock_sentry = MagicMock()
    mock_sentry.capture_exception.return_value = "sentry-event-123"
    mock_sentry.capture_message.return_value = "sentry-msg-456"

    with (
        patch("app.core.sentry._sentry_initialized", True),
        patch.dict("sys.modules", {"sentry_sdk": mock_sentry}),
    ):
        event_id = capture_exception(
            RuntimeError("Simulated Sentry crash"),
            tags={"tier": "staging"},
            extra={"meta": "info"},
        )
        assert event_id == "sentry-event-123"
        assert mock_sentry.capture_exception.called

        msg_id = capture_message("Test Sentry message", level="info")
        assert msg_id == "sentry-msg-456"
        assert mock_sentry.capture_message.called


def test_worker_health_check_broker_and_ping():
    """Verify worker health check detects broker connectivity."""
    mock_celery = MagicMock()
    mock_conn = MagicMock()
    mock_celery.connection_for_read.return_value.__enter__.return_value = mock_conn
    mock_inspector = MagicMock()
    mock_inspector.ping.return_value = {"celery@worker-1": {"ok": "pong"}}
    mock_celery.control.inspect.return_value = mock_inspector

    with patch("app.core.worker_health.celery_app", mock_celery):
        healthy = check_worker_health(timeout=1.0)
        assert healthy is True

    # When broker throws error, health check returns False
    mock_celery_fail = MagicMock()
    mock_celery_fail.connection_for_read.side_effect = ConnectionRefusedError("Broker offline")
    with patch("app.core.worker_health.celery_app", mock_celery_fail):
        healthy_fail = check_worker_health(timeout=1.0)
        assert healthy_fail is False


@pytest.mark.asyncio
async def test_request_timeout_middleware_enforcement():
    """Verify RequestTimeoutMiddleware returns 504 on timeout and passes fast requests."""
    test_app = FastAPI()
    test_app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=0.1)

    @test_app.get("/fast")
    async def fast_endpoint():
        return {"status": "fast"}

    @test_app.get("/slow")
    async def slow_endpoint():
        await asyncio.sleep(0.3)
        return {"status": "slow"}

    @test_app.get("/api/v1/health")
    async def health_endpoint():
        # Excluded path should not be subjected to timeout abort
        await asyncio.sleep(0.15)
        return {"status": "healthy"}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Fast request passes
        resp_fast = await client.get("/fast")
        assert resp_fast.status_code == 200
        assert resp_fast.json() == {"status": "fast"}

        # 2. Slow request gets 504
        resp_slow = await client.get("/slow")
        assert resp_slow.status_code == 504
        data = resp_slow.json()
        assert data["error"]["code"] == "REQUEST_TIMEOUT"
        assert "timeout_seconds" in data["error"]["details"]

        # 3. Excluded health path passes
        resp_health = await client.get("/api/v1/health")
        assert resp_health.status_code == 200
        assert resp_health.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_readiness_check_aggregates_dependencies():
    """Verify readiness check evaluates all components and formats output."""
    from app.api.v1.routes.health import _run_readiness_check

    mock_session = AsyncMock()
    mock_session.execute.return_value = MagicMock()

    mock_redis = AsyncMock()
    mock_redis.ping.return_value = True

    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {}

    mock_celery = MagicMock()
    mock_conn = MagicMock()
    mock_celery.connection_for_read.return_value.__enter__.return_value = mock_conn

    response = MagicMock()

    with (
        patch("app.api.v1.routes.health.Redis.from_url", return_value=mock_redis),
        patch("app.api.v1.routes.health.boto3.client", return_value=mock_s3),
        patch("app.api.v1.routes.health.celery_app", mock_celery),
    ):
        result = await _run_readiness_check(mock_session, response, strict=True)
        assert result["status"] == "ready"
        assert result["checks"]["database"] == "ok"
        assert result["checks"]["redis"] == "ok"
        assert result["checks"]["object_storage"] == "ok"
        assert result["checks"]["worker"] == "ok"
        assert "details" in result
        assert response.status_code != 503
