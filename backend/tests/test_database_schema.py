"""Schema checks that do not require a running PostgreSQL server."""

import io
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Uuid
from sqlalchemy.orm import configure_mappers

from alembic import command
from app.core.database import Base
from app.domain import models

FOUNDATION_TABLES = {
    "tenants",
    "users",
    "projects",
    "documents",
    "document_chunks",
    "project_events",
    "contracts",
    "contract_clauses",
    "boq_items",
    "rfis",
    "change_orders",
    "risks",
    "approvals",
    "evidence_links",
    "audit_events",
    "ai_traces",
}
SYSTEM_TABLES = {"auth_rate_limits", "authentication_events"}
TABLES = (
    FOUNDATION_TABLES
    | {"claims", "ai_answers", "site_photos"}
    | SYSTEM_TABLES
    | {"auth_sessions", "password_reset_grants", "project_memberships"}
    | {"document_entity_links", "document_review_tasks", "processing_dead_letters"}
)


def test_all_tables_have_uuid_keys_and_timestamps():
    configure_mappers()
    assert set(Base.metadata.tables) == TABLES
    for table in Base.metadata.tables.values():
        assert isinstance(table.c.id.type, Uuid)
        assert table.c.id.primary_key
        for name in ("created_at", "updated_at"):
            assert not table.c[name].nullable
            assert table.c[name].type.timezone
            assert table.c[name].server_default is not None


def test_tenant_and_project_ownership_is_constrained_and_indexed():
    for table in Base.metadata.tables.values():
        if table.name == "tenants" or table.name in SYSTEM_TABLES:
            continue
        assert not table.c.tenant_id.nullable
        assert any(fk.target_fullname == "tenants.id" for fk in table.c.tenant_id.foreign_keys)
        indexed = {tuple(c.name for c in index.columns) for index in table.indexes}
        assert ("tenant_id",) in indexed
        if "project_id" in table.c:
            assert ("project_id",) in indexed
            assert any(
                tuple(c.name for c in fk.columns) == ("project_id", "tenant_id")
                and fk.referred_table.name == "projects"
                for fk in table.foreign_key_constraints
            )
        if "status" in table.c:
            assert ("status",) in indexed


def test_offline_migration_contains_all_tables_and_timestamp_triggers():
    output = io.StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    for table in TABLES:
        assert f"CREATE TABLE {table} (" in sql
        assert f"CREATE TRIGGER trg_{table}_updated_at" in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "FOREIGN KEY(project_id, tenant_id) REFERENCES projects" in sql


def test_models_are_publicly_exported():
    assert len(models.__all__) == len(TABLES)
