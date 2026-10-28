"""Common extraction contract, independent of file format and OCR provider."""

from datetime import date as Date
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    text: str
    kind: Literal["paragraph", "heading", "table_row", "email_message"] = "paragraph"
    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None
    location: dict[str, Any] = Field(default_factory=dict)
    author: str | None = None
    date: Date | None = None
    revision: str | None = None
    language: str = "und"


class ExtractionResult(BaseModel):
    version: int = 1
    blocks: list[TextBlock] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text.strip())


class ExtractionService(Protocol):
    def extract(self, content: bytes) -> ExtractionResult:
        """Extract text and the source locations available in this format."""
        ...


class ImageOCR(Protocol):
    def recognize(self, content: bytes, *, page_number: int = 1) -> list[TextBlock]: ...
