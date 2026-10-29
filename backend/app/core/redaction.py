"""Sanitize structured fields before rendering logs. Never pass document text as events."""

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE = (
    "password", "passwd", "secret", "token", "apikey", "accesskey",
    "authorization", "cookie", "text", "documentcontent",
    "body", "payload", "content", "prompt", "completion", "extractedtext", "rawoutput",
    "exception", "excinfo", "stack", "error", "credential",
)
_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|[\w-]*token|[\w-]*secret|api[_-]?key|authorization)"
    r"\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\b(?:bearer|basic)\s+[a-z0-9._~+/=-]+")
_URL_CREDENTIALS = re.compile(r"(://)[^\s/@]+:[^\s/@]+@")


def redact(value: Any) -> Any:
    """Return a sanitized copy; avoid arbitrary object reprs and exception messages."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            name = str(key)
            normalized = re.sub(r"[^a-z0-9]", "", name.lower())
            # Narrow typed exceptions expose operational counters and version IDs,
            # never arbitrary token values or prompt bodies.
            if (
                normalized in {"inputtokens", "outputtokens", "totaltokens"}
                and type(item) is int and item >= 0
            ):
                result[name] = item
                continue
            if (
                normalized == "promptversion" and isinstance(item, str) and len(item) <= 64
                and re.fullmatch(r"(?:[a-z][a-z0-9_.-]{0,48}-)?v[0-9]+(?:[.-][0-9]+)*", item)
            ):
                result[name] = item
                continue
            result[name] = (
                REDACTED if any(part in normalized for part in _SENSITIVE)
                else redact(item)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = _ASSIGNMENT.sub(lambda m: f"{m[1]}={REDACTED}", value)
        value = _BEARER.sub(REDACTED, value)
        return _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return REDACTED
