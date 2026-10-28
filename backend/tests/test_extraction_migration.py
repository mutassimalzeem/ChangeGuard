"""Backfill provenance without discarding existing chunks or embeddings."""

import hashlib
from uuid import uuid4

from sqlalchemy import text

from alembic import command
from tests.conftest import migration_config


async def test_existing_chunks_are_backfilled_without_reembedding(test_engine):
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(
                lambda conn: command.downgrade(migration_config(conn), "0005_processing_pipeline")
            )
            tenant, project, document, chunk = (uuid4() for _ in range(4))
            await connection.execute(
                text("INSERT INTO tenants (id,name,slug) VALUES (:id,'Migration',:slug)"),
                {"id": tenant, "slug": str(tenant)},
            )
            await connection.execute(
                text(
                    "INSERT INTO projects (id,tenant_id,code,name) "
                    "VALUES (:id,:tenant,'MIGRATION','Migration')"
                ),
                {"id": project, "tenant": tenant},
            )
            await connection.execute(
                text("""
                INSERT INTO documents (id,tenant_id,project_id,filename,storage_key,mime_type,
                    size_bytes,document_version,access_level) VALUES
                    (:id,:tenant,:project,'legacy.pdf','legacy','application/pdf',1,7,'project')
            """),
                {"id": document, "tenant": tenant, "project": project},
            )
            await connection.execute(
                text("""
                INSERT INTO document_chunks (id,tenant_id,project_id,document_id,chunk_index,text,
                    page_number,embedding) VALUES
                    (:id,:tenant,:project,:document,0,'Legacy clause',2,CAST(:vector AS vector))
            """),
                {
                    "id": chunk,
                    "tenant": tenant,
                    "project": project,
                    "document": document,
                    "vector": str([0.1] * 1536),
                },
            )
            await connection.run_sync(lambda conn: command.upgrade(migration_config(conn), "head"))
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT *, embedding IS NOT NULL AS has_vector "
                            "FROM document_chunks WHERE id=:id"
                        ),
                        {"id": chunk},
                    )
                )
                .mappings()
                .one()
            )
            assert row["text"] == "Legacy clause" and row["page_number"] == 2
            assert row["chunk_hash"] == hashlib.sha256(b"Legacy clause").hexdigest()
            assert row["revision"] == "7" and row["access_level"] == "project"
            assert row["language"] == "und" and row["embedding_model"] == "unknown"
            assert row["has_vector"] is True
            assert row["date"] is None and row["author"] is None
        finally:
            await transaction.rollback()
