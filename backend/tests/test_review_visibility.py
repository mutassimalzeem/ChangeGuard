"""Visibility parity across source paths and committed changes between requests."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.api.dependencies import get_current_user
from app.api.exceptions import AuthorizationError
from app.core.database import ScopedAsyncSession, get_session
from app.core.security import create_access_token
from app.domain.models import (
    RFI,
    Approval,
    AuditEvent,
    BOQItem,
    ChangeOrder,
    Contract,
    ContractClause,
    Document,
    DocumentChunk,
    DocumentReviewTask,
    EvidenceLink,
    Project,
    ProjectEvent,
    ProjectMembership,
    Risk,
    SitePhoto,
    Tenant,
    User,
)
from app.main import app
from app.policy.review_page import REVIEW_PAGE
from tests.conftest import disposable_database_url, migration_config


@pytest.mark.parametrize("restriction", ["project", "document", "deleted", "chunk", "uploader"])
async def test_mixed_source_visibility(client, test_session, tenant, project, user, restriction):
    scope = dict(tenant_id=tenant.id, project_id=project.id)
    user.role = "commercial_manager"
    test_session.add(ProjectMembership(**scope, user_id=user.id))
    doc = Document(
        **scope,
        filename="Signed report",
        storage_key="source",
        mime_type="application/pdf",
        size_bytes=1,
        access_level="restricted" if restriction in {"document", "uploader"} else "project",
        deleted_at=datetime.now(UTC) if restriction == "deleted" else None,
        uploaded_by_id=user.id if restriction == "uploader" else None,
    )
    public = Document(
        **scope, filename="Public", storage_key="public", mime_type="text/plain", size_bytes=1
    )
    test_session.add_all([doc, public])
    await test_session.flush()
    contract = Contract(**scope, reference="C1", title="Contract", document_id=doc.id)
    evt = ProjectEvent(
        **scope,
        title="Instruction",
        event_type="instruction",
        occurred_at=datetime.now(UTC),
        document_id=doc.id,
    )
    rfi = RFI(**scope, reference="R1", subject="RFI", question="Confirm?", document_id=doc.id)
    test_session.add_all([contract, evt, rfi])
    await test_session.flush()
    sources = {
        "document": doc,
        "site_photo": SitePhoto(**scope, document_id=doc.id),
        "document_chunk": DocumentChunk(
            **scope,
            document_id=doc.id,
            chunk_index=0,
            text="Notice",
            access_level="restricted" if restriction in {"uploader", "chunk"} else "project",
        ),
        "project_event": evt,
        "contract_clause": ContractClause(
            **scope, contract_id=contract.id, clause_number="1", text="Notify"
        ),
        "boq_item": BOQItem(
            **scope,
            contract_id=contract.id,
            item_code="A",
            description="Concrete",
            unit="m3",
            quantity=1,
            unit_rate=1,
        ),
    }
    test_session.add_all(sources.values())
    await test_session.flush()
    expected = set()
    hidden = set()
    for kind, source in sources.items():
        risk = Risk(**scope, title=f"Risk {kind}", severity="high")
        test_session.add(risk)
        await test_session.flush()
        for tag, source_id in [(kind, source.id), ("document", public.id)]:
            test_session.add(
                EvidenceLink(
                    **scope,
                    subject_type="risk",
                    subject_id=risk.id,
                    source_type=tag,
                    source_id=source_id,
                    source_page=1,
                    source_text_snippet=f"Source for {kind}",
                )
            )
        visible = (
            restriction in {"project", "uploader"}
            or restriction == "chunk"
            and kind != "document_chunk"
        )
        (expected if visible else hidden).add(str(risk.id))
    # An order and its approval may inherit their only restricted source indirectly.
    for name, args in [
        ("contract", {"contract_id": contract.id}),
        ("rfi", {"rfi_id": rfi.id}),
        ("event", {"source_event_id": evt.id}),
    ]:
        order = ChangeOrder(**scope, reference=name, title=name, status="submitted", **args)
        test_session.add(order)
        await test_session.flush()
        approval = Approval(**scope, change_order_id=order.id)
        test_session.add(approval)
        await test_session.flush()
        (expected if restriction in {"project", "chunk", "uploader"} else hidden).add(
            str(approval.id)
        )

    linked = Risk(
        **scope, title="Risk with a linked order", severity="high", change_order_id=order.id
    )
    test_session.add(linked)
    await test_session.flush()
    risk_approval = Approval(**scope, risk_id=linked.id)
    test_session.add(risk_approval)
    await test_session.flush()
    (expected if restriction in {"project", "chunk", "uploader"} else hidden).update(
        (str(linked.id), str(risk_approval.id))
    )

    async def current():
        return user

    app.dependency_overrides[get_current_user] = current
    url = f"/api/v1/projects/{project.id}/review-queue/workspace"
    result = await client.get(url, params={"status": "all"})
    assert result.status_code == 200, result.text
    assert {row["id"] for row in result.json()["items"]} == expected
    assert result.json()["total"] == len(expected)
    assert all(record_id not in result.text for record_id in hidden)
    # A visible sibling quotation must never authorize a partially concealed subject.
    for record_id in hidden:
        for kind in ("risk", "approval"):
            assert (await client.get(f"{url}/{kind}/{record_id}")).status_code == 404


async def test_access_changes_across_transactions(client):
    """Leave two transactions open, commit a writer, then reuse the same reader connection."""
    async with disposable_database_url() as url:
        engine = create_async_engine(url)
        try:
            t, p, u, d, task, other = (uuid4() for _ in range(6))
            scope = dict(tenant_id=t, project_id=p)
            async with engine.begin() as setup:
                await setup.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
                await setup.execute(insert(Tenant).values(id=t, name="Test", slug="isolated"))
                await setup.execute(
                    insert(Project).values(id=p, tenant_id=t, code="P", name="Project")
                )
                await setup.execute(
                    insert(User).values(
                        id=u,
                        tenant_id=t,
                        role="project_manager",
                        email="m@example.invalid",
                        full_name="Manager",
                        password_hash="test",
                    )
                )
                await setup.execute(insert(ProjectMembership).values(**scope, user_id=u))
                await setup.execute(
                    insert(Document).values(
                        **scope,
                        id=d,
                        filename="Private plan",
                        storage_key="p",
                        mime_type="text/plain",
                        size_bytes=1,
                    )
                )
                await setup.execute(
                    insert(DocumentReviewTask).values(
                        **scope, id=task, document_id=d, reason="low_confidence"
                    )
                )
                await setup.execute(
                    insert(AuditEvent).values(
                        **scope,
                        entity_type="document_review_task",
                        entity_id=task,
                        actor_id=u,
                        action="review.add_note",
                        details={"reason": "Private note"},
                    )
                )
            async with engine.connect() as reader:

                async def fresh():
                    async with ScopedAsyncSession(bind=reader, expire_on_commit=False) as session:
                        yield session

                app.dependency_overrides[get_session] = fresh
                headers = {
                    "Authorization": "Bearer "
                    + create_access_token(str(u), str(t), ["project_manager"])
                }
                root = f"/api/v1/projects/{p}/review-queue/workspace"

                async def fetch(path=root):
                    return await client.get(path, headers=headers)

                async with engine.connect() as writer:
                    await writer.execute(
                        update(Document).where(Document.id == d).values(access_level="restricted")
                    )
                    # An uncommitted writer does not block or partially change the read.
                    before = await asyncio.wait_for(fetch(), timeout=5)
                    assert before.json()["total"] == 1
                    assert before.json()["items"][0]["history"][0]["reason"] == "Private note"
                    await writer.commit()
                    hidden = await fetch()
                    assert (
                        hidden.json() == {"items": [], "total": 0}
                        and "Private note" not in hidden.text
                    )
                    assert (await fetch(f"{root}/extraction/{task}")).status_code == 404
                    await writer.execute(update(User).where(User.id == u).values(role="admin"))
                    await writer.commit()
                    assert (await fetch()).json()["total"] == 1
                    await writer.execute(update(User).where(User.id == u).values(role="viewer"))
                    await writer.commit()
                    assert (await fetch()).status_code == 403
                    await writer.execute(
                        update(User).where(User.id == u).values(role="project_manager")
                    )
                    await writer.execute(
                        update(ProjectMembership)
                        .where(ProjectMembership.user_id == u)
                        .values(is_active=False)
                    )
                    await writer.commit()
                    assert (await fetch()).status_code == 404
                    assert (
                        await fetch(f"/api/v1/projects/{other}/review-queue/workspace")
                    ).status_code == 404
        finally:
            await engine.dispose()


async def test_fixed_read_rejects_unbound_session_and_statement_copies(
    test_session, tenant, project, user
):
    from app.policy.scope import bind_scope

    with pytest.raises(AuthorizationError):
        await test_session.execute(REVIEW_PAGE, {})
    user.role = "owner"
    await test_session.flush()
    bind_scope(test_session, user)
    with pytest.raises(AuthorizationError):
        await test_session.execute(REVIEW_PAGE.params(actor_id=uuid4()), {})
