"""Deterministic rule boundaries and false-positive prevention."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest

from app.document_processing.structured.schemas import schema_for
from app.domain.services.risk_engine import Source, document_rules, entity_rules, money
from app.domain.services.risks import RiskDecision

NOW = datetime(2026, 11, 3, tzinfo=UTC)


def change(**kwargs):
    return Row(
        **dict(
            dict(
                id=uuid4(),
                amount=Decimal("100.01"),
                currency="USD",
                status="submitted",
                time_impact_days=0,
                created_by_id=None,
                rfi_id="rfi",
                contract_id="contract",
                description="Extra work",
            ),
            **kwargs,
        )
    )


def approval(**kwargs):
    return Row(
        **dict(
            dict(
                id=uuid4(),
                status="pending",
                decided_at=None,
                due_at=NOW - timedelta(days=1),
                assigned_to_id=None,
            ),
            **kwargs,
        )
    )


def field(value=None):
    return {
        "value": value,
        "missing": value is None,
        "confidence": 0 if value is None else 0.9,
        "source_page": None if value is None else 1,
        "source_text_snippet": None if value is None else "Source quotation",
    }


def doc(kind="change_order", **values):
    schema = schema_for(kind)
    fields = {
        name: [] if name in {"items", "document_references"} else field()
        for name in schema.model_fields
    }
    fields.update(values)
    return Row(
        id=uuid4(),
        created_at=NOW,
        document_version=1,
        structured_extraction={"schema_version": 1, "document_type": kind, "fields": fields},
    )


def co_doc(**values):
    return doc(
        co_number=field("CO-1"),
        title=field("Works"),
        description=field("Extra work"),
        amount=field({"amount": "100", "currency": "USD"}),
        **values,
    )


def item(rate="130", **values):
    fields = dict(
        code=field("A1"),
        description=field("Concrete"),
        quantity=field({"amount": "3", "unit": "m3"}),
        unit_rate=field({"amount": rate, "currency": "USD"}),
        stated_total=field(),
        status=field(),
    )
    fields.update(values)
    return fields


def test_overdue_approval_exact_amount_and_no_invented_delay():
    result = entity_rules(change(), [approval()], [], [Source(uuid4())], NOW)[0]
    assert result.risk_type == "overdue_approval"
    assert result.financial_exposure == Decimal("100.01")
    assert result.schedule_impact_days is None


@pytest.mark.parametrize(
    "values",
    [
        {"status": "approved"},
        {"decided_at": NOW},
        {"due_at": NOW},
        {"due_at": None},
        {"due_at": NOW + timedelta(seconds=1)},
    ],
)
def test_overdue_approval_false_positives(values):
    assert entity_rules(change(), [approval(**values)], [], [], NOW) == []


@pytest.mark.parametrize("status", ["approved", "executed", "rejected", "cancelled"])
def test_terminal_change_is_not_overdue(status):
    assert not entity_rules(change(status=status), [approval()], [], [], NOW)


def test_schedule_days_come_from_record():
    result = entity_rules(change(time_impact_days=7), [], [], [Source(uuid4())], NOW)[0]
    assert result.risk_type == "schedule_impact_signal"
    assert result.schedule_impact_days == 7
    assert result.financial_exposure is None


@pytest.mark.parametrize(
    "values",
    [
        {"time_impact_days": 0},
        {"time_impact_days": -1},
        {"time_impact_days": None},
        {"time_impact_days": 7, "status": "draft"},
        {"time_impact_days": 7, "status": "rejected"},
    ],
)
def test_schedule_false_positives(values):
    assert not entity_rules(change(**values), [], [], [], NOW)


def test_duplicate_claim_and_missing_source_block():
    left, right = change(), change(description=" extra  WORK ")
    result = entity_rules(left, [], [(right, [Source(uuid4())])], [Source(uuid4())], NOW)[0]
    assert result.risk_type == "duplicate_change_order_claim"
    assert result.financial_exposure == Decimal("100.01")
    assert len(result.sources) == 2
    assert entity_rules(left, [], [(right, [])], [], NOW)[0].status == "insufficient_evidence"


@pytest.mark.parametrize(
    "values",
    [
        {"rfi_id": None},
        {"contract_id": "other"},
        {"amount": Decimal("100")},
        {"currency": "EUR"},
        {"description": "Other work"},
        {"status": "draft"},
    ],
)
def test_duplicate_false_positives(values):
    assert not entity_rules(change(), [], [(change(**values), [])], [], NOW)


def test_missing_required_evidence_and_complete_document():
    result = document_rules(doc(), [])[0]
    assert result.risk_type == "missing_required_evidence"
    assert "co_number" in result.description
    assert result.sources
    assert not document_rules(co_doc(), [])
    unsupported = co_doc()
    unsupported.structured_extraction = None
    assert document_rules(unsupported, [])[0].status == "insufficient_evidence"


def test_cost_outlier_exact_calculation():
    current, baseline = (
        doc("boq", title=field("BOQ"), items=[item()]),
        doc("boq", title=field("BOQ"), items=[item("100")]),
    )
    baseline.created_at -= timedelta(days=1)
    result = document_rules(current, [baseline])[0]
    assert result.risk_type == "cost_outlier"
    assert result.financial_exposure == Decimal("90.00")
    assert result.confidence == Decimal("0.9")


@pytest.mark.parametrize(
    "values",
    [
        {"unit_rate": field({"amount": "120", "currency": "USD"})},
        {"code": field("B1")},
        {"description": field("Steel")},
        {"quantity": field({"amount": "3", "unit": "kg"})},
        {"unit_rate": field({"amount": "130", "currency": "EUR"})},
        {"unit_rate": field()},
        {"quantity": field({"amount": "0", "unit": "m3"})},
    ],
)
def test_cost_false_positives(values):
    current = doc("boq", title=field("BOQ"), items=[item(**values)])
    baseline = doc("boq", title=field("BOQ"), items=[item("100")])
    baseline.created_at -= timedelta(days=1)
    assert not document_rules(current, [baseline])


def test_cost_does_not_use_future_or_lowest_cherry_picked_rate():
    current = doc("boq", title=field("BOQ"), items=[item()])
    low = deepcopy(current)
    low.id = uuid4()
    low.structured_extraction["fields"]["items"] = [item("100")]
    assert not document_rules(current, [low])
    low.created_at -= timedelta(days=1)
    high = deepcopy(low)
    high.id = uuid4()
    high.structured_extraction["fields"]["items"] = [item("125")]
    assert not document_rules(current, [low, high])


def test_conflict_exact_difference_with_two_sources():
    left, right = co_doc(), co_doc()
    right.structured_extraction["fields"]["amount"] = field({"amount": "140.01", "currency": "USD"})
    finding = document_rules(left, [right])[0]
    assert finding.risk_type == "conflicting_information"
    assert finding.financial_exposure == Decimal("40.01")
    assert len(finding.sources) == 2


@pytest.mark.parametrize(
    "name,value",
    [
        ("co_number", "CO-2"),
        ("status", "approved"),
        ("issue_date", "2026-11-01"),
        ("amount", {"amount": "140", "currency": "EUR"}),
        ("amount", None),
    ],
)
def test_conflict_false_positives(name, value):
    left, right = co_doc(), co_doc()
    right.structured_extraction["fields"]["amount"] = field({"amount": "140", "currency": "USD"})
    right.structured_extraction["fields"][name] = field(value)
    assert not document_rules(left, [right])


def test_revision_is_not_conflict():
    left, right = co_doc(), co_doc()
    right.document_version = 2
    right.structured_extraction["fields"]["amount"] = field({"amount": "140", "currency": "USD"})
    assert not document_rules(left, [right])


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "accept", "reason": " "},
        {"action": "dismiss"},
        {"action": "override", "reason": "Review"},
        {"action": "accept", "reason": "Review", "severity": "low"},
    ],
)
def test_review_requires_reason_and_explicit_override(payload):
    with pytest.raises(ValueError):
        RiskDecision(**payload)


def test_money_rounding_and_storage_boundaries():
    assert money(Decimal("10.005")) == Decimal("10.01")
    assert money(Decimal("10000000000000000")) is None
    assert money(Decimal("NaN")) is None


def test_own_entity_reference_is_linked_without_duplicate_reference():
    from app.document_processing.structured.pipeline import pipeline_summary

    result = co_doc().structured_extraction
    result["confidence"] = 0.9
    assert pipeline_summary(result)["entities"] == [{"kind": "change_order", "reference": "CO-1"}]
    result["fields"]["document_references"] = [field({"kind": "change_order", "reference": "CO-1"})]
    assert len(pipeline_summary(result)["entities"]) == 1
