"""PostgreSQL persistence, replay, evidence visibility and audited human decisions."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.api.dependencies import get_current_user
from app.domain.models import AuditEvent, Document, EvidenceLink, Project, Risk
from app.domain.services.risk_engine import run_risk_checks
from app.domain.services.risks import RiskDecision, RiskService
from app.main import app
from app.policy.scope import bind_scope
from tests.test_risk_engine import co_doc


@pytest.fixture
async def risks_setup(test_session, tenant, project, user):
    user.role = "owner"
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="co.pdf",
        storage_key="risk-test",
        mime_type="application/pdf",
        size_bytes=1,
    )
    risk = Risk(
        tenant_id=tenant.id,
        project_id=project.id,
        title="Test risk",
        risk_type="schedule_impact_signal",
        schedule_impact_days=3,
        exposure_amount=None,
        confidence="1",
        severity="medium",
        status="open",
    )
    test_session.add_all([document, risk])
    await test_session.flush()
    link = EvidenceLink(
        tenant_id=tenant.id,
        project_id=project.id,
        subject_type="risk",
        subject_id=risk.id,
        source_type="document",
        source_id=document.id,
    )
    test_session.add(link)
    await test_session.flush()
    return document.id, risk.id


@pytest.mark.parametrize(
    "action,changes,status",
    [
        ("accept", {}, "accepted"),
        ("dismiss", {}, "dismissed"),
        ("override", {"severity": "high", "schedule_impact_days": 8}, "overridden"),
    ],
)
async def test_decisions_are_atomic_and_audited(
    test_session, project, user, risks_setup, action, changes, status
):
    project_id = project.id
    _, risk_id = risks_setup
    project_id = project.id
    bind_scope(test_session, user)
    result = await RiskService(test_session, user).decide(
        project_id,
        risk_id,
        RiskDecision(action=action, reason=" Reviewed source records ", **changes),
        "request-123",
    )
    assert result["status"] == status
    audit = await test_session.scalar(select(AuditEvent).where(AuditEvent.entity_id == risk_id))
    assert audit.action == f"risk.{action}"
    assert audit.details["reason"] == "Reviewed source records"
    assert audit.details["before"]["schedule_impact_days"] == 3
    assert audit.details["after"]["status"] == status
    assert audit.request_id == "request-123"
    assert audit.actor_id == user.id


async def test_audit_failure_rolls_back_risk_change(test_session, project, user, risks_setup):
    project_id = project.id
    _, risk_id = risks_setup
    with pytest.raises(DBAPIError):
        async with test_session.begin_nested():
            await RiskService(test_session, user).decide(
                project_id,
                risk_id,
                RiskDecision(action="override", reason="Review", severity="high"),
                "x" * 65,
            )
    row = await test_session.scalar(select(Risk).where(Risk.id == risk_id))
    assert row.status == "open"
    assert row.severity == "medium"
    assert (
        await test_session.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == risk_id))
        is None
    )


async def test_no_evidence_cannot_be_accepted(test_session, tenant, project, user):
    project_id = project.id
    user.role = "owner"
    row = Risk(tenant_id=tenant.id, project_id=project_id, title="Unsupported")
    test_session.add(row)
    await test_session.flush()
    row_id = row.id
    service = RiskService(test_session, user)
    assert (await service.read(project_id, row_id))["status"] == "insufficient_evidence"
    with pytest.raises(HTTPException, match="insufficient_evidence"):
        await service.decide(project_id, row_id, RiskDecision(action="accept", reason="Review"))


async def test_restricted_or_deleted_source_hides_whole_risk(
    test_session, project, user, risks_setup
):
    project_id = project.id
    document_id, risk_id = risks_setup
    document = await test_session.get(Document, document_id)
    document.access_level = "restricted"
    await test_session.flush()
    user.role = "commercial_manager"
    from app.domain.models import ProjectMembership

    test_session.add(
        ProjectMembership(tenant_id=user.tenant_id, project_id=project_id, user_id=user.id)
    )
    await test_session.flush()
    # Service-level source checking also protects callers without a bound ORM scope.
    with pytest.raises(HTTPException) as error:
        await RiskService(test_session, user).read(project_id, risk_id)
    assert error.value.status_code == 404


async def test_other_project_risk_is_not_visible(test_session, tenant, project, user, risks_setup):
    _, risk_id = risks_setup
    other = Project(tenant_id=tenant.id, code="OTHER", name="Other")
    test_session.add(other)
    await test_session.flush()
    other_id = other.id
    with pytest.raises(HTTPException) as error:
        await RiskService(test_session, user).read(other_id, risk_id)
    assert error.value.status_code == 404


async def test_viewer_cannot_decide(test_session, project, user, risks_setup):
    project_id = project.id
    _, risk_id = risks_setup
    user.role = "viewer"
    with pytest.raises(HTTPException) as error:
        await RiskService(test_session, user).decide(
            project_id, risk_id, RiskDecision(action="dismiss", reason="Review")
        )
    assert error.value.status_code == 403


async def test_api_reason_contract_and_financial_access(
    client, test_session, project, user, risks_setup
):
    project_id = project.id
    _, risk_id = risks_setup
    url = f"/api/v1/projects/{project_id}/risks/{risk_id}"

    async def current():
        return user

    app.dependency_overrides[get_current_user] = current
    try:
        response = await client.get(url)
        assert response.status_code == 200
        assert set(response.json()) >= {
            "risk_type",
            "severity",
            "title",
            "description",
            "financial_exposure",
            "schedule_impact_days",
            "responsible_party",
            "evidence_links",
            "recommended_action",
            "confidence",
            "status",
        }
        assert (
            await client.post(url + "/decisions", json={"action": "dismiss", "reason": " "})
        ).status_code == 422
        assert (
            await client.post(url + "/decisions", json={"action": "accept", "reason": "Reviewed"})
        ).status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def test_risk_engine_idempotency_preserves_review(test_session, tenant, project, user):
    project_id = project.id
    from app.domain.models import Approval, ChangeOrder, DocumentEntityLink

    document = Document(
        tenant_id=tenant.id,
        project_id=project_id,
        filename="co.pdf",
        storage_key="risk-replay",
        mime_type="application/pdf",
        size_bytes=1,
        structured_extraction=co_doc().structured_extraction,
    )
    change = ChangeOrder(
        tenant_id=tenant.id,
        project_id=project_id,
        reference="CO-1",
        title="Work",
        status="submitted",
        amount=Decimal("101.25"),
        currency="USD",
        time_impact_days=5,
    )
    test_session.add_all([document, change])
    await test_session.flush()
    test_session.add_all(
        [
            DocumentEntityLink(
                tenant_id=tenant.id,
                project_id=project_id,
                document_id=document.id,
                change_order_id=change.id,
            ),
            Approval(
                tenant_id=tenant.id,
                project_id=project_id,
                change_order_id=change.id,
                status="pending",
                due_at=document.created_at - timedelta(days=1),
            ),
        ]
    )
    await test_session.flush()
    ids = await run_risk_checks(document, test_session)
    assert len(ids) == 2
    await test_session.flush()
    row = await test_session.get(Risk, UUID(ids[0]))
    row.status = "dismissed"
    await test_session.flush()
    assert ids == await run_risk_checks(document, test_session)
    assert row.status == "dismissed"
    assert len(list(await test_session.scalars(select(EvidenceLink)))) == 2


async def test_audit_is_append_only(test_session, project, user, risks_setup):
    project_id = project.id
    _, risk_id = risks_setup
    await RiskService(test_session, user).decide(
        project_id, risk_id, RiskDecision(action="dismiss", reason="Review")
    )
    with pytest.raises(DBAPIError):
        async with test_session.begin_nested():
            await (await test_session.connection()).execute(
                text("UPDATE audit_events SET action='tampered'")
            )


async def test_deleted_source_hides_risk_from_list(test_session, project, user, risks_setup):
    project_id = project.id
    document_id, risk_id = risks_setup
    document = await test_session.get(Document, document_id)
    document.deleted_at = document.created_at
    await test_session.flush()
    service = RiskService(test_session, user)
    assert await service.list(project_id) == []
    with pytest.raises(HTTPException) as error:
        await service.read(project_id, risk_id)
    assert error.value.status_code == 404


async def test_cross_tenant_risk_is_hidden(test_session, project, user, risks_setup):
    from app.domain.models import Tenant

    project_id = project.id
    other_tenant = Tenant(name="Other", slug="other-risk-tenant")
    test_session.add(other_tenant)
    await test_session.flush()
    other_project = Project(tenant_id=other_tenant.id, code="OTHER", name="Other")
    test_session.add(other_project)
    await test_session.flush()
    risk = Risk(tenant_id=other_tenant.id, project_id=other_project.id, title="Other tenant")
    test_session.add(risk)
    await test_session.flush()
    risk_id = risk.id
    with pytest.raises(HTTPException) as error:
        await RiskService(test_session, user).read(project_id, risk_id)
    assert error.value.status_code == 404


async def test_direct_override_cannot_bypass_review(test_session, project, user, risks_setup):
    from app.api.exceptions import AuthorizationError

    _, risk_id = risks_setup
    bind_scope(test_session, user)
    risk = await test_session.scalar(select(Risk).where(Risk.id == risk_id))
    with pytest.raises(AuthorizationError, match="audited human review"):
        async with test_session.begin_nested():
            risk.severity = "critical"
            await test_session.flush()
