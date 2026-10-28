"""Real PostgreSQL migration, ownership, persistence, and transaction tests."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from alembic import command
from app.core import database
from app.core.database import Base
from app.domain.models import (
    RFI,
    AITrace,
    Approval,
    AuditEvent,
    BOQItem,
    ChangeOrder,
    Contract,
    ContractClause,
    Document,
    DocumentChunk,
    EvidenceLink,
    Project,
    ProjectEvent,
    Risk,
    Tenant,
    User,
)
from tests.conftest import migration_config
from tests.test_database_schema import FOUNDATION_TABLES, TABLES

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_migration_round_trip_and_no_metadata_drift(test_engine):
    async with test_engine.begin() as connection:
        names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert set(names) == TABLES | {"alembic_version"}
        assert (
            await connection.scalar(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
            == "vector"
        )
        differences = await connection.run_sync(
            lambda conn: compare_metadata(
                MigrationContext.configure(
                    conn, opts={"compare_type": True, "compare_server_default": True}
                ),
                Base.metadata,
            )
        )
        assert differences == []
        await connection.run_sync(lambda conn: command.downgrade(migration_config(conn), "base"))
        assert await connection.run_sync(lambda conn: inspect(conn).get_table_names()) == [
            "alembic_version"
        ]
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))


async def test_persist_complete_project_graph(test_session, tenant, project, user):
    session = test_session
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="contract.pdf",
        storage_key="test/contract",
        mime_type="application/pdf",
        size_bytes=42,
        uploaded_by_id=user.id,
    )
    session.add(document)
    await session.flush()
    chunk = DocumentChunk(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        chunk_index=0,
        text="Test clause",
        embedding=[0.0] * 1536,
    )
    event = ProjectEvent(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        event_type="instruction",
        title="Instruction",
        occurred_at=datetime.now(timezone.utc),
    )
    contract = Contract(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        reference="CT-1",
        title="Main contract",
        value=Decimal("1234.56"),
    )
    rfi = RFI(
        tenant_id=tenant.id,
        project_id=project.id,
        reference="RFI-1",
        subject="Clarify",
        question="Test?",
        requested_by_id=user.id,
    )
    session.add_all([chunk, event, contract, rfi])
    await session.flush()
    clause = ContractClause(
        tenant_id=tenant.id,
        project_id=project.id,
        contract_id=contract.id,
        clause_number="1.1",
        text="Test obligation",
    )
    boq = BOQItem(
        tenant_id=tenant.id,
        project_id=project.id,
        contract_id=contract.id,
        item_code="BOQ-1",
        description="Concrete",
        unit="m3",
        quantity=Decimal("1.25"),
        unit_rate=Decimal("80.25"),
    )
    order = ChangeOrder(
        tenant_id=tenant.id,
        project_id=project.id,
        reference="CO-1",
        title="Variation",
        contract_id=contract.id,
        rfi_id=rfi.id,
        created_by_id=user.id,
    )
    session.add_all([clause, boq, order])
    await session.flush()
    risk = Risk(
        tenant_id=tenant.id,
        project_id=project.id,
        title="Delay",
        change_order_id=order.id,
        document_id=document.id,
        project_event_id=event.id,
        owner_id=user.id,
    )
    session.add(risk)
    await session.flush()
    session.add_all(
        [
            Approval(
                tenant_id=tenant.id,
                project_id=project.id,
                change_order_id=order.id,
                assigned_to_id=user.id,
            ),
            EvidenceLink(
                tenant_id=tenant.id,
                project_id=project.id,
                risk_id=risk.id,
                document_chunk_id=chunk.id,
            ),
            AuditEvent(
                tenant_id=tenant.id,
                project_id=project.id,
                actor_id=user.id,
                action="created",
                entity_type="change_order",
                entity_id=order.id,
            ),
            AITrace(
                tenant_id=tenant.id,
                project_id=project.id,
                operation="classify",
                provider="test",
                model="test-model",
            ),
        ]
    )
    await session.flush()
    session.expunge_all()
    loaded = await session.scalar(
        select(Document).options(selectinload(Document.chunks)).where(Document.id == document.id)
    )
    assert len(loaded.chunks) == 1
    assert len(loaded.chunks[0].embedding) == 1536
    stored_order = await session.scalar(
        select(ChangeOrder)
        .options(selectinload(ChangeOrder.approvals))
        .where(ChangeOrder.id == order.id)
    )
    assert len(stored_order.approvals) == 1
    assert (await session.get(Contract, contract.id)).value == Decimal("1234.56")
    for table in Base.metadata.sorted_tables:
        if table.name not in FOUNDATION_TABLES:
            continue
        assert await session.scalar(select(table.c.id).limit(1)) is not None


@pytest.mark.parametrize(
    "boundary", ["project_tenant", "document_tenant", "document_project", "user_tenant"]
)
async def test_reject_cross_tenant_and_cross_project_links(
    test_session, tenant, project, user, boundary
):
    other_tenant = Tenant(name="Other", slug=uuid4().hex)
    test_session.add(other_tenant)
    await test_session.flush()
    other_project = Project(tenant_id=other_tenant.id, code="OTHER", name="Other")
    sibling_project = Project(tenant_id=tenant.id, code="SIBLING", name="Sibling")
    test_session.add_all([other_project, sibling_project])
    await test_session.flush()
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="file",
        storage_key="file",
        mime_type="text/plain",
        size_bytes=1,
    )
    test_session.add(document)
    await test_session.flush()
    if boundary == "project_tenant":
        invalid = Document(
            tenant_id=other_tenant.id,
            project_id=project.id,
            filename="invalid",
            storage_key="invalid",
            mime_type="text/plain",
            size_bytes=1,
        )
    elif boundary == "user_tenant":
        invalid = Document(
            tenant_id=other_tenant.id,
            project_id=other_project.id,
            filename="invalid",
            storage_key="invalid",
            mime_type="text/plain",
            size_bytes=1,
            uploaded_by_id=user.id,
        )
    else:
        invalid = DocumentChunk(
            tenant_id=other_tenant.id if boundary == "document_tenant" else tenant.id,
            project_id=other_project.id if boundary == "document_tenant" else sibling_project.id,
            document_id=document.id,
            chunk_index=1,
            text="invalid",
        )
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(invalid)
            await test_session.flush()


async def test_tenant_scoped_uniqueness_and_orphan_rejection(test_session, tenant, user):
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(
                User(
                    tenant_id=tenant.id,
                    email=user.email,
                    full_name="Duplicate",
                    password_hash="test",
                )
            )
            await test_session.flush()
    another = Tenant(name="Another", slug=uuid4().hex)
    test_session.add(another)
    await test_session.flush()
    test_session.add(
        User(tenant_id=another.id, email=user.email, full_name="Allowed", password_hash="test")
    )
    await test_session.flush()
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(Project(tenant_id=uuid4(), code="ORPHAN", name="Orphan"))
            await test_session.flush()


@pytest.mark.parametrize("target", ["neither", "both"])
async def test_approval_requires_exactly_one_subject(test_session, tenant, project, target):
    order = ChangeOrder(tenant_id=tenant.id, project_id=project.id, reference="CO-1", title="Test")
    risk = Risk(tenant_id=tenant.id, project_id=project.id, title="Test")
    test_session.add_all([order, risk])
    await test_session.flush()
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(
                Approval(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    change_order_id=order.id if target == "both" else None,
                    risk_id=risk.id if target == "both" else None,
                )
            )
            await test_session.flush()


async def test_database_timestamp_trigger_handles_raw_sql(test_session, tenant):
    previous = tenant.updated_at
    await test_session.execute(
        text("UPDATE tenants SET name = 'Updated' WHERE id = :id"), {"id": tenant.id}
    )
    await test_session.refresh(tenant)
    assert tenant.updated_at > previous
    assert tenant.updated_at.tzinfo is not None


@pytest.mark.parametrize("invalid", ["no_claim", "no_source", "multiple_sources"])
async def test_evidence_requires_one_claim_and_one_source(test_session, tenant, project, invalid):
    order = ChangeOrder(
        tenant_id=tenant.id, project_id=project.id, reference="CO-E", title="Evidence"
    )
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="file",
        storage_key="file",
        mime_type="text/plain",
        size_bytes=1,
    )
    event = ProjectEvent(
        tenant_id=tenant.id,
        project_id=project.id,
        event_type="instruction",
        title="Test",
        occurred_at=datetime.now(timezone.utc),
    )
    test_session.add_all([order, document, event])
    await test_session.flush()
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(
                EvidenceLink(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    change_order_id=None if invalid == "no_claim" else order.id,
                    document_id=None if invalid == "no_source" else document.id,
                    project_event_id=event.id if invalid == "multiple_sources" else None,
                )
            )
            await test_session.flush()


async def test_session_commit_remains_isolated(test_session, test_engine):
    tenant = Tenant(name="Uncommitted", slug=uuid4().hex)
    test_session.add(tenant)
    await test_session.commit()
    async with test_engine.connect() as connection:
        assert await connection.scalar(select(Tenant.id).where(Tenant.id == tenant.id)) is None


async def test_fastapi_session_dependency_commits_and_rolls_back(test_session, monkeypatch):
    monkeypatch.setattr(
        database,
        "async_session_maker",
        async_sessionmaker(
            bind=test_session.bind,
            class_=AsyncSession,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ),
    )
    good_id, bad_id = uuid4(), uuid4()
    dependency = database.get_session()
    session = await anext(dependency)
    session.add(Tenant(id=good_id, name="Good", slug=uuid4().hex))
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)
    assert await test_session.get(Tenant, good_id) is not None
    dependency = database.get_session()
    session = await anext(dependency)
    session.add(Tenant(id=bad_id, name="Bad", slug=uuid4().hex))
    await session.flush()
    with pytest.raises(ValueError):
        await dependency.athrow(ValueError("rollback"))
    assert await test_session.get(Tenant, bad_id) is None
