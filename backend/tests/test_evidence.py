"""Real PostgreSQL integrity and API tests for grounded, immutable evidence."""

# Fixture arguments and HTTP status assertions keep integration cases explicit.
# ruff: noqa: PLR0913, PLR0917, PLR2004
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.api.dependencies import get_current_user
from app.domain.models import (
    AIAnswer,
    BOQItem,
    ChangeOrder,
    Claim,
    Contract,
    ContractClause,
    Document,
    DocumentChunk,
    EvidenceLink,
    Project,
    ProjectEvent,
    ProjectMembership,
    Risk,
    SitePhoto,
)
from app.domain.schemas.evidence import EvidenceCreate
from app.domain.services.evidence import EvidenceService
from app.main import app
from app.policy.scope import bind_scope
from tests.conftest import migration_config


@pytest.fixture
async def evidence_setup(test_session, tenant, project, user):
    user.role = "owner"
    doc = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="notice.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
    )
    risk = Risk(tenant_id=tenant.id, project_id=project.id, title="Delay")
    test_session.add_all([doc, risk])
    await test_session.flush()

    bind_scope(test_session, user)
    for model in (Project, Document, Risk):
        await test_session.scalars(select(model))
    return doc, risk


@pytest.mark.parametrize("ai_generated,verified", [(True, False), (True, True), (False, True)])
async def test_unsupported_claim_cannot_be_saved_by_service(
    test_session, project, user, evidence_setup, ai_generated, verified
):
    service = EvidenceService(test_session, user)
    with pytest.raises(HTTPException, match="insufficient_evidence"):
        await service.save_claim(
            project.id, "Unsupported", [], ai_generated=ai_generated, verified=verified
        )
    assert await test_session.scalar(select(Claim.id)) is None


@pytest.mark.parametrize(
    "ai_generated,status", [(True, "draft"), (True, "verified"), (False, "verified")]
)
async def test_direct_sql_cannot_save_unsupported_claim(
    test_session, tenant, project, ai_generated, status
):
    with pytest.raises(DBAPIError, match="insufficient_evidence"):
        async with test_session.begin_nested():
            await (await test_session.connection()).execute(
                text(
                    "INSERT INTO claims (tenant_id,project_id,text,ai_generated,status) VALUES "
                    "(:t,:p,'Unsupported',:ai,:status)"
                ),
                {"t": tenant.id, "p": project.id, "ai": ai_generated, "status": status},
            )
            await (await test_session.connection()).execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_supported_claim_and_answer_are_saved(test_session, project, user, evidence_setup):
    doc, _ = evidence_setup
    service = EvidenceService(test_session, user)
    source = EvidenceCreate(
        source_type="document", source_id=doc.id, source_page=2, confidence="0.9"
    )
    claim = await service.save_claim(project.id, "Grounded", [source], verified=True)
    assert claim.status == "verified"
    answer = await service.save_answer(project.id, [("Grounded answer", [source])])
    result = await service.view(project.id, "ai_answer", answer["answer"].id)
    assert result.status == "supported"
    assert result.evidence[0].source_page == 2
    # Exercise deferred database checks using the underlying trusted connection.
    connection = await test_session.connection()
    await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_partial_answer_is_rejected_without_saving(
    test_session, project, user, evidence_setup
):
    doc, _ = evidence_setup
    service = EvidenceService(test_session, user)
    result = await service.save_answer(
        project.id,
        [
            ("Supported", [EvidenceCreate(source_type="document", source_id=doc.id)]),
            ("Invented", []),
        ],
    )
    assert result == {"status": "insufficient_evidence", "answer": None}
    assert await test_session.scalar(select(AIAnswer.id)) is None
    assert await test_session.scalar(select(Claim.id)) is None


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE evidence_links SET confidence=0.5",
        "DELETE FROM evidence_links",
        "TRUNCATE evidence_links",
    ],
)
async def test_links_are_append_only_even_in_sql(
    test_session, tenant, project, user, evidence_setup, statement
):
    doc, risk = evidence_setup
    test_session.add(
        EvidenceLink(
            tenant_id=tenant.id,
            project_id=project.id,
            subject_type="risk",
            subject_id=risk.id,
            source_type="document",
            source_id=doc.id,
        )
    )
    await test_session.flush()
    with pytest.raises(DBAPIError, match="append_only"):
        async with test_session.begin_nested():
            await (await test_session.connection()).execute(text(statement))


