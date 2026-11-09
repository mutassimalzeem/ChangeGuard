"""Seeded metric semantics, independent of a database or provider."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as Row
from uuid import uuid4

import pytest

from app.domain.services.pilot_metrics import calculate_metrics, percentile

NOW = datetime(2026, 11, 16, tzinfo=UTC)


def document(status="linked", **kw):
    return Row(
        id=uuid4(),
        created_at=NOW - timedelta(days=2),
        status=status,
        processing_status="completed" if status == "linked" else status,
        processing_data=kw.pop("processing_data", {}),
        classification_result=kw.pop("classification_result", None),
        structured_extraction=kw.pop("structured_extraction", None),
        **kw,
    )


def calculate(**kw):
    return calculate_metrics(
        documents=kw.pop("documents", []),
        reviews=kw.pop("reviews", []),
        risks=kw.pop("risks", []),
        changes=kw.pop("changes", []),
        approvals=kw.pop("approvals", []),
        tasks=kw.pop("tasks", []),
        traces=kw.pop("traces", []),
        covered_document_ids=kw.pop("covered_document_ids", set()),
        start=NOW - timedelta(days=7),
        end=NOW,
        **kw,
    )


def test_empty_is_unknown_not_perfect():
    metrics = calculate()
    assert metrics["documents_uploaded"] == 0
    assert metrics["processing_failure_rate"]["value"] is None
    assert metrics["classification_accuracy"]["value"] is None
    assert metrics["extraction_accuracy"]["value"] is None
    assert metrics["processing_latency_seconds"]["p95"] is None
    assert metrics["ai_cost_per_document"]["value"] is None


def test_failures_exclude_quarantine_pending_and_review_required():
    docs = [
        document(),
        document("failed"),
        document("quarantined"),
        document("queued"),
        document("review_required"),
    ]
    metrics = calculate(documents=docs)
    assert metrics["documents_uploaded"] == 5
    assert metrics["documents_processed_successfully"] == 1
    assert metrics["processing_failure_rate"] == {"value": 0.5, "numerator": 1, "denominator": 2}


def test_percentiles_interpolate_and_do_not_mutate():
    samples = [100, 10, 30, 20]
    assert percentile(samples, 0.5) == 25
    assert percentile(samples, 0.9) == pytest.approx(79)
    assert percentile(samples, 0.95) == pytest.approx(89.5)
    assert samples == [100, 10, 30, 20]


def test_latency_uses_explicit_timing_not_updated_at():
    docs = [
        document(
            processing_data={
                "metrics": {
                    "started_at": (NOW - timedelta(seconds=101)).isoformat(),
                    "finished_at": (NOW - timedelta(seconds=1)).isoformat(),
                }
            }
        ),
        document(),
    ]
    result = calculate(documents=docs)["processing_latency_seconds"]
    assert result == {"p50": 100, "p90": 100, "p95": 100, "samples": 1, "eligible": 2}


def event(action, document_id=None, **details):
    return Row(
        id=uuid4(),
        created_at=NOW - timedelta(hours=1),
        action=action,
        entity_id=uuid4(),
        details={**({"document_id": str(document_id)} if document_id else {}), **details},
    )


def field(value, confidence=0.8):
    return {
        "value": value,
        "missing": value is None,
        "confidence": confidence,
        "source_page": 1,
        "source_text_snippet": "Synthetic evidence",
    }


def test_seeded_accuracy_counts_latest_reviews_and_field_values():
    first = document(
        classification_result={"document_type": "contract"},
        structured_extraction={
            "document_type": "contract",
            "fields": {"title": field("A"), "amount": field("10")},
        },
    )
    second = document(classification_result={"document_type": "rfi"})
    reviews = [
        event(
            "pilot.review",
            first.id,
            type_reviewed=True,
            extraction_reviewed=True,
            after={
                "document_type": "contract",
                "extraction": {
                    "document_type": "contract",
                    "fields": {"title": field("A", 0.1), "amount": field("20")},
                },
            },
        ),
        event("pilot.review", second.id, type_reviewed=True, after={"document_type": "contract"}),
    ]
    result = calculate(documents=[first, second], reviews=reviews)
    assert result["classification_accuracy"] == {"value": 0.5, "numerator": 1, "denominator": 2}
    assert result["extraction_accuracy"] == {"value": 0.5, "numerator": 1, "denominator": 2}
    assert result["human_override_rate"]["value"] == 1
    later = event("pilot.review", second.id, type_reviewed=True, after={"document_type": "rfi"})
    later.created_at += timedelta(minutes=1)
    assert (
        calculate(documents=[first, second], reviews=reviews + [later])["classification_accuracy"][
            "value"
        ]
        == 1
    )


def test_evidence_deduplication_and_event_decisions():
    docs = [document(), document()]
    result = calculate(
        documents=docs,
        covered_document_ids={docs[0].id},
        reviews=[event("risk.accept"), event("risk.dismiss"), event("risk.override")],
        risks=[Row(detected_at=NOW - timedelta(days=1))],
        changes=[Row(created_at=NOW - timedelta(days=1))],
    )
    assert result["evidence_link_coverage"]["value"] == 0.5
    assert (
        result["risks_detected"]
        == result["risks_accepted"]
        == result["risks_dismissed"]
        == result["change_orders_created"]
        == 1
    )
    assert result["human_override_rate"]["value"] == pytest.approx(1 / 3)


def test_approval_and_queue_durations_exclude_invalid_and_keep_open_ages():
    doc = document()
    entered = NOW - timedelta(hours=3)
    review = event("pilot.review", doc.id)
    tasks = [
        Row(created_at=entered, document_id=doc.id, status="pending"),
        Row(created_at=entered, document_id=uuid4(), status="pending"),
    ]
    approvals = [
        Row(created_at=entered, decided_at=NOW - timedelta(hours=1), status="approved"),
        Row(created_at=entered, decided_at=None, status="pending"),
    ]
    result = calculate(documents=[doc], reviews=[review], tasks=tasks, approvals=approvals)
    assert result["approval_cycle_time"]["value"] == result["time_in_review_queue"]["value"] == 7200
    assert result["open_review_queue_age"]["value"] == 10800


def test_costs_use_decimal_and_do_not_treat_unknown_as_zero():
    doc, run = str(uuid4()), str(uuid4())

    def trace(cost, **attributes):
        return Row(
            created_at=NOW - timedelta(hours=1),
            operation="reasoning",
            cost=cost,
            attributes=attributes,
        )

    traces = [
        trace(Decimal(".10"), document_id=doc),
        trace(Decimal(".20"), document_id=doc),
        trace(None, investigation_id=run),
    ]
    result = calculate(traces=traces)
    assert result["ai_cost_per_document"]["total"] == "0.30"
    assert result["ai_cost_per_document"]["resources"] == 1
    assert result["ai_cost_per_investigation"]["value"] is None
    assert result["ai_cost_per_investigation"]["known_cost_calls"] == 0


def test_half_open_boundaries_and_unknown_prediction():
    doc = document()
    doc.created_at = NOW
    assert calculate(documents=[doc])["documents_uploaded"] == 0
    review = event("pilot.review", doc.id, type_reviewed=True, after={"document_type": "contract"})
    doc.created_at = NOW - timedelta(days=1)
    assert (
        calculate(documents=[doc], reviews=[review])["classification_accuracy"]["denominator"] == 0
    )


def test_scope_inherits_resource_only_inside_same_project():
    from app.ai.gateway.context import current_scope, model_scope

    tenant, project, doc = uuid4(), uuid4(), uuid4()
    with model_scope(tenant, project, document_id=doc):
        with model_scope(tenant, project):
            assert current_scope().document_id == doc
        with model_scope(tenant, uuid4()):
            assert current_scope().document_id is None
    assert current_scope().document_id is None


@pytest.mark.asyncio
async def test_metrics_requires_authentication():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/projects/{uuid4()}/metrics")
    assert response.status_code == 401
