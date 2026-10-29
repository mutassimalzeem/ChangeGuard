"""Strict schemas, evidence checks, repair boundaries and durable pipeline results."""

import json
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.document_processing.providers import Services
from app.document_processing.structured.schemas import SCHEMAS, BOQItem, Contract
from app.document_processing.structured.service import (
    SchemaConstrainedExtractor,
    StructuredExtractionError,
    validate_result,
)
from app.document_processing.structured.validation import EvidenceError, validate_evidence
from app.domain.models import DocumentReviewTask, ProcessingDeadLetter
from tests.structured_cases import case, fact, item, missing
from tests.test_processing_pipeline import pipeline  # noqa: F401


@pytest.mark.parametrize("kind", SCHEMAS)
def test_valid_extraction_for_each_schema(kind):
    data, source = case(kind)
    generate = Mock(return_value=json.dumps(data))
    extracted = SchemaConstrainedExtractor(generate, model="mock-model").extract(source, kind)
    assert extracted["document_type"] == kind
    assert extracted["missing_required_fields"] == [] and extracted["confidence"] == 0.96
    assert extracted["model_or_rule_used"] == "llm:mock-model"
    assert validate_result(extracted, source, kind) == extracted
    generate.assert_called_once()


def test_decimals_are_exact_and_not_binary_floats():
    data, source = case("contract")
    facts = validate_evidence(Contract.model_validate(data), source)
    assert facts.contract_value.value.amount == Decimal("1250.50")
    assert isinstance(facts.contract_value.value.amount, Decimal)
    assert facts.model_dump(mode="json")["contract_value"]["value"]["amount"] == "1250.50"
    boq = BOQItem.model_validate(item())
    assert boq.quantity.value.amount == Decimal("10.25")


def test_native_decimal_bounds_and_date_token_boundaries():
    from app.document_processing.structured.schemas import Money
    from app.document_processing.structured.validation import has_date, has_money

    with pytest.raises(ValueError):
        Money(amount=Decimal("1E20"), currency="USD")
    assert not has_date("2026-01-15", "12026-01-1500")
    assert has_date("2026-01-15", "2026-01-15T10:00:00Z")
    assert not has_money(Money(amount=Decimal("1.250"), currency="EUR"), "EUR 1.250,50")
    assert has_money(Money(amount=Decimal("100"), currency="USD"), "Total USD 100.")


def test_every_object_has_strict_schema_required_keys():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for nested in node.values():
                check(nested)
        elif isinstance(node, list):
            for nested in node:
                check(nested)

    for model in [*SCHEMAS.values(), BOQItem]:
        check(model.model_json_schema())


@pytest.mark.parametrize(
    "bad", ["{broken", "```json\n{}\n```", '{"title":null,"title":null}', '{"confidence":NaN}']
)
def test_malformed_json_is_repaired_once(bad):
    data, source = case("contract")
    generate = Mock(side_effect=[bad, json.dumps(data)])
    extracted = SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    assert len(extracted["attempts"]) == 2
    previous = generate.call_args.kwargs["previous"]
    assert previous["raw_output"] == bad and previous["errors"]
    assert extracted["fields"]["reference"]["value"] == "CT-001"


def test_missing_required_facts_are_explicit_and_force_review_confidence():
    data, source = case("contract")
    data["contractor"] = missing()
    extracted = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock").extract(
        source, "contract"
    )
    assert extracted["missing_required_fields"] == ["contractor"]
    assert extracted["confidence"] == 0
    assert extracted["fields"]["contractor"] == missing()


def test_omitted_key_requires_repair_not_a_silent_default():
    data, source = case("contract")
    omitted = deepcopy(data)
    omitted.pop("contractor")
    repaired = {**data, "contractor": missing()}
    generate = Mock(side_effect=[json.dumps(omitted), json.dumps(repaired)])
    result = SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    assert result["missing_required_fields"] == ["contractor"]
    assert generate.call_count == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "invented_value",
        "invented_snippet",
        "wrong_page",
        "missing_flag",
        "reference_prefix",
        "float_amount",
        "fake_currency",
        "bad_date",
        "bad_status",
        "confidence",
        "page_type",
    ],
)
def test_invalid_or_hallucinated_fields_are_rejected(mutation):
    data, source = case("contract")
    if mutation == "extra":
        data["calculated_total"] = fact("9000", "Total 9000")
    elif mutation == "invented_value":
        data["employer"]["value"] = "Imaginary Client"
    elif mutation == "invented_snippet":
        data["employer"]["source_text_snippet"] = "Imaginary quotation"
    elif mutation == "wrong_page":
        data["employer"]["source_page"] = 999
    elif mutation == "missing_flag":
        data["employer"]["missing"] = True
    elif mutation == "reference_prefix":
        data["reference"]["value"] = "CT-00"
    elif mutation == "float_amount":
        data["contract_value"]["value"]["amount"] = 1250.5
    elif mutation == "fake_currency":
        data["contract_value"]["value"]["currency"] = "ZZZ"
    elif mutation == "bad_date":
        data["effective_date"]["value"] = "2026-02-30"
    elif mutation == "bad_status":
        data["status"]["value"] = "paid"
    elif mutation == "confidence":
        data["employer"]["confidence"] = 1.5
    else:
        data["employer"]["source_page"] = "1"
    generate = Mock(return_value=json.dumps(data))
    with pytest.raises(StructuredExtractionError) as error:
        SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    assert generate.call_count == 2
    assert len(error.value.attempts) == 2
    assert "Imaginary" not in str(error.value)


