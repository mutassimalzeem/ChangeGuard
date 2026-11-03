"""Full HTTP workflows, deterministic financials and PDF/citation validation."""

import asyncio
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.api.dependencies import get_current_user
from app.core.database import ScopedAsyncSession, get_session
from app.domain.models import (
    AuditEvent,
    Document,
    DocumentChunk,
    EvidenceLink,
    Project,
    ProjectEvent,
    Tenant,
    User,
)
from app.domain.schemas.change_order import ChangeOrderPatch, CostItem, DecisionInput, SubmitInput
from app.domain.services.change_orders import (
    TRANSITIONS,
    calculate_cost,
    check_transition,
    validate_draft,
)
from app.main import app


@pytest.fixture
async def workflow(client, test_session, tenant, project, user, monkeypatch):
    user.role = "owner"
    reviewer = User(
        tenant_id=tenant.id,
        email="reviewer@example.com",
        full_name="Reviewer",
        password_hash="test",
        role="owner",
    )
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="instruction.pdf",
        storage_key="workflow-test",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        processing_status="completed",
    )
    test_session.add_all([reviewer, document])
    await test_session.flush()
    chunk = DocumentChunk(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        chunk_index=0,
        access_level="project",
        text=(
            "CO-53 Relocate drainage. The consultant instructed "
            "additional drainage work at grid B4."
        ),
        page_number=2,
    )
    test_session.add(chunk)
    await test_session.flush()
    state = SimpleNamespace(
        actor=user,
        creator=user,
        reviewer=reviewer,
        project_id=project.id,
        document_id=document.id,
        chunk_id=chunk.id,
        tenant_id=tenant.id,
        session=test_session,
        client=client,
    )

    async def scoped_session():
        async with ScopedAsyncSession(
            bind=test_session.bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
            autoflush=False,
        ) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def actor():
        return state.actor

    app.dependency_overrides[get_session] = scoped_session
    app.dependency_overrides[get_current_user] = actor
    monkeypatch.setattr(
        "app.domain.services.change_orders.get_settings",
        lambda: SimpleNamespace(llm_provider="openai", llm_api_key=None),
    )
    state.payload = {
        "reference": "CO-53",
        "title": "Relocate drainage",
        "currency": "USD",
        "description": "Consultant instruction for revised drainage route.",
        "time_impact_days": 2,
        "cost_items": [{"description": "Excavation", "quantity": "3", "unit_rate": "100.005"}],
        "evidence": [{"source_type": "document", "source_id": str(document.id)}],
    }
    return state


async def create(workflow):
    result = await workflow.client.post(
        f"/api/v1/projects/{workflow.project_id}/change-orders", json=workflow.payload
    )
    assert result.status_code == 201, result.text
    return "/api/v1/change-orders/" + result.json()["id"]


async def drafted(workflow):
    url = await create(workflow)
    result = await workflow.client.post(url + "/convert")
    assert result.status_code == 200, result.text
    result = await workflow.client.post(url + "/draft", json={"query": "CO-53"})
    assert result.status_code == 200, result.text
    assert result.json()["draft"]["paragraphs"][0]["citations"] == ["E1"]
    return url


