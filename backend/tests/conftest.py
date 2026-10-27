"""Isolated PostgreSQL fixtures; never create/drop tables in a developer database."""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.database import get_session
from app.domain.models import Project, Tenant, User
from app.main import app


def migration_config(connection=None) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_database_url() -> AsyncIterator[str]:
    """Use an admin connection only to create/drop a new UUID-named database."""
    admin_url = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if not admin_url:
        pytest.skip(
            "Set TEST_DATABASE_ADMIN_URL to a PostgreSQL test server with CREATEDB privileges"
        )
    url = make_url(admin_url)
    if url.drivername != "postgresql+asyncpg":
        pytest.fail("TEST_DATABASE_ADMIN_URL must use postgresql+asyncpg")
    database_name = f"changeguard_test_{uuid4().hex}"
    admin = create_async_engine(
        url, isolation_level="AUTOCOMMIT", poolclass=NullPool, hide_parameters=True
    )
    created = False
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        created = True
        yield url.set(database=database_name).render_as_string(hide_password=False)
    finally:
        if created:
            async with admin.connect() as connection:
                await connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
        await admin.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_database_url, poolclass=NullPool, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Outer rollback survives application session.commit() via savepoints."""
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture
async def tenant(test_session: AsyncSession) -> Tenant:
    tenant = Tenant(name="Test tenant", slug=f"tenant-{uuid4().hex}")
    test_session.add(tenant)
    await test_session.flush()
    return tenant


@pytest_asyncio.fixture
async def project(test_session: AsyncSession, tenant: Tenant) -> Project:
    project = Project(tenant_id=tenant.id, code="TEST", name="Test project")
    test_session.add(project)
    await test_session.flush()
    return project


@pytest_asyncio.fixture
async def user(test_session: AsyncSession, tenant: Tenant) -> User:
    user = User(
        tenant_id=tenant.id,
        email="test@example.invalid",
        full_name="Test user",
        password_hash="test-hash",
    )
    test_session.add(user)
    await test_session.flush()
    return user


@pytest_asyncio.fixture
async def client(test_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_session():
        yield test_session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
