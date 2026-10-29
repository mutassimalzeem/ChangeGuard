"""Bounded hybrid retrieval contracts and explicit evidence outcomes."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID | None = None
    project_id: UUID | None = None
    document_type: str | None = Field(default=None, min_length=1, max_length=100)
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)
    access_level: Literal["project", "restricted"] | None = None
    revision: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def date_order(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not follow date_to")  # noqa: TRY003
        return self


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=20, ge=1, le=100)
    semantic: bool = True
    rerank: bool = False

    @field_validator("query")
    @classmethod
    def meaningful_query(cls, value):
        value = value.strip()
        if not any(character.isalnum() for character in value):
            raise ValueError("A search query must contain letters or numbers")  # noqa: TRY003
        return value


class SourceMetadata(BaseModel):
    tenant_id: UUID
    project_id: UUID
    filename: str
    document_type: str | None
    date: date | None
    status: str
    access_level: Literal["project", "restricted"]
    document_access_level: Literal["project", "restricted"]
    chunk_access_level: Literal["project", "restricted"]
    revision: str
    section: str
    author: str | None
    language: str
    embedding_model: str
    chunk_hash: str


class SearchHit(BaseModel):
    chunk_id: UUID
    text: str
    document_id: UUID
    page_number: int | None
    score: float
    fusion_score: float
    exact_identifier_match: bool = False
    keyword_score: float | None = None
    vector_similarity: float | None = None
    source_metadata: SourceMetadata


class SearchResponse(BaseModel):
    status: Literal["matched", "insufficient_evidence"]
    results: list[SearchHit]
    semantic_status: Literal["used", "disabled", "unavailable"]
    reranked: bool = False