async def test_referenced_source_cannot_be_deleted(test_session, tenant, project, evidence_setup):
    doc, risk = evidence_setup
    test_session.add(
        EvidenceLink(
            tenant_id=tenant.id,
            project_id=project.id,
            subject_type="risk",
            subject_id=risk.id,
            source_type="document",
            source_id=doc.id,
        )
    )
    await test_session.flush()
    with pytest.raises(DBAPIError, match="referenced_evidence_record"):
        async with test_session.begin_nested():
            await (await test_session.connection()).execute(
                text("DELETE FROM documents WHERE id=:id"), {"id": doc.id}
            )


async def test_cross_project_source_rejected(test_session, tenant, project, evidence_setup):
    doc, _risk = evidence_setup
    other = Project(tenant_id=tenant.id, code="OTHER", name="Other")
    test_session.add(other)
    await test_session.flush()
    other_risk = Risk(tenant_id=tenant.id, project_id=other.id, title="Other")
    test_session.add(other_risk)
    await test_session.flush()
    with pytest.raises(DBAPIError, match="invalid_evidence_source"):
        async with test_session.begin_nested():
            test_session.add(
                EvidenceLink(
                    tenant_id=tenant.id,
                    project_id=other.id,
                    subject_type="risk",
                    subject_id=other_risk.id,
                    source_type="document",
                    source_id=doc.id,
                )
            )
            await test_session.flush()


async def test_api_evidence_and_insufficient_result(
    client, test_session, project, user, evidence_setup
):
    doc, risk = evidence_setup
    app.dependency_overrides[get_current_user] = lambda: user
    url = f"/api/v1/projects/{project.id}/evidence/risk/{risk.id}"
    response = await client.get(url)
    assert response.status_code == 200
    assert response.json() == {"status": "insufficient_evidence", "evidence": []}
    response = await client.post(
        url,
        json=[
            {
                "source_type": "document",
                "source_id": str(doc.id),
                "source_text_snippet": "Notice issued",
            }
        ],
    )
    assert response.status_code == 201, response.text
    assert response.json()[0]["created_by"] == str(user.id)
    response = await client.get(url)
    assert response.json()["status"] == "supported"
    assert response.json()["evidence"][0]["evidence_link_id"]
    assert (await client.patch(url, json={})).status_code == 405
    assert (await client.delete(url)).status_code == 405


