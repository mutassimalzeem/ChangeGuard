"""Identifier-friendly full-text index alongside English keyword and pgvector indexes."""

from alembic import op

revision = "0010_hybrid_retrieval"
down_revision = "0009_evidence_links"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX ix_document_chunks_identifiers ON document_chunks "
        "USING gin (to_tsvector('simple', text))"
    )


def downgrade():
    op.drop_index("ix_document_chunks_identifiers", table_name="document_chunks")
