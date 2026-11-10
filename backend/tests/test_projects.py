"""Project management API tests - authorization and validation."""

from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.api.exceptions import AuthorizationError, ConflictError
from app.core.database import ScopedAsyncSession
from app.core.security import create_access_token
from app.domain.models import AuditEvent, Project, ProjectMembership, Tenant, User
from app.domain.services.project_service import ProjectService
from app.policy.permissions import Role
from app.policy.scope import bind_scope

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def bearer(user: User) -> dict[str, str]:
    token = create_access_token(
        str(user.id), str(user.tenant_id), [user.role], version=user.token_version
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def project_user(test_session, tenant):
    """Create a project_manager user for testing."""
    user = User(
        tenant_id=tenant.id,
        email="pm@example.com",
        full_name="Project Manager",
        password_hash="test",
        role=Role.PROJECT_MANAGER.value,
    )
    test_session.add(user)
    await test_session.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(test_session, tenant):
    """Create a viewer user for testing."""
    user = User(
        tenant_id=tenant.id,
        email="viewer@example.com",
        full_name="Viewer",
        password_hash="test",
        role=Role.VIEWER.value,
    )
    test_session.add(user)
    await test_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(test_session, tenant, request):
    """Create an admin user for testing."""
    user = User(
        tenant_id=tenant.id,
        email="admin@example.com",
        full_name="Admin",
        password_hash="test",
        role=getattr(request, "param", Role.ADMIN.value),
    )
    test_session.add(user)
    await test_session.flush()
    return user


@pytest_asyncio.fixture
async def outsider_user(test_session):
    """Create a user in a different tenant."""
    other_tenant = Tenant(name="Other Tenant", slug=uuid4().hex)
    test_session.add(other_tenant)
    await test_session.flush()
    user = User(
        tenant_id=other_tenant.id,
        email="outsider@example.com",
        full_name="Outsider",
        password_hash="test",
        role=Role.PROJECT_MANAGER.value,
    )
    test_session.add(user)
    await test_session.flush()
    return user


@pytest_asyncio.fixture
async def sample_project(test_session, tenant, project_user):
    """Create a sample project."""
    from app.domain.models import ProjectMembership

    project = Project(
        tenant_id=tenant.id,
        code="TEST",
        name="Test Project",
        description="A test project",
        status="active",
        currency="USD",
    )
    test_session.add(project)
    await test_session.flush()

    # Add membership for project_user
    membership = ProjectMembership(
        tenant_id=tenant.id,
        project_id=project.id,
        user_id=project_user.id,
        is_active=True,
    )
    test_session.add(membership)
    await test_session.flush()

    return project


@pytest_asyncio.fixture
async def member_projects(test_session, tenant, project_user):
    async def add(*projects):
        test_session.add_all(projects)
        await test_session.flush()
        test_session.add_all(
            [
                ProjectMembership(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    user_id=project_user.id,
                    is_active=True,
                )
                for project in projects
            ]
        )
        await test_session.flush()

    return add


@pytest_asyncio.fixture
async def audit_session(test_session, admin_user):
    # Independent authenticated reader on the fixture connection, not a scope bypass.
    async with ScopedAsyncSession(
        bind=test_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
    ) as session:
        bind_scope(session, admin_user)
        yield session


async def test_create_project_success(client: AsyncClient, project_user, tenant):
    """Test successful project creation by project_manager."""
    headers = bearer(project_user)
    payload = {
        "code": "NEWPROJ",
        "name": "New Project",
        "client_name": "Test Client",
        "description": "Project description",
        "contract_value": "100000.00",
        "currency": "USD",
        "start_date": "2024-01-01",
        "expected_end_date": "2024-12-31",
        "status": "active",
        "stakeholders": ["John Doe", "Jane Smith"],
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "NEWPROJ"
    assert data["name"] == "New Project"
    assert data["client_name"] == "Test Client"
    assert data["currency"] == "USD"
    assert data["status"] == "active"
    assert data["stakeholders"] == ["John Doe", "Jane Smith"]


async def test_create_project_duplicate_code_fails(
    client: AsyncClient, project_user, sample_project
):
    """Test that duplicate project code fails."""
    headers = bearer(project_user)
    payload = {
        "code": "TEST",  # Same as sample_project
        "name": "Another Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 400
    assert "already exists" in response.json()["error"]["message"]


async def test_create_project_invalid_code_format(client: AsyncClient, project_user):
    """Test that invalid code format is rejected."""
    headers = bearer(project_user)
    payload = {
        "code": "invalid-code!",  # Invalid characters
        "name": "Test Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 422


async def test_create_project_invalid_currency(client: AsyncClient, project_user):
    """Test that invalid currency is rejected."""
    headers = bearer(project_user)
    payload = {
        "code": "PROJ1",
        "name": "Test Project",
        "client_name": "Test Client",
        "currency": "USDD",  # Invalid length
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 422


async def test_create_project_invalid_status(client: AsyncClient, project_user):
    """Test that invalid status is rejected."""
    headers = bearer(project_user)
    payload = {
        "code": "PROJ1",
        "name": "Test Project",
        "client_name": "Test Client",
        "status": "invalid_status",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 422


async def test_create_project_end_date_before_start_date(client: AsyncClient, project_user):
    """Test that end date before start date is rejected."""
    headers = bearer(project_user)
    payload = {
        "code": "PROJ1",
        "name": "Test Project",
        "client_name": "Test Client",
        "start_date": "2024-12-31",
        "expected_end_date": "2024-01-01",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"]["errors"][0]["loc"] == ["body", "expected_end_date"]


async def test_create_project_negative_contract_value(client: AsyncClient, project_user):
    """Test that negative contract value is rejected."""
    headers = bearer(project_user)
    payload = {
        "code": "PROJ1",
        "name": "Test Project",
        "client_name": "Test Client",
        "contract_value": "-1000.00",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 422


async def test_create_project_viewer_forbidden(client: AsyncClient, viewer_user):
    """Test that viewer cannot create projects."""
    headers = bearer(viewer_user)
    payload = {
        "code": "PROJ1",
        "name": "Test Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 403


async def test_create_project_uses_authenticated_tenant(client: AsyncClient, outsider_user, tenant):
    """A permitted caller creates in their own tenant, irrespective of other tenants."""
    response = await client.post(
        "/api/v1/projects",
        headers=bearer(outsider_user),
        json={
            "code": "OWN",
            "name": "Own project",
            "client_name": "Own client",
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["tenant_id"] == str(outsider_user.tenant_id)
    assert created["tenant_id"] != str(tenant.id)
    assert (
        await client.get(f"/api/v1/projects/{created['id']}", headers=bearer(outsider_user))
    ).status_code == 200


async def test_create_project_rejects_tenant_override(client: AsyncClient, outsider_user, tenant):
    response = await client.post(
        "/api/v1/projects",
        headers=bearer(outsider_user),
        json={
            "code": "FOREIGN",
            "name": "Foreign project",
            "client_name": "Client",
            "tenant_id": str(tenant.id),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_list_projects_success(client: AsyncClient, project_user, sample_project):
    """Test listing projects."""
    headers = bearer(project_user)
    response = await client.get("/api/v1/projects", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["total_items"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["code"] == "TEST"


async def test_list_projects_pagination(
    client: AsyncClient, project_user, tenant, test_session, member_projects
):
    """Test project list pagination."""
    # Create multiple projects
    for i in range(5):
        proj = Project(tenant_id=tenant.id, code=f"PROJ{i}", name=f"Project {i}")
        await member_projects(proj)

    headers = bearer(project_user)
    response = await client.get("/api/v1/projects?page=1&page_size=2", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["page"] == 1
    assert data["metadata"]["page_size"] == 2
    assert len(data["items"]) == 2
    assert data["metadata"]["has_next"] is True


async def test_list_projects_filter_by_status(
    client: AsyncClient, project_user, tenant, test_session, member_projects
):
    """Test filtering projects by status."""
    active_proj = Project(
        tenant_id=tenant.id, code="ACTIVE1", name="Active Project", status="active"
    )
    completed_proj = Project(
        tenant_id=tenant.id, code="COMP1", name="Completed Project", status="completed"
    )
    await member_projects(active_proj, completed_proj)

    headers = bearer(project_user)
    response = await client.get("/api/v1/projects?status=active", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert [item["code"] for item in data["items"]] == ["ACTIVE1"]
    for item in data["items"]:
        assert item["status"] == "active"


async def test_list_projects_search_by_name(
    client: AsyncClient, project_user, tenant, test_session, member_projects
):
    """Test searching projects by name."""
    proj1 = Project(tenant_id=tenant.id, code="SEARCH1", name="Alpha Project")
    proj2 = Project(tenant_id=tenant.id, code="SEARCH2", name="Beta Project")
    await member_projects(proj1, proj2)

    headers = bearer(project_user)
    response = await client.get("/api/v1/projects?search=Alpha", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Alpha Project"


async def test_get_project_success(client: AsyncClient, project_user, sample_project):
    """Test getting a single project."""
    headers = bearer(project_user)
    response = await client.get(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_project.id)
    assert data["code"] == "TEST"


async def test_get_project_not_found(client: AsyncClient, project_user):
    """Test getting non-existent project returns 404."""
    headers = bearer(project_user)
    response = await client.get(f"/api/v1/projects/{uuid4()}", headers=headers)
    assert response.status_code == 404


async def test_get_project_outsider_forbidden(client: AsyncClient, outsider_user, sample_project):
    """Test that user from different tenant cannot access project."""
    headers = bearer(outsider_user)
    response = await client.get(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert response.status_code == 404  # Concealed as not found


async def test_get_project_unassigned_viewer_forbidden(
    client: AsyncClient, viewer_user, sample_project
):
    """Test that viewer without membership cannot access project."""
    headers = bearer(viewer_user)
    response = await client.get(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert response.status_code == 404  # Concealed as not found


async def test_update_project_success(client: AsyncClient, project_user, sample_project):
    """Test successful project update."""
    headers = bearer(project_user)
    payload = {
        "name": "Updated Project Name",
        "description": "Updated description",
        "status": "on_hold",
    }
    response = await client.patch(
        f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Project Name"
    assert data["description"] == "Updated description"
    assert data["status"] == "on_hold"


async def test_update_project_partial(client: AsyncClient, project_user, sample_project):
    """Test partial project update."""
    headers = bearer(project_user)
    payload = {"name": "Partially Updated"}
    response = await client.patch(
        f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Partially Updated"
    assert data["description"] == "A test project"  # Unchanged


async def test_update_project_invalid_status(client: AsyncClient, project_user, sample_project):
    """Test that invalid status is rejected on update."""
    headers = bearer(project_user)
    payload = {"status": "invalid"}
    response = await client.patch(
        f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers
    )
    assert response.status_code == 422


async def test_update_project_end_date_before_start_date(
    client: AsyncClient, project_user, sample_project, test_session
):
    """Test that end date before start date is rejected on update."""
    # Set a start date first
    sample_project.start_date = date.fromisoformat("2024-06-01")
    await test_session.flush()

    headers = bearer(project_user)
    payload = {"expected_end_date": "2024-01-01"}
    response = await client.patch(
        f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"] == {"field": "expected_end_date"}
    assert "end date must be on or after start date" in response.json()["error"]["message"].lower()


async def test_update_project_viewer_forbidden(client: AsyncClient, viewer_user, sample_project):
    """Test that viewer cannot update projects."""
    headers = bearer(viewer_user)
    payload = {"name": "Updated"}
    response = await client.patch(
        f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers
    )
    assert response.status_code == 403


@pytest.mark.parametrize("admin_user", ["owner", "admin"], indirect=True)
async def test_delete_project_requires_human_approval(
    client: AsyncClient, admin_user, sample_project
):
    project_id = sample_project.id
    response = await client.delete(f"/api/v1/projects/{project_id}", headers=bearer(admin_user))
    assert response.status_code == 409, response.text
    assert response.json()["error"]["message"] == "Human approval required"
    assert response.json()["error"]["details"]["reason"] == "human_approval_required"
    assert (
        await client.get(f"/api/v1/projects/{project_id}", headers=bearer(admin_user))
    ).status_code == 200


async def test_self_declared_confirmation_does_not_bypass_deletion_approval(
    client, admin_user, sample_project
):
    project_id = sample_project.id
    response = await client.delete(
        f"/api/v1/projects/{project_id}?approved=true",
        headers={**bearer(admin_user), "X-Human-Approved": "true"},
    )
    assert response.status_code == 409
    assert (
        await client.get(f"/api/v1/projects/{project_id}", headers=bearer(admin_user))
    ).status_code == 200


async def test_service_and_orm_refuse_unapproved_project_deletion(
    test_session, admin_user, sample_project
):
    project_id = sample_project.id
    with pytest.raises(ConflictError, match="Human approval required"):
        await ProjectService(test_session).delete_project(project_id, admin_user)
    with pytest.raises(AuthorizationError, match="Project deletion requires human approval"):
        async with test_session.begin_nested():
            project = await test_session.scalar(select(Project).where(Project.id == project_id))
            await test_session.delete(project)
            await test_session.flush()


async def test_delete_project_manager_forbidden(client, project_user, sample_project):
    response = await client.delete(
        f"/api/v1/projects/{sample_project.id}", headers=bearer(project_user)
    )
    assert response.status_code == 403


async def test_delete_project_not_found(client: AsyncClient, admin_user):
    response = await client.delete(f"/api/v1/projects/{uuid4()}", headers=bearer(admin_user))
    assert response.status_code == 404


async def test_delete_project_viewer_forbidden(client: AsyncClient, viewer_user, sample_project):
    """Test that viewer cannot delete projects."""
    headers = bearer(viewer_user)
    response = await client.delete(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert response.status_code == 403


async def test_admin_can_access_all_projects(client: AsyncClient, admin_user, tenant, test_session):
    """Test that admin can access all projects in tenant without membership."""
    # Create project without adding admin as member
    project = Project(tenant_id=tenant.id, code="ADMIN1", name="Admin Project")
    test_session.add(project)
    await test_session.flush()

    headers = bearer(admin_user)
    response = await client.get(f"/api/v1/projects/{project.id}", headers=headers)
    assert response.status_code == 200


async def test_audit_event_created_on_project_create(
    client: AsyncClient, project_user, tenant, test_session, audit_session
):
    """Test that audit event is created on project creation."""
    headers = bearer(project_user)
    payload = {
        "code": "AUDIT1",
        "name": "Audit Test Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    project_id = UUID(response.json()["id"])

    # Check audit event
    audit = await audit_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "project",
            AuditEvent.entity_id == project_id,
            AuditEvent.action == "project.create",
        )
    )
    assert audit is not None
    assert audit.actor_id == project_user.id
    assert audit.details["name"] == "Audit Test Project"
    assert audit.details["code"] == "AUDIT1"


async def test_audit_event_created_on_project_update(
    client: AsyncClient, project_user, sample_project, test_session, audit_session
):
    """Test that audit event is created on project update."""
    headers = bearer(project_user)
    payload = {"name": "Updated Name", "status": "on_hold"}
    response = await client.patch(
        f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers
    )
    assert response.status_code == 200

    # Check audit event
    audit = await audit_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "project",
            AuditEvent.entity_id == sample_project.id,
            AuditEvent.action == "project.update",
        )
    )
    assert audit is not None
    assert audit.details["changes"]["name"]["new"] == "Updated Name"
    assert audit.details["changes"]["status"]["new"] == "on_hold"


async def test_unapproved_deletion_has_no_success_audit(
    client, admin_user, sample_project, audit_session
):
    project_id = sample_project.id
    response = await client.delete(f"/api/v1/projects/{project_id}", headers=bearer(admin_user))
    assert response.status_code == 409, response.text
    audit = await audit_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == project_id, AuditEvent.action == "project.delete"
        )
    )
    assert audit is None


async def test_project_manager_cannot_read_audits_even_with_project_access(
    client,
    project_user,
    sample_project,
    test_session,
):
    response = await client.get(
        f"/api/v1/projects/{sample_project.id}", headers=bearer(project_user)
    )
    assert response.status_code == 200
    for query in (
        select(AuditEvent),
        select(AuditEvent.id),
        select(func.count()).select_from(AuditEvent),
    ):
        with pytest.raises(AuthorizationError):
            await test_session.execute(query)


async def test_patch_dates_are_parsed_and_validate_the_resulting_record(
    client,
    project_user,
    sample_project,
    test_session,
):
    project_id = sample_project.id
    url = f"/api/v1/projects/{project_id}"
    headers = bearer(project_user)
    response = await client.patch(
        url,
        headers=headers,
        json={
            "start_date": "2026-06-01",
            "expected_end_date": "2026-06-30",
        },
    )
    assert response.status_code == 200, response.text
    project = await test_session.scalar(select(Project).where(Project.id == project_id))
    assert project.start_date == date(2026, 6, 1)
    assert project.end_date == date(2026, 6, 30)
    # A start-only PATCH must also respect the persisted end date, atomically.
    response = await client.patch(
        url, headers=headers, json={"start_date": "2026-07-01", "name": "Must not persist"}
    )
    assert response.status_code == 422
    result = await client.get(url, headers=headers)
    assert result.json()["start_date"] == "2026-06-01"
    assert result.json()["name"] == "Test Project"
    # Explicit null can clear an optional date; omission does not clear it.
    response = await client.patch(url, headers=headers, json={"expected_end_date": None})
    assert response.status_code == 200
    assert response.json()["start_date"] == "2026-06-01"
    assert response.json()["expected_end_date"] is None


async def test_stakeholders_deduplication(client: AsyncClient, project_user):
    """Test that stakeholder list is deduplicated."""
    headers = bearer(project_user)
    payload = {
        "code": "STAKE1",
        "name": "Stakeholder Test",
        "client_name": "Test Client",
        "stakeholders": ["John", "Jane", "John", "Bob"],
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["stakeholders"] == ["John", "Jane", "Bob"]


async def test_empty_stakeholders_list(client: AsyncClient, project_user):
    """Test that empty stakeholders list is handled."""
    headers = bearer(project_user)
    payload = {
        "code": "STAKE2",
        "name": "Stakeholder Test 2",
        "client_name": "Test Client",
        "stakeholders": [],
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["stakeholders"] == []


async def test_unauthenticated_access_denied(client: AsyncClient, sample_project):
    """Test that unauthenticated requests are denied."""
    response = await client.get("/api/v1/projects")
    assert response.status_code == 401

    response = await client.get(f"/api/v1/projects/{sample_project.id}")
    assert response.status_code == 401

    response = await client.post("/api/v1/projects", json={})
    assert response.status_code == 401

    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json={})
    assert response.status_code == 401

    response = await client.delete(f"/api/v1/projects/{sample_project.id}")
    assert response.status_code == 401


async def test_contract_value_decimal_places(client: AsyncClient, project_user):
    """Test that contract value accepts decimal places."""
    headers = bearer(project_user)
    payload = {
        "code": "DEC1",
        "name": "Decimal Test",
        "client_name": "Test Client",
        "contract_value": "123456.78",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["contract_value"] == "123456.78"
