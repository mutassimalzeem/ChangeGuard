"""Golden documents and adversarial/fallback cases; no network model calls."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.document_processing.classification import ClassificationInput, RuleFirstClassifier
from app.document_processing.providers import Services
from app.domain.models import DocumentReviewTask
from app.evaluation.classification import DEFAULT_DATASET, evaluate, main
from tests.test_processing_pipeline import pipeline  # noqa: F401

GOLDEN = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))


def result(kind="rfi", confidence=0.92):
    return {
        "document_type": kind,
        "confidence": confidence,
        "reasoning": "Document purpose and headings agree.",
        "model_or_rule_used": "llm:mock",
    }


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: c["id"])
def test_golden_documents(case):
    fallback = Mock(return_value=result(case["expected"]))
    classified = RuleFirstClassifier(fallback).classify(
        ClassificationInput.model_validate(case["input"])
    )
    assert classified.document_type == case["expected"]
    assert classified.reasoning and classified.model_or_rule_used
    assert fallback.call_count == int(case["requires_fallback_or_review"])


def test_rules_only_evaluation_reports_real_abstentions():
    report = evaluate(GOLDEN, RuleFirstClassifier().classify)
    assert report["documents"] >= 10
    assert len(report["per_type"]) == 10
    assert report["correct"] == 20 and report["accuracy"] == 20 / 22
    assert report["llm_calls"] == 0
    assert {failure["id"] for failure in report["failures"]} == {
        "rfi_misleading_filename",
        "unlabelled_photo",
    }
    assert report["review_required"] == 4


def test_conflicting_rules_call_llm_once():
    fallback = Mock(return_value=result())
    document = ClassificationInput(
        filename="contract.pdf", extracted_text="Request for Information\nQuestion: Clarify levels."
    )
    assert RuleFirstClassifier(fallback).classify(document).document_type == "rfi"
    fallback.assert_called_once_with(document)


def test_untrusted_metadata_hint_alone_is_not_authoritative():
    classified = RuleFirstClassifier().classify(
        ClassificationInput(metadata={"document_type": "contract"})
    )
    assert classified.document_type == "other" and classified.confidence < 0.8


def test_same_input_has_stable_rule_output_and_no_raw_quotes():
    document = ClassificationInput(
        filename="BOQ_003.xlsx",
        extracted_text="Description Quantity Unit Rate\nSECRET PROJECT RATE",
    )
    classifier = RuleFirstClassifier()
    assert classifier.classify(document) == classifier.classify(document)
    assert "SECRET" not in classifier.classify(document).reasoning


@pytest.mark.parametrize(
    "override",
    [
        {"document_type": "invoice"},
        {"confidence": float("nan")},
        {"confidence": 2},
        {"reasoning": ""},
        {"approved": True},
    ],
)
def test_invalid_llm_output_is_rejected(override):
    with pytest.raises(ValueError):
        RuleFirstClassifier(lambda _: {**result(), **override}).classify(ClassificationInput())


def test_services_stamp_actual_model_and_limit_metadata(monkeypatch):
    services = Services()
    monkeypatch.setattr(services.settings, "llm_provider", "openai")
    monkeypatch.setattr(services.settings, "llm_api_key", "unit-test-not-a-secret")
    from app.document_processing.schema import Classification

    structured = Mock(
        return_value=SimpleNamespace(
            value=Classification(**{**result(), "model_or_rule_used": "rules:forged"}),
            model="fallback-classifier",
        )
    )
    monkeypatch.setattr(services.gateway, "generate", structured)
    classified = services.classify(
        ClassificationInput(
            filename="unknown.pdf", metadata={"api_key": "NEVER_SEND", "tenant_id": "PRIVATE"}
        )
    )
    assert classified["model_or_rule_used"] == "llm:fallback-classifier"
    assert (
        "NEVER_SEND" not in structured.call_args.args[1][1]["content"]
        and "PRIVATE" not in structured.call_args.args[1][1]["content"]
    )
    assert "untrusted" in structured.call_args.args[1][0]["content"]


def test_unconfigured_llm_returns_safe_low_confidence_other(monkeypatch):
    services = Services()
    monkeypatch.setattr(services.settings, "llm_provider", "none")
    client = Mock(side_effect=AssertionError("No LLM should be invoked"))
    monkeypatch.setattr(services.gateway, "generate", client)
    assert services.classify(ClassificationInput())["document_type"] == "other"
    client.assert_not_called()


def test_configured_llm_is_not_called_for_clear_rules(monkeypatch):
    services = Services()
    monkeypatch.setattr(services.settings, "llm_provider", "openai")
    monkeypatch.setattr(services.settings, "llm_api_key", "unit-test-not-a-secret")
    fallback = Mock(side_effect=AssertionError("Rules must run first"))
    monkeypatch.setattr(services, "classify_with_llm", fallback)
    assert services.classify(ClassificationInput(filename="BOQ.xlsx"))["document_type"] == "boq"
    fallback.assert_not_called()


def test_transient_fallback_failure_is_not_disguised_as_classification():
    fallback = Mock(side_effect=TimeoutError("provider failure"))
    with pytest.raises(TimeoutError):
        RuleFirstClassifier(fallback).classify(ClassificationInput())


def test_evaluation_cli_exit_code_and_json(tmp_path, capsys):
    path = tmp_path / "evaluation.json"
    assert main(["--output", str(path), "--min-accuracy", "0.9"]) == 0
    report = json.loads(path.read_text())
    assert report["mode"] == "rules_only" and report["llm_calls"] == 0
    assert json.loads(capsys.readouterr().out)["accuracy"] == report["accuracy"]
    assert main(["--min-accuracy", "1"]) == 1


@pytest.mark.parametrize("confidence,review", [(0.79, True), (0.8, False)])
async def test_review_threshold(pipeline, test_session, confidence, review):  # noqa: F811
    pipeline.services.classify.return_value = result("contract", confidence)
    for _ in range(4):
        delay = await pipeline.step()
    document = await pipeline.refresh()
    assert document.document_type == "contract"
    assert document.classification_result == result("contract", confidence)
    from app.domain.schemas.document import DocumentRead

    assert (
        DocumentRead.model_validate(document).classification_result.model_dump()
        == document.classification_result
    )
    assert document.processing_status == ("review_required" if review else "classify_document_done")
    task = await test_session.scalar(select(DocumentReviewTask))
    assert (task is not None) == review
    if review:
        assert task.reason == "low_classification_confidence" and delay is None
        await pipeline.step()
        pipeline.services.extract.assert_not_called()
        pipeline.services.classify.assert_called_once()


async def test_site_photo_classifies_without_ocr_or_llm(pipeline, test_session):  # noqa: F811
    from app.document_processing.extraction.types import ExtractionResult

    # Validation/storage stages are already covered by registry tests; retain their checkpoints.
    document = pipeline.document
    document.filename, document.file_type, document.mime_type = (
        "site_photo_001.jpg",
        "jpg",
        "image/jpeg",
    )
    document.processing_data = {"results": {"validate_file": {}, "store_original": {}}}
    await test_session.commit()
    services = Services()
    pipeline.services.classify.side_effect = services.classify
    await pipeline.step()
    assert (await pipeline.refresh()).processing_data["results"][
        "extract_text"
    ] == ExtractionResult().model_dump(mode="json")
    await pipeline.step()
    document = await pipeline.refresh()
    assert (
        document.document_type == "site_photo" and document.processing_status == "review_required"
    )
    pipeline.services.extraction.assert_not_called()
    assert (
        await test_session.scalar(select(DocumentReviewTask))
    ).reason == "visual_document_without_text"


@pytest.mark.parametrize("unavailable", [False, True])
async def test_image_review(pipeline, test_session, monkeypatch, unavailable):  # noqa: F811
    from app.document_processing.extraction.types import ExtractionResult
    from app.document_processing.providers import ProviderUnavailable

    document = pipeline.document
    document.filename, document.file_type, document.mime_type = "IMG_001.png", "png", "image/png"
    document.processing_data = {"results": {"validate_file": {}, "store_original": {}}}
    await test_session.commit()
    services = Services()
    monkeypatch.setattr(services.settings, "llm_provider", "none")
    pipeline.services.classify.side_effect = services.classify
    pipeline.services.extraction.side_effect = ProviderUnavailable() if unavailable else None
    pipeline.services.extraction.return_value = ExtractionResult()
    await pipeline.step()
    await pipeline.step()
    document = await pipeline.refresh()
    assert document.document_type == "other" and document.processing_status == "review_required"
    assert (
        await test_session.scalar(select(DocumentReviewTask))
    ).reason == "low_classification_confidence"
