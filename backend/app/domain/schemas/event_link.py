"""Human-entered explicit relationship; no model-supplied matching scores."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["rfi", "change_order"]
    entity_id: UUID
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("A reason is mandatory")
        return value.strip()


class EventLinkRead(EventLinkCreate):
    id: UUID
    event_id: UUID
    actor_id: UUID
    linked_at: datetime


class EventLinkResult(BaseModel):
    link: EventLinkRead
    resolved_risk_ids: list[UUID]


class RiskResolution(BaseModel):
    entity_type: Literal["rfi", "change_order"]
    entity_id: UUID
    event_link_id: UUID
    actor_id: UUID
    resolved_at: datetime
    reason: str
