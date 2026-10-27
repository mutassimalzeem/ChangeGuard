"""Custom application exceptions."""

from typing import Any


class ChangeGuardException(Exception):
    """Base exception for ChangeGuard application."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(ChangeGuardException):
    """Validation error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "VALIDATION_ERROR", 400, details)


class AuthenticationError(ChangeGuardException):
    """Authentication error."""

    def __init__(self, message: str = "Authentication failed", details: dict[str, Any] | None = None):
        super().__init__(message, "AUTHENTICATION_ERROR", 401, details)


class AuthorizationError(ChangeGuardException):
    """Authorization error."""

    def __init__(self, message: str = "Insufficient permissions", details: dict[str, Any] | None = None):
        super().__init__(message, "AUTHORIZATION_ERROR", 403, details)


class NotFoundError(ChangeGuardException):
    """Resource not found error."""

    def __init__(self, resource: str, identifier: str | int, details: dict[str, Any] | None = None):
        message = f"{resource} not found: {identifier}"
        super().__init__(message, "NOT_FOUND", 404, {"resource": resource, "identifier": identifier, **(details or {})})


class ConflictError(ChangeGuardException):
    """Resource conflict error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, "CONFLICT", 409, details)


class ProcessingError(ChangeGuardException):
    """Document processing error."""

    def __init__(self, message: str, document_id: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, "PROCESSING_ERROR", 500, {"document_id": document_id, **(details or {})})


class AIError(ChangeGuardException):
    """AI service error."""

    def __init__(self, message: str, model: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, "AI_ERROR", 502, {"model": model, **(details or {})})


class RateLimitError(ChangeGuardException):
    """Rate limit exceeded error."""

    def __init__(self, message: str = "Rate limit exceeded", details: dict[str, Any] | None = None):
        super().__init__(message, "RATE_LIMIT_EXCEEDED", 429, details)


class TenantIsolationError(ChangeGuardException):
    """Tenant isolation violation."""

    def __init__(self, message: str = "Tenant isolation violation", details: dict[str, Any] | None = None):
        super().__init__(message, "TENANT_ISOLATION_ERROR", 403, details)


class WorkflowError(ChangeGuardException):
    """Workflow state machine error."""

    def __init__(self, message: str, state: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, "WORKFLOW_ERROR", 400, {"state": state, **(details or {})})


class InsufficientEvidenceError(ChangeGuardException):
    """Insufficient evidence for AI conclusion."""

    def __init__(self, message: str = "Insufficient evidence to reach conclusion", details: dict[str, Any] | None = None):
        super().__init__(message, "INSUFFICIENT_EVIDENCE", 422, details)