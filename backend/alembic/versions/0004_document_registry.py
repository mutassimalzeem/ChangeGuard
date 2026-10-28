"""Document registry metadata, duplicate boundary and processing states."""

import sqlalchemy as sa

from alembic import op

revision = "0004_document_registry"
down_revision = "0003_roles_permissions"
branch_labels = None
depends_on = None

STATES = "'received','validating','stored','queued','processing','extracted','classified','indexed','linked','review_required','failed','quarantined'"


def upgrade():
    op.alter_column("documents", "size_bytes", type_=sa.BigInteger(), existing_type=sa.Integer())
    for column in (
        sa.Column("file_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("source", sa.String(64), nullable=False, server_default="upload"),
        sa.Column("document_type", sa.String(100)),
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("access_level", sa.String(32), nullable=False, server_default="project"),
        sa.Column("extraction_confidence", sa.Numeric(5, 4)),
        sa.Column("error_message", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("documents", column)
    op.execute("UPDATE documents SET status='review_required' WHERE status NOT IN (" + STATES + ")")
    # Existing duplicate hashes must be reconciled explicitly before migration.
    op.alter_column("documents", "status", server_default="received")
    op.create_unique_constraint(
        "uq_documents_tenant_id_project_id_checksum",
        "documents",
        ["tenant_id", "project_id", "checksum"],
    )
    op.create_check_constraint(
        op.f("ck_documents_document_status_allowed"), "documents", "status IN (" + STATES + ")"
    )
    op.create_check_constraint(
        op.f("ck_documents_document_access_allowed"),
        "documents",
        "access_level IN ('project','restricted')",
    )


def downgrade():
    op.alter_column("documents", "size_bytes", type_=sa.Integer(), existing_type=sa.BigInteger())
    op.drop_constraint(op.f("ck_documents_document_access_allowed"), "documents")
    op.drop_constraint(op.f("ck_documents_document_status_allowed"), "documents")
    op.drop_constraint("uq_documents_tenant_id_project_id_checksum", "documents")
    op.alter_column("documents", "status", server_default="uploaded")
    for name in (
        "deleted_at",
        "error_message",
        "extraction_confidence",
        "access_level",
        "document_version",
        "document_type",
        "source",
        "file_type",
    ):
        op.drop_column("documents", name)
