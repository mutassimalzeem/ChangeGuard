"""RBAC and mandatory query scoping against a real PostgreSQL database."""

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from sqlalchemy import func, literal_column, select, text, update
from sqlalchemy.exc import IntegrityError, InvalidRequestError, NoResultFound
from sqlalchemy.orm import aliased, joinedload, selectinload, undefer

from alembic import command
from app.api.dependencies import (
    require_authenticated_user,
    require_permission,
    require_policy_action,
    require_project_access,
    require_role,
    require_tenant_access,
)
from app.api.exceptions import AuthorizationError, ChangeGuardException
from app.core.database import get_session
from app.core.security import create_access_token
from app.domain.models import (
    AuditEvent,
    AuthSession,
    ChangeOrder,
    Document,
    Project,
    ProjectMembership,
    Tenant,
    User,
)
from app.domain.services.project_access import ProjectAccessService
from app.main import changeguard_exception_handler
from app.policy.permissions import Action, Role
from app.policy.scope import SCOPE_KEY, bind_scope, project_record_data
from tests.conftest import migration_config

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def world(test_session):
    """Seed two tenants, assigned/unassigned projects, and financial records."""
    session = test_session
    tenants = [Tenant(name=f"Tenant {n}", slug=uuid4().hex) for n in range(2)]
    session.add_all(tenants)
    await session.flush()
    user = User(
        tenant_id=tenants[0].id,
        email="viewer@example.com",
        full_name="User",
        password_hash="test",
        role="viewer",
    )
    outsider = User(
        tenant_id=tenants[1].id,
        email="outsider@example.com",
        full_name="Outsider",
        password_hash="test",
        role="owner",
    )
    projects = [
        Project(tenant_id=tenants[0].id, code="A", name="Assigned"),
        Project(tenant_id=tenants[0].id, code="B", name="Unassigned"),
        Project(tenant_id=tenants[1].id, code="C", name="Foreign"),
    ]
    session.add_all([user, outsider, *projects])
    await session.flush()
    orders, documents = [], []
    for n, project in enumerate(projects):
        order = ChangeOrder(
            tenant_id=project.tenant_id,
            project_id=project.id,
            reference=f"CO-{n}",
            title=f"Order {n}",
            amount=Decimal("1234.56"),
        )
        document = Document(
            tenant_id=project.tenant_id,
            project_id=project.id,
            filename=f"file-{n}",
            storage_key=f"file-{n}",
            mime_type="text/plain",
            size_bytes=1,
        )
        session.add_all([order, document])
        orders.append(order)
        documents.append(document)
    session.add(
        ProjectMembership(tenant_id=user.tenant_id, project_id=projects[0].id, user_id=user.id)
    )
    await session.flush()
    data = {
        "user": user,
        "outsider": outsider,
        "user_id": user.id,
        "tenant_id": tenants[0].id,
        "foreign_tenant": tenants[1].id,
        "projects": [p.id for p in projects],
        "orders": [o.id for o in orders],
        "documents": [d.id for d in documents],
    }
    yield data
    session.info.pop(SCOPE_KEY, None)


@pytest_asyncio.fixture
async def rbac_client(test_session):
    probe = FastAPI()
    probe.add_exception_handler(ChangeGuardException, changeguard_exception_handler)

    async def session():
        try:
            yield test_session
        finally:
            test_session.info.pop(SCOPE_KEY, None)

    probe.dependency_overrides[get_session] = session

    @probe.get("/projects/{project_id}")
    async def project_route(project: Project = Depends(require_project_access)):
        return {"id": str(project.id)}

    @probe.get("/tenants/{tenant_id}")
    async def tenant_route(user: User = Depends(require_tenant_access)):
        return {"tenant_id": str(user.tenant_id)}

    @probe.get("/admin")
    async def admin_route(user: User = Depends(require_role(Role.OWNER, Role.ADMIN))):
        return {"role": user.role}

    @probe.get("/financial")
    async def financial_route(user: User = Depends(require_permission(Action.FINANCIAL_READ))):
        return {"role": user.role}

    @probe.post("/projects/{project_id}/release")
    async def release_route(
        project: Project = Depends(require_policy_action(Action.FINANCIAL_RELEASE)),
    ):
        return {"id": str(project.id)}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=probe), base_url="http://test"
    ) as client:
        yield client


