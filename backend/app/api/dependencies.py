"""Reusable authentication dependency; authorization uses the current database user."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.domain.models import Project, Tenant, User
from app.policy.decisions import Decision, PolicyContext, decide
from app.policy.permissions import Action, Role, has_permission
from app.policy.scope import bind_scope

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    failure = HTTPException(
        status_code=401, detail="Authentication failed", headers={"WWW-Authenticate": "Bearer"}
    )
    if not credentials:
        raise failure
    try:
        claims = decode_token(credentials.credentials)
        user_id, tenant_id = UUID(claims["sub"]), UUID(claims["tenant_id"])
    except (JWTError, ValueError, KeyError, TypeError):
        raise failure from None
    user = await session.scalar(
        select(User)
        .join(Tenant)
        .where(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.is_active.is_(True),
            Tenant.status == "active",
            User.token_version == claims["ver"],
        )
    )
    if user is None:
        raise failure
    request.state.tenant_id = str(user.tenant_id)
    request.state.user_id = str(user.id)
    return user


async def require_authenticated_user(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    bind_scope(session, user)
    return user


def require_role(*roles: Role | str):
    allowed = frozenset(Role(role) for role in roles)
    if not allowed:
        raise ValueError("At least one role is required")

    async def dependency(user: User = Depends(require_authenticated_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Access denied")
        return user

    return dependency


async def require_tenant_access(
    tenant_id: UUID,
    user: User = Depends(require_authenticated_user),
) -> User:
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return user


async def require_project_access(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> Project:
    # Session criteria also enforce membership for all non-owner/admin roles.
    project = await session.scalar(
        select(Project).where(Project.id == project_id, Project.tenant_id == user.tenant_id)
    )
    if project is None:
        # Conceal whether the project exists or belongs to a different tenant.
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_permission(action: Action):
    async def dependency(user: User = Depends(require_authenticated_user)) -> User:
        if not has_permission(user.role, action):
            raise HTTPException(status_code=403, detail="Access denied")
        return user

    return dependency


def require_policy_action(action: Action):
    async def dependency(
        project: Project = Depends(require_project_access),
        user: User = Depends(require_authenticated_user),
    ) -> Project:
        result = decide(
            user.role,
            action,
            PolicyContext(
                actor_tenant_id=user.tenant_id,
                resource_tenant_id=project.tenant_id,
                project_access=True,
                actor_id=user.id,
            ),
        )
        if result.decision == Decision.DENIED:
            raise HTTPException(status_code=403, detail="Access denied")
        if result.decision == Decision.REQUIRES_HUMAN_APPROVAL:
            raise HTTPException(status_code=409, detail="Human approval required")
        return project

    return dependency
