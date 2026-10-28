"""Chunk provenance and extraction metadata; preserve existing chunks and vectors."""

import sqlalchemy as sa

from alembic import op

revision = "0006_text_extraction"
down_revision = "0005_processing_pipeline"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("section", sa.String(512), nullable=False, server_default="document"),
        sa.Column("revision", sa.String(100), nullable=False, server_default="1"),
        sa.Column("date", sa.Date()),
        sa.Column("author", sa.Text()),
        sa.Column("access_level", sa.String(32), nullable=False, server_default="restricted"),
        sa.Column("language", sa.String(35), nullable=False, server_default="und"),
        sa.Column("chunk_hash", sa.String(64)),
        sa.Column("embedding_model", sa.String(255), nullable=False, server_default="unknown"),
    ):
        op.add_column("document_chunks", column)
    op.execute("""
        UPDATE document_chunks AS chunk SET
            revision = document.document_version::text,
            access_level = document.access_level,
            chunk_hash = encode(sha256(convert_to(chunk.text, 'UTF8')), 'hex')
        FROM documents AS document WHERE chunk.document_id = document.id
            AND chunk.project_id = document.project_id AND chunk.tenant_id = document.tenant_id
    """)
    op.alter_column("document_chunks", "chunk_hash", nullable=False)
    op.create_check_constraint(
        op.f("ck_document_chunks_chunk_access_allowed"),
        "document_chunks",
        "access_level IN ('project','restricted')",
    )


def downgrade():
    op.drop_constraint(op.f("ck_document_chunks_chunk_access_allowed"), "document_chunks")
    for name in (
        "embedding_model",
        "chunk_hash",
        "language",
        "access_level",
        "author",
        "date",
        "revision",
        "section",
    ):
        op.drop_column("document_chunks", name)
