"""Real PostgreSQL API/worker integration; external providers are controlled fakes."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_processing.extraction.types import TextBlock
from app.document_processing.pipeline import STAGES, run_one_stage
from app.domain.models import (
    AuditEvent,
    Document,
    ProjectMembership,
    Risk,
    Tenant,
    User,
)
from app.domain.services.object_storage import get_object_storage_service
from app.domain.services.potential_changes import detect, persist
from app.domain.services.risk_engine import run_risk_checks
from app.main import app
from app.policy.scope import SCOPE_KEY
from tests.structured_cases import case
from tests.test_documents import bearer, pdf_bytes
from tests.test_processing_pipeline import providers


@pytest.fixture
async def owner(test_session, user, request):
    user.role = getattr(request, "param", "owner")
    await test_session.flush()
    return user


@pytest.fixture
def storage(monkeypatch):
    objects = {}
    service = MagicMock()
    service._sanitize_filename.side_effect = lambda value: value

    def store(key, stream, mime):
        assert key not in objects, "Original overwritten"
        objects[key] = stream.read()

    service.store_original.side_effect = store
    service.download_file.side_effect = lambda key: objects[key]
    app.dependency_overrides[get_object_storage_service] = lambda: service
    monkeypatch.setattr("app.ingestion.tasks.process_uploaded_file.delay", MagicMock())
    yield service
    app.dependency_overrides.pop(get_object_storage_service, None)


async def create_and_upload(client, owner, storage, extension="pdf"):
    content = (
        pdf_bytes()
        if extension == "pdf"
        else (Path(__file__).parent / "fixtures/extraction/report.png").read_bytes()
    )
    response = await client.post(
        "/api/v1/projects",
        headers=bearer(owner),
        json={
            "code": "SLICE",
            "name": "Daily report pilot",
            "client_name": "Example client",
            "contract_value": "12000.50",
            "currency": "BDT",
            "expected_end_date": "2027-01-01",
            "stakeholders": ["Site team"],
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["client_name"] == "Example client"
    assert project["contract_value"] == "12000.50"
    result = await client.post(
        f"/api/v1/projects/{project['id']}/documents",
        headers={**bearer(owner), "X-Request-ID": "54a0f1cd-897f-47d7-80fb-96d010c0606e"},
        files={"file": (f"daily_report.{extension}", content)},
    )
    assert result.status_code == 201, result.text
    return UUID(project["id"]), UUID(result.json()["document_id"])


async def prepare_risk(test_session, project_id, document_id, page=1):
    # Worker sessions are explicitly tenant/project scoped and separate from HTTP scope.
    test_session.info.pop(SCOPE_KEY, None)
    document = await test_session.get(Document, document_id)
    document.document_type = "daily_report"
    _, source = case("daily_report")
    source.blocks.append(
        TextBlock(text="Work was delayed by late steel delivery.", page_number=page)
    )
    await persist(document, await detect(source), test_session)
    await test_session.flush()
    await run_risk_checks(document, test_session)
    await test_session.flush()
    return document


@pytest.mark.parametrize("owner", ["owner", "project_manager"], indirect=True)
async def test_project_upload_rule_timeline_and_audits(client, test_session, owner, storage):
    project_id, document_id = await create_and_upload(client, owner, storage)
    document = await prepare_risk(test_session, project_id, document_id)
    await run_risk_checks(document, test_session)
    await test_session.flush()
    risk = await test_session.scalar(
        select(Risk).where(Risk.risk_type == "daily_report_delay_without_link")
    )
    assert risk.exposure_amount is None and risk.schedule_impact_days is None
    response = await client.get(f"/api/v1/projects/{project_id}/timeline", headers=bearer(owner))
    assert response.status_code == 200, response.text
    rows = response.json()["items"]
    (row,) = [item for item in rows if item["event_type"] == "daily_report_delay_without_link"]
    assert row["status"] == "open"
    assert row["evidence"][0]["source_text_snippet"] == "Work was delayed by late steel delivery."
    assert row["evidence"][0]["source_page"] == 1
    test_session.info.pop(SCOPE_KEY, None)
    audits = list(await test_session.scalars(select(AuditEvent)))
    assert {"project.create", "document.upload", "risk.create"} <= {a.action for a in audits}
    assert len([a for a in audits if a.action == "risk.create" and a.entity_id == risk.id]) == 1
    assert (
        next(a for a in audits if a.action == "document.upload").request_id
        == document.processing_data["request_id"]
    )
    assert all("late steel" not in str(a.details) for a in audits)
    storage.store_original.assert_called_once()


async def test_timeline_conceals_other_tenants_nonmembers_and_deleted_sources(
    client,
    test_session,
    owner,
    storage,
):
    project_id, document_id = await create_and_upload(client, owner, storage)
    document = await prepare_risk(test_session, project_id, document_id)
    other = Tenant(name="Other", slug=uuid4().hex)
    test_session.add(other)
    await test_session.flush()
    outsider = User(
        tenant_id=other.id,
        email="other@example.invalid",
        full_name="Other",
        password_hash="test",
        role="owner",
    )
    nonmember = User(
        tenant_id=owner.tenant_id,
        email="pm@example.invalid",
        full_name="PM",
        password_hash="test",
        role="project_manager",
    )
    test_session.add_all([outsider, nonmember])
    await test_session.flush()
    url = f"/api/v1/projects/{project_id}/timeline"
    for user in [outsider, nonmember]:
        test_session.info.pop(SCOPE_KEY, None)
        response = await client.get(url, headers=bearer(user))
        assert response.status_code == 404, response.text
    test_session.info.pop(SCOPE_KEY, None)
    await test_session.refresh(document)
    document.deleted_at = document.created_at
    await test_session.flush()
    assert (await client.get(url, headers=bearer(owner))).json()["items"] == []


async def test_timeline_pagination_and_restricted_source(client, test_session, owner, storage):
    project_id, document_id = await create_and_upload(client, owner, storage)
    document = await prepare_risk(test_session, project_id, document_id)
    url = f"/api/v1/projects/{project_id}/timeline"
    page = await client.get(url + "?limit=1", headers=bearer(owner))
    assert page.status_code == 200, page.text
    assert page.json()["has_more"] is True
    assert len(page.json()["items"]) == 1
    test_session.info.pop(SCOPE_KEY, None)
    member = User(
        tenant_id=owner.tenant_id,
        email="member@example.invalid",
        full_name="Member",
        password_hash="test",
        role="project_manager",
    )
    test_session.add(member)
    await test_session.flush()
    test_session.add(
        ProjectMembership(tenant_id=owner.tenant_id, project_id=project_id, user_id=member.id)
    )
    document.access_level = "restricted"
    await test_session.flush()
    response = await client.get(url, headers=bearer(member))
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


async def test_insufficient_delay_keeps_original_link_and_cannot_be_accepted(
    client,
    test_session,
    owner,
    storage,
):
    project_id, document_id = await create_and_upload(client, owner, storage)
    await prepare_risk(test_session, project_id, document_id, page=None)
    risk = await test_session.scalar(
        select(Risk).where(Risk.risk_type == "daily_report_delay_without_link")
    )
    assert risk.status == "insufficient_evidence"
    url = f"/api/v1/projects/{project_id}"
    response = await client.get(url + "/timeline", headers=bearer(owner))
    assert response.status_code == 200, response.text
    (item,) = [
        item
        for item in response.json()["items"]
        if item["event_type"] == "daily_report_delay_without_link"
    ]
    assert item["evidence_status"] == "insufficient_evidence"
    assert item["evidence"][0]["source_id"] == str(document_id)
    assert item["evidence"][0]["source_text_snippet"] is None
    response = await client.post(
        url + f"/risks/{item['id']}/decisions",
        headers=bearer(owner),
        json={"action": "accept", "reason": "Reviewed"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("extension", ["pdf", "png"])
async def test_full_worker_to_timeline(client, test_session, owner, storage, extension):
    project_id, document_id = await create_and_upload(client, owner, storage, extension)
    test_session.info.pop(SCOPE_KEY, None)
    fields, source = case("daily_report")
    source.blocks.append(TextBlock(text="Work was delayed by late steel delivery.", page_number=1))
    services = providers()
    services.extraction.side_effect = None
    services.extraction.return_value = source
    services.classify.return_value["document_type"] = "daily_report"
    services.extract.return_value = {
        "schema_version": 1,
        "document_type": "daily_report",
        "fields": fields,
        "confidence": 0.96,
        "missing_required_fields": [],
        "attempts": [],
        "model_or_rule_used": "test:strict",
    }

    @asynccontextmanager
    async def factory():
        async with AsyncSession(
            bind=test_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    for _ in STAGES:
        await run_one_stage(
            document_id, owner.tenant_id, factory, services=services, storage=storage
        )
    assert (
        await run_one_stage(
            document_id, owner.tenant_id, factory, services=services, storage=storage
        )
        is None
    )
    document = await test_session.get(Document, document_id, populate_existing=True)
    assert document.processing_status == "review_required", document.error_message
    response = await client.get(f"/api/v1/projects/{project_id}/timeline", headers=bearer(owner))
    assert response.status_code == 200, response.text
    assert any(
        item["event_type"] == "daily_report_delay_without_link" for item in response.json()["items"]
    )
    test_session.info.pop(SCOPE_KEY, None)
    audits = list(
        await test_session.scalars(
            select(AuditEvent).where(AuditEvent.action == "document.processing")
        )
    )
    assert len(audits) == len(STAGES)
    assert all(a.request_id == document.processing_data["request_id"] for a in audits)
