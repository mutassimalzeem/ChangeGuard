"""Project entry point for tenant-filtered queries and checked membership changes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import AuthorizationError, NotFoundError
from app.domain.models import Project, ProjectMembership, User
from app.policy.decisions import PolicyContext, decide
from app.policy.permissions import Action, has_permission
from app.policy.scope import bind_scope, project_record_data


class ProjectAccessService:
    def __init__(self, session: AsyncSession, user: User):
        self.session = session
        self.principal = bind_scope(session, user)

    async def project(self, project_id: UUID) -> Project:
        project = await self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == self.principal.tenant_id,
            )
        )
        if project is None:
            raise NotFoundError("Project", project_id)
        return project

    async def records(self, model, project_id: UUID) -> list[dict]:
        await self.project(project_id)
        if not hasattr(model, "project_id"):
            raise ValueError("A project-scoped model is required")
        rows = await self.session.scalars(
            select(model).where(
                model.project_id == project_id,
                model.tenant_id == self.principal.tenant_id,
            )
        )
        return [project_record_data(row, self.principal) for row in rows]

    async def policy(
        self, action: Action, project_id: UUID, *, automated=False, requested_by_id=None
    ):
        project = await self.project(project_id)
        return decide(
            self.principal.role,
            action,
            PolicyContext(
                actor_tenant_id=self.principal.tenant_id,
                resource_tenant_id=project.tenant_id,
                project_access=True,
                actor_id=self.principal.user_id,
                requested_by_id=requested_by_id,
                automated=automated,
            ),
        )

    async def set_membership(self, project_id: UUID, user_id: UUID, *, active: bool = True):
        if not has_permission(self.principal.role, Action.MEMBERS_MANAGE):
            raise AuthorizationError()
        await self.project(project_id)
        user = await self.session.scalar(
            select(User).where(
                User.id == user_id,
                User.tenant_id == self.principal.tenant_id,
            )
        )
        if user is None:
            raise AuthorizationError()
        membership = await self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.tenant_id == self.principal.tenant_id,
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
        if membership is None:
            membership = ProjectMembership(
                tenant_id=self.principal.tenant_id,
                project_id=project_id,
                user_id=user_id,
                is_active=active,
            )
            self.session.add(membership)
        else:
            membership.is_active = active
        await self.session.flush()
        return membership