def test_llm_cannot_calculate_total_or_copy_an_operand_as_total():
    data, source = case("boq")
    source.blocks[0].text += "\nQuantity 10, Unit rate USD 20\nTotal = USD 10 * 20\nTotal USD 10-20"
    for value in ("200", "10", "20"):
        data["stated_total"] = fact({"amount": value, "currency": "USD"}, source.blocks[0].text)
        with pytest.raises(StructuredExtractionError):
            SchemaConstrainedExtractor(
                lambda **_: json.dumps(data), model="mock", repair_retries=0
            ).extract(source, "boq")


def test_unrelated_number_and_currency_do_not_prove_money():
    data, source = case("contract")
    source.blocks[0].text += "\nQuantity: 10 m3. Budget: USD 900"
    data["contract_value"] = fact(
        {"amount": "10", "currency": "USD"}, "Quantity: 10 m3. Budget: USD 900"
    )
    with pytest.raises(EvidenceError):
        validate_evidence(Contract.model_validate(data), source)


def test_negated_status_is_not_an_approval():
    data, source = case("contract")
    source.blocks[0].text += "\nStatus: not signed"
    data["status"] = fact("signed", "Status: not signed")
    with pytest.raises(EvidenceError):
        validate_evidence(Contract.model_validate(data), source)


def test_exhausted_repair_retains_attempts_but_does_not_log_source(caplog):
    _, source = case("contract")
    generate = Mock(return_value="SECRET DOCUMENT INVALID JSON")
    with pytest.raises(StructuredExtractionError) as error:
        SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    assert error.value.attempts[0]["raw_output"] == "SECRET DOCUMENT INVALID JSON"
    assert "SECRET" not in caplog.text + str(error.value)


def test_provider_errors_are_not_repaired_as_invalid_json():
    _, source = case("contract")
    generate = Mock(side_effect=TimeoutError())
    with pytest.raises(TimeoutError):
        SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    generate.assert_called_once()


def test_provider_request_uses_strict_json_schema(monkeypatch):
    from app.ai.gateway.provider import OpenAIProvider
    from app.ai.gateway.service import ModelGateway

    services = Services()
    data, source = case("contract")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=json.dumps(data), refusal=None),
            )
        ],
        usage=None,
    )
    client = Mock()
    client.chat.completions.create.return_value = response
    services.gateway = ModelGateway(
        settings=services.settings, provider=OpenAIProvider(services.settings, client=client)
    )
    assert services.extract(source, {"document_type": "contract"})["fields"] == data
    request = client.chat.completions.create.call_args.kwargs
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert request["timeout"] <= 60


def test_truncated_output_uses_bounded_repair_but_refusal_does_not(monkeypatch):
    from app.document_processing.structured.service import (
        IncompleteStructuredOutput,
        StructuredExtractionRefused,
    )

    data, source = case("contract")
    generate = Mock(side_effect=[IncompleteStructuredOutput('{"title":'), json.dumps(data)])
    result = SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    assert result["attempts"][0]["errors"][0]["type"] == "incomplete_output"
    generate = Mock(side_effect=StructuredExtractionRefused("refused"))
    with pytest.raises(StructuredExtractionRefused):
        SchemaConstrainedExtractor(generate, model="mock").extract(source, "contract")
    generate.assert_called_once()


def test_legacy_classifier_label_uses_typed_schema_without_relabelling():
    data, source = case("other")
    result = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock").extract(
        source, "invoice"
    )
    assert (
        result["document_type"] == "invoice" and result["fields"]["title"]["value"] == "Site notes"
    )


def test_reference_kind_must_be_supported_by_quotation():
    data, source = case("rfi")
    data["document_references"][0]["value"]["kind"] = "contract"
    with pytest.raises(EvidenceError):
        validate_evidence(SCHEMAS["rfi"].model_validate(data), source)


