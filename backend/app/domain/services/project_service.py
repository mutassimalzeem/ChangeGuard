"""Project service layer for business logic."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.domain.models import AuditEvent, Project, Tenant, User
from app.domain.schemas.project import (
    PaginatedProjectResponse,
    ProjectCreate,
    ProjectListParams,
    ProjectRead,
    ProjectUpdate,
)
from app.policy.permissions import Action


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectService:
    """Business logic for project management."""

    def __init__(self, session: AsyncSession, request=None):
        self.session = session
        self.request = request

    def _get_request_id(self) -> str | None:
        if self.request and hasattr(self.request.state, "request_id"):
            return self.request.state.request_id
        return None

    def _get_actor_id(self) -> UUID | None:
        if self.request and hasattr(self.request.state, "user_id"):
            return UUID(self.request.state.user_id)
        return None

    async def _record_audit(
        self,
        action: str,
        project: Project,
        actor_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an audit event for project operations."""
        audit = AuditEvent(
            tenant_id=project.tenant_id,
            project_id=project.id,
            actor_id=actor_id or self._get_actor_id(),
            action=action,
            entity_type="project",
            entity_id=project.id,
            request_id=self._get_request_id(),
            details=details or {},
        )
        self.session.add(audit)

    async def create_project(self, payload: ProjectCreate, user: User) -> ProjectRead:
        """Create a new project."""
        # Check for duplicate code within tenant
        existing = await self.session.scalar(
            select(Project).where(
                Project.tenant_id == user.tenant_id,
                Project.code == payload.code.upper(),
            )
        )
        if existing:
            raise ValueError(f"Project with code '{payload.code}' already exists")

        # Create project
        project = Project(
            tenant_id=user.tenant_id,
            code=payload.code.upper(),
            name=payload.name,
            description=payload.description,
            status=payload.status,
            start_date=payload.start_date,
            end_date=payload.expected_end_date,
            currency=payload.currency.upper(),
        )
        self.session.add(project)
        await self.session.flush()

        # Record audit event
        await self._record_audit(
            "project.create",
            project,
            details={
                "name": project.name,
                "code": project.code,
                "client_name": payload.client_name,
                "contract_value": str(payload.contract_value) if payload.contract_value else None,
                "currency": project.currency,
                "start_date": str(project.start_date) if project.start_date else None,
                "expected_end_date": str(project.end_date) if project.end_date else None,
                "status": project.status,
                "stakeholders": payload.stakeholders,
            },
        )

        # Add creator as project member
        from app.domain.models import ProjectMembership
        membership = ProjectMembership(
            tenant_id=user.tenant_id,
            project_id=project.id,
            user_id=user.id,
            is_active=True,
        )
        self.session.add(membership)

        return ProjectRead.model_validate(project)

    async def list_projects(
        self,
        params: ProjectListParams,
        user: User,
    ) -> PaginatedProjectResponse:
        """List projects with pagination, filtering, and search."""
        from app.api.pagination import paginate_query, PageParams

        page_params = PageParams(page=params.page, page_size=params.page_size)

        # Base query - only projects in user's tenant
        query = select(Project).where(Project.tenant_id == user.tenant_id)

        # Apply status filter
        if params.status:
            query = query.where(Project.status == params.status)

        # Apply search filter (name or client_name - but client_name not in model, search on name)
        if params.search:
            search_term = f"%{params.search}%"
            query = query.where(Project.name.ilike(search_term))

        # Order by created_at desc
        query = query.order_by(Project.created_at.desc())

        # Execute paginated query
        items, total = await paginate_query(self.session, query, page_params)

        # Convert to read schemas
        project_reads = [ProjectRead.model_validate(item) for item in items]

        return PaginatedProjectResponse.create(
            items=project_reads,
            total_items=total,
            page=page_params.page,
            page_size=page_params.page_size,
        )

    async def get_project(self, project_id: UUID, user: User) -> ProjectRead:
        """Get a single project by ID."""
        project = await self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == user.tenant_id,
            )
        )
        if not project:
            raise ValueError("Project not found")
        return ProjectRead.model_validate(project)

    async def update_project(
        self,
        project_id: UUID,
        payload: ProjectUpdate,
        user: User,
    ) -> ProjectRead:
        """Update a project."""
        project = await self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == user.tenant_id,
            )
        )
        if not project:
            raise ValueError("Project not found")

        # Track changes for audit
        changes = {}
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "expected_end_date":
                field = "end_date"
            if field == "currency" and value:
                value = value.upper()
            if field == "status" and value:
                valid_statuses = {"active", "on_hold", "completed", "cancelled", "archived"}
                if value not in valid_statuses:
                    raise ValueError(f"Invalid status: {value}")

            old_value = getattr(project, field, None)
            if old_value != value:
                changes[field] = {"old": str(old_value) if old_value is not None else None, "new": str(value) if value is not None else None}
                setattr(project, field, value)

        if changes:
            await self._record_audit(
                "project.update",
                project,
                details={"changes": changes},
            )

        await self.session.flush()
        return ProjectRead.model_validate(project)

    async def delete_project(self, project_id: UUID, user: User) -> None:
        """Delete a project."""
        project = await self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == user.tenant_id,
            )
        )
        if not project:
            raise ValueError("Project not found")

        # Record audit event before deletion
        await self._record_audit(
            "project.delete",
            project,
            details={
                "name": project.name,
                "code": project.code,
                "status": project.status,
            },
        )

        await self.session.delete(project)
        await self.session.flush()