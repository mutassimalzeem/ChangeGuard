"""Realistic source fixtures and conservative deterministic/ambiguous boundaries."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.document_processing.extraction.types import ExtractionResult, TextBlock
from app.domain.services.potential_changes import classify_rules, detect, suggestions

FIXTURES = Path(__file__).parent / "fixtures" / "potential_changes"


def source(text):
    return ExtractionResult(blocks=[TextBlock(text=text, page_number=2)])


async def test_realistic_daily_report_detects_events_and_explicit_suggestions():
    fallback = Mock(side_effect=AssertionError("Clear rules must not invoke the model"))
    signals = await detect(source((FIXTURES / "daily_report.txt").read_text()), fallback=fallback)
    assert {s.event_type for s in signals} == {
        "site_instruction",
        "scope_change",
        "additional_work",
        "delay",
        "material_issue",
        "design_conflict",
    }
    extra = next(s for s in signals if s.event_type == "additional_work")
    assert extra.cost == Decimal("1250.50")
    assert extra.currency == "USD"
    assert extra.days == 2
    assert all(s.page == 2 and s.quote and s.confidence == Decimal("0.95") for s in signals)
    fallback.assert_not_called()


async def test_realistic_email_only_ambiguous_clause_calls_model():
    quote = "Please obtain clarification on the unexpected service obstruction near grid E-12."
    fallback = Mock(
        return_value={
            "event_type": "additional_work",
            "explanation": "Service obstruction requires review.",
            "source_quote": quote,
            "confidence": 0.9,
        }
    )
    signals = await detect(source((FIXTURES / "email.txt").read_text()), fallback=fallback)
    assert {s.event_type for s in signals} >= {
        "site_instruction",
        "scope_change",
        "delay",
        "additional_work",
    }
    assert not any(s.event_type == "material_issue" for s in signals)
    assert len([s for s in signals if s.method == "llm:v1"]) == 1
    assert all(s.cost is None and s.days is None for s in signals)
    assert any(call.args[0] == quote for call in fallback.call_args_list)


@pytest.mark.parametrize(
    "text",
    [
        "No additional work was required.",
        "The delivery was not rejected.",
        "The material shortage has been resolved.",
        "No design conflict found.",
        "Routine site inspection completed.",
        "The delay was avoided.",
        "If additional work is required, please notify the engineer.",
        "Could additional excavation be required?",
    ],
)
async def test_no_false_positive_from_negated_routine_or_hypothetical_text(text):
    assert await detect(source(text)) == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("RFI 107: Drawings do not match the drainage detail.", "design_conflict"),
        ("Drawing A-12: dimension mismatch at stair landing.", "design_conflict"),
        ("This work is not included in the original scope.", "scope_change"),
        ("The client instructed us to construct an extra plinth.", "site_instruction"),
    ],
)
async def test_rfi_and_drawing_change_signals(text, expected):
    assert expected in {s.event_type for s in await detect(source(text))}


@pytest.mark.parametrize(
    "response",
    [
        {
            "event_type": "delay",
            "explanation": "Maybe delayed",
            "source_quote": "invented evidence",
            "confidence": 0.9,
        },
        {
            "event_type": "delay",
            "explanation": "Maybe delayed",
            "source_quote": "",
            "confidence": 0.9,
        },
        {
            "event_type": None,
            "explanation": "Routine clarification",
            "source_quote": "clarification",
            "confidence": 0.9,
        },
        {
            "event_type": "delay",
            "explanation": "Uncertain",
            "source_quote": "clarification",
            "confidence": 0.4,
        },
        {
            "event_type": "delay",
            "explanation": "Uncertain",
            "source_quote": "clarification",
            "confidence": 0.9,
            "cost": 100,
        },
    ],
)
async def test_unsupported_ambiguous_output_cannot_create_event(response):
    assert not await detect(
        source("Please obtain clarification."), fallback=Mock(return_value=response)
    )


async def test_optional_model_failure_preserves_rule_findings():
    fallback = Mock(side_effect=RuntimeError("Provider unavailable"))
    result = await detect(
        source("Additional work required. Clarification needed."), fallback=fallback
    )
    assert len(result) == 1
    assert result[0].event_type == "additional_work"


def test_financial_values_are_not_calculated_or_guessed():
    assert suggestions("20 hours at USD 50 plus 5 units at USD 100")[0] is None
    assert suggestions("estimated cost USD 100 and additional cost USD 200")[0] is None
    assert suggestions("estimated cost USD -10")[0] is None
    assert suggestions("delay of 0 days")[2] is None
    assert suggestions("delay of 3 days and delay of 5 days")[2] is None
    assert suggestions("Action owner: Site Engineer")[3] == "Site Engineer"
    assert suggestions("Estimated cost USD 100.")[0] == Decimal("100")
    assert suggestions("Estimated cost USD 1.234.")[0] is None
    assert suggestions("Estimated cost USD 1,2.")[0] is None


def test_meaningful_negative_is_a_design_signal():
    assert classify_rules("The drawings do not match.")[0] == ["design_conflict"]


async def test_ambiguous_model_budget_is_bounded():
    fallback = Mock(
        return_value={
            "event_type": None,
            "explanation": "Routine clarification.",
            "source_quote": "",
            "confidence": 0.8,
        }
    )
    assert not await detect(source("Clarification needed. " * 20), fallback=fallback)
    assert fallback.call_count == 8
