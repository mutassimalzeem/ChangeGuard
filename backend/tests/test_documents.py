"""Document API integration tests with isolated PostgreSQL and mocked IO."""

import hashlib
from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from pypdf import PdfWriter
from sqlalchemy import select

from app.core.security import create_access_token
from app.domain.models import Document, Project, ProjectMembership, User
from app.domain.services.object_storage import get_object_storage_service
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def bearer(user):
    return {
        "Authorization": "Bearer "
        + create_access_token(str(user.id), str(user.tenant_id), user.token_version)
    }


def pdf_bytes():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    return output.getvalue()


@pytest_asyncio.fixture
async def registry(test_session, tenant, project, user, monkeypatch):
    user.role = "site_engineer"
    test_session.add(ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    await test_session.flush()
    storage = MagicMock()
    storage._sanitize_filename.side_effect = lambda name: name.split("/")[-1]
    storage.generate_presigned_url.return_value = "https://storage.test/signed"
    app.dependency_overrides[get_object_storage_service] = lambda: storage
    publish = MagicMock()
    monkeypatch.setattr("app.ingestion.tasks.process_uploaded_file.delay", publish)
    yield project.id, user, storage, publish
    app.dependency_overrides.pop(get_object_storage_service, None)


async def upload(client, registry, name="test.pdf", content=None, **data):
    project_id, user, _, _ = registry
    return await client.post(
        f"/api/v1/projects/{project_id}/documents",
        headers=bearer(user),
        files={"file": (name, pdf_bytes() if content is None else content)},
        data=data,
    )


async def test_upload_registry_download_and_soft_delete(client, registry, test_session):
    project_id, user, storage, publish = registry
    result = await upload(client, registry)
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["file_hash"] == hashlib.sha256(pdf_bytes()).hexdigest()
    assert row["processing_status"] == "queued"
    assert row["uploaded_by"] == str(user.id)
    assert row["file_type"] == "pdf"
    storage.store_original.assert_called_once()
    publish.assert_called_once_with(row["document_id"], str(user.tenant_id))
    headers = bearer(user)
    base = f"/api/v1/documents/{row['document_id']}"
    assert (await client.get(base, headers=headers)).status_code == 200
    listing = await client.get(f"/api/v1/projects/{project_id}/documents", headers=headers)
    assert len(listing.json()) == 1
    signed = await client.get(base + "/download-url", headers=headers)
    assert signed.json() == {"url": "https://storage.test/signed", "expires_in": 3600}
    assert (await client.delete(base, headers=headers)).status_code == 204
    assert (await client.get(base, headers=headers)).status_code == 404
    assert (await client.get(base + "/download-url", headers=headers)).status_code == 404
    storage.delete_file.assert_not_called()
    assert (await upload(client, registry)).status_code == 409


async def test_duplicate_does_not_overwrite_or_queue(client, registry):
    assert (await upload(client, registry)).status_code == 201
    assert (await upload(client, registry, name="renamed.pdf")).status_code == 409
    registry[2].store_original.assert_called_once()
    registry[3].assert_called_once()


@pytest.mark.parametrize(
    "name,content", [("bad.exe", b"executable"), ("bad.pdf", b"%PDF-broken"), ("empty.pdf", b"")]
)
async def test_invalid_files_are_preserved_in_quarantine(client, registry, name, content):
    result = await upload(client, registry, name, content)
    assert result.status_code == 422, result.text
    row = result.json()
    assert row["processing_status"] == "quarantined"
    assert "/quarantine/" in row["original_file_key"]
    assert row["error_message"]
    registry[2].store_original.assert_called_once()
    registry[3].assert_not_called()
    signed = await client.get(
        f"/api/v1/documents/{row['document_id']}/download-url", headers=bearer(registry[1])
    )
    assert signed.status_code == 409


async def test_oversized_file_is_preserved(client, registry, monkeypatch):
    monkeypatch.setattr("app.domain.services.document_service.MAX_SIZE", 10)
    result = await upload(client, registry, content=b"x" * 11)
    assert result.status_code == 413
    assert result.json()["processing_status"] == "quarantined"
    assert result.json()["file_size"] == 11
    registry[2].store_original.assert_called_once()
    registry[3].assert_not_called()


async def test_queue_failure_retains_recoverable_row(client, registry):
    registry[3].side_effect = ConnectionError()
    result = await upload(client, registry)
    assert result.status_code == 201
    assert result.json()["processing_status"] == "queued"
    assert "automatic retry" in result.json()["error_message"]


async def test_storage_failure_retains_failed_metadata(client, registry, test_session):
    registry[2].store_original.side_effect = ConnectionError()
    assert (await upload(client, registry)).status_code == 503
    row = await test_session.scalar(select(Document))
    assert row.status == "failed"
    registry[3].assert_not_called()


async def test_viewer_cannot_upload_or_delete(client, registry, test_session):
    user = registry[1]
    user.role = "viewer"
    await test_session.flush()
    assert (await upload(client, registry)).status_code == 403
    assert (
        await client.delete(f"/api/v1/documents/{uuid4()}", headers=bearer(user))
    ).status_code == 403


async def test_unassigned_project_is_hidden(client, registry, test_session, tenant):
    other = Project(tenant_id=tenant.id, code="OTHER", name="Unassigned")
    # Unscoped fixture session has not yet been bound by an API request.
    test_session.add(other)
    await test_session.flush()
    result = await client.post(
        f"/api/v1/projects/{other.id}/documents",
        headers=bearer(registry[1]),
        files={"file": ("a.pdf", pdf_bytes())},
    )
    assert result.status_code == 404
    registry[2].store_original.assert_not_called()


async def test_cross_tenant_and_unauthenticated_access(client, registry, test_session):
    from app.domain.models import Tenant

    other_tenant = Tenant(name="Other", slug=uuid4().hex)
    test_session.add(other_tenant)
    await test_session.flush()
    other_project = Project(tenant_id=other_tenant.id, name="Other", code="OTHER")
    test_session.add(other_project)
    await test_session.flush()
    other_document = Document(
        tenant_id=other_tenant.id,
        project_id=other_project.id,
        filename="hidden.pdf",
        storage_key="hidden",
        mime_type="application/pdf",
        size_bytes=1,
    )
    test_session.add(other_document)
    await test_session.flush()
    hidden_id, hidden_project = other_document.id, other_project.id
    for suffix in ("", "/download-url"):
        assert (
            await client.get(f"/api/v1/documents/{hidden_id}{suffix}", headers=bearer(registry[1]))
        ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/projects/{hidden_project}/documents", headers=bearer(registry[1])
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/projects/{registry[0]}/documents", files={"file": ("a.pdf", pdf_bytes())}
        )
    ).status_code == 401


