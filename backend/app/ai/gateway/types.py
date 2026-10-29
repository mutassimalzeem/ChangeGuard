"""Provider-independent responses and safe gateway failures."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.gateway.config import TaskPolicy


class GatewayError(RuntimeError):
    """Safe message; provider errors and document data are never interpolated."""


class GatewayUnavailableError(GatewayError):
    pass


class GatewayRefusedError(GatewayError):
    pass


class GatewayValidationError(GatewayError):
    def __init__(self, attempts):
        super().__init__("Model output failed validation after bounded repair")
        self.attempts = attempts


class ProviderCallError(GatewayError):
    def __init__(self, *, retryable=False):
        super().__init__("Model provider request failed")
        self.retryable = retryable


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    content: str = ""
    usage: Usage = field(default_factory=Usage)
    finish_reason: str = "stop"
    refused: bool = False
    vectors: list[list[float]] | None = None


@dataclass(frozen=True)
class GatewayResult:
    value: Any
    model: str
    trace_id: str
    usage: Usage
    cost_estimate: float | None
    attempts: list[dict]


class Provider(Protocol):
    def generate(
        self, *, policy: TaskPolicy, messages: list[dict], schema: dict | None
    ) -> ProviderResponse: ...
    def embed(self, *, policy: TaskPolicy, texts: list[str]) -> ProviderResponse: ...
