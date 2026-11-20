"""Validated workspace filters and explicit human commands."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Kind = Literal["risk", "extraction", "change_order", "approval"]
Category = Literal[
    "insufficient_evidence_risk",
    "low_confidence_extraction",
    "missing_required_field",
    "pilot_risk",
    "potential_duplicate",
    "conflicting_evidence",
    "high_severity_risk",
    "high_value_change",
    "approval_request",
]
Severity = Literal["low", "medium", "high", "critical"]


class QueueFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category | None = None
    severity: Severity | None = None
    status: Literal[
        "actionable",
        "all",
        "review_required",
        "insufficient_evidence",
        "accepted",
        "dismissed",
        "converted_to_change_order",
        "resolved",
        "evidence_requested",
    ] = "actionable"
    owner_id: UUID | None = None
    created_from: date | None = None
    created_to: date | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_confidence: float | None = Field(default=None, ge=0, le=1)
    sort: Literal["severity", "deadline", "confidence", "created_at"] = "created_at"
    direction: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def ordered_ranges(self):
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("Start date must precede end date")
        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise ValueError("Minimum confidence exceeds maximum")
        return self


class ReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: UUID
    action: Literal[
        "assign_owner",
        "add_note",
        "accept",
        "dismiss",
        "request_evidence",
        "convert_to_change_order",
        "override",
        "approve",
        "reject",
    ]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    owner_id: UUID | None = None
    severity: Severity | None = None

    @model_validator(mode="after")
    def action_arguments(self):
        if (self.action == "assign_owner") != (self.owner_id is not None):
            raise ValueError("Assignment requires an owner")
        if (self.action == "override") != (self.severity is not None):
            raise ValueError("Override requires a severity")
        return self
