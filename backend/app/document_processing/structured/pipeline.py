"""Deterministic projections for existing linking and risk-check stages."""

from app.document_processing.structured.schemas import schema_for


def pipeline_summary(result):
    facts = schema_for(result["document_type"]).model_validate(result["fields"])
    money = None
    for name in ("amount", "contract_value", "stated_total"):
        field = getattr(facts, name, None)
        if field is not None and not field.missing:
            money = field.value
            break
    due = getattr(facts, "due_date", None)
    return {
        **result,
        "amount": str(money.amount) if money else None,
        "currency": money.currency if money else None,
        "due_date": due.value if due is not None and not due.missing else None,
        "entities": [
            {"kind": ref.value.kind, "reference": ref.value.reference}
            for ref in facts.document_references
            if not ref.missing and ref.value.kind in {"contract", "rfi", "change_order"}
        ],
    }