async def submitted(workflow):
    url = await drafted(workflow)
    result = await workflow.client.post(url + "/submit", json={"cost_confirmed": True})
    assert result.status_code == 200, result.text
    return url


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_full_decision_workflow_and_pdf(workflow, decision):
    url = await submitted(workflow)
    workflow.actor = workflow.reviewer
    response = await workflow.client.post(
        url + "/" + decision, json={"reason": "Checked against signed instruction"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == {"approve": "approved", "reject": "rejected"}[decision]
    assert response.json()["amount"] == "300.02"
    assert response.json()["approval_history"][0]["reason"] == "Checked against signed instruction"
    response = await workflow.client.patch(
        url, json={"status": "closed", "reason": "Commercial review complete"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"
    exported = await workflow.client.post(url + "/export")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/pdf"
    pdf = PdfReader(BytesIO(exported.content))
    content = "\n".join(page.extract_text() for page in pdf.pages)
    for expected in (
        "CO-53",
        "300.02",
        "Evidence table",
        "E1",
        "Approval history",
        "Checked against signed instruction",
    ):
        assert expected in content
    order_id = UUID(url.rsplit("/", 1)[1])
    audits = list(
        await workflow.session.scalars(
            select(AuditEvent)
            .where(AuditEvent.entity_id == order_id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
    )
    transitions = {(row.details["from_status"], row.details["to_status"]) for row in audits}
    assert (None, "potential") in transitions
    assert ("potential", "under_review") in transitions
    assert ("under_review", "drafted") in transitions
    assert ("drafted", "submitted") in transitions
    assert len(audits) == 7
    assert all(row.actor_id and row.details["reason"] for row in audits)


async def test_dispute_then_close(workflow):
    url = await submitted(workflow)
    result = await workflow.client.patch(
        url, json={"status": "disputed", "reason": "Entitlement disputed"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["approval_history"][0]["status"] == "disputed"
    assert (
        await workflow.client.post(url + "/approve", json={"reason": "Too late"})
    ).status_code == 409
    assert (
        await workflow.client.patch(url, json={"status": "closed", "reason": "Dispute recorded"})
    ).status_code == 200


@pytest.mark.parametrize(
    "action,body",
    [
        ("approve", {"reason": "Reviewed"}),
        ("reject", {"reason": "Rejected"}),
        ("submit", {"cost_confirmed": True}),
        ("draft", {}),
    ],
)
async def test_cannot_skip_required_states(workflow, action, body):
    url = await create(workflow)
    assert (await workflow.client.post(url + "/" + action, json=body)).status_code == 409
    assert (await workflow.client.get(url)).json()["status"] == "potential"


@pytest.mark.parametrize("reason", [None, "", "   "])
@pytest.mark.parametrize("action", ["approve", "reject"])
async def test_decision_requires_nonblank_reason(workflow, action, reason):
    url = await submitted(workflow)
    workflow.actor = workflow.reviewer
    payload = {} if reason is None else {"reason": reason}
    assert (await workflow.client.post(url + "/" + action, json=payload)).status_code == 422
    assert (await workflow.client.get(url)).json()["status"] == "submitted"


async def test_self_approval_and_repeat_submission_blocked(workflow):
    url = await submitted(workflow)
    assert (
        await workflow.client.post(url + "/approve", json={"reason": "Self approval"})
    ).status_code == 403
    assert (
        await workflow.client.post(url + "/submit", json={"cost_confirmed": True})
    ).status_code == 409
    assert (
        await workflow.client.patch(url, json={"title": "Alter submitted record"})
    ).status_code == 409
    assert (
        await workflow.client.patch(url, json={"status": "approved", "reason": "Bypass"})
    ).status_code == 422


async def test_editing_invalidates_draft_and_requires_regeneration(workflow):
    url = await drafted(workflow)
    response = await workflow.client.patch(
        url,
        json={
            "cost_items": [{"description": "Measured work", "quantity": "2", "unit_rate": "125"}]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["draft"] is None
    assert response.json()["amount"] == "250.00"
    assert (
        await workflow.client.post(url + "/submit", json={"cost_confirmed": True})
    ).status_code == 422
    assert (await workflow.client.post(url + "/draft", json={"query": "CO-53"})).status_code == 200
    assert (
        await workflow.client.post(url + "/submit", json={"cost_confirmed": True})
    ).status_code == 200


async def test_missing_evidence_and_missing_costs_block_progress(workflow):
    workflow.payload["evidence"] = []
    workflow.payload["cost_items"] = []
    url = await create(workflow)
    assert (await workflow.client.post(url + "/convert")).status_code == 422


async def test_empty_retrieval_blocks_draft(workflow):
    url = await create(workflow)
    assert (await workflow.client.post(url + "/convert")).status_code == 200
    result = await workflow.client.post(
        url + "/draft", json={"query": "absolutelyunmatchedidentifier"}
    )
    assert result.status_code == 422, result.text
    assert (await workflow.client.get(url)).json()["status"] == "under_review"


async def test_changed_source_blocks_submission(workflow):
    url = await drafted(workflow)
    chunk = await workflow.session.get(DocumentChunk, workflow.chunk_id)
    chunk.text = "Different content"
    await workflow.session.flush()
    assert (
        await workflow.client.post(url + "/submit", json={"cost_confirmed": True})
    ).status_code == 422


async def test_source_visibility_is_rechecked(workflow):
    url = await drafted(workflow)
    document = await workflow.session.get(Document, workflow.document_id)
    document.deleted_at = document.created_at
    await workflow.session.flush()
    assert (await workflow.client.get(url)).status_code == 404
    assert (await workflow.client.post(url + "/export")).status_code == 404


async def test_duplicate_reference_and_financial_input_bypass(workflow):
    url = await create(workflow)
    duplicate = await workflow.client.post(
        f"/api/v1/projects/{workflow.project_id}/change-orders", json=workflow.payload
    )
    assert duplicate.status_code == 409
    assert (await workflow.client.patch(url, json={"amount": "999999"})).status_code == 422


async def test_unauthorized_roles_and_foreign_project_evidence(workflow):
    other = Project(tenant_id=workflow.tenant_id, code="OTHER-WF", name="Other")
    workflow.session.add(other)
    await workflow.session.flush()
    payload = dict(workflow.payload)
    assert (
        await workflow.client.post(f"/api/v1/projects/{other.id}/change-orders", json=payload)
    ).status_code == 404
    url = await create(workflow)
    workflow.actor = User(id=uuid4(), tenant_id=workflow.tenant_id, role="viewer")
    assert (await workflow.client.get(url)).status_code == 403


async def test_order_audit_cannot_be_modified(workflow):
    await create(workflow)
    with pytest.raises(DBAPIError):
        async with workflow.session.begin_nested():
            await workflow.session.execute(
                text("UPDATE audit_events SET action='tampered' WHERE entity_type='change_order'")
            )


@pytest.mark.parametrize("current", list(TRANSITIONS))
@pytest.mark.parametrize("target", list(TRANSITIONS))
def test_exhaustive_transition_matrix(current, target):
    if target in TRANSITIONS[current]:
        check_transition(current, target)
    else:
        with pytest.raises(HTTPException):
            check_transition(current, target)


def test_exact_costs_credits_and_rounding():
    items = [
        CostItem(description="A", quantity="3", unit_rate="100.005"),
        CostItem(description="Credit", quantity="1", unit_rate="-0.01"),
    ]
    assert calculate_cost(items) == Decimal("300.01")
    assert calculate_cost([]) is None
    with pytest.raises(HTTPException):
        calculate_cost(
            [
                CostItem(
                    description="Overflow", quantity="999999999999999", unit_rate="999999999999999"
                )
            ]
        )


@pytest.mark.parametrize(
    "data",
    [
        {"paragraphs": [{"text": "Supported", "citations": ["E999"]}]},
        {"paragraphs": [{"text": "Unsupported", "citations": []}]},
        {"paragraphs": [{"text": "Final cost USD 9999", "citations": ["E1"]}]},
        {"paragraphs": [{"text": "Supported", "citations": ["E1"]}], "amount": "999"},
    ],
)
def test_model_cannot_invent_citations_or_supply_final_cost(data):
    with pytest.raises(ValueError):
        validate_draft(data, {"E1": {}})


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_cost_confirmation_is_explicit(value):
    with pytest.raises(ValueError):
        SubmitInput(cost_confirmed=value)


def test_patch_cannot_combine_status_and_edit_or_omit_reason():
    with pytest.raises(ValueError):
        ChangeOrderPatch(status="closed")
    with pytest.raises(ValueError):
        ChangeOrderPatch(status="closed", title="Changed", reason="Review")
    with pytest.raises(ValueError):
        DecisionInput(reason=" ")


async def test_conversion_preserves_evidence_not_suggested_cost(workflow):
    from datetime import UTC, datetime

    event = ProjectEvent(
        tenant_id=workflow.tenant_id,
        project_id=workflow.project_id,
        document_id=workflow.document_id,
        title="Potential relocation",
        event_type="additional_work",
        status="potential_change",
        detection_key="wf-source",
        occurred_at=datetime.now(UTC),
        suggested_cost_impact=Decimal("9999"),
    )
    workflow.session.add(event)
    await workflow.session.flush()
    workflow.session.add(
        EvidenceLink(
            tenant_id=workflow.tenant_id,
            project_id=workflow.project_id,
            subject_type="project_event",
            subject_id=event.id,
            source_type="document",
            source_id=workflow.document_id,
        )
    )
    await workflow.session.flush()
    workflow.payload.update(source_event_id=str(event.id), cost_items=[], evidence=[])
    url = await create(workflow)
    row = (await workflow.client.get(url)).json()
    assert row["amount"] is None
    assert len(row["evidence_links"]) == 1
    assert (await workflow.client.post(url + "/convert")).status_code == 200
    workflow.payload["reference"] = "CO-54"
    duplicate = await workflow.client.post(
        f"/api/v1/projects/{workflow.project_id}/change-orders", json=workflow.payload
    )
    assert duplicate.status_code == 409


@pytest.mark.parametrize("valid", [True, False])
async def test_model_draft_preserves_cost_and_checks_citations(workflow, monkeypatch, valid):
    gateway = Mock()
    gateway.generate.return_value = SimpleNamespace(
        value={
            "paragraphs": [
                {
                    "text": "The consultant instructed relocation.",
                    "citations": ["E1" if valid else "E999"],
                }
            ]
        }
    )
    monkeypatch.setattr(
        "app.domain.services.change_orders.get_settings",
        lambda: SimpleNamespace(llm_provider="openai", llm_api_key="test"),
    )
    monkeypatch.setattr("app.domain.services.change_orders.ModelGateway", lambda **_: gateway)
    url = await create(workflow)
    assert (await workflow.client.post(url + "/convert")).status_code == 200
    response = await workflow.client.post(url + "/draft", json={"query": "CO-53"})
    assert response.status_code == (200 if valid else 422), response.text
    row = (await workflow.client.get(url)).json()
    assert row["amount"] == "300.02"
    assert row["status"] == ("drafted" if valid else "under_review")
    gateway.generate.assert_called_once()
    assert "validator" in gateway.generate.call_args.kwargs


async def test_missing_cost_items_cannot_be_submitted(workflow):
    workflow.payload["cost_items"] = []
    url = await drafted(workflow)
    assert (
        await workflow.client.post(url + "/submit", json={"cost_confirmed": True})
    ).status_code == 422


async def test_database_rejects_skipped_state_transition(workflow):
    url = await create(workflow)
    with pytest.raises(DBAPIError, match="invalid_change_order_transition"):
        async with workflow.session.begin_nested():
            await workflow.session.execute(
                text("UPDATE change_orders SET status='approved' WHERE id=:id"),
                {"id": UUID(url.rsplit("/", 1)[1])},
            )


async def test_audit_failure_rolls_back_decision_and_approval(workflow):
    url = await submitted(workflow)
    workflow.actor = workflow.reviewer
    await workflow.session.execute(
        text(
            "ALTER TABLE audit_events ADD CONSTRAINT wf_fail_audit "
            "CHECK (action <> 'change_order.approved')"
        )
    )
    with pytest.raises(DBAPIError):
        await workflow.client.post(url + "/approve", json={"reason": "Reviewed"})
    row = (await workflow.client.get(url)).json()
    assert row["status"] == "submitted"
    assert row["approval_history"][0]["status"] == "pending"


async def test_concurrent_decisions_have_one_winner(test_engine, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(
        test_engine, class_=ScopedAsyncSession, expire_on_commit=False, autoflush=False
    )
    async with factory() as session:
        tenant = Tenant(name="Concurrent workflow", slug="workflow-" + uuid4().hex)
        session.add(tenant)
        await session.flush()
        creator = User(
            tenant_id=tenant.id,
            email="creator@example.com",
            full_name="Creator",
            password_hash="test",
            role="owner",
        )
        reviewer = User(
            tenant_id=tenant.id,
            email="approver@example.com",
            full_name="Approver",
            password_hash="test",
            role="owner",
        )
        project = Project(tenant_id=tenant.id, code="CONCURRENT", name="Concurrent")
        session.add_all([creator, reviewer, project])
        await session.flush()
        document = Document(
            tenant_id=tenant.id,
            project_id=project.id,
            filename="concurrent.pdf",
            storage_key="concurrent",
            mime_type="application/pdf",
            size_bytes=1,
            status="linked",
        )
        session.add(document)
        await session.flush()
        session.add(
            DocumentChunk(
                tenant_id=tenant.id,
                project_id=project.id,
                document_id=document.id,
                chunk_index=0,
                text="CO-RACE Consultant instructed drainage relocation.",
            )
        )
        await session.commit()
    state = SimpleNamespace(actor=creator)

    async def scoped_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def actor():
        return state.actor

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = scoped_session
    app.dependency_overrides[get_current_user] = actor
    monkeypatch.setattr(
        "app.domain.services.change_orders.get_settings",
        lambda: SimpleNamespace(llm_provider="openai", llm_api_key=None),
    )
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/projects/{project.id}/change-orders",
                json={
                    "reference": "CO-RACE",
                    "title": "Drainage relocation",
                    "currency": "USD",
                    "cost_items": [{"description": "Work", "quantity": "1", "unit_rate": "100"}],
                    "evidence": [{"source_type": "document", "source_id": str(document.id)}],
                },
            )
            assert response.status_code == 201, response.text
            url = "/api/v1/change-orders/" + response.json()["id"]
            assert (await client.post(url + "/convert")).status_code == 200
            assert (await client.post(url + "/draft", json={"query": "CO-RACE"})).status_code == 200
            assert (
                await client.post(url + "/submit", json={"cost_confirmed": True})
            ).status_code == 200
            state.actor = reviewer
            results = await asyncio.gather(
                client.post(url + "/approve", json={"reason": "Approved by reviewer"}),
                client.post(url + "/reject", json={"reason": "Rejected by reviewer"}),
            )
            assert sorted(response.status_code for response in results) == [200, 409]
            result = (await client.get(url)).json()
            assert len(result["approval_history"]) == 1
            assert result["approval_history"][0]["status"] in {"approved", "rejected"}
        async with factory() as session:
            events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == UUID(url.rsplit("/", 1)[1]),
                        AuditEvent.action.in_(["change_order.approved", "change_order.rejected"]),
                    )
                )
            )
            assert len(events) == 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def test_long_pdf_table_paginates_and_escapes_source_text(workflow):
    chunk = await workflow.session.get(DocumentChunk, workflow.chunk_id)
    chunk.text = "CO-53 Relocate drainage. " + "Evidence <angle> & quotation. " * 300
    await workflow.session.flush()
    url = await drafted(workflow)
    result = await workflow.client.post(url + "/export")
    assert result.status_code == 200, result.text
    pdf = PdfReader(BytesIO(result.content))
    assert len(pdf.pages) > 1
    assert "<angle>" in "\n".join(page.extract_text() for page in pdf.pages)


async def test_regeneration_creates_new_evidence_quote_without_overwriting_history(workflow):
    url = await drafted(workflow)
    previous = (await workflow.client.get(url)).json()["draft"]["sources"]["E1"]
    chunk = await workflow.session.get(DocumentChunk, workflow.chunk_id)
    chunk.text = "CO-53 Relocate drainage. Revised instruction confirms the east drainage route."
    await workflow.session.flush()
    response = await workflow.client.post(url + "/draft", json={"query": "CO-53"})
    assert response.status_code == 200, response.text
    current = response.json()["draft"]["sources"]["E1"]
    assert current["evidence_link_id"] != previous["evidence_link_id"]
    old = await workflow.session.get(EvidenceLink, UUID(previous["evidence_link_id"]))
    new = await workflow.session.get(EvidenceLink, UUID(current["evidence_link_id"]))
    assert old.source_text_snippet == previous["text"]
    assert new.source_text_snippet == current["text"] == chunk.text
    assert (await workflow.client.post(url + "/export")).status_code == 200


async def test_cross_tenant_order_is_hidden(workflow):
    url = await create(workflow)
    tenant = Tenant(name="Foreign", slug="foreign-workflow")
    workflow.session.add(tenant)
    await workflow.session.flush()
    foreign = User(
        tenant_id=tenant.id,
        email="foreign@example.com",
        full_name="Foreign",
        password_hash="test",
        role="owner",
    )
    workflow.session.add(foreign)
    await workflow.session.flush()
    workflow.actor = foreign
    assert (await workflow.client.get(url)).status_code == 404


@pytest.mark.parametrize("restricted", [True, False])
async def test_commercial_reviewer_requires_membership_and_visible_evidence(workflow, restricted):
    from app.domain.models import ProjectMembership

    url = await submitted(workflow)
    workflow.reviewer.role = "commercial_manager"
    workflow.session.add(
        ProjectMembership(
            tenant_id=workflow.tenant_id,
            project_id=workflow.project_id,
            user_id=workflow.reviewer.id,
        )
    )
    document = await workflow.session.get(Document, workflow.document_id)
    if restricted:
        document.access_level = "restricted"
    await workflow.session.flush()
    workflow.actor = workflow.reviewer
    result = await workflow.client.post(
        url + "/approve", json={"reason": "Commercial review complete"}
    )
    assert result.status_code == (404 if restricted else 200), result.text
