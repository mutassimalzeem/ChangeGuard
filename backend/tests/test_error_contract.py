"""Every API failure uses one envelope without reflecting rejected input."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, field_validator

from app.api.exceptions import ConflictError
from app.main import app


def test_openapi_validation_response_matches_runtime_envelope():
    schema = app.openapi()
    validation = schema["paths"]["/api/v1/projects"]["post"]["responses"]["422"]
    assert validation["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope",
    }
    assert set(schema["components"]["schemas"]["ErrorBody"]["properties"]) == {
        "code",
        "message",
        "details",
    }


@pytest.mark.parametrize(
    "method,path,status,code",
    [
        ("GET", "/api/v1/projects", 401, "AUTHENTICATION_ERROR"),
        ("GET", "/no-such-route", 404, "NOT_FOUND"),
        ("POST", "/health/live", 405, "METHOD_NOT_ALLOWED"),
    ],
)
async def test_http_errors_share_domain_envelope(client, method, path, status, code):
    response = await client.request(method, path)
    assert response.status_code == status
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message", "details"}
    assert response.json()["error"]["code"] == code
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_validation_envelope_excludes_input_context_and_body(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "test",
            "email": "invalid",
            "password": "private-password",
            "refresh_token": "private-token",
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid authentication request",
            "details": {},
        }
    }
    assert "private-password" not in response.text
    assert "private-token" not in response.text


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("domain", 409, "CONFLICT"),
        ("http", 429, "RATE_LIMIT_EXCEEDED"),
        ("validation", 422, "VALIDATION_ERROR"),
        ("unhandled", 500, "INTERNAL_SERVER_ERROR"),
    ],
)
async def test_error_handlers_preserve_status_headers_and_safe_details(kind, status, code):
    test_app = FastAPI(exception_handlers=app.exception_handlers)

    @test_app.get("/error")
    async def fail(count: int = 1):
        if kind == "domain":
            raise ConflictError("Conflict", {"reason": "review_required"})
        if kind == "http":
            raise HTTPException(429, "Too many requests", headers={"Retry-After": "30"})
        raise RuntimeError("private-exception-body")

    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get(
            "/error", params={"count": "private-input"} if kind == "validation" else {}
        )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "private-input" not in response.text
    assert "private-exception-body" not in response.text
    if kind == "validation":
        assert response.json()["error"]["details"]["errors"][0]["loc"] == ["query", "count"]
    if kind == "http":
        assert response.headers["Retry-After"] == "30"


async def test_custom_validator_messages_and_context_cannot_reflect_secrets():
    class Payload(BaseModel):
        password: str

        @field_validator("password")
        @classmethod
        def reject(cls, value):
            raise ValueError(f"Rejected password: {value}")

    test_app = FastAPI(exception_handlers=app.exception_handlers)

    @test_app.post("/validate")
    async def validate(payload: Payload):
        return {}

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/validate", json={"password": "do-not-reflect"})
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {
                "errors": [
                    {"loc": ["body", "password"], "type": "value_error", "msg": "Invalid value"}
                ]
            },
        }
    }
    assert "do-not-reflect" not in response.text
