"""Explicit source-event relationships resolve only their own risks, atomically."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import AuthorizationError
from app.core.database import ScopedAsyncSession, get_session
from app.core.security import create_access_token
from app.domain.models import (
    RFI,
    AuditEvent,
    ChangeOrder,
    Document,
    EventEntityLink,
    EvidenceLink,
    Project,
    ProjectEvent,
    ProjectMembership,
    Risk,
    Tenant,
    User,
)
from app.main import app
from app.policy.scope import bind_scope


def headers(user):
    return {
        "Authorization": "Bearer "
        + create_access_token(
            str(user.id), str(user.tenant_id), [user.role], version=user.token_version
        )
    }


@pytest.fixture
async def linked_world(test_session, tenant, project, user):
    user.role = "owner"
    users = {}
    for role in ["project_manager", "site_engineer", "viewer"]:
        actor = User(
            tenant_id=tenant.id,
            email=f"{role}@example.invalid",
            full_name=role,
            password_hash="test",
            role=role,
        )
        test_session.add(actor)
        await test_session.flush()
        test_session.add(
            ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=actor.id)
        )
        users[role] = actor
    nonmember = User(
        tenant_id=tenant.id,
        email="nonmember@example.invalid",
        full_name="No membership",
        password_hash="test",
        role="project_manager",
    )
    other_tenant = Tenant(name="Other tenant", slug=uuid4().hex)
    other_project = Project(tenant_id=tenant.id, code="OTHER", name="Another project")
    test_session.add_all([nonmember, other_tenant, other_project])
    await test_session.flush()
    outsider = User(
        tenant_id=other_tenant.id,
        email="outsider@example.invalid",
        full_name="Outsider",
        password_hash="test",
        role="owner",
    )
    document = Document(
        tenant_id=tenant.id,
        project_id=project.id,
        filename="daily_report.pdf",
        storage_key="original",
        mime_type="application/pdf",
        size_bytes=1,
        status="linked",
        document_type="daily_report",
    )
    test_session.add_all([outsider, document])
    await test_session.flush()
    event = ProjectEvent(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        event_type="delay",
        title="Reported delay",
        detection_key=uuid4().hex,
        description="Work delayed.",
        occurred_at=datetime.now(UTC),
        status="potential_change",
        confidence="0.95",
    )
    unrelated = ProjectEvent(
        tenant_id=tenant.id,
        project_id=project.id,
        document_id=document.id,
        event_type="delay",
        title="Similar reported delay",
        detection_key=uuid4().hex,
        description="Work delayed.",
        occurred_at=datetime.now(UTC),
        status="potential_change",
        confidence="0.95",
    )
    rfi = RFI(
        tenant_id=tenant.id,
        project_id=project.id,
        reference="RFI-1",
        subject="Reported delay",
        question="Work delayed.",
    )
    order = ChangeOrder(
        tenant_id=tenant.id,
        project_id=project.id,
        reference="CO-1",
        title="Reported delay",
        description="Work delayed.",
    )
    foreign_rfi = RFI(
        tenant_id=tenant.id,
        project_id=other_project.id,
        reference="RFI-OTHER",
        subject="Reported delay",
        question="Work delayed.",
    )
    test_session.add_all([event, unrelated, rfi, order, foreign_rfi])
    await test_session.flush()
    risk = Risk(
        tenant_id=tenant.id,
        project_id=project.id,
        project_event_id=event.id,
        document_id=document.id,
        title="Daily report delay without link",
        description="Daily report indicates delay.",
        risk_type="daily_report_delay_without_link",
        status="open",
        confidence="0.95",
    )
    test_session.add(risk)
    await test_session.flush()
    original_links = []
    for kind, subject in [("risk", risk), ("project_event", event), ("project_event", unrelated)]:
        link = EvidenceLink(
            tenant_id=tenant.id,
            project_id=project.id,
            subject_type=kind,
            subject_id=subject.id,
            source_type="document",
            source_id=document.id,
            source_page=1,
            source_text_snippet="Work delayed.",
        )
        test_session.add(link)
        original_links.append(link)
    await test_session.flush()

    async def request_session():
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

    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = request_session
    yield SimpleNamespace(
        owner=user,
        users=users,
        nonmember=nonmember,
        outsider=outsider,
        project_id=project.id,
        event_id=event.id,
        unrelated_id=unrelated.id,
        risk_id=risk.id,
        rfi_id=rfi.id,
        order_id=order.id,
        foreign_rfi_id=foreign_rfi.id,
        document_id=document.id,
        evidence_ids=[link.id for link in original_links],
    )
    if previous is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = previous


async def link(client, world, entity_type="rfi", *, actor=None, event_id=None, entity_id=None):
    return await client.post(
        f"/api/v1/projects/{world.project_id}/events/{event_id or world.event_id}/links",
        headers=headers(actor or world.owner),
        json={
            "entity_type": entity_type,
            "entity_id": str(
                entity_id or (world.rfi_id if entity_type == "rfi" else world.order_id)
            ),
            "reason": "Explicitly linked after project review",
        },
    )


@pytest.mark.parametrize("entity_type", ["rfi", "change_order"])
async def test_later_explicit_link_resolves_and_retains_original_history(
    client, linked_world, test_session, entity_type
):
    world = linked_world
    response = await link(client, world, entity_type)
    assert response.status_code == 200, response.text
    bind_scope(test_session, world.owner)
    risk = await test_session.scalar(select(Risk).where(Risk.id == world.risk_id))
    assert risk.status == "resolved"
    assert risk.project_event_id == world.event_id
    assert risk.description == "Daily report indicates delay."
    assert {e.id for e in await test_session.scalars(select(EvidenceLink))} == set(
        world.evidence_ids
    )
    (audit,) = list(
        await test_session.scalars(select(AuditEvent).where(AuditEvent.action == "risk.resolve"))
    )
    assert audit.actor_id == world.owner.id and audit.entity_id == world.risk_id
    assert audit.details["resolving_entity_type"] == entity_type
    assert audit.details["resolving_entity_id"] == str(
        world.rfi_id if entity_type == "rfi" else world.order_id
    )
    assert audit.details["reason"] == "Explicitly linked after project review"
    assert datetime.fromisoformat(audit.details["resolved_at"]).tzinfo is not None
    read = await client.get(
        f"/api/v1/projects/{world.project_id}/risks/{world.risk_id}", headers=headers(world.owner)
    )
    assert read.json()["resolution"]["entity_type"] == entity_type
    assert read.json()["resolution"]["actor_id"] == str(world.owner.id)
    assert audit.request_id == response.headers["X-Request-ID"]
    timeline = await client.get(
        f"/api/v1/projects/{world.project_id}/timeline", headers=headers(world.owner)
    )
    (row,) = [row for row in timeline.json()["items"] if row["id"] == str(world.risk_id)]
    assert row["status"] == "resolved" and row["resolution"]["entity_type"] == entity_type


async def test_similar_entity_or_unrelated_event_does_not_resolve(
    client, linked_world, test_session
):
    world = linked_world
    # Identical descriptions are insufficient until the exact event is linked.
    response = await link(client, world, event_id=world.unrelated_id)
    assert response.status_code == 200, response.text
    bind_scope(test_session, world.owner)
    risk = await test_session.scalar(select(Risk).where(Risk.id == world.risk_id))
    assert risk.status == "open"
    assert (
        await test_session.scalar(select(AuditEvent.id).where(AuditEvent.action == "risk.resolve"))
        is None
    )


@pytest.mark.parametrize(
    "role,status", [("viewer", 403), ("site_engineer", 403), ("project_manager", 200)]
)
async def test_link_permissions(client, linked_world, role, status):
    response = await link(client, linked_world, actor=linked_world.users[role])
    assert response.status_code == status, response.text


@pytest.mark.parametrize("actor", ["nonmember", "outsider"])
async def test_other_tenants_and_nonmembers_cannot_link(client, linked_world, actor):
    response = await link(client, linked_world, actor=getattr(linked_world, actor))
    assert response.status_code == 404, response.text


async def test_cross_project_target_and_invalid_reason_rejected(client, linked_world):
    world = linked_world
    assert (await link(client, world, entity_id=world.foreign_rfi_id)).status_code == 404
    response = await client.post(
        f"/api/v1/projects/{world.project_id}/events/{world.event_id}/links",
        headers=headers(world.owner),
        json={"entity_type": "rfi", "entity_id": str(world.rfi_id), "reason": "  "},
    )
    assert response.status_code == 422


async def test_repeated_link_does_not_duplicate_or_overwrite_resolution(
    client, linked_world, test_session
):
    first = await link(client, linked_world)
    assert first.status_code == 200, first.text
    assert (await link(client, linked_world)).json()["link"]["id"] == first.json()["link"]["id"]
    assert (await link(client, linked_world, "change_order")).status_code == 200
    bind_scope(test_session, linked_world.owner)
    audits = list(
        await test_session.scalars(select(AuditEvent).where(AuditEvent.action == "risk.resolve"))
    )
    assert len(audits) == 1
    assert audits[0].details["resolving_entity_type"] == "rfi"


async def test_creating_change_order_from_exact_event_resolves(client, linked_world):
    world = linked_world
    response = await client.post(
        f"/api/v1/projects/{world.project_id}/change-orders",
        headers=headers(world.owner),
        json={
            "reference": "CO-LATER",
            "title": "Formal record",
            "source_event_id": str(world.event_id),
        },
    )
    assert response.status_code == 201, response.text
    risk = await client.get(
        f"/api/v1/projects/{world.project_id}/risks/{world.risk_id}", headers=headers(world.owner)
    )
    assert risk.json()["status"] == "resolved"
    assert risk.json()["resolution"]["entity_id"] == response.json()["id"]


async def test_change_order_without_explicit_event_does_not_resolve(client, linked_world):
    world = linked_world
    response = await client.post(
        f"/api/v1/projects/{world.project_id}/change-orders",
        headers=headers(world.owner),
        json={"reference": "CO-SIMILAR", "title": "Reported delay", "description": "Work delayed."},
    )
    assert response.status_code == 201, response.text
    risk = await client.get(
        f"/api/v1/projects/{world.project_id}/risks/{world.risk_id}", headers=headers(world.owner)
    )
    assert risk.json()["status"] == "open" and risk.json()["resolution"] is None


async def test_copied_event_provenance_is_not_a_new_explicit_link(
    client, linked_world, test_session
):
    world = linked_world
    unrelated_risk = Risk(
        tenant_id=world.owner.tenant_id,
        project_id=world.project_id,
        project_event_id=world.unrelated_id,
        document_id=world.document_id,
        title="Another report delay",
        risk_type="daily_report_delay_without_link",
    )
    test_session.add(unrelated_risk)
    test_session.add(
        EvidenceLink(
            tenant_id=world.owner.tenant_id,
            project_id=world.project_id,
            subject_type="project_event",
            subject_id=world.event_id,
            source_type="project_event",
            source_id=world.unrelated_id,
        )
    )
    await test_session.flush()
    other_id = unrelated_risk.id
    response = await client.post(
        f"/api/v1/projects/{world.project_id}/change-orders",
        headers=headers(world.owner),
        json={
            "reference": "CO-COPY",
            "title": "Formal record",
            "source_event_id": str(world.event_id),
        },
    )
    assert response.status_code == 201, response.text
    bind_scope(test_session, world.owner)
    assert (await test_session.scalar(select(Risk).where(Risk.id == other_id))).status == "open"
    assert (
        await test_session.scalar(
            select(EventEntityLink.id).where(EventEntityLink.event_id == world.unrelated_id)
        )
        is None
    )


async def test_existing_change_order_event_evidence_path_resolves(client, linked_world):
    world = linked_world
    response = await client.post(
        f"/api/v1/projects/{world.project_id}/evidence/change_order/{world.order_id}",
        headers=headers(world.owner),
        json=[{"source_type": "project_event", "source_id": str(world.event_id)}],
    )
    assert response.status_code == 201, response.text
    risk = await client.get(
        f"/api/v1/projects/{world.project_id}/risks/{world.risk_id}", headers=headers(world.owner)
    )
    assert risk.json()["status"] == "resolved"


async def test_restricted_source_cannot_be_used_for_resolution(client, linked_world, test_session):
    world = linked_world
    doc = await test_session.get(Document, world.document_id)
    doc.access_level = "restricted"
    await test_session.flush()
    response = await link(client, world, actor=world.users["project_manager"])
    assert response.status_code == 404
    bind_scope(test_session, world.owner)
    assert (
        await test_session.scalar(select(Risk).where(Risk.id == world.risk_id))
    ).status == "open"
    assert await test_session.scalar(select(EventEntityLink.id)) is None


async def test_resolved_risk_cannot_be_reopened_via_review(client, linked_world):
    world = linked_world
    assert (await link(client, world)).status_code == 200
    response = await client.post(
        f"/api/v1/projects/{world.project_id}/risks/{world.risk_id}/decisions",
        headers=headers(world.owner),
        json={"action": "dismiss", "reason": "Try changing history"},
    )
    assert response.status_code == 409, response.text


async def test_rerun_rule_keeps_resolved_risk_and_no_duplicate_delay(
    client, linked_world, test_session
):
    from app.domain.services.risk_engine import run_risk_checks

    world = linked_world
    assert (await link(client, world)).status_code == 200
    # Exercise the same trusted, scoped-by-document worker boundary as Celery.
    async with AsyncSession(
        bind=test_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as worker:
        document = await worker.get(Document, world.document_id)
        await run_risk_checks(document, worker)
        await worker.flush()
    bind_scope(test_session, world.owner)
    risks = list(
        await test_session.scalars(
            select(Risk).where(Risk.risk_type == "daily_report_delay_without_link")
        )
    )
    assert len(risks) == 1 and risks[0].status == "resolved"


async def test_failure_to_write_resolution_audit_rolls_back_link_and_status(
    client, linked_world, test_session
):
    def fail_audit(mapper, connection, target):
        if target.action == "risk.resolve":
            raise RuntimeError("audit unavailable")

    sa_event.listen(AuditEvent, "before_insert", fail_audit)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await link(client, linked_world)
    finally:
        sa_event.remove(AuditEvent, "before_insert", fail_audit)
    bind_scope(test_session, linked_world.owner)
    assert await test_session.scalar(select(EventEntityLink.id)) is None
    risk = await test_session.scalar(select(Risk).where(Risk.id == linked_world.risk_id))
    assert risk.status == "open" and risk.resolution_link_id is None


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE event_entity_links SET reason='replacement'",
        "DELETE FROM event_entity_links",
        "UPDATE risks SET resolution_reason='replacement' WHERE resolution_link_id IS NOT NULL",
        "DELETE FROM audit_events WHERE action='risk.resolve'",
    ],
)
async def test_resolution_history_is_immutable_even_in_sql(
    client, linked_world, test_session, statement
):
    assert (await link(client, linked_world)).status_code == 200
    bind_scope(test_session, linked_world.owner)
    with pytest.raises(DBAPIError, match="append_only|immutable"):
        async with test_session.begin_nested():
            await (await test_session.connection()).execute(text(statement))


async def test_database_rejects_resolution_without_audit(linked_world, test_session):
    world = linked_world
    with pytest.raises(DBAPIError, match="risk_resolution_requires_audit"):
        async with test_session.begin_nested():
            connection = await test_session.connection()
            link_id = uuid4()
            await connection.execute(
                insert(EventEntityLink.__table__).values(
                    id=link_id,
                    tenant_id=world.owner.tenant_id,
                    project_id=world.project_id,
                    event_id=world.event_id,
                    rfi_id=world.rfi_id,
                    actor_id=world.owner.id,
                    reason="Reviewed",
                )
            )
            await connection.execute(
                update(Risk.__table__)
                .where(Risk.id == world.risk_id)
                .values(
                    status="resolved",
                    resolution_link_id=link_id,
                    resolved_by_id=world.owner.id,
                    resolved_at=datetime.now(UTC),
                    resolution_reason="Reviewed",
                )
            )
            await connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_status_and_resolution_metadata_require_audited_service(linked_world, test_session):
    world = linked_world
    bind_scope(test_session, world.owner)
    for changes in ({"status": "resolved"}, {"resolved_by_id": world.owner.id}):
        with pytest.raises(AuthorizationError):
            async with test_session.begin_nested():
                risk = await test_session.scalar(select(Risk).where(Risk.id == world.risk_id))
                for field, value in changes.items():
                    setattr(risk, field, value)
                await test_session.flush()


async def test_resolution_entity_visibility_is_checked_on_later_reads(
    client, linked_world, test_session
):
    world = linked_world
    assert (await link(client, world)).status_code == 200
    # A later restriction on the resolving RFI's source must not leak its ID/reason.
    doc = Document(
        tenant_id=world.owner.tenant_id,
        project_id=world.project_id,
        filename="rfi.pdf",
        storage_key="rfi-restricted",
        mime_type="application/pdf",
        size_bytes=1,
        access_level="restricted",
    )
    test_session.add(doc)
    await test_session.flush()
    rfi = await test_session.get(RFI, world.rfi_id)
    rfi.document_id = doc.id
    await test_session.flush()
    pm = world.users["project_manager"]
    response = await client.get(
        f"/api/v1/projects/{world.project_id}/risks/{world.risk_id}", headers=headers(pm)
    )
    assert response.status_code == 404
    timeline = await client.get(
        f"/api/v1/projects/{world.project_id}/timeline", headers=headers(pm)
    )
    assert all(row["id"] != str(world.risk_id) for row in timeline.json()["items"])
