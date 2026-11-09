"""Pilot persistence tests use the normal migrated test database by default.

PILOT_SCHEMA_ONLY=1 permits a disposable PostgreSQL server without pgvector;
that mode builds unrelated parent tables from metadata and runs migration 0014.
It does not validate earlier migrations or the ingestion worker.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request

from app.api.v1.routes.pilot import (
    ChecklistUpdate,
    PilotCreate,
    Review,
    checklist,
    create,
    progress,
    readiness,
    review,
    save_checklist,
)
from app.domain.models import (
    ChangeOrder,
    Document,
    ProjectMembership,
    Tenant,
    User,
)
from app.domain.services.document_service import DocumentService
from app.policy.scope import bind_scope


def request():
    return Request({"type": "http", "headers": [], "state": {"request_id": "pilot-test"}})


async def setup_pilot(session, role="owner"):
    tenant = Tenant(name="Pilot tenant", slug=uuid4().hex)
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"{uuid4().hex}@example.invalid",
        full_name="Pilot owner",
        password_hash="test",
        role=role,
    )
    session.add(user)
    await session.flush()
    bind_scope(session, user)
    result = await create(PilotCreate(name="Pilot customer"), request(), user, session)
    return user, UUID(result["project_id"])


@pytest.mark.parametrize("role", ["owner", "project_manager"])
async def test_create_checklist_and_report(pilot_session, role):
    user, project_id = await setup_pilot(pilot_session, role)
    service = DocumentService(pilot_session, user, None)
    assert (await checklist(project_id, user, pilot_session))["completed"] == []
    await save_checklist(
        project_id, ChecklistUpdate(completed=["scope"]), request(), user, pilot_session
    )
    assert (await checklist(project_id, user, pilot_session))["completed"] == ["scope"]
    result = await readiness(project_id, service)
    assert result["classification_accuracy"] is None
    assert result["missing_evidence"] == ["contract", "boq", "drawing"]
    assert result["pending_exposure"] == {}


async def test_review_preserves_prediction_and_rejects_stale_version(pilot_session):
    from fastapi import HTTPException

    user, project_id = await setup_pilot(pilot_session)
    doc = Document(
        tenant_id=user.tenant_id,
        project_id=project_id,
        filename="contract.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        processing_status="linked",
        document_type="rfi",
        classification_result={"document_type": "rfi"},
        attributes={},
        document_version=1,
    )
    pilot_session.add(doc)
    await pilot_session.commit()
    service = DocumentService(pilot_session, user, None)
    await review(
        doc.id,
        Review(document_type="contract", reason="Compared source", version=1),
        request(),
        service,
    )
    assert doc.document_type == "contract"
    assert doc.classification_result == {"document_type": "rfi"}
    assert (await readiness(project_id, service))["classification_accuracy"] == 0
    with pytest.raises(HTTPException) as exc:
        await review(
            doc.id,
            Review(document_type="contract", reason="Reviewed", version=1),
            request(),
            service,
        )
    assert exc.value.status_code == 409


async def test_nonmember_cannot_open_pilot(pilot_session):
    from app.api.exceptions import NotFoundError

    user, project_id = await setup_pilot(pilot_session)
    tenant_id = user.tenant_id
    pilot_session.info.clear()
    stranger = User(
        tenant_id=tenant_id,
        email=f"{uuid4().hex}@example.invalid",
        full_name="Stranger",
        password_hash="test",
        role="viewer",
    )
    pilot_session.add(stranger)
    await pilot_session.flush()
    bind_scope(pilot_session, stranger)
    with pytest.raises(NotFoundError):
        await checklist(project_id, stranger, pilot_session)


async def test_restricted_document_not_in_progress(pilot_session):
    user, project_id = await setup_pilot(pilot_session)
    doc = Document(
        tenant_id=user.tenant_id,
        project_id=project_id,
        filename="restricted.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        access_level="restricted",
        uploaded_by_id=user.id,
    )
    pilot_session.add(doc)
    await pilot_session.commit()
    tenant_id = user.tenant_id
    pilot_session.info.clear()
    viewer = User(
        tenant_id=tenant_id,
        email=f"{uuid4().hex}@example.invalid",
        full_name="Viewer",
        password_hash="test",
        role="viewer",
    )
    pilot_session.add(viewer)
    await pilot_session.flush()
    pilot_session.add(
        ProjectMembership(
            tenant_id=tenant_id, project_id=project_id, user_id=viewer.id, is_active=True
        )
    )
    await pilot_session.flush()
    bind_scope(pilot_session, viewer)
    assert await progress(project_id, DocumentService(pilot_session, viewer, None)) == []


async def test_extraction_overlay_preserves_original_and_confidence(pilot_session):
    from app.document_processing.structured.schemas import schema_for
    from tests.structured_cases import blank, fact

    user, project_id = await setup_pilot(pilot_session)
    original = {"document_type": "contract", "fields": blank(schema_for("contract"))}
    doc = Document(
        tenant_id=user.tenant_id,
        project_id=project_id,
        filename="contract.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        processing_status="linked",
        document_type="contract",
        structured_extraction=original,
        extraction_confidence=Decimal("0.5000"),
        attributes={},
        document_version=1,
    )
    pilot_session.add(doc)
    await pilot_session.commit()
    fields = blank(schema_for("contract"))
    fields["title"] = fact("Customer correction", "Title: Customer correction")
    service = DocumentService(pilot_session, user, None)
    await review(
        doc.id,
        Review(fields=fields, reason="Checked original title", version=1),
        request(),
        service,
    )
    assert doc.structured_extraction == original
    assert (
        doc.attributes["pilot_review"]["extraction"]["fields"]["title"]["value"]
        == "Customer correction"
    )
    assert (await readiness(project_id, service))["extraction_confidence"] == 0.5


async def test_report_exposure_overdue_and_risks(pilot_session):
    from app.domain.models import Approval, Risk

    user, project_id = await setup_pilot(pilot_session)
    risk = Risk(
        tenant_id=user.tenant_id, project_id=project_id, title="Overdue response", status="open"
    )
    pilot_session.add(risk)
    await pilot_session.flush()
    pilot_session.info.clear()  # Trusted fixture setup; no workflow transitions are simulated.
    for number, currency, amount in [
        (1, "USD", "0.10"),
        (2, "USD", "0.20"),
        (3, "BDT", "100"),
        (4, "USD", None),
    ]:
        pilot_session.add(
            ChangeOrder(
                tenant_id=user.tenant_id,
                project_id=project_id,
                reference=f"CO-{number}",
                title="Pending",
                status="potential",
                currency=currency,
                amount=amount,
            )
        )
    pilot_session.add(
        Approval(
            tenant_id=user.tenant_id,
            project_id=project_id,
            risk_id=risk.id,
            status="pending",
            due_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await pilot_session.flush()
    bind_scope(pilot_session, user)
    result = await readiness(project_id, DocumentService(pilot_session, user, None))
    assert result["pending_exposure"] == {"USD": "0.30", "BDT": "100.00"}
    assert result["unknown_exposure_count"] == 1
    assert result["overdue_approvals"] == 1
    assert result["risks_detected"] == 1


async def test_api_denies_financial_report_for_viewer(pilot_session):
    from httpx import ASGITransport, AsyncClient

    from app.api.dependencies import get_current_user
    from app.core.database import get_session
    from app.main import app

    user, project_id = await setup_pilot(pilot_session)
    tenant_id = user.tenant_id
    pilot_session.info.clear()
    viewer = User(
        tenant_id=tenant_id,
        email=f"{uuid4().hex}@example.invalid",
        full_name="Viewer",
        password_hash="test",
        role="viewer",
    )
    pilot_session.add(viewer)
    await pilot_session.flush()
    pilot_session.add(
        ProjectMembership(
            tenant_id=tenant_id, project_id=project_id, user_id=viewer.id, is_active=True
        )
    )
    await pilot_session.flush()

    async def current():
        return viewer

    async def session():
        yield pilot_session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = current
    app.dependency_overrides[get_session] = session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for suffix in ["readiness", "readiness.pdf"]:
                assert (
                    await client.get(f"/api/v1/pilot/projects/{project_id}/{suffix}")
                ).status_code == 403
            assert (
                await client.get(f"/api/v1/pilot/projects/{project_id}/documents")
            ).status_code == 200
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def test_zip_import_outcomes_and_retry(pilot_session, monkeypatch):
    from io import BytesIO
    from pathlib import PurePosixPath
    from unittest.mock import Mock

    from fastapi import UploadFile

    from app.api.v1.routes.pilot import upload_zip
    from app.domain.services.pilot import render_report
    from app.ingestion.tasks import process_uploaded_file
    from tests.test_pilot import archive

    user, project_id = await setup_pilot(pilot_session)
    storage = Mock()
    storage._sanitize_filename.side_effect = lambda name: PurePosixPath(name).name
    monkeypatch.setattr(process_uploaded_file, "delay", Mock())
    service = DocumentService(pilot_session, user, storage)
    content = archive(
        [("good.pdf", render_report({"project_name": "Pilot"})), ("bad.pdf", b"invalid pdf")]
    )
    outcome = await upload_zip(
        project_id, UploadFile(filename="pilot.zip", file=BytesIO(content)), service
    )
    assert [item["status"] for item in outcome["items"]] == [201, 422]
    assert storage.store_original.call_count == 2
    assert process_uploaded_file.delay.call_count == 1
    retry = await upload_zip(
        project_id, UploadFile(filename="pilot.zip", file=BytesIO(content)), service
    )
    assert [item["status"] for item in retry["items"]] == [409, 409]
    assert len(await progress(project_id, service)) == 2


async def test_pilot_list_respects_membership(pilot_session):
    from app.api.v1.routes.pilot import list_pilots

    user, project_id = await setup_pilot(pilot_session)
    assert (await list_pilots(user, pilot_session))[0]["project_id"] == str(project_id)
    tenant_id = user.tenant_id
    pilot_session.info.clear()
    viewer = User(
        tenant_id=tenant_id,
        email=f"{uuid4().hex}@example.invalid",
        full_name="Unassigned",
        password_hash="test",
        role="viewer",
    )
    pilot_session.add(viewer)
    await pilot_session.flush()
    bind_scope(pilot_session, viewer)
    assert await list_pilots(viewer, pilot_session) == []
