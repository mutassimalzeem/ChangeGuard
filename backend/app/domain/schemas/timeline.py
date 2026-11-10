"""Timeline items contain permission-checked source details, never invented citations."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.domain.schemas.event_link import RiskResolution
from app.domain.schemas.evidence import EvidenceRead


class TimelineItem(BaseModel):
    id: UUID
    kind: Literal["event", "risk"]
    occurred_at: datetime
    title: str
    description: str | None
    event_type: str
    status: str
    confidence: Decimal | None
    severity: str | None = None
    evidence: list[EvidenceRead]
    evidence_status: Literal["supported", "insufficient_evidence"]
    resolution: RiskResolution | None = None


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    offset: int
    limit: int
    has_more: bool
