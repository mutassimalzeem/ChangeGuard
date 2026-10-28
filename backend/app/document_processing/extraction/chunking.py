"""Structure first; size limits split only oversized logical units."""

import hashlib
import re
from datetime import date as Date

from pydantic import BaseModel, Field

from app.document_processing.extraction.types import ExtractionResult, TextBlock

CLAUSE = re.compile(r"^(?:(?:clause|article|section)\s+[\w.-]+|\d+(?:\.\d+)*[.)]?\s+\S)", re.I)
RFI = re.compile(
    r"^(?:RFI\b.*|(?:subject|question|response|answer|clarification|background|"
    r"requested information|reference|description)(?:\s*[:\-]|\s*$))",
    re.I,
)
REPORT = re.compile(
    r"^(?:daily report\b.*|(?:date|weather|labou?r|workforce|plant|equipment|activities|"
    r"work performed|progress|delays|safety|issues|materials|visitors)(?:\s*[:\-]|\s*$))",
    re.I,
)
BOQ_HEADERS = {"item", "item no", "description", "qty", "quantity", "unit", "rate", "amount"}


class LogicalChunk(BaseModel):
    text: str
    section: str = Field(max_length=512)
    kind: str
    page_number: int | None
    revision: str | None
    date: Date | None
    author: str | None
    language: str = Field(max_length=35)
    chunk_hash: str
    locations: list[dict]


def units(block: TextBlock):
    """Expose headings inside multiline paragraphs/OCR, retaining source offsets."""
    if block.kind in {"email_message", "table_row"}:
        yield block, 0
        return
    offset = 0
    for line in block.text.splitlines(keepends=True):
        if line.strip():
            leading = len(line) - len(line.lstrip())
            yield block.model_copy(update={"text": line.strip()}), offset + leading
        offset += len(line)


def split_ranges(text, limit):
    start = 0
    while start < len(text):
        if len(text) - start <= limit:
            yield start, len(text)
            return
        window = text[start : start + limit + 1]
        # Prefer paragraph, then sentence, then word boundaries; hard split is last resort.
        candidates = [m.end() for m in re.finditer(r"\n\s*\n", window)]
        if not candidates:
            candidates = [m.end() for m in re.finditer(r"[.!?](?:\s+|$)", window)]
        if not candidates:
            candidates = [m.start() for m in re.finditer(r"\s+", window)]
        boundary = max((p for p in candidates if 0 < p <= limit), default=limit)
        yield start, start + boundary
        start += boundary


def logical_chunks(result: ExtractionResult, document_type="other", *, max_chars=8000, limit=500):
    if max_chars < 1 or limit < 1:
        raise ValueError("Invalid logical chunk limits")
    groups, current = [], []
    section, kind = "document", "section"

    def flush():
        nonlocal current
        if current:
            groups.append((section, kind, current))
            current = []

    source = None
    for original in result.blocks:
        provenance = (
            original.location.get("archive_member"),
            original.author,
            original.date,
            original.revision,
            original.language,
        )
        if source is not None and source != provenance:
            flush()
            if source[0] != provenance[0]:
                section, kind = "document", "section"
        source = provenance
        for block, source_offset in units(original):
            if not block.text.strip():
                continue
            text = block.text.strip()
            boq = (
                document_type == "boq"
                or len(
                    {str(h).strip().lower() for h in block.location.get("headers", [])}
                    & BOQ_HEADERS
                )
                >= 2
            )
            special = block.kind == "email_message" or (
                block.kind == "table_row" and (boq or block.location.get("source") == "xlsx")
            )
            if special:
                flush()
                if block.kind == "email_message":
                    section, kind = block.section or "Email message", "email_thread_message"
                else:
                    kind = (
                        "table_header"
                        if block.location.get("is_header")
                        else ("boq_item" if boq else "table_row")
                    )
                    section = f"{block.section or 'Table'} / {kind} {text.split(chr(9))[0]}"
                current.append((block, source_offset))
                flush()
                continue
            heading_kind = None
            if document_type == "boq" and re.match(r"^(?:[A-Z]+[-.]?)?\d+(?:[.-]\d+)*\s+\S", text):
                heading_kind = "boq_item"
            elif (document_type == "rfi" or document_type == "other") and RFI.match(text):
                heading_kind = "rfi_section"
            elif (document_type == "daily_report" or document_type == "other") and REPORT.match(
                text
            ):
                heading_kind = "daily_report_section"
            elif (document_type == "contract" or document_type == "other") and CLAUSE.match(text):
                heading_kind = "contract_clause"
            elif block.kind == "heading":
                heading_kind = {
                    "contract": "contract_clause",
                    "rfi": "rfi_section",
                    "daily_report": "daily_report_section",
                }.get(document_type, "section")
            if heading_kind or (block.section and block.section != section):
                flush()
                section = text if heading_kind else block.section
                kind = heading_kind or "section"
            current.append((block, source_offset))
    flush()

    output = []
    for section, kind, entries in groups:
        text, spans = "", []
        for block, source_offset in entries:
            if text:
                text += "\n"
            start = len(text)
            text += block.text
            spans.append(
                {
                    "start": start,
                    "end": len(text),
                    "page_number": block.page_number,
                    "source_text_start": source_offset,
                    "location": block.location,
                }
            )
        for part, (start, end) in enumerate(split_ranges(text, max_chars), 1):
            leading = len(text[start:end]) - len(text[start:end].lstrip())
            trailing = len(text[start:end]) - len(text[start:end].rstrip())
            start, end = start + leading, end - trailing
            if start >= end:
                continue
            locations = []
            for span in spans:
                a, b = max(start, span["start"]), min(end, span["end"])
                if a < b:
                    locations.append(
                        {
                            **span,
                            "start": a - start,
                            "end": b - start,
                            "source_text_start": span["source_text_start"] + a - span["start"],
                        }
                    )
            # Metadata follows the source block at the start of this continuation.
            first = next(
                block
                for (block, _), span in zip(entries, spans, strict=True)
                if span["end"] > start
            )
            chunk_text = text[start:end]
            output.append(
                LogicalChunk(
                    text=chunk_text,
                    section=section[:512],
                    kind=kind,
                    page_number=locations[0]["page_number"] if locations else None,
                    revision=first.revision,
                    date=first.date,
                    author=first.author,
                    language=first.language or "und",
                    chunk_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                    locations=[{**loc, "part": part} for loc in locations],
                )
            )
            if len(output) > limit:
                raise ValueError("Document chunk limit exceeded")
    if not output:
        raise ValueError("No document text extracted")
    return output
