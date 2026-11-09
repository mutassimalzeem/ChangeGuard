"""Seeded PostgreSQL source records, scoped API contracts, exports and usage persistence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.domain.models import (
    AITrace,
    Approval,
    AuditEvent,
    ChangeOrder,
    Document,
    DocumentReviewTask,
    EvidenceLink,
    Project,
    Risk,
    Tenant,
    User,
)
from app.domain.services.pilot_metrics import PilotMetricsService
from app.main import app

NOW = datetime(2026, 11, 16, tzinfo=UTC)


@pytest.fixture
async def metrics_seed(pilot_session):
    session = pilot_session
    tenant = Tenant(name="Metrics customer", slug=uuid4().hex)
    other_tenant = Tenant(name="Other customer", slug=uuid4().hex)
    session.add_all([tenant, other_tenant])
    await session.flush()
    project = Project(tenant_id=tenant.id, code=uuid4().hex, name="Seeded pilot")
    another = Project(tenant_id=tenant.id, code=uuid4().hex, name="Other project")
    foreign = Project(tenant_id=other_tenant.id, code=uuid4().hex, name="Foreign project")
    user = User(
        tenant_id=tenant.id,
        email=f"{uuid4().hex}@example.invalid",
        full_name="Owner",
        password_hash="test",
        role="owner",
    )
    session.add_all([project, another, foreign, user])
    await session.flush()
    created = NOW - timedelta(days=2)
    success = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="processed.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        created_at=created,
        status="linked",
        processing_status="completed",
        processing_data={
            "metrics": {
                "started_at": created.isoformat(),
                "finished_at": (created + timedelta(seconds=120)).isoformat(),
            }
        },
        classification_result={"document_type": "contract"},
    )
    failed = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="failed.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        created_at=created,
        status="failed",
        processing_status="dead_letter",
    )
    excluded = Document(
        tenant_id=tenant.id,
        project_id=another.id,
        filename="not-this-project.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        created_at=created,
    )
    risk = Risk(
        tenant_id=tenant.id,
        project_id=project.id,
        title="Risk",
        status="accepted",
        detected_at=created,
    )
    session.add_all([success, failed, excluded, risk])
    await session.flush()
    session.add_all(
        [
            AuditEvent(
                tenant_id=tenant.id,
                project_id=project.id,
                actor_id=user.id,
                action="pilot.review",
                entity_type="pilot",
                entity_id=project.id,
                created_at=created + timedelta(hours=1),
                details={
                    "document_id": str(success.id),
                    "type_reviewed": True,
                    "after": {"document_type": "contract"},
                },
            ),
            AuditEvent(
                tenant_id=tenant.id,
                project_id=project.id,
                actor_id=user.id,
                action="risk.accept",
                entity_type="risk",
                entity_id=risk.id,
                created_at=created + timedelta(hours=2),
                details={},
            ),
            DocumentReviewTask(
                tenant_id=tenant.id,
                project_id=project.id,
                document_id=success.id,
                reason="review",
                status="pending",
                created_at=created,
            ),
            EvidenceLink(
                tenant_id=tenant.id,
                project_id=project.id,
                subject_type="risk",
                subject_id=risk.id,
                source_type="document",
                source_id=success.id,
                created_at=created,
            ),
            Approval(
                tenant_id=tenant.id,
                project_id=project.id,
                risk_id=risk.id,
                status="approved",
                created_at=created,
                decided_at=created + timedelta(hours=2),
            ),
            ChangeOrder(
                tenant_id=tenant.id,
                project_id=project.id,
                reference="CO-1",
                title="Change",
                status="potential",
                created_at=created,
            ),
            AITrace(
                tenant_id=tenant.id,
                project_id=project.id,
                operation="classification",
                provider="openai",
                model="seed",
                status="valid",
                cost=Decimal(".10"),
                created_at=created,
                attributes={"document_id": str(success.id), "usage_complete": True},
            ),
            AITrace(
                tenant_id=tenant.id,
                project_id=project.id,
                operation="reasoning",
                provider="openai",
                model="seed",
                status="valid",
                cost=Decimal(".20"),
                created_at=created,
                attributes={"investigation_id": str(uuid4()), "usage_complete": True},
            ),
        ]
    )
    await session.flush()
    return user, project.id, another.id, foreign.id


async def test_seeded_project_service(pilot_session, metrics_seed):
    user, project_id, _, _ = metrics_seed
    report = await PilotMetricsService(pilot_session, user, clock=lambda: NOW).report(
        project_id, NOW - timedelta(days=7), NOW
    )
    values = report.metrics
    assert values.documents_uploaded == 2
    assert values.documents_processed_successfully == 1
    assert values.processing_failure_rate.value == 0.5
    assert values.classification_accuracy.value == 1
    assert values.extraction_accuracy.value is None
    assert values.evidence_link_coverage.value == 0.5
    assert values.risks_detected == values.risks_accepted == values.change_orders_created == 1
    assert values.approval_cycle_time.value == 7200
    assert values.time_in_review_queue.value == 3600
    assert values.ai_cost_per_document.value == "0.100000"
    assert values.ai_cost_per_investigation.value == "0.200000"
    assert values.processing_latency_seconds.p95 == 120


@pytest.fixture
async def metrics_client(pilot_session, metrics_seed):
    user, *_ = metrics_seed

    async def current():
        return user

    async def session():
        yield pilot_session

    from app.api.v1.routes.pilot_metrics import metrics_service

    async def service():
        return PilotMetricsService(pilot_session, user, clock=lambda: NOW)

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = current
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[metrics_service] = service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def test_api_dashboard_and_weekly_csv(metrics_client, metrics_seed):
    _, project_id, _, _ = metrics_seed
    root = f"/api/v1/projects/{project_id}/metrics"
    response = await metrics_client.get(
        root + "/dashboard", params={"start": "2026-11-09T00:00:00Z", "end": NOW.isoformat()}
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["report"]["metrics"]["documents_uploaded"] == 2
    assert "ai_cost" in response.json()["sections"]
    exported = await metrics_client.get(root + "/weekly.csv?week_start=2026-11-09")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "documents_uploaded,count,2" in exported.text
    assert "processed.pdf" not in exported.text
    assert "classification_accuracy,value,1.0" in exported.text


@pytest.mark.parametrize(
    "query",
    [
        "start=2026-11-15T00:00:00",
        "start=2026-11-16T00:00:00Z&end=2026-11-09T00:00:00Z",
        "start=2024-01-01T00:00:00Z&end=2026-11-09T00:00:00Z",
    ],
)
async def test_invalid_windows(metrics_client, metrics_seed, query):
    _, project_id, _, _ = metrics_seed
    response = await metrics_client.get(f"/api/v1/projects/{project_id}/metrics?{query}")
    assert response.status_code == 422


async def test_week_start_and_cross_tenant(metrics_client, metrics_seed):
    _, project_id, _, foreign_id = metrics_seed
    assert (
        await metrics_client.get(
            f"/api/v1/projects/{project_id}/metrics/weekly.csv?week_start=2026-11-10"
        )
    ).status_code == 422
    assert (await metrics_client.get(f"/api/v1/projects/{foreign_id}/metrics")).status_code == 404


@pytest.mark.parametrize(
    "role", ["viewer", "site_engineer", "project_manager", "commercial_manager", "auditor"]
)
async def test_api_does_not_broaden_audit_or_financial_permissions(
    pilot_session, metrics_seed, metrics_client, role
):
    user, project_id, *_ = metrics_seed
    user.role = role
    await pilot_session.flush()
    response = await metrics_client.get(f"/api/v1/projects/{project_id}/metrics")
    assert response.status_code == 403


async def test_durable_usage_sink_is_idempotent_and_checks_document_ownership(
    pilot_session, metrics_seed
):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from app.ai.gateway.usage import persist_usage

    user, project_id, another_id, _ = metrics_seed
    doc_id = await pilot_session.scalar(
        select(Document.id).where(Document.project_id == project_id).limit(1)
    )
    summary = dict(
        tenant_id=str(user.tenant_id),
        project_id=str(project_id),
        document_id=str(doc_id),
        investigation_id=None,
        trace_id=str(uuid4()),
        task_type="classification",
        model="test",
        prompt_version="classification-v1",
        validation_result="valid",
        usage={"input_tokens": 10, "output_tokens": 20},
        latency_ms=12,
        cost_estimate=Decimal(".123456"),
        usage_complete=True,
        attempts=2,
        cost_currency="USD",
        raw_output="DO NOT PERSIST",
        messages="DO NOT PERSIST",
    )
    conn = await pilot_session.connection()

    def store(connection):
        engine = SimpleNamespace(begin=lambda: nullcontext(connection))
        persist_usage(summary, engine=engine)
        persist_usage(summary, engine=engine)
        with pytest.raises(ValueError):
            persist_usage(
                {**summary, "trace_id": str(uuid4()), "project_id": str(another_id)}, engine=engine
            )

    await conn.run_sync(store)
    row = await pilot_session.scalar(select(AITrace).where(AITrace.id == UUID(summary["trace_id"])))
    assert row.cost == Decimal(".123456")
    assert row.attributes["document_id"] == str(doc_id)
    assert "DO NOT PERSIST" not in str(row.attributes)


async def test_pipeline_records_durable_start_and_finish(pilot_session, metrics_seed, monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, Mock

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.document_processing.pipeline import STAGES, run_one_stage

    user, project_id, *_ = metrics_seed
    doc = Document(
        tenant_id=user.tenant_id,
        project_id=project_id,
        filename="timing.pdf",
        storage_key="test",
        mime_type="application/pdf",
        size_bytes=1,
        status="queued",
        processing_status="queued",
        processing_data={},
    )
    pilot_session.add(doc)
    await pilot_session.flush()

    @asynccontextmanager
    async def factory():
        async with AsyncSession(
            bind=pilot_session.bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session

    monkeypatch.setattr(
        "app.document_processing.pipeline.execute_stage",
        AsyncMock(return_value={"required": False}),
    )
    assert (
        await run_one_stage(doc.id, user.tenant_id, factory, services=Mock(), storage=Mock()) == 0
    )
    await pilot_session.refresh(doc)
    started = doc.processing_data["metrics"]["started_at"]
    doc.processing_data = {**doc.processing_data, "results": {stage: {} for stage in STAGES[:-1]}}
    await pilot_session.flush()
    assert (
        await run_one_stage(doc.id, user.tenant_id, factory, services=Mock(), storage=Mock())
        is None
    )
    await pilot_session.refresh(doc)
    assert doc.processing_status == "completed"
    timing = doc.processing_data["metrics"]
    assert datetime.fromisoformat(timing["started_at"]) <= datetime.fromisoformat(
        timing["finished_at"]
    )
    assert timing["started_at"] == started
    first = timing.copy()
    assert (
        await run_one_stage(doc.id, user.tenant_id, factory, services=Mock(), storage=Mock())
        is None
    )
    await pilot_session.refresh(doc)
    assert doc.processing_data["metrics"] == first


async def test_current_week_is_partial_and_offsets_normalize(pilot_session, metrics_seed):
    user, project_id, *_ = metrics_seed
    service = PilotMetricsService(pilot_session, user, clock=lambda: NOW)
    report = await service.report(project_id, NOW - timedelta(days=2), NOW + timedelta(days=3))
    assert report.end == NOW
    assert report.metrics.open_review_queue_age.value is None
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as failure:
        await service.report(project_id, NOW + timedelta(days=1), NOW + timedelta(days=2))
    assert failure.value.status_code == 422


async def test_usage_commits_independently_of_business_rollback(pilot_engine):
    import asyncio

    from sqlalchemy import create_engine
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy.pool import NullPool

    from app.ai.gateway.usage import persist_usage

    factory = async_sessionmaker(pilot_engine, expire_on_commit=False)
    async with factory() as session:
        tenant = Tenant(name="Usage durability", slug=uuid4().hex)
        session.add(tenant)
        await session.flush()
        project = Project(tenant_id=tenant.id, code=uuid4().hex, name="Usage project")
        session.add(project)
        await session.flush()
        doc = Document(
            tenant_id=tenant.id,
            project_id=project.id,
            filename="usage.pdf",
            storage_key="usage",
            mime_type="application/pdf",
            size_bytes=1,
        )
        session.add(doc)
        await session.commit()
        summary = dict(
            tenant_id=str(tenant.id),
            project_id=str(project.id),
            document_id=str(doc.id),
            investigation_id=None,
            trace_id=str(uuid4()),
            task_type="extraction",
            model="test",
            prompt_version="extraction-v1",
            validation_result="valid",
            usage={"input_tokens": 10, "output_tokens": 20},
            latency_ms=10,
            cost_estimate=Decimal(".01"),
            usage_complete=True,
            attempts=1,
            cost_currency="USD",
        )
        sync_engine = create_engine(
            pilot_engine.url.set(drivername="postgresql+psycopg2"),
            poolclass=NullPool,
            hide_parameters=True,
        )
        try:
            await asyncio.to_thread(persist_usage, summary, engine=sync_engine)
            doc.error_message = "Uncommitted business change"
            await session.flush()
            await session.rollback()
            saved = await session.scalar(
                select(AITrace).where(AITrace.id == UUID(summary["trace_id"]))
            )
            assert saved.cost == Decimal(".010000")
        finally:
            sync_engine.dispose()
