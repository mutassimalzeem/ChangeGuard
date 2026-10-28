"""Project management API tests - authorization and validation."""

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.domain.models import AuditEvent, Project, Tenant, User
from app.policy.permissions import Action, Role


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def bearer(user: User, tenant_id: str | None = None) -> dict[str, str]:
    token = create_access_token(str(user.id), str(user.tenant_id), user.token_version)
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
async def admin_user(test_session, tenant):
    """Create an admin user for testing."""
    user = User(
        tenant_id=tenant.id,
        email="admin@example.com",
        full_name="Admin",
        password_hash="test",
        role=Role.ADMIN.value,
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


async def test_create_project_duplicate_code_fails(client: AsyncClient, project_user, sample_project):
    """Test that duplicate project code fails."""
    headers = bearer(project_user)
    payload = {
        "code": "TEST",  # Same as sample_project
        "name": "Another Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


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
    assert "end date must be on or after start date" in response.json()["detail"].lower()


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


async def test_create_project_outsider_forbidden(client: AsyncClient, outsider_user, tenant):
    """Test that user from different tenant cannot create projects."""
    headers = bearer(outsider_user)
    payload = {
        "code": "PROJ1",
        "name": "Test Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    # Should be 403 because user is not in the same tenant
    assert response.status_code == 403


async def test_list_projects_success(client: AsyncClient, project_user, sample_project):
    """Test listing projects."""
    headers = bearer(project_user)
    response = await client.get("/api/v1/projects", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["total_items"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["code"] == "TEST"


async def test_list_projects_pagination(client: AsyncClient, project_user, tenant, test_session):
    """Test project list pagination."""
    # Create multiple projects
    for i in range(5):
        proj = Project(tenant_id=tenant.id, code=f"PROJ{i}", name=f"Project {i}")
        test_session.add(proj)
    await test_session.flush()

    headers = bearer(project_user)
    response = await client.get("/api/v1/projects?page=1&page_size=2", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["page"] == 1
    assert data["metadata"]["page_size"] == 2
    assert len(data["items"]) == 2
    assert data["metadata"]["has_next"] is True


async def test_list_projects_filter_by_status(client: AsyncClient, project_user, tenant, test_session):
    """Test filtering projects by status."""
    active_proj = Project(tenant_id=tenant.id, code="ACTIVE1", name="Active Project", status="active")
    completed_proj = Project(tenant_id=tenant.id, code="COMP1", name="Completed Project", status="completed")
    test_session.add_all([active_proj, completed_proj])
    await test_session.flush()

    headers = bearer(project_user)
    response = await client.get("/api/v1/projects?status=active", headers=headers)
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "active"


async def test_list_projects_search_by_name(client: AsyncClient, project_user, tenant, test_session):
    """Test searching projects by name."""
    proj1 = Project(tenant_id=tenant.id, code="SEARCH1", name="Alpha Project")
    proj2 = Project(tenant_id=tenant.id, code="SEARCH2", name="Beta Project")
    test_session.add_all([proj1, proj2])
    await test_session.flush()

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


async def test_get_project_unassigned_viewer_forbidden(client: AsyncClient, viewer_user, sample_project):
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
    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Project Name"
    assert data["description"] == "Updated description"
    assert data["status"] == "on_hold"


async def test_update_project_partial(client: AsyncClient, project_user, sample_project):
    """Test partial project update."""
    headers = bearer(project_user)
    payload = {"name": "Partially Updated"}
    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Partially Updated"
    assert data["description"] == "A test project"  # Unchanged


async def test_update_project_invalid_status(client: AsyncClient, project_user, sample_project):
    """Test that invalid status is rejected on update."""
    headers = bearer(project_user)
    payload = {"status": "invalid"}
    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers)
    assert response.status_code == 422


async def test_update_project_end_date_before_start_date(client: AsyncClient, project_user, sample_project, test_session):
    """Test that end date before start date is rejected on update."""
    # Set a start date first
    sample_project.start_date = "2024-06-01"
    await test_session.flush()

    headers = bearer(project_user)
    payload = {"expected_end_date": "2024-01-01"}
    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers)
    assert response.status_code == 422
    assert "end date must be on or after start date" in response.json()["detail"].lower()


async def test_update_project_viewer_forbidden(client: AsyncClient, viewer_user, sample_project):
    """Test that viewer cannot update projects."""
    headers = bearer(viewer_user)
    payload = {"name": "Updated"}
    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers)
    assert response.status_code == 403


async def test_delete_project_success(client: AsyncClient, project_user, sample_project):
    """Test successful project deletion."""
    headers = bearer(project_user)
    response = await client.delete(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert response.status_code == 204

    # Verify project is deleted
    get_response = await client.get(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert get_response.status_code == 404


async def test_delete_project_not_found(client: AsyncClient, project_user):
    """Test deleting non-existent project returns 404."""
    headers = bearer(project_user)
    response = await client.delete(f"/api/v1/projects/{uuid4()}", headers=headers)
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


async def test_audit_event_created_on_project_create(client: AsyncClient, project_user, tenant, test_session):
    """Test that audit event is created on project creation."""
    headers = bearer(project_user)
    payload = {
        "code": "AUDIT1",
        "name": "Audit Test Project",
        "client_name": "Test Client",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201
    project_id = response.json()["id"]

    # Check audit event
    audit = await test_session.scalar(
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


async def test_audit_event_created_on_project_update(client: AsyncClient, project_user, sample_project, test_session):
    """Test that audit event is created on project update."""
    headers = bearer(project_user)
    payload = {"name": "Updated Name", "status": "on_hold"}
    response = await client.patch(f"/api/v1/projects/{sample_project.id}", json=payload, headers=headers)
    assert response.status_code == 200

    # Check audit event
    audit = await test_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "project",
            AuditEvent.entity_id == sample_project.id,
            AuditEvent.action == "project.update",
        )
    )
    assert audit is not None
    assert audit.details["changes"]["name"]["new"] == "Updated Name"
    assert audit.details["changes"]["status"]["new"] == "on_hold"


async def test_audit_event_created_on_project_delete(client: AsyncClient, project_user, sample_project, test_session):
    """Test that audit event is created on project deletion."""
    headers = bearer(project_user)
    response = await client.delete(f"/api/v1/projects/{sample_project.id}", headers=headers)
    assert response.status_code == 204

    # Check audit event
    audit = await test_session.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "project",
            AuditEvent.entity_id == sample_project.id,
            AuditEvent.action == "project.delete",
        )
    )
    assert audit is not None
    assert audit.details["name"] == "Test Project"
    assert audit.details["code"] == "TEST"


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