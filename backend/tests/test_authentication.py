"""Authentication endpoints backed by the real migrated PostgreSQL database."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, Request
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.dependencies import get_current_user
from app.api.v1.routes.auth import router as auth_router
from app.core.config import get_settings
from app.core.database import get_session
from app.core.request_logging import RequestLoggingMiddleware
from app.core.reset_mail import get_password_reset_mailer
from app.core.security import create_access_token, decode_token, get_password_hash, token_hash
from app.domain.models import (
    AuditEvent,
    AuthenticationEvent,
    AuthRateLimit,
    AuthSession,
    PasswordResetGrant,
    Tenant,
    User,
)
from app.domain.services.authentication import utcnow
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
PREFIX = "/api/v1/auth"
PASSWORD = "an-example-strong-password"


@pytest_asyncio.fixture
async def account(client, test_session):
    data = {
        "email": "owner@example.com",
        "password": PASSWORD,
        "full_name": "Owner",
        "tenant_name": "Test organization",
        "tenant_slug": "org-" + uuid4().hex,
    }
    response = await client.post(f"{PREFIX}/register", json=data)
    assert response.status_code == 202, response.text
    user = await test_session.scalar(select(User).where(User.email == data["email"]))
    return data, user


def credentials(data, **extra):
    return {
        "tenant_slug": data["tenant_slug"],
        "email": data["email"],
        "password": data["password"],
        **extra,
    }


@pytest_asyncio.fixture
async def protected_client(test_session):
    probe = FastAPI()
    probe.add_middleware(RequestLoggingMiddleware)

    @probe.get("/protected")
    async def protected(request: Request, user: User = Depends(get_current_user)):
        return {"id": str(user.id), "tenant_id": request.state.tenant_id}

    async def session():
        yield test_session

    probe.dependency_overrides[get_session] = session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=probe), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def mailbox():
    sent = []

    class Mailer:
        def queue(self, tasks, email, token):
            tasks.add_task(lambda: sent.append((email, token)))

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_password_reset_mailer] = lambda: Mailer()
    yield sent
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


async def test_registration_login_and_current_user(client, account, test_session, protected_client):
    data, user = account
    assert user.password_hash.startswith("$argon2id$")
    assert user.role == "owner"
    response = await client.post(
        f"{PREFIX}/login", json=credentials(data, email=data["email"].upper())
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    pair = response.json()
    assert pair["token_type"] == "bearer"
    assert pair["expires_in"] <= 1800
    claims = decode_token(pair["access_token"])
    assert claims["sub"] == str(user.id)
    assert claims["tenant_id"] == str(user.tenant_id)
    session = await test_session.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert session.token_hash == token_hash(pair["refresh_token"])
    assert session.token_hash != pair["refresh_token"]
    protected = await protected_client.get(
        "/protected", headers={"Authorization": "Bearer " + pair["access_token"]}
    )
    assert protected.json() == {"id": str(user.id), "tenant_id": str(user.tenant_id)}
    assert await test_session.scalar(select(AuditEvent.id).where(AuditEvent.action == "auth.login"))


async def test_login_errors_do_not_enumerate_accounts(client, account, test_session):
    data, _ = account
    wrong = await client.post(f"{PREFIX}/login", json=credentials(data, password="wrong"))
    absent = await client.post(
        f"{PREFIX}/login", json=credentials(data, email="absent@example.com")
    )
    absent_tenant = await client.post(
        f"{PREFIX}/login", json=credentials(data, tenant_slug="nonexistent")
    )
    assert wrong.status_code == absent.status_code == absent_tenant.status_code == 401
    assert (
        wrong.json() == absent.json() == absent_tenant.json() == {"detail": "Authentication failed"}
    )
    assert (
        len(
            (
                await test_session.scalars(
                    select(AuthenticationEvent).where(
                        AuthenticationEvent.action == "auth.login_failed"
                    )
                )
            ).all()
        )
        == 3
    )
    assert await test_session.scalar(
        select(AuditEvent.id).where(AuditEvent.action == "auth.login_failed")
    )


async def test_registration_cannot_join_existing_tenant_or_reveal_email(
    client, account, test_session
):
    data, _ = account
    duplicate = await client.post(f"{PREFIX}/register", json=data)
    stranger = await client.post(
        f"{PREFIX}/register", json={**data, "email": "stranger@example.com"}
    )
    assert duplicate.status_code == stranger.status_code == 202
    assert duplicate.json() == stranger.json()
    assert len((await test_session.scalars(select(User))).all()) == 1


async def test_expired_wrong_purpose_and_tampered_access_tokens(client, account, protected_client):
    _, user = account
    expired = create_access_token(
        str(user.id), str(user.tenant_id), [user.role], timedelta(seconds=-10)
    )
    for value in (expired, expired + "bad", "not-a-jwt"):
        response = await protected_client.get(
            "/protected", headers={"Authorization": "Bearer " + value}
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "Authentication failed"}
    assert (await protected_client.get("/protected")).status_code == 401


async def test_rotation_and_replay_revokes_whole_family(client, account, test_session):
    data, _ = account
    first = (await client.post(f"{PREFIX}/login", json=credentials(data))).json()
    rotated = await client.post(f"{PREFIX}/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    assert (
        await client.post(f"{PREFIX}/refresh", json={"refresh_token": first["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post(f"{PREFIX}/refresh", json={"refresh_token": second["refresh_token"]})
    ).status_code == 401
    assert all(
        row.revoked_at is not None
        for row in (await test_session.scalars(select(AuthSession))).all()
    )


async def test_logout_revokes_refresh_and_is_idempotent(client, account, test_session):
    data, _ = account
    pair = (await client.post(f"{PREFIX}/login", json=credentials(data))).json()
    for _ in range(2):
        assert (
            await client.post(f"{PREFIX}/logout", json={"refresh_token": pair["refresh_token"]})
        ).status_code == 204
    assert (
        await client.post(f"{PREFIX}/refresh", json={"refresh_token": pair["refresh_token"]})
    ).status_code == 401
    assert (
        await client.post(f"{PREFIX}/logout", json={"refresh_token": "unknown"})
    ).status_code == 204
    assert await test_session.scalar(
        select(AuditEvent.id).where(AuditEvent.action == "auth.logout")
    )


async def test_expired_refresh_and_inactive_user_are_denied(client, account, test_session):
    data, user = account
    pair = (await client.post(f"{PREFIX}/login", json=credentials(data))).json()
    await test_session.execute(
        update(AuthSession).values(expires_at=utcnow() - timedelta(seconds=1))
    )
    assert (
        await client.post(f"{PREFIX}/refresh", json={"refresh_token": pair["refresh_token"]})
    ).status_code == 401
    user.is_active = False
    await test_session.flush()
    assert (await client.post(f"{PREFIX}/login", json=credentials(data))).status_code == 401


async def test_failed_login_rate_limit_persists_and_expires(
    client, account, test_session, monkeypatch
):
    data, _ = account
    monkeypatch.setattr(get_settings(), "login_max_failures", 2)
    for _ in range(2):
        assert (
            await client.post(f"{PREFIX}/login", json=credentials(data, password="wrong"))
        ).status_code == 401
    limited = await client.post(f"{PREFIX}/login", json=credentials(data))
    assert limited.status_code == 429
    assert "retry-after" in limited.headers
    await test_session.execute(
        update(AuthRateLimit).values(expires_at=utcnow() - timedelta(seconds=1))
    )
    assert (await client.post(f"{PREFIX}/login", json=credentials(data))).status_code == 200


async def test_password_reset_delivery_single_use_and_session_revocation(
    client, account, mailbox, test_session, protected_client
):
    data, user = account
    old = (await client.post(f"{PREFIX}/login", json=credentials(data))).json()
    identity = {"tenant_slug": data["tenant_slug"], "email": data["email"]}
    known = await client.post(f"{PREFIX}/password-reset/request", json=identity)
    unknown = await client.post(
        f"{PREFIX}/password-reset/request", json={**identity, "email": "absent@example.com"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mailbox) == 1
    email, value = mailbox[0]
    assert email == data["email"]
    assert value not in known.text
    grant = await test_session.scalar(select(PasswordResetGrant))
    assert grant.token_hash == token_hash(value)
    assert (
        await protected_client.get("/protected", headers={"Authorization": "Bearer " + value})
    ).status_code == 401
    payload = {"token": value, "password": "a-new-long-password"}
    confirmed = await client.post(f"{PREFIX}/password-reset/confirm", json=payload)
    assert confirmed.status_code == 200, confirmed.text
    assert (await client.post(f"{PREFIX}/password-reset/confirm", json=payload)).status_code == 401
    assert (await client.post(f"{PREFIX}/login", json=credentials(data))).status_code == 401
    assert (
        await client.post(f"{PREFIX}/login", json=credentials(data, password=payload["password"]))
    ).status_code == 200
    assert (
        await client.post(f"{PREFIX}/refresh", json={"refresh_token": old["refresh_token"]})
    ).status_code == 401
    assert (
        await protected_client.get(
            "/protected", headers={"Authorization": "Bearer " + old["access_token"]}
        )
    ).status_code == 401
    assert await test_session.scalar(
        select(AuditEvent.id).where(AuditEvent.action == "auth.password_reset")
    )


async def test_reset_expiration_and_superseded_requests(client, account, mailbox, test_session):
    data, _ = account
    identity = {"tenant_slug": data["tenant_slug"], "email": data["email"]}
    await client.post(f"{PREFIX}/password-reset/request", json=identity)
    first = mailbox[-1][1]
    await client.post(f"{PREFIX}/password-reset/request", json=identity)
    assert (
        await client.post(
            f"{PREFIX}/password-reset/confirm", json={"token": first, "password": PASSWORD}
        )
    ).status_code == 401
    await test_session.execute(
        update(PasswordResetGrant).values(expires_at=utcnow() - timedelta(seconds=1))
    )
    assert (
        await client.post(
            f"{PREFIX}/password-reset/confirm", json={"token": mailbox[-1][1], "password": PASSWORD}
        )
    ).status_code == 401


async def test_validation_errors_never_echo_secrets(client):
    response = await client.post(
        f"{PREFIX}/login",
        json={"tenant_slug": "test", "email": "invalid", "password": "do-not-reflect-this"},
    )
    assert response.status_code == 422
    assert "do-not-reflect-this" not in response.text
    assert response.json() == {"detail": "Invalid authentication request"}


async def test_disabled_smtp_returns_same_error_for_every_account(client, account, monkeypatch):
    data, _ = account
    monkeypatch.setattr(get_settings(), "smtp_host", None)
    identity = {"tenant_slug": data["tenant_slug"], "email": data["email"]}
    known = await client.post(f"{PREFIX}/password-reset/request", json=identity)
    unknown = await client.post(
        f"{PREFIX}/password-reset/request", json={**identity, "email": "absent@example.com"}
    )
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()


async def test_disabled_tenant_and_wrong_tenant_access_are_denied(
    client, account, protected_client, test_session
):
    data, user = account
    wrong_tenant = create_access_token(str(user.id), str(uuid4()), [user.role])
    assert (
        await protected_client.get(
            "/protected", headers={"Authorization": "Bearer " + wrong_tenant}
        )
    ).status_code == 401
    good = (await client.post(f"{PREFIX}/login", json=credentials(data))).json()
    await test_session.execute(
        update(Tenant).where(Tenant.id == user.tenant_id).values(status="suspended")
    )
    assert (
        await protected_client.get(
            "/protected", headers={"Authorization": "Bearer " + good["access_token"]}
        )
    ).status_code == 401
    assert (
        await client.post(f"{PREFIX}/refresh", json={"refresh_token": good["refresh_token"]})
    ).status_code == 401
    assert (await client.post(f"{PREFIX}/login", json=credentials(data))).status_code == 401


@pytest.mark.parametrize("operation", ["refresh", "failed_login"])
async def test_concurrent_rotation_and_login_limits(test_engine, operation, monkeypatch):
    """Separate connections exercise actual row locking, not a shared test session."""
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant_id = uuid4()
    async with sessions() as session:
        tenant = Tenant(id=tenant_id, name="Concurrent", slug="concurrent-" + uuid4().hex)
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant_id,
            email="concurrent@example.com",
            full_name="Concurrent",
            password_hash=get_password_hash(PASSWORD),
        )
        session.add(user)
        await session.commit()
        login_data = {"tenant_slug": tenant.slug, "email": user.email, "password": PASSWORD}
    probe = FastAPI()
    probe.add_middleware(RequestLoggingMiddleware)
    probe.include_router(auth_router, prefix=PREFIX)

    async def isolated_session():
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    probe.dependency_overrides[get_session] = isolated_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=probe), base_url="http://test"
        ) as client:
            if operation == "refresh":
                pair = (await client.post(f"{PREFIX}/login", json=login_data)).json()
                first, second = await asyncio.gather(
                    *[
                        client.post(
                            f"{PREFIX}/refresh", json={"refresh_token": pair["refresh_token"]}
                        )
                        for _ in range(2)
                    ]
                )
                assert sorted([first.status_code, second.status_code]) == [200, 401]
                winner = first if first.status_code == 200 else second
                assert (
                    await client.post(
                        f"{PREFIX}/refresh", json={"refresh_token": winner.json()["refresh_token"]}
                    )
                ).status_code == 401
                async with sessions() as session:
                    assert await session.scalar(
                        select(AuthenticationEvent.id).where(
                            AuthenticationEvent.tenant_id == tenant_id,
                            AuthenticationEvent.action == "auth.refresh_replay",
                        )
                    )
            else:
                monkeypatch.setattr(get_settings(), "login_max_failures", 1)
                first, second = await asyncio.gather(
                    *[
                        client.post(f"{PREFIX}/login", json={**login_data, "password": "wrong"})
                        for _ in range(2)
                    ]
                )
                assert sorted([first.status_code, second.status_code]) == [401, 429]
    finally:
        async with sessions() as session:
            for model in (AuthSession, PasswordResetGrant, AuthenticationEvent, AuditEvent, User):
                await session.execute(delete(model).where(model.tenant_id == tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
