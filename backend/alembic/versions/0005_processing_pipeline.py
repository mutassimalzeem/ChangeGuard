"""Durable processing checkpoints, review tasks, and dead-letter outbox."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0005_processing_pipeline"
down_revision = "0004_document_registry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="queued"),
    )
    op.add_column(
        "documents",
        sa.Column("processing_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute("UPDATE documents SET processing_status=status")
    op.create_index("ix_documents_processing_status", "documents", ["processing_status"])
    for name, columns in (
        ("document_review_tasks", [sa.Column("reason", sa.String(100), nullable=False)]),
        (
            "processing_dead_letters",
            [
                sa.Column("stage", sa.String(32), nullable=False),
                sa.Column("attempts", sa.Integer(), nullable=False),
                sa.Column("error_type", sa.String(100), nullable=False),
            ],
        ),
    ):
        op.create_table(
            name,
            sa.Column(
                "id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "tenant_id",
                sa.Uuid(),
                sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column("document_id", sa.Uuid(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            *columns,
            sa.UniqueConstraint("document_id"),
            sa.UniqueConstraint("id", "tenant_id"),
            sa.UniqueConstraint("id", "project_id", "tenant_id"),
            sa.ForeignKeyConstraint(
                ["project_id", "tenant_id"],
                ["projects.id", "projects.tenant_id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["document_id", "project_id", "tenant_id"],
                ["documents.id", "documents.project_id", "documents.tenant_id"],
                ondelete="RESTRICT",
            ),
        )
        for column in ("created_at", "tenant_id", "project_id", "document_id"):
            op.create_index(f"ix_{name}_{column}", name, [column])
        op.create_index(f"ix_{name}_status", name, ["status"])
    op.create_table(
        "document_entity_links",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid()),
        sa.Column("rfi_id", sa.Uuid()),
        sa.Column("change_order_id", sa.Uuid()),
        sa.UniqueConstraint("id", "tenant_id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "num_nonnulls(contract_id, rfi_id, change_order_id) = 1",
            name=op.f("ck_document_entity_links_one_entity"),
        ),
        *[
            sa.ForeignKeyConstraint(
                [column, "project_id", "tenant_id"],
                [f"{table}.id", f"{table}.project_id", f"{table}.tenant_id"],
                ondelete="RESTRICT",
            )
            for column, table in (
                ("document_id", "documents"),
                ("contract_id", "contracts"),
                ("rfi_id", "rfis"),
                ("change_order_id", "change_orders"),
            )
        ],
        *[
            sa.UniqueConstraint("document_id", column)
            for column in ("contract_id", "rfi_id", "change_order_id")
        ],
    )
    for column in ("created_at", "tenant_id", "project_id", "document_id"):
        op.create_index(f"ix_document_entity_links_{column}", "document_entity_links", [column])
    for table in ("document_entity_links", "document_review_tasks", "processing_dead_letters"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION changeguard_set_updated_at()"
        )
    op.execute(
        "CREATE INDEX ix_document_chunks_search ON document_chunks "
        "USING gin (to_tsvector('english', text))"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_vector ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade():
    op.drop_table("document_entity_links")
    op.drop_index("ix_document_chunks_vector", table_name="document_chunks")
    op.drop_index("ix_document_chunks_search", table_name="document_chunks")
    op.drop_table("processing_dead_letters")
    op.drop_table("document_review_tasks")
    op.drop_index("ix_documents_processing_status", table_name="documents")
    op.drop_column("documents", "processing_data")
    op.drop_column("documents", "processing_status")
