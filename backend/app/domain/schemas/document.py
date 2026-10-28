"""Public registry metadata; storage aliases keep existing foreign keys intact."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProcessingStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    STORED = "stored"
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    CLASSIFIED = "classified"
    INDEXED = "indexed"
    LINKED = "linked"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    document_id: UUID = Field(validation_alias="id")
    tenant_id: UUID
    project_id: UUID
    original_file_key: str = Field(validation_alias="storage_key")
    file_name: str = Field(validation_alias="filename")
    file_hash: str | None = Field(validation_alias="checksum")
    file_type: str
    mime_type: str
    file_size: int = Field(validation_alias="size_bytes")
    uploaded_by: UUID | None = Field(validation_alias="uploaded_by_id")
    uploaded_at: datetime = Field(validation_alias="created_at")
    source: str
    processing_status: str
    status: ProcessingStatus
    document_type: str | None
    document_version: int
    access_level: str
    extraction_confidence: float | None
    error_message: str | None
