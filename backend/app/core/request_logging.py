"""Request context and access logging without inspecting headers or bodies."""

from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_context: ContextVar[dict | None] = ContextVar("request_context", default=None)


class RequestLoggingMiddleware:
    """Assign server-generated IDs; auth may set state.tenant_id/state.user_id."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from app.core.logging import get_logger

        state = scope.setdefault("state", {})
        state["request_id"] = str(uuid4())
        token = request_context.set(state)
        started = perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = state["request_id"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            try:
                route = scope.get("route")
                get_logger(__name__).info(
                    "http_request",
                    method=scope["method"],
                    path=getattr(route, "path", "<unmatched>"),
                    status_code=status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                )
            finally:
                request_context.reset(token)
