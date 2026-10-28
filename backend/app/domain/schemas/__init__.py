"""Domain schemas package."""

# Pydantic schemas for request/response validation
from app.domain.schemas.auth import (
    Identity,
    Login,
    Message,
    Refresh,
    Register,
    ResetConfirm,
    TokenPair,
)
from app.domain.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ProjectListParams,
    PaginatedProjectResponse,
)

__all__ = [
    "Identity",
    "Login",
    "Message",
    "Refresh",
    "Register",
    "ResetConfirm",
    "TokenPair",
    "ProjectCreate",
    "ProjectRead",
    "ProjectUpdate",
    "ProjectListParams",
    "PaginatedProjectResponse",
]