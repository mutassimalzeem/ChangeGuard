"""Opt-in real Redis/Celery worker smoke test with mocked AI services."""

import asyncio
import hashlib
import os
from uuid import uuid4

import pytest
from celery.contrib.testing.worker import start_worker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.domain.models import Document, Project, Tenant
from app.ingestion.tasks import process_uploaded_file
from tests.test_documents import pdf_bytes
from tests.test_processing_pipeline import providers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_REDIS_URL"),
        reason="Set TEST_REDIS_URL and CELERY_BROKER_URL to disposable Redis",
    ),
]


async def test_real_redis_worker_runs_all_stages(test_engine, monkeypatch):
    from unittest.mock import Mock

    settings = get_settings()
    assert settings.celery_broker_url == os.environ["TEST_REDIS_URL"]
    monkeypatch.setattr(
        settings, "database_url", test_engine.url.render_as_string(hide_password=False)
    )
    content = pdf_bytes()
    services = providers()
    storage = Mock()
    storage.download_file.return_value = content
    monkeypatch.setattr("app.document_processing.pipeline.Services", lambda: services)
    monkeypatch.setattr(
        "app.domain.services.object_storage.get_object_storage_service", lambda: storage
    )
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        tenant = Tenant(id=uuid4(), name="Redis smoke", slug=uuid4().hex)
        session.add(tenant)
        await session.flush()
        project = Project(id=uuid4(), tenant_id=tenant.id, code="SMOKE", name="Redis smoke")
        session.add(project)
        await session.flush()
        document = Document(
            id=uuid4(),
            tenant_id=tenant.id,
            project_id=project.id,
            filename="file.pdf",
            storage_key="smoke/original",
            file_type="pdf",
            mime_type="application/pdf",
            size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
            status="queued",
            processing_status="queued",
        )
        session.add(document)
        await session.commit()
        document_id, tenant_id = document.id, tenant.id
    with start_worker(celery_app, pool="solo", queues=["ingestion"], perform_ping_check=False):
        process_uploaded_file.delay(str(document_id), str(tenant_id))
        for _ in range(150):
            async with AsyncSession(test_engine) as session:
                status = await session.scalar(
                    select(Document.processing_status).where(Document.id == document_id)
                )
            if status in {"completed", "dead_letter"}:
                break
            await asyncio.sleep(0.1)
        assert status == "completed"
    for name in ("ocr", "classify", "extract", "embed"):
        getattr(services, name).assert_called_once()
