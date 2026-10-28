"""Reusable authentication dependency; authorization uses the current database user."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.domain.models import Tenant, User

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
