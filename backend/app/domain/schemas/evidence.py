"""Evidence contracts; each link identifies exactly one source."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SubjectType = Literal["claim", "risk", "project_event", "change_order", "ai_answer"]
SourceType = Literal[
    "document", "document_chunk", "site_photo", "project_event", "boq_item", "contract_clause"
]


class EvidenceCreate(BaseModel):
    source_type: SourceType
    source_id: UUID
    relevance: Decimal | None = Field(default=None, ge=0, le=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    source_page: int | None = Field(default=None, gt=0)
    source_text_snippet: str | None = Field(default=None, max_length=4000)


class EvidenceRead(EvidenceCreate):
    model_config = ConfigDict(from_attributes=True)
    evidence_link_id: UUID
    tenant_id: UUID
    project_id: UUID
    subject_type: SubjectType
    subject_id: UUID
    created_by: UUID | None
    created_at: datetime


class EvidenceResult(BaseModel):
    status: Literal["supported", "insufficient_evidence"]
    evidence: list[EvidenceRead]
