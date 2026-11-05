"""ASGI middleware for enforcing request timeouts on HTTP requests."""

import asyncio
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

EXCLUDED_PATHS = {
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/health",
    "/health/live",
    "/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/openapi.json",
}


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Enforces request processing time limits on incoming HTTP requests.

    Returns HTTP 504 Gateway Timeout if the downstream handler takes
    longer than timeout_seconds to complete.
    """

    def __init__(self, app: Any, timeout_seconds: float | None = None) -> None:
        super().__init__(app)
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(settings.request_timeout_seconds)
        )

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        path = request.url.path
        if path in EXCLUDED_PATHS:
            return await call_next(request)

        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await call_next(request)
        except TimeoutError:
            logger.warning(
                "Request timed out",
                method=request.method,
                path=path,
                timeout_seconds=self.timeout_seconds,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "REQUEST_TIMEOUT",
                        "message": (
                            f"Request processing exceeded timeout limit of "
                            f"{self.timeout_seconds:.1f} seconds"
                        ),
                        "details": {
                            "timeout_seconds": self.timeout_seconds,
                            "path": path,
                            "method": request.method,
                        },
                    }
                },
            )
