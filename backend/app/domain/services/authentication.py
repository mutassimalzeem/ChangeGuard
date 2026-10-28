"""Transactional authentication. All expected denials are committed by the router."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Request
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    identifier_hash,
    password_hasher,
    token_hash,
    verify_password,
)
from app.domain.models import (
    AuditEvent,
    AuthenticationEvent,
    AuthRateLimit,
    AuthSession,
    PasswordResetGrant,
    Tenant,
    User,
)
from app.domain.schemas.auth import Identity, Login, Register, ResetConfirm, TokenPair


class AuthFailure(Exception):
    def __init__(self, status: int = 401):
        self.status = status


def utcnow():
    return datetime.now(timezone.utc)


class AuthenticationService:
    def __init__(self, session: AsyncSession, request: Request):
        self.session = session
        self.request = request
        self.settings = get_settings()

    def account_key(self, identity: Identity) -> str:
        return identifier_hash(f"{identity.tenant_slug}:{identity.email}")

    async def audit(self, action: str, tenant=None, user=None, identity=None):
        if user is not None:
            self.request.state.tenant_id = str(user.tenant_id)
            self.request.state.user_id = str(user.id)
        request_id = getattr(self.request.state, "request_id", None)
        self.session.add(
            AuthenticationEvent(
                action=action,
                tenant_id=tenant.id if tenant else None,
                user_id=user.id if user else None,
                request_id=request_id,
                identifier_hash=self.account_key(identity) if identity else None,
            )
        )
        if tenant:
            self.session.add(
                AuditEvent(
                    tenant_id=tenant.id,
                    actor_id=user.id if user else None,
                    action=action,
                    entity_type="authentication",
                    entity_id=user.id if user else None,
                    request_id=request_id,
                )
            )

    async def limits(self, action: str, identity: Identity | None = None, failed_only=False):
        """Lock account and IP buckets in stable order across workers."""
        now = utcnow()
        ip = self.request.client.host if self.request.client else "unknown"
        limit = (
            self.settings.login_max_failures if failed_only else self.settings.auth_request_limit
        )
        keys = [(identifier_hash(f"{action}:ip:{ip}"), limit * 10)]
        if identity:
            keys.append((identifier_hash(f"{action}:account:{self.account_key(identity)}"), limit))
        buckets = []
        for key, maximum in sorted(keys):
            await self.session.execute(
                insert(AuthRateLimit)
                .values(
                    key_hash=key,
                    attempts=0,
                    expires_at=now + timedelta(seconds=self.settings.login_window_seconds),
                )
                .on_conflict_do_nothing(index_elements=[AuthRateLimit.key_hash])
            )
            bucket = await self.session.scalar(
                select(AuthRateLimit).where(AuthRateLimit.key_hash == key).with_for_update()
            )
            if bucket.expires_at <= now:
                bucket.attempts = 0
                bucket.expires_at = now + timedelta(seconds=self.settings.login_window_seconds)
            if bucket.attempts >= maximum:
                raise AuthFailure(429)
            buckets.append(bucket)
        if not failed_only:
            for bucket in buckets:
                bucket.attempts += 1
        return buckets

    async def tenant_for(self, identity: Identity):
        return await self.session.scalar(select(Tenant).where(Tenant.slug == identity.tenant_slug))

    async def user_for(self, tenant_id: UUID, *, email=None, user_id=None):
        query = (
            select(User)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                Tenant.status == "active",
            )
        )
        query = (
            query.where(User.email == email)
            if email is not None
            else query.where(User.id == user_id)
        )
        return await self.session.scalar(
            query.with_for_update(of=User).execution_options(populate_existing=True)
        )

    async def register(self, payload: Register):
        await self.limits("register", payload)
        hashed = await run_in_threadpool(get_password_hash, payload.password.get_secret_value())
        # A slug identifies an organization, never an invitation to join it.
        tenant = await self.tenant_for(payload)
        if tenant:
            return
        tenant_id = uuid4()
        created = await self.session.scalar(
            insert(Tenant)
            .values(
                id=tenant_id,
                name=payload.tenant_name,
                slug=payload.tenant_slug,
            )
            .on_conflict_do_nothing(index_elements=[Tenant.slug])
            .returning(Tenant.id)
        )
        if created is None:
            return
        user = User(
            tenant_id=tenant_id,
            email=str(payload.email),
            full_name=payload.full_name,
            password_hash=hashed,
            role="owner",
        )
        self.session.add(user)
        await self.session.flush()
        tenant = await self.session.get(Tenant, tenant_id)
        await self.audit("auth.register", tenant, user)

    async def pair(self, user: User, family_id=None, expires_at=None):
        refresh = create_refresh_token()
        self.session.add(
            AuthSession(
                tenant_id=user.tenant_id,
                user_id=user.id,
                family_id=family_id or uuid4(),
                token_hash=token_hash(refresh),
                expires_at=expires_at
                or utcnow() + timedelta(days=self.settings.refresh_token_expire_days),
            )
        )
        self.request.state.tenant_id = str(user.tenant_id)
        self.request.state.user_id = str(user.id)
        return TokenPair(
            access_token=create_access_token(
                str(user.id), str(user.tenant_id), [user.role], version=user.token_version
            ),
            refresh_token=refresh,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )

    async def login(self, payload: Login):
        tenant = await self.tenant_for(payload)
        try:
            buckets = await self.limits("login", payload, failed_only=True)
        except AuthFailure:
            await self.audit("auth.login_failed", tenant=tenant, identity=payload)
            raise
        user = await self.user_for(tenant.id, email=str(payload.email)) if tenant else None
        valid = await run_in_threadpool(
            verify_password,
            payload.password.get_secret_value(),
            user.password_hash if user else DUMMY_PASSWORD_HASH,
        )
        if not user or not valid:
            for bucket in buckets:
                bucket.attempts += 1
            await self.audit("auth.login_failed", tenant=tenant, identity=payload)
            raise AuthFailure()
        # Upgrade older bcrypt or Argon2 parameters after successful verification.
        if not user.password_hash.startswith("$argon2id$") or password_hasher.check_needs_rehash(
            user.password_hash
        ):
            user.password_hash = await run_in_threadpool(
                get_password_hash, payload.password.get_secret_value()
            )
        user.last_login_at = utcnow()
        await self.audit("auth.login", tenant, user)
        return await self.pair(user)

    async def refresh(self, value: str):
        row = await self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash(value))
        )
        if not row:
            raise AuthFailure()
        user = await self.user_for(row.tenant_id, user_id=row.user_id)
        # User lock serializes rotation, logout, and password reset for this user.
        row = await self.session.scalar(
            select(AuthSession)
            .where(AuthSession.id == row.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        tenant = await self.session.get(Tenant, row.tenant_id)
        if row.rotated_at is not None:
            await self.revoke_family(row.family_id)
            await self.audit("auth.refresh_replay", tenant)
            raise AuthFailure()
        if not user or row.revoked_at is not None or row.expires_at <= utcnow():
            raise AuthFailure()
        row.rotated_at = utcnow()
        return await self.pair(user, row.family_id, row.expires_at)

    async def revoke_family(self, family_id):
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    async def logout(self, value: str):
        row = await self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash(value))
        )
        if not row:
            await self.audit("auth.logout")
            return
        user = await self.session.scalar(
            select(User).where(User.id == row.user_id).with_for_update()
        )
        await self.revoke_family(row.family_id)
        tenant = await self.session.get(Tenant, row.tenant_id)
        await self.audit("auth.logout", tenant, user)

    async def request_reset(self, payload: Identity):
        await self.limits("password_reset", payload)
        tenant = await self.tenant_for(payload)
        user = await self.user_for(tenant.id, email=str(payload.email)) if tenant else None
        await self.audit("auth.password_reset_requested", tenant=tenant, identity=payload)
        if not user:
            return None
        value = create_password_reset_token(str(user.id), str(user.tenant_id), user.token_version)
        await self.session.execute(
            update(PasswordResetGrant)
            .where(PasswordResetGrant.user_id == user.id, PasswordResetGrant.used_at.is_(None))
            .values(used_at=utcnow())
        )
        self.session.add(
            PasswordResetGrant(
                tenant_id=user.tenant_id,
                user_id=user.id,
                token_hash=token_hash(value),
                expires_at=utcnow()
                + timedelta(minutes=self.settings.password_reset_expire_minutes),
            )
        )
        return user.email, value

    async def confirm_reset(self, payload: ResetConfirm):
        await self.limits("password_reset_confirm")
        value = payload.token.get_secret_value()
        try:
            claims = decode_token(value, "password_reset")
            tenant_id, user_id = UUID(claims["tenant_id"]), UUID(claims["sub"])
        except (JWTError, ValueError, KeyError, TypeError):
            await self.audit("auth.password_reset_failed")
            raise AuthFailure() from None
        user = await self.user_for(tenant_id, user_id=user_id)
        grant = await self.session.scalar(
            select(PasswordResetGrant)
            .where(
                PasswordResetGrant.token_hash == token_hash(value),
                PasswordResetGrant.user_id == user_id,
                PasswordResetGrant.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if (
            not user
            or not grant
            or grant.used_at is not None
            or grant.expires_at <= utcnow()
            or claims["ver"] != user.token_version
        ):
            await self.audit("auth.password_reset_failed")
            raise AuthFailure()
        user.password_hash = await run_in_threadpool(
            get_password_hash, payload.password.get_secret_value()
        )
        user.token_version += 1
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.tenant_id == tenant_id)
            .values(revoked_at=utcnow())
        )
        await self.session.execute(
            update(PasswordResetGrant)
            .where(
                PasswordResetGrant.user_id == user.id,
                PasswordResetGrant.tenant_id == tenant_id,
                PasswordResetGrant.used_at.is_(None),
            )
            .values(used_at=utcnow())
        )
        tenant = await self.session.get(Tenant, tenant_id)
        await self.audit("auth.password_reset", tenant, user)
