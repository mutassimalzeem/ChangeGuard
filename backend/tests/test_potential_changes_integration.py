"""Real database provenance, pipeline and API isolation tests."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.document_processing.providers import Services
from app.domain.models import Document, EvidenceLink, ProjectEvent
from app.domain.services.potential_changes import process
from app.main import app
from tests.test_potential_changes import FIXTURES, source
from tests.test_processing_pipeline import pipeline  # noqa: F401


@pytest.fixture
async def potential(test_session, tenant, project, user):
    user.role = "owner"
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="daily-report.pdf",
        storage_key="potential",
        mime_type="application/pdf",
        size_bytes=1,
        document_type="daily_report",
    )
    test_session.add(document)
    await test_session.flush()
    ids = await process(
        document,
        source("Additional work required, estimated cost USD 1250.50 and delay of 2 days."),
        test_session,
        SimpleNamespace(settings=None),
    )
    await test_session.flush()
    return project.id, document.id, ids


async def test_record_contract_evidence_and_idempotency(test_session, potential):
    project_id, document_id, ids = potential
    assert len(ids) == 2
    event = await test_session.get(ProjectEvent, UUID(ids[0]))
    assert event.detected_date and event.status == "potential_change"
    assert event.suggested_cost_impact == Decimal("1250.50")
    assert event.suggested_schedule_impact == 2
    assert event.attributes["human_review_required"] is True
    document = await test_session.get(Document, document_id)
    again = await process(
        document,
        source("Additional work required, estimated cost USD 1250.50 and delay of 2 days."),
        test_session,
        SimpleNamespace(settings=None),
    )
    assert ids == again
    links = list(await test_session.scalars(select(EvidenceLink)))
    assert len(links) == 2
    assert all(link.source_id == document_id and link.source_page == 2 for link in links)
    assert all(link.subject_type == "project_event" for link in links)


async def test_photo_uses_ambiguous_vision_classification_with_review(
    test_session, tenant, project
):
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="photo.jpg",
        storage_key="photo",
        mime_type="image/jpeg",
        size_bytes=1,
        document_type="site_photo",
    )
    test_session.add(document)
    await test_session.flush()
    fallback = Mock(
        return_value={
            "event_type": "material_issue",
            "source_quote": "",
            "explanation": "Visible damaged material requires inspection.",
            "confidence": 0.92,
        }
    )
    services = SimpleNamespace(
        settings=SimpleNamespace(llm_provider="openai", llm_api_key="test"),
        potential_change_classification=fallback,
    )
    from app.document_processing.extraction.types import ExtractionResult

    ids = await process(document, ExtractionResult(), test_session, services, image=b"image")
    await test_session.flush()
    event = await test_session.get(ProjectEvent, UUID(ids[0]))
    assert event.confidence == Decimal("0.65")
    assert event.suggested_cost_impact is None
    assert event.suggested_schedule_impact is None
    assert event.attributes["human_review_required"] is True
    assert fallback.call_args.kwargs["image"] == b"image"
    assert (await test_session.scalar(select(EvidenceLink))).source_text_snippet is None


async def test_unsupported_document_type_skips_models_and_records(test_session, tenant, project):
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="contract.pdf",
        storage_key="contract",
        mime_type="application/pdf",
        size_bytes=1,
        document_type="contract",
    )
    services = Mock(spec=Services)
    assert (
        await process(document, source("Additional work required."), test_session, services) == []
    )
    services.potential_change_classification.assert_not_called()


async def test_daily_report_pipeline_creates_potential_change(pipeline, test_session):  # noqa: F811
    pipeline.services.classify.return_value["document_type"] = "daily_report"
    pipeline.services.extraction.side_effect = None
    pipeline.services.extraction.return_value = source((FIXTURES / "daily_report.txt").read_text())
    for _ in range(12):
        await pipeline.step()
    document = await pipeline.refresh()
    assert document.processing_status == "review_required"
    ids = document.processing_data["results"]["link_entities"]["potential_changes"]
    assert len(ids) >= 6
    assert len(list(await test_session.scalars(select(ProjectEvent)))) == len(ids)
    await pipeline.step()
    assert len(list(await test_session.scalars(select(ProjectEvent)))) == len(ids)


async def test_api_contract_and_evidence_visibility(client, test_session, user, potential):
    project_id, document_id, ids = potential
    url = f"/api/v1/projects/{project_id}/potential-changes"

    async def current():
        return user

    app.dependency_overrides[get_current_user] = current
    try:
        response = await client.get(url)
        assert response.status_code == 200
        row = response.json()[0]
        assert set(row) >= {
            "title",
            "description",
            "detected_date",
            "event_type",
            "evidence_links",
            "confidence",
            "suggested_owner",
            "suggested_cost_impact",
            "suggested_schedule_impact",
        }
        assert row["human_review_required"] is True
        assert row["suggested_cost_impact"] == "1250.50"
        assert (await client.get(url + "/" + ids[0])).status_code == 200
        document = await test_session.scalar(select(Document).where(Document.id == document_id))
        document.deleted_at = document.created_at
        await test_session.flush()
        assert (await client.get(url)).json() == []
        assert (await client.get(url + "/" + ids[0])).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_model_adapter_only_classifies_and_explains():
    from app.domain.services.potential_changes import AmbiguousEvent

    value = AmbiguousEvent(
        event_type=None, explanation="Routine clarification.", source_quote="", confidence=0.8
    )
    gateway = Mock()
    gateway.generate.return_value = SimpleNamespace(value=value)
    services = Services(gateway=gateway)
    assert services.potential_change_classification("Please clarify.")["event_type"] is None
    assert gateway.generate.call_args.kwargs["schema"] is AmbiguousEvent
    assert "cost" not in AmbiguousEvent.model_fields


async def test_api_does_not_expose_another_projects_event(
    client, test_session, tenant, user, potential
):
    from app.domain.models import Project

    _, _, ids = potential
    other = Project(tenant_id=tenant.id, code="OTHER-PC", name="Other")
    test_session.add(other)
    await test_session.flush()
    url = f"/api/v1/projects/{other.id}/potential-changes/{ids[0]}"

    async def current():
        return user

    app.dependency_overrides[get_current_user] = current
    try:
        assert (await client.get(url)).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_nonfinancial_user_cannot_read_suggestions(client, test_session, user, potential):
    from app.api.exceptions import AuthorizationError
    from app.policy.scope import bind_scope

    project_id, _, _ = potential
    user.role = "viewer"
    await test_session.flush()

    async def current():
        return user

    app.dependency_overrides[get_current_user] = current
    try:
        assert (
            await client.get(f"/api/v1/projects/{project_id}/potential-changes")
        ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    bind_scope(test_session, user)
    with pytest.raises(AuthorizationError):
        await test_session.scalar(select(ProjectEvent.suggested_cost_impact))


async def test_unavailable_classifier_queues_manual_review(test_session, tenant, project):
    from app.domain.models import DocumentReviewTask

    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="email.eml",
        storage_key="ambiguous-email",
        mime_type="message/rfc822",
        size_bytes=1,
        document_type="email",
    )
    test_session.add(document)
    await test_session.flush()
    services = SimpleNamespace(settings=None)
    assert (
        await process(
            document,
            source("Clarification needed on unexpected obstruction."),
            test_session,
            services,
        )
        == []
    )
    assert (
        await process(
            document,
            source("Clarification needed on unexpected obstruction."),
            test_session,
            services,
        )
        == []
    )
    tasks = list(await test_session.scalars(select(DocumentReviewTask)))
    assert len(tasks) == 1
    assert tasks[0].reason == "potential_change_classification_required"
