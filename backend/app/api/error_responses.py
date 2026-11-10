"""One JSON error contract for framework, authentication and domain failures."""

from http import HTTPStatus
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody


HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "AUTHENTICATION_ERROR",
    403: "AUTHORIZATION_ERROR",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    503: "SERVICE_UNAVAILABLE",
}


def error_response(status_code, message, *, code=None, details=None, headers=None):
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(
            error=ErrorBody(
                code=code or HTTP_ERROR_CODES.get(status_code, "HTTP_ERROR"),
                message=message,
                details=details if details is not None else {},
            )
        ).model_dump(mode="json"),
        headers=headers,
    )


async def http_exception_handler(request, exc):
    # Preserve security/rate-limit headers as well as the original status.
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return error_response(exc.status_code, message, headers=exc.headers)


async def request_validation_handler(request, exc):
    # Never expose Pydantic input, body, ctx, or validator exception text. Custom
    # validators can interpolate secrets into their messages just as input can.
    errors = [
        {
            "loc": list(error["loc"]),
            "type": error["type"],
            "msg": "Field required" if error["type"] == "missing" else "Invalid value",
        }
        for error in exc.errors()
    ]
    return error_response(422, "Request validation failed", details={"errors": errors})