async def test_restricted_source_snippet_is_hidden(
    test_session, tenant, project, user, evidence_setup
):

    doc, risk = evidence_setup
    test_session.info.pop("access_principal", None)
    doc.access_level = "restricted"
    user.role = "viewer"
    test_session.add(ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    test_session.add(
        EvidenceLink(
            tenant_id=tenant.id,
            project_id=project.id,
            subject_type="risk",
            subject_id=risk.id,
            source_type="document",
            source_id=doc.id,
            source_text_snippet="Secret",
        )
    )
    await test_session.flush()
    project_id, risk_id = project.id, risk.id
    result = await EvidenceService(test_session, user).view(project_id, "risk", risk_id)
    assert result.status == "insufficient_evidence"
    assert result.evidence == []


async def test_api_conceals_foreign_project(client, user, evidence_setup):
    app.dependency_overrides[get_current_user] = lambda: user
    response = await client.get(f"/api/v1/projects/{uuid4()}/evidence/risk/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "subject_type", ["claim", "risk", "project_event", "change_order", "ai_answer"]
)
@pytest.mark.parametrize(
    "source_type",
    ["document", "document_chunk", "site_photo", "project_event", "boq_item", "contract_clause"],
)
async def test_all_subject_source_pairs(test_session, tenant, project, subject_type, source_type):

    ownership = {"tenant_id": tenant.id, "project_id": project.id}
    doc = Document(
        **ownership,
        filename="test.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
    )
    contract = Contract(**ownership, reference="C1", title="Contract")
    event = ProjectEvent(
        **ownership, title="Instruction", event_type="instruction", occurred_at=datetime.now(UTC)
    )
    test_session.add_all([doc, contract, event])
    await test_session.flush()
    sources = {
        "document": doc,
        "project_event": event,
        "document_chunk": DocumentChunk(
            **ownership, document_id=doc.id, chunk_index=0, text="Notice"
        ),
        "site_photo": SitePhoto(**ownership, document_id=doc.id),
        "boq_item": BOQItem(
            **ownership, item_code="1", description="Concrete", unit="m3", quantity=1, unit_rate=1
        ),
        "contract_clause": ContractClause(
            **ownership, contract_id=contract.id, clause_number="1", text="Notify"
        ),
    }
    subjects = {
        "claim": Claim(**ownership, text="Fact", ai_generated=True, status="verified"),
        "risk": Risk(**ownership, title="Delay"),
        "project_event": event,
        "change_order": ChangeOrder(**ownership, reference="CO1", title="Change"),
        "ai_answer": AIAnswer(**ownership, text="Fact", status="supported"),
    }
    subject, source = subjects[subject_type], sources[source_type]
    test_session.add_all([subject, source])
    await test_session.flush()
    test_session.add(
        EvidenceLink(
            **ownership,
            subject_type=subject_type,
            subject_id=subject.id,
            source_type=source_type,
            source_id=source.id,
        )
    )
    await test_session.flush()
    await test_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_verified_transition_without_evidence_fails(test_session, tenant, project):
    claim = Claim(tenant_id=tenant.id, project_id=project.id, text="Unverified", ai_generated=False)
    test_session.add(claim)
    await test_session.flush()
    with pytest.raises(DBAPIError, match="insufficient_evidence"):
        async with test_session.begin_nested():
            claim.status = "verified"
            await test_session.flush()
            await test_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_legacy_evidence_is_backfilled(test_engine):

    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(
                lambda conn: command.downgrade(migration_config(conn), "0008_structured_extraction")
            )
            ids = {key: uuid4() for key in ["tenant", "project", "document", "risk", "link"]}
            await connection.execute(
                text(
                    "INSERT INTO tenants (id,name,slug) "
                    "VALUES (:tenant,'Legacy',cast(cast(:tenant AS "
                    "uuid) AS text))"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "INSERT INTO projects (id,tenant_id,code,name) VALUES "
                    "(:project,:tenant,'LEG','Legacy')"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "INSERT INTO documents "
                    "(id,tenant_id,project_id,filename,storage_key,mime_type,size_bytes) VALUES "
                    "(:document,:tenant,:project,'legacy.pdf','legacy','application/pdf',1)"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "INSERT INTO risks (id,tenant_id,project_id,title) VALUES "
                    "(:risk,:tenant,:project,'Delay')"
                ),
                ids,
            )
            await connection.execute(
                text(
                    "INSERT INTO evidence_links "
                    "(id,tenant_id,project_id,risk_id,document_id,rationale,confidence) VALUES "
                    "(:link,:tenant,:project,:risk,:document,'Reasoning, not a quotation',0.7)"
                ),
                ids,
            )
            await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
            row = (
                (await connection.execute(text("SELECT * FROM evidence_links WHERE id=:link"), ids))
                .mappings()
                .one()
            )
            assert row["subject_type"] == "risk" and row["subject_id"] == ids["risk"]
            assert row["source_type"] == "document" and row["source_id"] == ids["document"]
            assert row["rationale"] == "Reasoning, not a quotation"
            assert row["source_text_snippet"] is None
            assert row["created_by"] is None
        finally:
            await transaction.rollback()


async def test_sql_answer_without_evidence_cannot_be_supported(test_session, tenant, project):
    with pytest.raises(DBAPIError, match="insufficient_evidence"):
        async with test_session.begin_nested():
            test_session.add(
                AIAnswer(
                    tenant_id=tenant.id, project_id=project.id, text="Invented", status="supported"
                )
            )
            await test_session.flush()
            await test_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.parametrize("kind", ["change_order", "risk", "ai_answer"])
async def test_required_subjects_have_view_api(
    client, test_session, tenant, project, user, evidence_setup, kind
):

    doc, risk = evidence_setup
    if kind == "change_order":
        subject = ChangeOrder(
            tenant_id=tenant.id, project_id=project.id, reference="CO-API", title="Change"
        )
    elif kind == "ai_answer":
        subject = AIAnswer(tenant_id=tenant.id, project_id=project.id, text="Answer")
    else:
        subject = risk
    test_session.add(subject)
    await test_session.flush()
    test_session.add(
        EvidenceLink(
            tenant_id=tenant.id,
            project_id=project.id,
            subject_type=kind,
            subject_id=subject.id,
            source_type="document",
            source_id=doc.id,
        )
    )
    await test_session.flush()
    app.dependency_overrides[get_current_user] = lambda: user
    response = await client.get(f"/api/v1/projects/{project.id}/evidence/{kind}/{subject.id}")
    assert response.status_code == 200
    assert response.json()["evidence"][0]["source_id"] == str(doc.id)
