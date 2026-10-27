"""Observability tests use an isolated ASGI app and need no database."""

import asyncio
import io
import json
import logging

import httpx
import pytest
from fastapi import FastAPI, Request

from app.core.logging import JSONFormatter, get_logger
from app.core.redaction import REDACTED, redact
from app.core.request_logging import RequestLoggingMiddleware, request_context


@pytest.fixture
def logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    previous = root.handlers[:]
    root.handlers = [handler]
    yield stream
    root.handlers = previous


def records(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.parametrize("key", [
    "password", "Password", "access_token", "refreshToken", "API-Key",
    "Authorization", "cookie", "JWT_SECRET", "raw_document_text", "document_content",
    "extracted_text", "body", "payload", "prompt", "client_secret",
])
def test_nested_redaction_does_not_mutate_input(key):
    source = {"items": [{key: "private-value", "count": 3}]}
    assert redact(source) == {"items": [{key: REDACTED, "count": 3}]}
    assert source["items"][0][key] == "private-value"


def test_structlog_and_stdlib_are_json_and_redacted(logs):
    get_logger(__name__).info(
        "safe_event", password="password-value", headers={"Authorization": "Bearer token-value"},
        document_text="private document", nested=[{"api_key": "key-value"}],
    )
    logging.getLogger(__name__).error(
        "password=hunter2 Bearer abc.def postgresql://user:password@host/db",
        extra={"token": "token-value"},
        exc_info=(ValueError, ValueError("private document"), None),
    )
    output = logs.getvalue()
    for secret in ("password-value", "token-value", "private document", "key-value", "hunter2", "abc.def", "user:password"):
        assert secret not in output
    for record in records(logs):
        assert {"timestamp", "level", "service", "environment", "request_id"} <= record.keys()
        assert record["request_id"] is None


def test_free_form_library_logs_and_objects_cannot_leak_documents(logs):
    logging.getLogger("third_party").warning("arbitrary confidential document words")
    get_logger(__name__).info("document_processed", document_text="confidential", result=ValueError("secret"))
    output = logs.getvalue()
    assert "confidential" not in output
    assert "arbitrary" not in output
    assert records(logs)[-1]["result"] == REDACTED


def test_redacts_credentials_embedded_in_structured_strings(logs):
    get_logger(__name__).info(
        "operation_failed", detail="password=hunter2 Bearer abc.def postgresql://user:pass@host/db",
    )
    output = logs.getvalue()
    assert "hunter2" not in output
    assert "abc.def" not in output
    assert "user:pass" not in output


@pytest.mark.asyncio
async def test_request_context_timing_and_isolation(logs):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/tenants/{tenant}")
    async def endpoint(tenant: str, request: Request):
        request.state.tenant_id = tenant
        request.state.user_id = "user-" + tenant
        await asyncio.sleep(0)
        get_logger(__name__).info("endpoint_event")
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        responses = await asyncio.gather(*[
            client.get(f"/tenants/{tenant}?token=query-secret", headers={"Authorization": "Bearer header-secret", "X-Request-ID": "untrusted"})
            for tenant in ("a", "b")
        ])
        await client.get("/missing/private-path")
    assert request_context.get() is None
    ids = [r.headers["x-request-id"] for r in responses]
    assert len(set(ids)) == 2
    assert "untrusted" not in ids
    access = [r for r in records(logs) if r["event"] == "http_request"]
    assert len(access) == 3
    for index, tenant in enumerate(("a", "b")):
        tenant_records = [r for r in records(logs) if r.get("tenant_id") == tenant]
        assert len(tenant_records) == 2
        assert all(r["request_id"] == ids[index] and r["user_id"] == "user-" + tenant for r in tenant_records)
    assert all(r["duration_ms"] >= 0 and r["method"] == "GET" for r in access)
    assert {r["path"] for r in access} == {"/tenants/{tenant}", "<unmatched>"}
    assert access[-1]["status_code"] == 404
    assert "tenant_id" not in access[-1]
    assert "query-secret" not in logs.getvalue()
    assert "header-secret" not in logs.getvalue()
    assert "private-path" not in logs.getvalue()


@pytest.mark.asyncio
async def test_failure_is_logged_and_context_reset(logs):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/fail")
    async def fail():
        raise ValueError("password=never-log-this")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with pytest.raises(ValueError):
            await client.get("/fail")
    access = [r for r in records(logs) if r["event"] == "http_request"]
    assert access[0]["status_code"] == 500
    assert request_context.get() is None
    assert "never-log-this" not in logs.getvalue()
