"""API authorization and evidence rules for the persisted review queue."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.domain.models import (
    Approval,
    AuditEvent,
    ChangeOrder,
    Document,
    DocumentReviewTask,
    EvidenceLink,
    Project,
    ProjectEvent,
    ProjectMembership,
    Risk,
    Tenant,
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


async def test_workspace_scoped_history_and_retry(
    client, test_session, user, project, tenant, queue
):
    base, risk, task, _ = queue
    user.role = "project_manager"
    other = User(
        tenant_id=tenant.id,
        email="peer@example.invalid",
        full_name="Peer",
        password_hash="test",
        role="commercial_manager",
    )
    test_session.add(other)
    await test_session.flush()
    for member in (user, other):
        test_session.add(
            ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=member.id)
        )
    await test_session.flush()
    root = f"{base}/review-queue"
    people = await client.get(f"{root}/reviewers")
    assert people.status_code == 200, people.text
    assert {p["id"] for p in people.json()} == {str(other.id), str(user.id)}
    url = f"{root}/risk/{risk}/commands"
    for action, args in [("assign_owner", {"owner_id": str(other.id)}), ("add_note", {})]:
        body = {
            "action": action,
            "key": str(uuid4()),
            "reason": "Please verify the field report",
            **args,
        }
        for _ in range(2):
            res = await client.post(url, json=body)
            assert res.status_code == 200, res.text
        assert (await client.post(url, json={**body, "reason": "Changed"})).status_code == 409
    res = await client.get(f"{root}/workspace", params={"owner_id": str(other.id), "page_size": 1})
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 1
    item = res.json()["items"][0]
    assert item["review_state"] == "insufficient_evidence"
    assert item["evidence_details"][0]["source_page"] == 2
    assert {e["action"] for e in item["history"]} == {"review.assign_owner", "review.add_note"}
    assert len(item["history"]) == 2
    assert (
        await client.post(url, json={"action": "accept", "key": str(uuid4()), "reason": "Reviewed"})
    ).status_code == 422
    body = {"action": "dismiss", "key": str(uuid4()), "reason": "Duplicate"}
    assert (await client.post(url, json=body)).status_code == 200
    assert (await client.post(url, json=body)).status_code == 200
    assert (
        await client.post(url, json={**body, "key": str(uuid4()), "action": "add_note"})
    ).status_code == 409
    assert (await client.get(f"{root}/workspace")).json()["total"] == 1
    page = (await client.get(f"{root}/workspace?status=dismissed")).json()
    assert page["total"] == 1 and page["items"][0]["id"] == str(risk)
    assert (await client.get(f"{root}/workspace?page_size=101")).status_code == 422
    exact = await client.get(f"{root}/workspace?min_confidence=0.42&max_confidence=0.42")
    assert [item["id"] for item in exact.json()["items"]] == [str(task)]
    assert (
        await client.get(f"{root}/workspace?min_confidence=0.8&max_confidence=0.3")
    ).status_code == 422


@pytest.mark.parametrize("hidden", ["deleted", "restricted"])
async def test_workspace_visibility_rechecked_for_every_action(
    client, test_session, tenant, project, user, queue, hidden
):
    base, risk, task, doc_id = queue
    doc = await test_session.get(Document, doc_id)
    if hidden == "restricted":
        doc.access_level = "restricted"
    else:
        doc.deleted_at = datetime.now(UTC)
    user.role = "commercial_manager"
    test_session.add(ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    await test_session.flush()
    assert (await client.get(f"{base}/review-queue/workspace")).json() == {"items": [], "total": 0}
    for kind, record in [("risk", risk), ("extraction", task)]:
        res = await client.post(
            f"{base}/review-queue/{kind}/{record}/commands",
            json={"key": str(uuid4()), "action": "add_note", "reason": "Check"},
        )
        assert res.status_code == 404


async def test_thresholds_and_pending_approval(
    client, test_session, tenant, project, user, queue, monkeypatch
):
    from decimal import Decimal

    from app.core.config import get_settings

    base, *_ = queue
    user.role = "owner"
    order = ChangeOrder(
        tenant_id=tenant.id,
        project_id=project.id,
        title="Manual valuation",
        reference="CO-9",
        currency="EUR",
        amount=1000,
        status="submitted",
    )
    test_session.add(order)
    await test_session.flush()
    approval = Approval(
        tenant_id=tenant.id,
        project_id=project.id,
        change_order_id=order.id,
        due_at=datetime.now(UTC),
    )
    test_session.add(approval)
    await test_session.flush()
    root = f"{base}/review-queue"
    monkeypatch.setattr(get_settings(), "review_high_value_thresholds", {"USD": Decimal("100")})
    assert (await client.get(f"{root}/workspace?category=high_value_change")).json()["total"] == 0
    monkeypatch.setattr(get_settings(), "review_high_value_thresholds", {"EUR": Decimal("1000")})
    page = (await client.get(f"{root}/workspace?category=high_value_change")).json()
    assert page["items"][0]["id"] == str(order.id)
    page = (await client.get(f"{root}/workspace?category=approval_request")).json()
    assert page["items"][0]["deadline"] and page["items"][0]["can_decide"]
    body = {"action": "reject", "reason": " ", "key": str(uuid4())}
    url = f"{root}/approval/{approval.id}/commands"
    assert (await client.post(url, json=body)).status_code == 422
    for _ in range(2):
        res = await client.post(url, json={**body, "reason": "No supporting evidence"})
        assert res.status_code == 200, res.text
    history = (
        await client.get(f"{root}/workspace?category=approval_request&status=resolved")
    ).json()
    assert history["items"][0]["history"][-1]["action"] == "change_order.rejected"


async def test_workspace_replays_override_and_conversion(client, test_session, user, queue):
    base, risk_id, _, _ = queue
    user.role = "owner"
    risk = await test_session.get(Risk, risk_id)
    risk.status, risk.risk_type = "open", "delay"
    await test_session.flush()
    url = f"{base}/review-queue/risk/{risk_id}/commands"
    override = {
        "action": "override",
        "reason": "Current schedule verified",
        "severity": "low",
        "key": str(uuid4()),
    }
    for _ in range(2):
        response = await client.post(url, json=override)
        assert response.status_code == 200, response.text
    accept = await client.post(
        url, json={"action": "accept", "key": str(uuid4()), "reason": "Page verified"}
    )
    assert accept.status_code == 200, accept.text
    convert = {"action": "convert_to_change_order", "reason": "Prepare draft", "key": str(uuid4())}
    draft = await client.post(url, json=convert)
    assert draft.status_code == 200, draft.text
    replay = await client.post(url, json=convert)
    assert replay.status_code == 200 and replay.json() == draft.json()
    page = await client.get(f"{base}/review-queue/workspace?status=converted_to_change_order")
    assert page.json()["items"][0]["change_order_id"] == draft.json()["change_order_id"]


async def test_bulk_note_is_atomic_and_tenant_scoped(client, test_session, user, queue):
    base, risk_id, task_id, _ = queue
    user.role = "owner"
    foreign = Tenant(name="Other", slug=f"other-{uuid4().hex}")
    test_session.add(foreign)
    await test_session.flush()
    project = Project(tenant_id=foreign.id, code="OTHER", name="Other")
    test_session.add(project)
    await test_session.flush()
    other_project = project.id
    root = f"{base}/review-queue"
    payload = {
        "key": str(uuid4()),
        "reason": "Verify signed documents",
        "targets": [
            {"kind": "extraction", "id": str(task_id)},
            {"kind": "risk", "id": str(uuid4())},
        ],
    }
    assert (await client.post(f"{root}/notes", json=payload)).status_code == 404
    assert (await client.get(f"{root}/workspace?category=low_confidence_extraction")).json()[
        "items"
    ][0]["history"] == []
    payload["targets"][1]["id"] = str(risk_id)
    for _ in range(2):
        response = await client.post(f"{root}/notes", json=payload)
        assert response.status_code == 204, response.text
    for item in (await client.get(f"{root}/workspace")).json()["items"]:
        assert [e["action"] for e in item["history"]] == ["review.add_note"]
    for suffix in ("workspace", "reviewers"):
        assert (
            await client.get(f"/api/v1/projects/{other_project}/review-queue/{suffix}")
        ).status_code == 404
    assert (
        await client.post(f"/api/v1/projects/{other_project}/review-queue/notes", json=payload)
    ).status_code == 404


def test_workspace_sort_limits_and_ranges():
    from app.domain.schemas.review_workspace import QueueFilters
    from app.domain.services.review_workspace import page_items

    now = datetime.now(UTC)
    items = [
        dict(
            id=i,
            kind="risk",
            severity=s,
            deadline=None,
            confidence=c,
            reviewable=True,
            categories=["high_severity_risk"],
            review_state="review_required",
            created_at=now,
        )
        for i, s, c in [(1, "medium", None), (2, "high", 0.4), (3, "critical", 0.9)]
    ]
    for field in ("severity", "confidence"):
        page = page_items(items, QueueFilters(sort=field, page=2, page_size=1, direction="desc"))
        assert page["total"] == 3 and page["items"][0]["id"] == 2
    page = page_items(
        items,
        QueueFilters(
            sort="deadline",
            min_confidence=0.3,
            max_confidence=0.5,
            created_from=now.date(),
            created_to=now.date(),
        ),
    )
    assert [i["id"] for i in page["items"]] == [2]


async def test_extraction_audit_is_immutable_in_postgres(client, test_session, user, queue):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    base, _, task, _ = queue
    user.role = "owner"
    url = f"{base}/review-queue/extraction/{task}/commands"
    assert (
        await client.post(
            url, json={"key": str(uuid4()), "action": "add_note", "reason": "Checked"}
        )
    ).status_code == 200
    connection = await test_session.connection()
    for statement in [
        "DELETE FROM audit_events WHERE entity_id=:id",
        "UPDATE audit_events SET details='{}'::jsonb WHERE entity_id=:id",
    ]:
        with pytest.raises(IntegrityError, match="review_audit_events_are_append_only"):
            async with connection.begin_nested():
                await connection.execute(text(statement), {"id": task})