def test_quotation_can_span_contiguous_blocks_on_same_page():
    from app.document_processing.extraction.types import TextBlock

    data, source = case("rfi")
    source.blocks.extend(
        [
            TextBlock(text="Please confirm", page_number=1),
            TextBlock(text="the footing level.", page_number=1),
        ]
    )
    data["question"] = fact(
        "Please confirm\nthe footing level.", "Please confirm\nthe footing level."
    )
    assert validate_evidence(SCHEMAS["rfi"].model_validate(data), source)


def test_confidence_and_missing_summary_are_computed_not_model_claims():
    data, source = case("contract")
    data["contractor"] = missing()
    result = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock").extract(
        source, "contract"
    )
    result.update({"confidence": 1, "missing_required_fields": []})
    checked = validate_result(result, source, "contract")
    assert checked["confidence"] == 0 and checked["missing_required_fields"] == ["contractor"]


async def test_pipeline_persists_typed_facts(pipeline, test_session):  # noqa: F811
    data, source = case("contract")
    pipeline.services.extraction.side_effect = None
    pipeline.services.extraction.return_value = source
    extractor = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock")
    pipeline.services.extract.side_effect = lambda source, classification: extractor.extract(
        source, classification["document_type"]
    )
    for _ in range(12):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "completed"
    stored = document.structured_extraction
    assert stored["fields"]["contract_value"]["value"] == {"amount": "1250.50", "currency": "BDT"}
    assert stored["fields"]["contractor"]["source_page"] == 1
    assert float(document.extraction_confidence) == 0.95
    assert await pipeline.step() is None
    pipeline.services.extract.assert_called_once()


async def test_pipeline_retains_failed_repair_attempts(pipeline, test_session):  # noqa: F811
    _, source = case("contract")
    pipeline.services.extraction.side_effect = None
    pipeline.services.extraction.return_value = source
    generate = Mock(return_value="{malformed")
    extractor = SchemaConstrainedExtractor(generate, model="mock")
    pipeline.services.extract.side_effect = lambda source, classification: extractor.extract(
        source, classification["document_type"]
    )
    for _ in range(5):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "dead_letter" and document.structured_extraction is None
    assert len(document.processing_data["structured_extraction_attempts"]) == 2
    assert "extract_text" in document.processing_data["results"]
    assert (await test_session.scalar(select(ProcessingDeadLetter))).stage == "extract_fields"


async def test_pipeline_missing_required_field_creates_review(pipeline, test_session):  # noqa: F811
    data, source = case("contract")
    data["contractor"] = missing()
    pipeline.services.extraction.side_effect = None
    pipeline.services.extraction.return_value = source
    extractor = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock")
    pipeline.services.extract.side_effect = lambda source, classification: extractor.extract(
        source, classification["document_type"]
    )
    for _ in range(12):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "review_required"
    assert document.structured_extraction["missing_required_fields"] == ["contractor"]
    assert (await test_session.scalar(select(DocumentReviewTask))).reason == "low_confidence"


async def test_field_confidence_rounding_cannot_bypass_review(pipeline, test_session):  # noqa: F811
    data, source = case("contract")
    data["status"]["confidence"] = 0.79999
    pipeline.services.extraction.side_effect = None
    pipeline.services.extraction.return_value = source
    extractor = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock")
    pipeline.services.extract.side_effect = lambda source, classification: extractor.extract(
        source, classification["document_type"]
    )
    for _ in range(12):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "review_required"


async def test_decimal_credit_reaches_deterministic_risk_check(pipeline, test_session):  # noqa: F811
    from app.domain.models import Risk

    data, source = case("change_order")
    pipeline.services.classify.return_value["document_type"] = "change_order"
    pipeline.services.extraction.side_effect = None
    pipeline.services.extraction.return_value = source
    extractor = SchemaConstrainedExtractor(lambda **_: json.dumps(data), model="mock")
    pipeline.services.extract.side_effect = lambda source, classification: extractor.extract(
        source, classification["document_type"]
    )
    for _ in range(12):
        await pipeline.step()
    assert (await pipeline.refresh()).processing_status == "review_required"
    assert (await test_session.scalar(select(Risk))).title == "Negative amount"


async def test_site_photo_with_caption_still_requires_visual_review(pipeline, test_session):  # noqa: F811
    pipeline.services.classify.return_value["document_type"] = "site_photo"
    for _ in range(4):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "review_required"
    assert (
        await test_session.scalar(select(DocumentReviewTask))
    ).reason == "visual_document_requires_review"
    pipeline.services.extract.assert_not_called()
