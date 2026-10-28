"""Project Pydantic schemas for request/response validation."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectBase(BaseModel):
    """Base project fields shared by create/update schemas."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]
    client_name: Annotated[str, Field(min_length=1, max_length=255)]
    description: Annotated[str | None, Field(default=None, max_length=5000)]
    contract_value: Annotated[Decimal | None, Field(default=None, ge=0, decimal_places=2)]
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] = "USD"
    start_date: date | None = None
    expected_end_date: date | None = None
    status: Annotated[str, Field(min_length=1, max_length=32)] = "active"
    stakeholders: Annotated[list[str] | None, Field(default=None, max_length=20)] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        valid_statuses = {"active", "on_hold", "completed", "cancelled", "archived"}
        if value not in valid_statuses:
            raise ValueError(f"Status must be one of: {', '.join(sorted(valid_statuses))}")
        return value

    @field_validator("stakeholders")
    @classmethod
    def validate_stakeholders(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            for stakeholder in value:
                if not stakeholder.strip():
                    raise ValueError("Stakeholder names cannot be empty")
            seen = set()
            unique = []
            for s in value:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            return unique
        return value

    @field_validator("expected_end_date")
    @classmethod
    def validate_dates(cls, value: date | None, info) -> date | None:
        if value is not None and info.data.get("start_date") is not None:
            if value < info.data["start_date"]:
                raise ValueError("Expected end date must be on or after start date")
        return value


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""

    code: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9_-]+$")]

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return value.upper()


class ProjectUpdate(BaseModel):
    """Schema for updating a project (all fields optional)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    client_name: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None
    description: Annotated[str | None, Field(default=None, max_length=5000)] = None
    contract_value: Annotated[Decimal | None, Field(default=None, ge=0, decimal_places=2)] = None
    currency: Annotated[str | None, Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] = None
    start_date: date | None = None
    expected_end_date: date | None = None
    status: Annotated[str | None, Field(default=None, min_length=1, max_length=32)] = None
    stakeholders: Annotated[list[str] | None, Field(default=None, max_length=20)] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None:
            valid_statuses = {"active", "on_hold", "completed", "cancelled", "archived"}
            if value not in valid_statuses:
                raise ValueError(f"Status must be one of: {', '.join(sorted(valid_statuses))}")
        return value

    @field_validator("stakeholders")
    @classmethod
    def validate_stakeholders(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            for stakeholder in value:
                if not stakeholder.strip():
                    raise ValueError("Stakeholder names cannot be empty")
            seen = set()
            unique = []
            for s in value:
                if s not in seen:
                    seen.add(s)
                    unique.append(s)
            return unique
        return value

    @field_validator("expected_end_date")
    @classmethod
    def validate_dates(cls, value: date | None, info) -> date | None:
        if value is not None and info.data.get("start_date") is not None:
            if value < info.data["start_date"]:
                raise ValueError("Expected end date must be on or after start date")
        return value


class ProjectRead(ProjectBase):
    """Schema for reading a project."""

    id: UUID
    code: str
    tenant_id: UUID
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class ProjectListParams(BaseModel):
    """Query parameters for listing projects."""

    model_config = ConfigDict(extra="forbid")

    page: Annotated[int, Field(default=1, ge=1)] = 1
    page_size: Annotated[int, Field(default=20, ge=1, le=100)] = 20
    status: Annotated[str | None, Field(default=None, pattern=r"^(active|on_hold|completed|cancelled|archived)$")] = None
    search: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None


class PaginatedProjectResponse(BaseModel):
    """Paginated response for project listings."""

    items: list[ProjectRead]
    metadata: dict

    model_config = ConfigDict(from_attributes=True)