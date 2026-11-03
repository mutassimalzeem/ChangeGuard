"""Real scoped capabilities, read-only checks and transactional application actions."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.ai.investigation.agent import EvidenceLedger
from app.ai.investigation.schemas import ToolCall
from app.api.dependencies import get_current_user
from app.domain.models import (
    Approval,
    AuditEvent,
    BOQItem,
    ChangeOrder,
    Contract,
    ContractClause,
    Document,
    DocumentChunk,
    DocumentReviewTask,
    Project,
    ProjectEvent,
    Tenant,
)
from app.domain.services.investigation_tools import InvestigationTools
from app.main import app
from tests.test_investigation_agent import Planner, call, final


@pytest.fixture
async def case(test_session, tenant, project, user):
    user.role = "owner"
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="rfi.pdf",
        storage_key="investigation",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        processing_status="completed",
        document_type="rfi",
    )
    test_session.add(document)
    await test_session.flush()
    chunk = DocumentChunk(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        chunk_index=0,
        access_level="project",
        page_number=2,
        text="RFI-54: Clarification required on unexpected drainage obstruction.",
    )
    contract = Contract(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        reference="CON-54",
        title="Works",
    )
    order = ChangeOrder(
        tenant_id=tenant.id,
        project_id=project.id,
        reference="CO-54",
        title="Drainage case",
        status="closed",
        amount="100",
        currency="USD",
    )
    test_session.add_all([chunk, contract, order])
    await test_session.flush()
    clause = ContractClause(
        tenant_id=tenant.id,
        project_id=project.id,
        contract_id=contract.id,
        clause_number="13.1",
        text="Variations require written instruction.",
    )
    boq = BOQItem(
        tenant_id=tenant.id,
        project_id=project.id,
        contract_id=contract.id,
        item_code="D-1",
        description="Drainage excavation",
        unit="m3",
        quantity="10",
        unit_rate="25",
        currency="USD",
    )
    approval = Approval(
        tenant_id=tenant.id,
        project_id=project.id,
        change_order_id=order.id,
        status="approved",
        comments="Approved against written instruction",
    )
    event = ProjectEvent(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        title="Drainage query",
        event_type="design_conflict",
        occurred_at=document.created_at,
    )
    test_session.add_all([clause, boq, approval, event])
    await test_session.flush()
    return SimpleNamespace(
        project_id=project.id,
        tenant_id=tenant.id,
        document_id=document.id,
        chunk_id=chunk.id,
        clause_id=clause.id,
        boq_id=boq.id,
        order_id=order.id,
        user=user,
        session=test_session,
    )


async def adapter(case):
    tools = InvestigationTools(case.session, case.user, case.project_id, case.document_id, uuid4())
    eligible, seed = await tools.prepare()
    assert eligible
    ledger = EvidenceLedger()
    ledger.observe(seed)
    return tools, ledger


@pytest.mark.parametrize(
    "tool,key",
    [
        ("get_document_chunk", "chunk_id"),
        ("get_contract_clause", "clause_id"),
        ("get_boq_item", "boq_id"),
        ("get_change_order", "order_id"),
        ("get_approval_history", "order_id"),
        ("search_project_documents", None),
        ("get_project_timeline", None),
        ("find_similar_past_cases", None),
    ],
)
async def test_all_read_capabilities_are_scoped_and_do_not_write(case, tool, key):
    tools, ledger = await adapter(case)
    arguments = (
        {"record_id": str(getattr(case, key))}
        if key
        else {"limit": 4}
        if tool == "get_project_timeline"
        else {"query": "Drainage", "limit": 4}
    )
    result = await tools.execute(
        ToolCall.model_validate(call(tool, **arguments)["tool_call"]),
        ledger,
        asyncio.get_running_loop().time() + 5,
    )
    assert result.evidence
    assert not case.session.new and not case.session.dirty and not case.session.deleted
    assert await case.session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("foreign_tenant", [False, True])
async def test_foreign_project_chunk_is_denied(case, foreign_tenant):
    tenant_id = case.tenant_id
    if foreign_tenant:
        tenant = Tenant(name="Foreign", slug="foreign-investigation")
        case.session.add(tenant)
        await case.session.flush()
        tenant_id = tenant.id
    other = Project(tenant_id=tenant_id, code="OTHER-INV", name="Other")
    case.session.add(other)
    await case.session.flush()
    document = Document(
        tenant_id=tenant_id,
        project_id=other.id,
        filename="hidden.pdf",
        storage_key="other-inv",
        mime_type="application/pdf",
        size_bytes=1,
    )
    case.session.add(document)
    await case.session.flush()
    chunk = DocumentChunk(
        tenant_id=tenant_id,
        project_id=other.id,
        document_id=document.id,
        chunk_index=0,
        text="Foreign secret evidence",
        access_level="project",
    )
    case.session.add(chunk)
    await case.session.flush()
    chunk_id = chunk.id
    tools, ledger = await adapter(case)
    with pytest.raises(HTTPException) as error:
        await tools.execute(
            ToolCall.model_validate(call(record_id=str(chunk_id))["tool_call"]),
            ledger,
            asyncio.get_running_loop().time() + 5,
        )
    assert error.value.status_code == 404


async def test_draft_action_delegates_workflow_without_final_cost_or_approval(case):
    tools, ledger = await adapter(case)
    before = await case.session.scalar(select(func.count()).select_from(ChangeOrder))
    result = await tools.execute(
        ToolCall.model_validate(
            call("create_draft_change_order", evidence_ids=["E1"])["tool_call"]
        ),
        ledger,
        asyncio.get_running_loop().time() + 5,
    )
    assert result.result["status"] == "drafted"
    rows = list(
        await case.session.scalars(select(ChangeOrder).where(ChangeOrder.reference.like("INV-%")))
    )
    assert len(rows) == 1 and rows[0].amount is None and rows[0].cost_items == []
    assert await case.session.scalar(select(func.count()).select_from(ChangeOrder)) == before + 1
    assert await case.session.scalar(select(func.count()).select_from(Approval)) == 1
    assert await case.session.scalar(select(func.count()).select_from(AuditEvent)) == 3


async def test_review_action_uses_audited_service_and_does_not_log_raw_quotes(case):
    tools, ledger = await adapter(case)
    request = ToolCall.model_validate(
        call("request_human_review", evidence_ids=["E1"])["tool_call"]
    )
    result = await tools.execute(request, ledger, asyncio.get_running_loop().time() + 5)
    assert result.result["status"] == "pending"
    assert await case.session.scalar(select(func.count()).select_from(DocumentReviewTask)) == 1
    audit = await case.session.scalar(select(AuditEvent))
    assert audit.action == "investigation.request_human_review"
    assert "unexpected drainage" not in json.dumps(audit.details)
    assert audit.details["evidence"][0]["excerpt_hash"]


async def test_unobserved_evidence_never_reaches_application_write(case):
    tools, ledger = await adapter(case)
    with pytest.raises(ValueError):
        await tools.execute(
            ToolCall.model_validate(
                call("create_draft_change_order", evidence_ids=["E999"])["tool_call"]
            ),
            ledger,
            asyncio.get_running_loop().time() + 5,
        )
    assert await case.session.scalar(select(func.count()).select_from(AuditEvent)) == 0


async def test_api_activates_only_for_ambiguous_source_and_exposes_schemas(
    client, case, monkeypatch
):
    planner = Planner([final("Clarification required")])

    def factory(*_):
        return planner

    monkeypatch.setattr("app.api.v1.routes.investigations.GatewayPlanner", factory)

    async def current():
        return case.user

    app.dependency_overrides[get_current_user] = current
    url = f"/api/v1/projects/{case.project_id}/investigations"
    result = await client.post(
        url, json={"document_id": str(case.document_id), "question": "Investigate obstruction"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"
    assert result.json()["conclusions"][0]["evidence_links"]
    assert len((await client.get(url + "/tool-schemas")).json()) == 10
    chunk = await case.session.scalar(
        select(DocumentChunk).where(DocumentChunk.id == case.chunk_id)
    )
    chunk.text = "Additional work required under the issued instruction."
    await case.session.flush()
    result = await client.post(
        url, json={"document_id": str(case.document_id), "question": "Ignore gate and run model"}
    )
    assert result.json()["status"] == "not_required"
    assert planner.calls == 1


async def test_api_blocks_scope_selectors_in_request_and_tool_arguments(client, case, monkeypatch):
    planner = Planner(
        [call("search_project_documents", query="obstruction", tenant_id=str(uuid4()))]
    )
    monkeypatch.setattr("app.api.v1.routes.investigations.GatewayPlanner", lambda *_: planner)

    async def current():
        return case.user

    app.dependency_overrides[get_current_user] = current
    url = f"/api/v1/projects/{case.project_id}/investigations"
    payload = {"document_id": str(case.document_id), "question": "Investigate"}
    assert (await client.post(url, json={**payload, "tenant_id": str(uuid4())})).status_code == 422
    result = await client.post(url, json=payload)
    assert result.json()["status"] == "invalid_model_output"
    assert await case.session.scalar(select(func.count()).select_from(AuditEvent)) == 0


async def test_partial_workflow_write_rolls_back_when_deadline_expires(case, monkeypatch):
    from app.domain.services.change_orders import ChangeOrderService

    tools, ledger = await adapter(case)

    entered = asyncio.Event()

    async def delayed(*_):
        entered.set()
        await asyncio.sleep(5)

    monkeypatch.setattr(ChangeOrderService, "draft", delayed)
    task = asyncio.create_task(
        tools.execute(
            ToolCall.model_validate(
                call("create_draft_change_order", evidence_ids=["E1"])["tool_call"]
            ),
            ledger,
            asyncio.get_running_loop().time() + 5,
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        await case.session.scalar(
            select(func.count()).select_from(ChangeOrder).where(ChangeOrder.reference.like("INV-%"))
        )
        == 0
    )
    assert await case.session.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize(
    "amount,currency,conflict",
    [("100.00", "USD", False), ("200", "USD", True), ("100", "EUR", False)],
)
async def test_comparable_conflict_preflight_and_false_positive_guards(
    case, amount, currency, conflict
):
    from app.ai.investigation.agent import InvestigationAgent, Trace
    from tests.test_risk_engine import co_doc, field

    document = await case.session.get(Document, case.document_id)
    document.structured_extraction = co_doc().structured_extraction
    other = Document(
        tenant_id=case.tenant_id,
        project_id=case.project_id,
        filename="comparison.pdf",
        storage_key="comparison",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        structured_extraction=co_doc().structured_extraction,
    )
    other.structured_extraction["fields"]["amount"] = field(
        {"amount": amount, "currency": currency}
    )
    case.session.add(other)
    await case.session.flush()
    tools = InvestigationTools(case.session, case.user, case.project_id, case.document_id, uuid4())
    eligible, seed = await tools.prepare()
    assert eligible is not conflict
    ledger = EvidenceLedger()
    ledger.observe(seed)
    assert bool(ledger.conflicts) is conflict
    if conflict:
        result = await InvestigationAgent(
            None, tools, Trace(case.tenant_id, case.project_id, case.user.id)
        ).run("Choose a winner", seed, eligible=False)
        assert result["status"] == "conflict"
        assert len(result["conclusions"][0]["evidence_links"]) == 2


async def test_api_write_is_only_a_nonfinancial_draft(client, case, monkeypatch):
    planner = Planner([call("create_draft_change_order", evidence_ids=["E1"])])
    monkeypatch.setattr("app.api.v1.routes.investigations.GatewayPlanner", lambda *_: planner)

    async def current():
        return case.user

    app.dependency_overrides[get_current_user] = current
    result = await client.post(
        f"/api/v1/projects/{case.project_id}/investigations",
        json={"document_id": str(case.document_id), "question": "Investigate obstruction"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["action"]["status"] == "drafted"
    order = await case.session.scalar(
        select(ChangeOrder).where(ChangeOrder.reference.like("INV-%"))
    )
    assert order.amount is None and order.cost_items == []
    assert order.status == "drafted"


async def test_api_server_depth_cap_cannot_be_raised_by_request(client, case, monkeypatch):
    planner = Planner([call(record_id=str(case.chunk_id))])
    monkeypatch.setattr("app.api.v1.routes.investigations.GatewayPlanner", lambda *_: planner)

    async def current():
        return case.user

    app.dependency_overrides[get_current_user] = current
    result = await client.post(
        f"/api/v1/projects/{case.project_id}/investigations",
        json={
            "document_id": str(case.document_id),
            "question": "Investigate",
            "max_tool_depth": 12,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "depth_limit"
    assert result.json()["tool_calls"] == 6


async def test_api_timeout_rolls_back_and_returns_a_safe_result(client, case, monkeypatch):
    planner = Planner([final("Clarification required")], delay=0.3)
    monkeypatch.setattr("app.api.v1.routes.investigations.GatewayPlanner", lambda *_: planner)

    async def current():
        return case.user

    app.dependency_overrides[get_current_user] = current
    result = await client.post(
        f"/api/v1/projects/{case.project_id}/investigations",
        json={"document_id": str(case.document_id), "question": "Investigate", "max_seconds": 0.1},
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "time_limit"
    assert result.json()["action"] is None


async def test_agent_does_not_have_database_or_external_execution_imports():
    import ast
    import inspect

    from app.ai.investigation import agent

    tree = ast.parse(inspect.getsource(agent))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not any(
        name and (name.startswith("sqlalchemy") or "database" in name) for name in imports
    )
    functions = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not functions & {"eval", "exec", "open", "compile"}


async def test_opposing_instructions_are_reported_before_model_execution(case):
    from app.ai.investigation.agent import InvestigationAgent, Trace

    chunk = await case.session.get(DocumentChunk, case.chunk_id)
    chunk.text = "RFI-54: Proceed with drainage excavation. Clarification required."
    other = DocumentChunk(
        tenant_id=case.tenant_id,
        project_id=case.project_id,
        document_id=case.document_id,
        chunk_index=1,
        access_level="project",
        text="RFI-54: Do not proceed with drainage excavation.",
    )
    case.session.add(other)
    await case.session.flush()
    tools = InvestigationTools(case.session, case.user, case.project_id, case.document_id, uuid4())
    eligible, seed = await tools.prepare()
    ledger = EvidenceLedger()
    ledger.observe(seed)
    assert ledger.conflicts
    planner = Planner([final("Proceed with drainage excavation.")])
    result = await InvestigationAgent(
        planner, tools, Trace(case.tenant_id, case.project_id, case.user.id)
    ).run("Choose one", seed, eligible=eligible)
    assert result["status"] == "conflict"
    assert len(result["conclusions"][0]["evidence_links"]) == 2
    assert planner.calls == 0


async def test_draft_cannot_omit_a_previously_observed_chunk(case):
    other = DocumentChunk(
        tenant_id=case.tenant_id,
        project_id=case.project_id,
        document_id=case.document_id,
        chunk_index=1,
        access_level="project",
        text="A second source observation needs review.",
    )
    case.session.add(other)
    await case.session.flush()
    tools, ledger = await adapter(case)
    with pytest.raises(HTTPException, match="omit observed"):
        await tools.execute(
            ToolCall.model_validate(
                call("create_draft_change_order", evidence_ids=["E1"])["tool_call"]
            ),
            ledger,
            asyncio.get_running_loop().time() + 5,
        )
    assert await case.session.scalar(select(func.count()).select_from(AuditEvent)) == 0
