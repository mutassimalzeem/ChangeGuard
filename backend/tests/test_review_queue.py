"""API authorization and evidence rules for the persisted review queue."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.domain.models import (
    AuditEvent,
    Document,
    DocumentReviewTask,
    EvidenceLink,
    Project,
    ProjectEvent,
    ProjectMembership,
    Risk,
    User,
)
from app.main import app
from app.policy.scope import SCOPE_KEY
from tests.test_risk_engine import co_doc


@pytest.fixture
async def queue(client, test_session, tenant, project, user):
    extraction = co_doc().structured_extraction
    extraction["fields"]["description"].update(
        confidence=0.42, source_page=3, source_text_snippet="Additional excavation"
    )
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="report.pdf",
        storage_key="review-queue",
        mime_type="application/pdf",
        size_bytes=1,
        extraction_confidence="0.42",
        structured_extraction=extraction,
    )
    risk = Risk(
        tenant_id=tenant.id,
        project_id=project.id,
        title="Unconfirmed delay",
        risk_type="conflicting_information",
        severity="high",
        status="insufficient_evidence",
    )
    test_session.add_all([document, risk])
    await test_session.flush()
    task = DocumentReviewTask(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        reason="low_confidence",
    )
    test_session.add_all(
        [
            task,
            EvidenceLink(
                tenant_id=tenant.id,
                project_id=project.id,
                subject_type="risk",
                subject_id=risk.id,
                source_type="document",
                source_id=document.id,
                source_page=2,
                source_text_snippet="Delivery date is unconfirmed.",
            ),
        ]
    )
    await test_session.flush()

    async def current():
        return user

    app.dependency_overrides[get_current_user] = current
    yield f"/api/v1/projects/{project.id}", risk.id, task.id, document.id


@pytest.mark.parametrize("role", ["viewer", "site_engineer", "auditor"])
async def test_review_actions_require_commercial_permission(client, user, queue, role):
    base, risk_id, task_id, _ = queue
    user.role = role
    assert (await client.get(f"{base}/review-queue")).status_code == 403
    for path in [
        f"review-queue/extractions/{task_id}/decisions",
        f"risks/{risk_id}/decisions",
        f"risks/{risk_id}/change-order-draft",
    ]:
        response = await client.post(
            f"{base}/{path}", json={"action": "dismiss", "reason": "Duplicate"}
        )
        assert response.status_code == 403


async def test_review_queue_retains_insufficient_evidence_after_request(
    client, test_session, user, queue
):
    base, risk_id, task_id, document_id = queue
    user.role = "owner"
    response = await client.get(f"{base}/review-queue")
    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()}
    risk = items[str(risk_id)]
    assert set(risk["categories"]) == {
        "insufficient_evidence_risk",
        "conflicting_evidence",
        "high_severity_risk",
    }
    assert risk["evidence_details"][0]["source_page"] == 2
    assert risk["document_id"] == str(document_id)
    assert items[str(task_id)]["categories"] == ["low_confidence_extraction"]
    citation = items[str(task_id)]["evidence_details"][0]
    assert citation["source_page"] == 3
    assert citation["source_text_snippet"] == "Additional excavation"

    risk_url = f"{base}/risks/{risk_id}"
    response = await client.post(
        f"{risk_url}/decisions", json={"action": "request_evidence", "reason": "Verify date"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "evidence_requested"
    assert response.json()["evidence_supported"] is False
    assert (
        await client.post(f"{risk_url}/decisions", json={"action": "accept", "reason": "Reviewed"})
    ).status_code == 422
    assert (await client.post(f"{risk_url}/change-order-draft", json={})).status_code == 422

    task_url = f"{base}/review-queue/extractions/{task_id}/decisions"
    assert (
        await client.post(task_url, json={"action": "dismiss", "reason": "  "})
    ).status_code == 422
    assert (
        await client.post(task_url, json={"action": "request_evidence", "reason": "Verify field"})
    ).status_code == 204
    assert (
        await client.post(task_url, json={"action": "dismiss", "reason": "Superseded"})
    ).status_code == 204
    audit = await test_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == task_id, AuditEvent.action == "document_review_task.dismiss"
        )
    )
    assert audit.actor_id == user.id
    assert audit.details == {
        "reason": "Superseded",
        "before": "evidence_requested",
        "after": "dismissed",
    }


async def test_queue_hides_restricted_sources_and_denies_other_projects(
    client, test_session, tenant, project, user, queue
):
    base, risk_id, task_id, doc_id = queue
    document = await test_session.get(Document, doc_id)
    document.access_level = "restricted"
    test_session.add(ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    other = Project(tenant_id=tenant.id, code="OTHER", name="Other")
    test_session.add(other)
    user.role = "commercial_manager"
    await test_session.flush()
    other_id = other.id

    response = await client.get(f"{base}/review-queue")
    assert response.status_code == 200
    assert response.json() == []
    assert (await client.get(f"/api/v1/projects/{other_id}/review-queue")).status_code == 404
    for path in (
        f"review-queue/extractions/{task_id}/decisions",
        f"risks/{risk_id}/decisions",
    ):
        assert (
            await client.post(f"{base}/{path}", json={"action": "dismiss", "reason": "Reviewed"})
        ).status_code == 404


@pytest.mark.parametrize("decision,final_status", [("approve", "approved"), ("reject", "rejected")])
async def test_supported_risk_converts_and_both_records_are_audited(
    client, test_session, user, queue, monkeypatch, decision, final_status
):
    base, risk_id, _, document_id = queue
    user.role = "owner"
    risk = await test_session.get(Risk, risk_id)
    event = ProjectEvent(
        tenant_id=user.tenant_id,
        project_id=risk.project_id,
        document_id=document_id,
        event_type="delay",
        title="Delivery delay",
        occurred_at=datetime.now(UTC),
    )
    reviewer = User(
        tenant_id=user.tenant_id,
        email="reviewer@example.invalid",
        full_name="Reviewer",
        password_hash="test-hash",
        role="owner",
    )
    test_session.add_all([event, reviewer])
    await test_session.flush()
    event_id = event.id
    risk.status = "open"
    risk.risk_type = "daily_report_delay_without_link"
    risk.severity = "high"
    risk.project_event_id = event_id
    risk.responsible_party = "Steel subcontractor"
    risk.document_id = document_id
    await test_session.flush()
    monkeypatch.setattr(
        "app.domain.services.change_orders.get_settings",
        lambda: SimpleNamespace(llm_provider="openai", llm_api_key=None),
    )

    url = f"{base}/risks/{risk_id}"
    assert (
        await client.post(
            f"{url}/decisions", json={"action": "override", "reason": " ", "severity": "critical"}
        )
    ).status_code == 422
    response = await client.post(
        f"{url}/change-order-draft", json={"reason": "Verified delivery notice"}
    )
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "drafted"
    assert order["amount"] is None
    assert order["time_impact_days"] is None
    assert order["source_event_id"] == str(event_id)
    assert order["responsible_party"] == "Steel subcontractor"
    assert {source["evidence_link_id"] for source in order["draft"]["sources"].values()} == set(
        order["evidence_links"]
    )
    order_url = f"/api/v1/change-orders/{order['id']}"
    edited = await client.patch(
        order_url,
        json={
            "title": "Delivery recovery",
            "cost_items": [
                {"description": "Expedite delivery", "quantity": "1", "unit_rate": "125"}
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    submitted = await client.post(f"{order_url}/submit", json={"cost_confirmed": True})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert (await client.post(f"{order_url}/approve", json={"reason": " "})).status_code == 422
    assert (
        await client.post(f"{order_url}/approve", json={"reason": "Reviewed"})
    ).status_code == 403
    items = (await client.get(f"{base}/review-queue")).json()
    item = next(item for item in items if item["id"] == str(risk_id))
    assert item["status"] == "converted"
    assert item["reviewable"] is False
    assert item["change_order_id"] == order["id"]
    audit = await test_session.scalar(select(AuditEvent).where(AuditEvent.entity_id == risk_id))
    assert audit.action == "risk.converted_to_change_order"
    assert audit.details["reason"] == "Verified delivery notice"
    actions = (
        await test_session.scalars(
            select(AuditEvent.action).where(AuditEvent.entity_id == UUID(order["id"]))
        )
    ).all()
    assert set(actions) == {
        "change_order.draft_created_from_risk",
        "change_order.patch",
        "change_order.submit",
    }
    order_audit = await test_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == UUID(order["id"]),
            AuditEvent.action == "change_order.draft_created_from_risk",
        )
    )
    assert order_audit.action == "change_order.draft_created_from_risk"
    assert order_audit.actor_id == user.id
    # The shared integration fixture uses one database transaction for both requests.
    # Reset its principal to model a new authenticated request by the other reviewer.
    test_session.info.pop(SCOPE_KEY)

    async def current_reviewer():
        return reviewer

    app.dependency_overrides[get_current_user] = current_reviewer
    listing = await client.get(f"{base}/change-orders")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["status"] == "submitted"
    decided = await client.post(
        f"{order_url}/{decision}", json={"reason": "Reviewed evidence package"}
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == final_status
    audit = await test_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == UUID(order["id"]),
            AuditEvent.action == f"change_order.{final_status}",
        )
    )
    assert audit.actor_id == reviewer.id
    assert audit.details["reason"] == "Reviewed evidence package"
