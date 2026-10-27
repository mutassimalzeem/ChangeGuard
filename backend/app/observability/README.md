# Backend logging

Use `get_logger(__name__)` from `app.core.logging` with a fixed event name
and structured metadata. Never interpolate user input, document text, credentials,
or exception messages into event names or field names. Never log request/response
bodies. The redactor masks sensitive fields recursively, including nested headers,
tokens, keys, text, content, payloads, and exception details. Unknown objects are
masked instead of calling their repr.

Logs always use JSON, even if the legacy `LOG_FORMAT` setting is `console`.
Each record includes UTC timestamp, level, service (`OTEL_SERVICE_NAME`),
environment, and request_id (null outside HTTP requests). Authentication code
should set `request.state.tenant_id` and `request.state.user_id` after validating
identity; do not copy these from unverified headers. Those fields then appear in
subsequent request logs. Request context is reset on completion or failure.

The middleware generates a new UUID, returns it in `X-Request-ID`, and logs method,
route template as path, status_code, and duration_ms. Unmatched routes use
`<unmatched>`. Query strings, path parameter values, headers, and bodies are not
recorded. Unhandled failures are logged as 500 and re-raised. Streaming duration
includes sending the response. Incoming request IDs are intentionally not trusted.

Standard-library/third-party records retain level, logger, context, and redacted
structured extras, but their free-form message, traceback, and stack text are
suppressed because they can contain arbitrary secrets or document text. Use
structlog for diagnostic events. SQL echo and parameter logging are disabled;
the middleware replaces Uvicorn access logging.