def bearer(world, role="owner"):
    # Deliberately claim owner in JWT: dependencies must use the database role.
    value = create_access_token(str(world["user_id"]), str(world["tenant_id"]), [role])
    return {"Authorization": "Bearer " + value}


async def test_valid_membership_and_cross_tenant_project_denial(rbac_client, world):
    headers = bearer(world)
    assert (
        await rbac_client.get(f"/projects/{world['projects'][0]}", headers=headers)
    ).status_code == 200
    assert (
        await rbac_client.get(f"/projects/{world['projects'][1]}", headers=headers)
    ).status_code == 404
    assert (
        await rbac_client.get(f"/projects/{world['projects'][2]}", headers=headers)
    ).status_code == 404
    assert (await rbac_client.get(f"/projects/{uuid4()}", headers=headers)).status_code == 404
    assert (await rbac_client.get(f"/projects/{world['projects'][0]}")).status_code == 401


async def test_tenant_and_role_dependencies_ignore_forged_role_claim(rbac_client, world):
    headers = bearer(world)
    assert (
        await rbac_client.get(f"/tenants/{world['tenant_id']}", headers=headers)
    ).status_code == 200
    assert (
        await rbac_client.get(f"/tenants/{world['foreign_tenant']}", headers=headers)
    ).status_code == 403
    assert (await rbac_client.get("/admin", headers=headers)).status_code == 403
    assert (await rbac_client.get("/financial", headers=headers)).status_code == 403


async def test_owner_bypasses_membership_but_not_tenant_and_needs_approval(
    rbac_client, world, test_session
):
    world["user"].role = "owner"
    await test_session.flush()
    headers = bearer(world)
    assert (
        await rbac_client.get(f"/projects/{world['projects'][1]}", headers=headers)
    ).status_code == 200
    assert (
        await rbac_client.get(f"/projects/{world['projects'][2]}", headers=headers)
    ).status_code == 404
    assert (await rbac_client.get("/admin", headers=headers)).status_code == 200
    assert (
        await rbac_client.post(f"/projects/{world['projects'][0]}/release", headers=headers)
    ).status_code == 409


async def test_revoked_project_membership_takes_effect(rbac_client, world, test_session):
    headers = bearer(world)
    assert (
        await rbac_client.get(f"/projects/{world['projects'][0]}", headers=headers)
    ).status_code == 200
    membership = await test_session.scalar(
        select(ProjectMembership).where(ProjectMembership.user_id == world["user_id"])
    )
    membership.is_active = False
    await test_session.flush()
    assert (
        await rbac_client.get(f"/projects/{world['projects'][0]}", headers=headers)
    ).status_code == 404


async def test_selects_aliases_counts_relationships_and_identity_map_are_scoped(
    test_session, world
):
    bind_scope(test_session, world["user"])
    assert (await test_session.scalars(select(Project.id))).all() == [world["projects"][0]]
    assert await test_session.scalar(select(func.count(Document.id))) == 1
    alias = aliased(Document)
    assert (await test_session.scalars(select(alias.id))).all() == [world["documents"][0]]
    for option in (selectinload(Project.documents), joinedload(Project.documents)):
        projects = (
            (await test_session.execute(select(Project).options(option))).unique().scalars().all()
        )
        assert len(projects) == 1
        assert len(projects[0].documents) == 1
    assert await test_session.get(Project, world["projects"][2]) is None
    assert await test_session.get(Document, world["documents"][1]) is None
    with pytest.raises(NoResultFound):
        await test_session.get_one(Project, world["projects"][2])


