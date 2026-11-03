"""Closed workflow inputs: models never supply final monetary values."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.document_processing.structured.schemas import DecimalValue
from app.domain.schemas.evidence import EvidenceCreate


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def trim_strings(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Blank strings are not allowed")
        return value


class CostItem(Input):
    description: str = Field(min_length=1, max_length=1000)
    quantity: DecimalValue = Field(gt=Decimal("0"))
    unit_rate: DecimalValue


class ChangeOrderCreate(Input):
    reference: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._/-]*$")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    time_impact_days: int | None = Field(default=None, ge=0, le=36500)
    cost_items: list[CostItem] = Field(default_factory=list, max_length=100)
    source_event_id: UUID | None = None
    contract_id: UUID | None = None
    rfi_id: UUID | None = None
    evidence: list[EvidenceCreate] = Field(default_factory=list, max_length=100)


class ChangeOrderPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    time_impact_days: int | None = Field(default=None, ge=0, le=36500)
    cost_items: list[CostItem] | None = Field(default=None, max_length=100)
    status: Literal["disputed", "closed"] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def meaningful_patch(self):
        changed = self.model_fields_set - {"reason"}
        if not changed:
            raise ValueError("At least one change is required")
        if self.status is not None and (not self.reason or changed != {"status"}):
            raise ValueError(
                "Status transitions require a reason and cannot be combined with edits"
            )
        for name in ("title", "currency", "cost_items", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError("This field cannot be null")
        return self


class ActionInput(Input):
    reason: str | None = Field(default=None, min_length=1, max_length=2000)


class DraftInput(ActionInput):
    query: str | None = Field(default=None, min_length=1, max_length=1000)


class SubmitInput(ActionInput):
    cost_confirmed: Literal[True]

    @field_validator("cost_confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit human cost confirmation is required")
        return value


class DecisionInput(Input):
    reason: str = Field(min_length=1, max_length=2000)


class CitedParagraph(Input):
    text: str = Field(min_length=1, max_length=2000)
    citations: list[str] = Field(min_length=1, max_length=8)


class CitedDraft(Input):
    paragraphs: list[CitedParagraph] = Field(min_length=1, max_length=12)
