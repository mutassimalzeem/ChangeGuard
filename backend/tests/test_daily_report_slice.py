"""Daily report delay boundaries, independent of providers and databases."""

from decimal import Decimal
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.services.potential_changes import ExtractedEvent
from app.domain.services.risk_engine import daily_report_delay_rules


def setup_delay():
    document = Row(id=uuid4(), document_type="daily_report")
    event = Row(id=uuid4(), document_id=document.id, event_type="delay", confidence=Decimal("0.95"))
    evidence = Row(
        subject_id=event.id,
        source_type="document",
        source_id=document.id,
        source_page=1,
        source_text_snippet="Work was delayed by late steel delivery.",
    )
    return document, event, evidence


def test_delay_is_evidence_backed_and_does_not_estimate_impacts():
    document, event, evidence = setup_delay()
    (finding,) = daily_report_delay_rules(document, [event], [evidence], [], [])
    assert finding.risk_type == "daily_report_delay_without_link"
    assert finding.status == "open"
    assert finding.sources[0].snippet == evidence.source_text_snippet
    assert finding.financial_exposure is None
    assert finding.schedule_impact_days is None


@pytest.mark.parametrize("kind", ["rfi_id", "change_order_id"])
def test_linked_record_suppresses_delay(kind):
    document, event, evidence = setup_delay()
    link = Row(document_id=document.id, rfi_id=None, change_order_id=None)
    setattr(link, kind, uuid4())
    assert daily_report_delay_rules(document, [event], [evidence], [link], []) == []


def test_change_order_from_event_suppresses_delay():
    document, event, evidence = setup_delay()
    assert (
        daily_report_delay_rules(document, [event], [evidence], [], [Row(source_event_id=event.id)])
        == []
    )


@pytest.mark.parametrize("missing", ["source_page", "source_text_snippet"])
def test_missing_provenance_is_insufficient_and_still_links_report(missing):
    document, event, evidence = setup_delay()
    setattr(evidence, missing, None)
    (finding,) = daily_report_delay_rules(document, [event], [evidence], [], [])
    assert finding.status == "insufficient_evidence"
    assert finding.sources[0].document_id == document.id


def test_other_documents_and_non_delay_events_do_not_trigger():
    document, event, evidence = setup_delay()
    document.document_type = "email"
    assert daily_report_delay_rules(document, [event], [evidence], [], []) == []
    document.document_type = "daily_report"
    event.event_type = "scope_change"
    assert daily_report_delay_rules(document, [event], [evidence], [], []) == []


def test_event_schema_rejects_coercion_and_extra_model_calculations():
    payload = dict(
        event_type="delay",
        quote="Work delayed.",
        page=1,
        confidence=Decimal("0.95"),
        method="rules:v1",
        explanation="Explicit delay.",
    )
    assert ExtractedEvent.model_validate(payload).page == 1
    with pytest.raises(ValidationError):
        ExtractedEvent.model_validate({**payload, "page": "1"})
    with pytest.raises(ValidationError):
        ExtractedEvent.model_validate({**payload, "financial_exposure": 100})