async def test_financial_fields_are_not_loaded_or_serialized_for_viewer(test_session, world):
    principal = bind_scope(test_session, world["user"])
    order = await test_session.scalar(
        select(ChangeOrder).where(ChangeOrder.id == world["orders"][0])
    )
    assert "amount" not in project_record_data(order, principal)
    assert "currency" not in project_record_data(order, principal)
    with pytest.raises(InvalidRequestError):
        _ = order.amount
    for statement in (
        select(ChangeOrder.amount),
        select(func.sum(ChangeOrder.amount)),
        select(ChangeOrder).where(ChangeOrder.amount > 0),
        select(ChangeOrder).order_by(ChangeOrder.amount),
    ):
        with pytest.raises(AuthorizationError):
            await test_session.execute(statement)


async def test_authorized_financial_role_sees_only_accessible_projects(test_session, world):
    world["user"].role = "commercial_manager"
    await test_session.flush()
    principal = bind_scope(test_session, world["user"])
    orders = (await test_session.scalars(select(ChangeOrder))).all()
    assert len(orders) == 1
    assert project_record_data(orders[0], principal)["amount"] == Decimal("1234.56")


async def test_raw_sql_bulk_updates_and_viewer_writes_fail_closed(test_session, world):
    bind_scope(test_session, world["user"])
    for statement in (text("SELECT * FROM projects"), update(Project).values(name="bypass")):
        with pytest.raises(AuthorizationError):
            await test_session.execute(statement)
    order = await test_session.scalar(select(ChangeOrder))
    with pytest.raises(AuthorizationError):
        async with test_session.begin_nested():
            order.title = "forbidden"
            await test_session.flush()


async def test_editor_cannot_write_financial_fields(test_session, world):
    world["user"].role = "site_engineer"
    await test_session.flush()
    bind_scope(test_session, world["user"])
    order = await test_session.scalar(select(ChangeOrder))
    order.title = "valid edit"
    await test_session.flush()
    with pytest.raises(AuthorizationError):
        async with test_session.begin_nested():
            order.amount = Decimal("999")
            await test_session.flush()


async def test_membership_service_and_database_reject_foreign_users(test_session, world):
    world["user"].role = "owner"
    await test_session.flush()
    service = ProjectAccessService(test_session, world["user"])
    with pytest.raises(AuthorizationError):
        await service.set_membership(world["projects"][0], world["outsider"].id)
    own = User(
        tenant_id=world["tenant_id"],
        email="new@example.com",
        full_name="New",
        password_hash="test",
        role="site_engineer",
    )
    test_session.add(own)
    await test_session.flush()
    membership = await service.set_membership(world["projects"][1], own.id)
    assert membership.is_active
    test_session.info.pop(SCOPE_KEY)
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            test_session.add(
                ProjectMembership(
                    tenant_id=world["tenant_id"],
                    project_id=world["projects"][0],
                    user_id=world["outsider"].id,
                )
            )
            await test_session.flush()


async def test_invalid_database_role_is_rejected(test_session, world):
    with pytest.raises(IntegrityError):
        async with test_session.begin_nested():
            world["user"].role = "superuser"
            await test_session.flush()


async def test_core_subqueries_projections_and_literals_cannot_bypass_scope(test_session, world):
    bind_scope(test_session, world["user"])
    raw_alias = Document.__table__.alias("unscoped_documents")
    statements = [
        select(Project.id, select(Document.__table__.c.id).limit(1).scalar_subquery()),
        select(Project.id, Document.__table__.c.id),
        select(Project.id, raw_alias.c.id),
        select(Project.id, literal_column("(SELECT amount FROM change_orders LIMIT 1)")),
        select(Project).from_statement(text("SELECT * FROM projects")),
    ]
    for statement in statements:
        with pytest.raises(AuthorizationError):
            await test_session.execute(statement)


async def test_financial_eager_loads_and_foreign_refresh_fail_closed(test_session, world):
    foreign = await test_session.get(Project, world["projects"][2])
    bind_scope(test_session, world["user"])
    result = await test_session.execute(select(Project).options(joinedload(Project.change_orders)))
    project = result.unique().scalar_one()
    with pytest.raises(InvalidRequestError):
        _ = project.change_orders[0].amount
    with pytest.raises(AuthorizationError):
        await test_session.refresh(foreign)