async def test_restricted_document_only_visible_to_uploader(client, registry, test_session, tenant):
    colleague = User(
        tenant_id=tenant.id,
        email="colleague@test.invalid",
        full_name="Colleague",
        password_hash="x",
        role="viewer",
    )
    test_session.add(colleague)
    await test_session.flush()
    test_session.add(
        ProjectMembership(tenant_id=tenant.id, project_id=registry[0], user_id=colleague.id)
    )
    await test_session.flush()
    result = await upload(client, registry, access_level="restricted")
    # A fresh session is used below because scoped sessions cannot change identity.
    from app.core.database import ScopedAsyncSession, get_session

    async def colleague_session():
        async with ScopedAsyncSession(
            bind=test_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    app.dependency_overrides[get_session] = colleague_session
    headers = bearer(colleague)
    base = f"/api/v1/documents/{result.json()['document_id']}"
    assert (await client.get(base, headers=headers)).status_code == 404
    assert (await client.get(base + "/download-url", headers=headers)).status_code == 404
    assert (
        await client.get(f"/api/v1/projects/{registry[0]}/documents", headers=headers)
    ).json() == []


@pytest.mark.parametrize("corrupted", [False, True])
async def test_worker_is_idempotent_and_preserves_failed_original(
    client, registry, test_session, monkeypatch, corrupted
):
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ingestion.tasks import process_registry_document

    result = await upload(client, registry)
    row = result.json()
    storage = registry[2]
    storage.download_file.return_value = b"corrupt" if corrupted else pdf_bytes()

    @asynccontextmanager
    async def worker_session():
        async with AsyncSession(
            bind=test_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    monkeypatch.setattr("app.ingestion.tasks.registry_worker_session", worker_session)
    monkeypatch.setattr(
        "app.domain.services.object_storage.get_object_storage_service", lambda: storage
    )
    await process_registry_document(row["document_id"], str(uuid4()))
    storage.download_file.assert_not_called()
    await process_registry_document(row["document_id"], str(registry[1].tenant_id))
    await process_registry_document(row["document_id"], str(registry[1].tenant_id))
    storage.download_file.assert_called_once()
    document = await test_session.scalar(select(Document).execution_options(populate_existing=True))
    assert document.status == ("quarantined" if corrupted else "review_required")
    storage.delete_file.assert_not_called()


async def test_queue_recovery_republishes_durable_pending_record(
    client, registry, test_session, monkeypatch
):
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ingestion.tasks import recover_registry_queue

    result = await upload(client, registry)
    document = await test_session.scalar(select(Document))
    document.updated_at = datetime.now(UTC) - timedelta(minutes=10)
    await test_session.commit()
    registry[3].reset_mock()

    @asynccontextmanager
    async def worker_session():
        async with AsyncSession(
            bind=test_session.bind, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    monkeypatch.setattr("app.ingestion.tasks.registry_worker_session", worker_session)
    await recover_registry_queue(now=datetime.now(UTC) + timedelta(minutes=10))
    registry[3].assert_called_once_with(result.json()["document_id"], str(registry[1].tenant_id))


async def test_database_constraint_rejects_duplicate_hash(client, registry, test_session):
    from sqlalchemy.exc import IntegrityError

    result = await upload(client, registry)
    row = result.json()
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(
                Document(
                    tenant_id=registry[1].tenant_id,
                    project_id=registry[0],
                    filename="concurrent.pdf",
                    storage_key="different-key",
                    mime_type="application/pdf",
                    size_bytes=row["file_size"],
                    checksum=row["file_hash"],
                )
            )
            await test_session.flush()


async def test_same_bytes_allowed_in_different_project(client, registry, test_session, tenant):
    other = Project(tenant_id=tenant.id, code="SECOND", name="Second")
    test_session.add(other)
    await test_session.flush()
    other_id = other.id
    test_session.add(
        ProjectMembership(tenant_id=tenant.id, project_id=other_id, user_id=registry[1].id)
    )
    await test_session.flush()
    first = await upload(client, registry)
    second = await client.post(
        f"/api/v1/projects/{other_id}/documents",
        headers=bearer(registry[1]),
        files={"file": ("same.pdf", pdf_bytes())},
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["document_id"] != second.json()["document_id"]


async def test_download_storage_failure_returns_503(client, registry):
    result = await upload(client, registry)
    registry[2].generate_presigned_url.side_effect = ConnectionError()
    response = await client.get(
        f"/api/v1/documents/{result.json()['document_id']}/download-url",
        headers=bearer(registry[1]),
    )
    assert response.status_code == 503
