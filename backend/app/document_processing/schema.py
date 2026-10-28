"""Validated provider outputs. Model text is data, never workflow authority."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal[
        "contract",
        "boq",
        "rfi",
        "daily_report",
        "change_order",
        "invoice",
        "correspondence",
        "other",
    ]
    confidence: float = Field(ge=0, le=1)


class EntityReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["contract", "rfi", "change_order"]
    reference: str = Field(min_length=1, max_length=100)


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(max_length=10000)
    confidence: float = Field(ge=0, le=1)
    amount: float | None = Field(default=None, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    due_date: date | None = None
    entities: list[EntityReference] = Field(default_factory=list, max_length=100)
