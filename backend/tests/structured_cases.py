"""Synthetic, fully quoted extraction cases for each document schema."""

from typing import get_origin

from app.document_processing.extraction.types import ExtractionResult, TextBlock
from app.document_processing.structured.schemas import SCHEMAS, BOQItem


def missing():
    return {
        "value": None,
        "confidence": 0.0,
        "source_page": None,
        "source_text_snippet": None,
        "missing": True,
    }


def blank(schema):
    return {
        name: [] if get_origin(field.annotation) is list else missing()
        for name, field in schema.model_fields.items()
    }


def fact(value, snippet, page=1):
    return {
        "value": value,
        "confidence": 0.96,
        "source_page": page,
        "source_text_snippet": snippet,
        "missing": False,
    }


def item():
    result = blank(BOQItem)
    result.update(
        {
            "code": fact("A-01", "BOQ code: A-01"),
            "description": fact("Concrete", "Description: Concrete"),
            "quantity": fact({"amount": "10.25", "unit": "m3"}, "Quantity: 10.25 m³"),
            "unit_rate": fact({"amount": "20.50", "currency": "USD"}, "Unit rate: USD 20.50"),
        }
    )
    return result


def case(kind):
    result = blank(SCHEMAS[kind])
    if kind == "contract":
        result.update(
            {
                "reference": fact("CT-001", "Contract reference: CT-001"),
                "title": fact("Foundation Works", "Title: Foundation Works"),
                "employer": fact("Example Owner", "Employer: Example Owner"),
                "contractor": fact("Example Build", "Contractor: Example Build"),
                "effective_date": fact("2026-01-15", "Effective date: 15 January 2026"),
                "contract_value": fact(
                    {"amount": "1250.50", "currency": "BDT"}, "Contract value: BDT 1,250.50"
                ),
                "status": fact("signed", "Status: signed"),
            }
        )
    elif kind == "boq":
        result.update({"title": fact("Foundation BOQ", "Title: Foundation BOQ"), "items": [item()]})
    elif kind == "drawing":
        result.update(
            {
                "drawing_number": fact("DR-101", "Drawing number: DR-101"),
                "title": fact("Foundation Plan", "Title: Foundation Plan"),
                "revision": fact("C", "Revision: C"),
                "status": fact("issued_for_construction", "Status: IFC"),
            }
        )
    elif kind == "rfi":
        result.update(
            {
                "rfi_number": fact("RFI-10", "RFI number: RFI-10"),
                "subject": fact("Footing level", "Subject: Footing level"),
                "question": fact("Confirm level", "Question: Confirm level"),
                "due_date": fact("2026-02-01", "Due date: 2026-02-01"),
                "document_references": [
                    fact({"kind": "drawing", "reference": "DR-101"}, "Drawing reference: DR-101")
                ],
            }
        )
    elif kind == "change_order":
        result.update(
            {
                "co_number": fact("CO-05", "CO number: CO-05"),
                "title": fact("Extra concrete", "Title: Extra concrete"),
                "description": fact(
                    "Additional foundations", "Description: Additional foundations"
                ),
                "amount": fact({"amount": "-100.25", "currency": "USD"}, "Amount: USD -100.25"),
            }
        )
    elif kind == "daily_report":
        result.update(
            {
                "report_date": fact("2026-01-15", "Report date: 2026-01-15"),
                "activities": fact("Concrete placement", "Activities: Concrete placement"),
                "labour_quantity": fact({"amount": "8", "unit": "h"}, "Labour: 8 hours"),
            }
        )
    elif kind == "email":
        result.update(
            {
                "subject": fact("Footing clarification", "Subject: Footing clarification", None),
                "sender": fact("engineer@example.test", "From: engineer@example.test", None),
                "body": fact("Confirm footing level", "Confirm footing level", None),
            }
        )
    elif kind == "quotation":
        result.update(
            {
                "reference": fact("Q-101", "Quotation reference: Q-101"),
                "supplier": fact("Example Supplier", "Supplier: Example Supplier"),
                "issue_date": fact("2026-01-15", "Issue date: 2026-01-15"),
                "stated_total": fact(
                    {"amount": "210.125", "currency": "USD"}, "Total: USD 210.125"
                ),
                "items": [item()],
            }
        )
    else:
        result.update({"title": fact("Site notes", "Title: Site notes")})
    snippets = []

    def visit(value):
        if isinstance(value, dict):
            if value.get("source_text_snippet"):
                snippets.append(value["source_text_snippet"])
            else:
                for nested in value.values():
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(result)
    return result, ExtractionResult(
        blocks=[TextBlock(text="\n".join(snippets), page_number=None if kind == "email" else 1)]
    )