async def test_count_from_and_scoped_orm_subqueries_are_supported(test_session, world):
    bind_scope(test_session, world["user"])
    assert await test_session.scalar(select(func.count()).select_from(Document)) == 1
    subquery = select(Document.id).subquery()
    assert await test_session.scalar(select(func.count()).select_from(subquery)) == 1


async def test_runtime_session_requires_scope_before_any_project_query(test_session, world):
    test_session.info["require_project_scope"] = True
    try:
        with pytest.raises(AuthorizationError):
            await test_session.execute(select(Project))
        with pytest.raises(AuthorizationError):
            await test_session.execute(text("SELECT * FROM documents"))
        assert await test_session.scalar(text("SELECT 1")) == 1
        bind_scope(test_session, world["user"])
        assert (await test_session.scalars(select(Project.id))).all() == [world["projects"][0]]
    finally:
        test_session.info.pop("require_project_scope", None)


@pytest.mark.parametrize("role", list(Role))
async def test_all_roles_require_membership_except_tenant_admins(
    rbac_client, world, test_session, role
):
    world["user"].role = role.value
    await test_session.flush()
    headers = bearer(world)
    assert (
        await rbac_client.get(f"/projects/{world['projects'][0]}", headers=headers)
    ).status_code == 200
    expected = 200 if role in {Role.OWNER, Role.ADMIN} else 404
    assert (
        await rbac_client.get(f"/projects/{world['projects'][1]}", headers=headers)
    ).status_code == expected
    assert (
        await rbac_client.get(f"/projects/{world['projects'][2]}", headers=headers)
    ).status_code == 404


async def test_direct_approval_status_changes_do_not_bypass_human_policy(test_session, world):
    world["user"].role = "owner"
    await test_session.flush()
    bind_scope(test_session, world["user"])
    order = await test_session.scalar(
        select(ChangeOrder).where(ChangeOrder.id == world["orders"][0])
    )
    with pytest.raises(AuthorizationError):
        async with test_session.begin_nested():
            order.status = "approved"
            await test_session.flush()


async def test_role_migration_demotes_legacy_roles_and_preserves_owner(test_engine):
    tenant_id, legacy_id, owner_id = uuid4(), uuid4(), uuid4()
    async with test_engine.begin() as connection:
        await connection.run_sync(
            lambda conn: command.downgrade(migration_config(conn), "0002_authentication")
        )
        await connection.execute(
            Tenant.__table__.insert().values(id=tenant_id, name="Migration", slug=uuid4().hex)
        )
        for user_id, role in ((legacy_id, "member"), (owner_id, "owner")):
            await connection.execute(
                User.__table__.insert().values(
                    id=user_id,
                    tenant_id=tenant_id,
                    email=f"{user_id}@example.com",
                    full_name="Test",
                    password_hash="test",
                    role=role,
                )
            )
        await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        roles = dict(
            (
                await connection.execute(
                    select(User.id, User.role).where(User.tenant_id == tenant_id)
                )
            ).all()
        )
        assert roles == {legacy_id: "viewer", owner_id: "owner"}
        await connection.execute(User.__table__.delete().where(User.tenant_id == tenant_id))
        await connection.execute(Tenant.__table__.delete().where(Tenant.id == tenant_id))


async def test_aggregates_do_not_bypass_audit_or_auth_state_permissions(test_session, world):
    bind_scope(test_session, world["user"])
    for model in (AuditEvent, AuthSession):
        with pytest.raises(AuthorizationError):
            await test_session.scalar(select(func.count()).select_from(model))


async def test_explicit_undefer_cannot_bypass_financial_permissions(test_session, world):
    bind_scope(test_session, world["user"])
    for statement in (
        select(ChangeOrder).options(undefer(ChangeOrder.amount)),
        select(ChangeOrder).options(undefer("*")),
        select(Project).options(joinedload(Project.change_orders).undefer(ChangeOrder.amount)),
    ):
        with pytest.raises(AuthorizationError):
            await test_session.execute(statement)
