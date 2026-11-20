"""Read one authorized queue snapshot and validate the selected extraction quotations."""

import json
from decimal import Decimal

from pydantic import ValidationError

from app.api.exceptions import NotFoundError
from app.core.config import get_settings
from app.document_processing.structured.schemas import schema_for
from app.document_processing.structured.validation import fields
from app.policy.review_page import REVIEW_PAGE

EXTRACTION_REASONS = ("low_confidence", "low_classification_confidence")
RISK_CATEGORIES = {
    "missing_required_evidence": "missing_required_field",
    "duplicate_change_order_claim": "potential_duplicate",
    "conflicting_information": "conflicting_evidence",
}


def extraction_evidence(task_id, document_id, filename, extraction):
    extraction = extraction or {}
    schema = (
        schema_for(extraction.get("document_type"))
        if extraction.get("schema_version") == 1
        else None
    )
    if schema is None:
        return []
    try:
        facts = schema.model_validate(extraction.get("fields"))
    except ValidationError:
        return []
    citation = min(
        (field for _, field in fields(facts) if not field.missing),
        key=lambda field: field.confidence,
        default=None,
    )
    if citation is None:
        return []
    return [
        {
            "id": task_id,
            "source_type": "document",
            "document_id": document_id,
            "document_name": filename,
            "source_page": citation.source_page,
            "source_text_snippet": citation.source_text_snippet,
        }
    ]


async def read_review_page(session, project_id, filters, *, kind=None, item_id=None, legacy=False):
    # Textual reads do not trigger ORM autoflush. See pending work on this transaction.
    if session.new or session.dirty or session.deleted:
        await session.flush()
    params = {
        "project_id": project_id,
        "kind": kind,
        "item_id": item_id,
        "category": filters.category,
        "severity": filters.severity,
        "status": filters.status,
        "owner_id": filters.owner_id,
        "date_from": filters.created_from,
        "date_to": filters.created_to,
        "min_conf": Decimal(str(filters.min_confidence))
        if filters.min_confidence is not None
        else None,
        "max_conf": Decimal(str(filters.max_confidence))
        if filters.max_confidence is not None
        else None,
        "sort": filters.sort,
        "sign": 1 if filters.direction == "asc" else -1,
        "legacy": legacy,
        "limit": None if legacy else filters.page_size,
        "offset": (filters.page - 1) * filters.page_size,
        "risk_categories": json.dumps(RISK_CATEGORIES),
        "extraction_reasons": list(EXTRACTION_REASONS),
        "thresholds": json.dumps(get_settings().review_high_value_thresholds, default=str),
    }
    rows = (await session.execute(REVIEW_PAGE, params)).mappings().all()
    if not rows:
        raise NotFoundError("Project", str(project_id))
    items = []
    for row in rows:
        if row["id"] is None:
            continue
        item = dict(row)
        extraction = item.pop("structured_extraction")
        item.pop("total")
        if item["kind"] == "extraction":
            item["evidence_details"] = extraction_evidence(
                item["id"], item["document_id"], item["title"], extraction
            )
        items.append(item)
    return {"total": rows[0]["total"], "items": items}
