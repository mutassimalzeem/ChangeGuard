"""First-class immutable evidence and deferred factual support constraints."""

# Long SQL statements are kept together for migration review.
# ruff: noqa: E501
import sqlalchemy as sa

from alembic import op

revision = "0009_evidence_links"
down_revision = "0008_structured_extraction"
branch_labels = None
depends_on = None

SUBJECTS = {
    "claim": "claims",
    "risk": "risks",
    "project_event": "project_events",
    "change_order": "change_orders",
    "ai_answer": "ai_answers",
}
SOURCES = {
    "document": "documents",
    "document_chunk": "document_chunks",
    "site_photo": "site_photos",
    "project_event": "project_events",
    "boq_item": "boq_items",
    "contract_clause": "contract_clauses",
}
LEGACY = [
    "change_order_id",
    "risk_id",
    "document_id",
    "document_chunk_id",
    "project_event_id",
    "boq_item_id",
    "contract_clause_id",
]


def upgrade():
    for table, extra in [
        (
            "ai_answers",
            [
                sa.Column("text", sa.Text(), nullable=False),
                sa.CheckConstraint(
                    "status IN ('supported','insufficient_evidence')", name="answer_status"
                ),
                sa.Column(
                    "status", sa.String(32), nullable=False, server_default="insufficient_evidence"
                ),
                sa.Column("created_by", sa.Uuid()),
                sa.ForeignKeyConstraint(
                    ["created_by", "tenant_id"],
                    ["users.id", "users.tenant_id"],
                    ondelete="RESTRICT",
                ),
            ],
        ),
        (
            "claims",
            [
                sa.Column("text", sa.Text(), nullable=False),
                sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
                sa.Column(
                    "ai_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")
                ),
                sa.Column("ai_answer_id", sa.Uuid()),
                sa.ForeignKeyConstraint(
                    ["ai_answer_id", "project_id", "tenant_id"],
                    ["ai_answers.id", "ai_answers.project_id", "ai_answers.tenant_id"],
                    ondelete="RESTRICT",
                ),
                sa.CheckConstraint(
                    "status IN ('draft','verified','insufficient_evidence')", name="claim_status"
                ),
            ],
        ),
        (
            "site_photos",
            [
                sa.Column("document_id", sa.Uuid(), nullable=False),
                sa.Column("caption", sa.Text()),
                sa.ForeignKeyConstraint(
                    ["document_id", "project_id", "tenant_id"],
                    ["documents.id", "documents.project_id", "documents.tenant_id"],
                    ondelete="RESTRICT",
                ),
            ],
        ),
    ]:
        op.create_table(
            table,
            sa.Column(
                "id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")
            ),
            sa.Column(
                "tenant_id",
                sa.Uuid(),
                sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("project_id", sa.Uuid(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("id", "tenant_id"),
            sa.UniqueConstraint("id", "project_id", "tenant_id"),
            sa.ForeignKeyConstraint(
                ["project_id", "tenant_id"],
                ["projects.id", "projects.tenant_id"],
                ondelete="RESTRICT",
            ),
            *extra,
        )
        for column in (
            ["tenant_id", "project_id", "created_at"]
            + (["status"] if table != "site_photos" else ["document_id"])
            + (["ai_answer_id"] if table == "claims" else [])
        ):
            op.create_index(f"ix_{table}_{column}", table, [column])
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION changeguard_set_updated_at()"
        )
    for name, kind in [
        ("subject_type", sa.String(32)),
        ("subject_id", sa.Uuid()),
        ("source_type", sa.String(32)),
        ("source_id", sa.Uuid()),
        ("relevance", sa.Numeric(5, 4)),
        ("source_page", sa.Integer()),
        ("source_text_snippet", sa.Text()),
        ("created_by", sa.Uuid()),
    ]:
        op.add_column("evidence_links", sa.Column(name, kind))
    op.execute("""UPDATE evidence_links SET
        subject_type = CASE WHEN change_order_id IS NOT NULL THEN 'change_order' ELSE 'risk' END,
        subject_id = coalesce(change_order_id, risk_id),
        source_type = CASE WHEN document_id IS NOT NULL THEN 'document' WHEN document_chunk_id IS NOT NULL THEN 'document_chunk' WHEN project_event_id IS NOT NULL THEN 'project_event' WHEN boq_item_id IS NOT NULL THEN 'boq_item' ELSE 'contract_clause' END,
        source_id = coalesce(document_id, document_chunk_id, project_event_id, boq_item_id, contract_clause_id)""")
    for name in ["subject_type", "subject_id", "source_type", "source_id"]:
        op.alter_column("evidence_links", name, nullable=False)
    for name in ["exactly_one_claim", "exactly_one_source"]:
        op.drop_constraint(op.f(f"ck_evidence_links_{name}"), "evidence_links", type_="check")
    for name in LEGACY:
        # Drop dependent legacy indexes and composite FKs with their columns.
        op.execute(f"ALTER TABLE evidence_links DROP COLUMN {name} CASCADE")
    op.create_foreign_key(
        "fk_evidence_links_created_by_users",
        "evidence_links",
        "users",
        ["created_by", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="RESTRICT",
    )
    for name, condition in [
        (
            "subject_type",
            "subject_type IN ('claim','risk','project_event','change_order','ai_answer')",
        ),
        (
            "source_type",
            "source_type IN ('document','document_chunk','site_photo','project_event','boq_item','contract_clause')",
        ),
        ("relevance_range", "relevance >= 0 AND relevance <= 1"),
        ("confidence_range", "confidence >= 0 AND confidence <= 1"),
        ("source_page_positive", "source_page > 0"),
    ]:
        op.create_check_constraint(name, "evidence_links", condition)
    op.create_index(
        "ix_evidence_links_subject",
        "evidence_links",
        ["tenant_id", "project_id", "subject_type", "subject_id"],
    )
    op.create_index("ix_evidence_links_source", "evidence_links", ["source_type", "source_id"])
    op.execute("""CREATE FUNCTION changeguard_evidence_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE target_table text; found_id uuid;
    BEGIN
      target_table := CASE NEW.subject_type WHEN 'claim' THEN 'claims' WHEN 'risk' THEN 'risks' WHEN 'project_event' THEN 'project_events' WHEN 'change_order' THEN 'change_orders' WHEN 'ai_answer' THEN 'ai_answers' END;
      IF target_table IS NULL THEN RAISE EXCEPTION 'invalid_subject' USING ERRCODE='23514'; END IF;
      EXECUTE format('SELECT id FROM %I WHERE id=$1 AND tenant_id=$2 AND project_id=$3 FOR SHARE', target_table) INTO found_id USING NEW.subject_id, NEW.tenant_id, NEW.project_id;
      IF found_id IS NULL THEN RAISE EXCEPTION 'invalid_evidence_subject' USING ERRCODE='23503'; END IF;
      target_table := CASE NEW.source_type WHEN 'document' THEN 'documents' WHEN 'document_chunk' THEN 'document_chunks' WHEN 'site_photo' THEN 'site_photos' WHEN 'project_event' THEN 'project_events' WHEN 'boq_item' THEN 'boq_items' WHEN 'contract_clause' THEN 'contract_clauses' END;
      IF target_table IS NULL THEN RAISE EXCEPTION 'invalid_source' USING ERRCODE='23514'; END IF;
      EXECUTE format('SELECT id FROM %I WHERE id=$1 AND tenant_id=$2 AND project_id=$3 FOR SHARE', target_table) INTO found_id USING NEW.source_id, NEW.tenant_id, NEW.project_id;
      IF found_id IS NULL THEN RAISE EXCEPTION 'invalid_evidence_source' USING ERRCODE='23503'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER evidence_insert BEFORE INSERT ON evidence_links FOR EACH ROW EXECUTE FUNCTION changeguard_evidence_insert()"
    )
    op.execute("""CREATE FUNCTION changeguard_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'evidence_links_are_append_only' USING ERRCODE='23514'; END $$""")
    op.execute(
        "CREATE TRIGGER evidence_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON evidence_links FOR EACH STATEMENT EXECUTE FUNCTION changeguard_evidence_immutable()"
    )
    op.execute("""CREATE FUNCTION changeguard_evidence_reference() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'UPDATE' AND NEW.id = OLD.id AND NEW.tenant_id = OLD.tenant_id AND NEW.project_id = OLD.project_id THEN RETURN NEW; END IF;
      IF EXISTS (SELECT 1 FROM evidence_links WHERE tenant_id=OLD.tenant_id AND project_id=OLD.project_id AND ((subject_type=TG_ARGV[0] AND subject_id=OLD.id) OR (source_type=TG_ARGV[0] AND source_id=OLD.id))) THEN
        RAISE EXCEPTION 'referenced_evidence_record' USING ERRCODE='23503';
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$""")
    for kind, table in (SUBJECTS | SOURCES).items():
        op.execute(
            f"CREATE TRIGGER evidence_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION changeguard_evidence_immutable()"
        )
        op.execute(
            f"CREATE TRIGGER evidence_reference BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION changeguard_evidence_reference('{kind}')"
        )
    op.execute("""CREATE FUNCTION changeguard_claim_support() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE current_claim claims;
    BEGIN
      SELECT * INTO current_claim FROM claims WHERE id=NEW.id;
      IF (current_claim.ai_generated OR current_claim.status='verified') AND NOT EXISTS
        (SELECT 1 FROM evidence_links WHERE subject_type='claim' AND subject_id=current_claim.id AND tenant_id=current_claim.tenant_id AND project_id=current_claim.project_id) THEN
        RAISE EXCEPTION 'insufficient_evidence' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER claim_support AFTER INSERT OR UPDATE ON claims DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION changeguard_claim_support()"
    )
    op.execute("""CREATE FUNCTION changeguard_answer_support() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (SELECT 1 FROM ai_answers a WHERE a.id=NEW.id AND a.status <> 'insufficient_evidence' AND NOT EXISTS (SELECT 1 FROM evidence_links e WHERE e.subject_type='ai_answer' AND e.subject_id=a.id AND e.tenant_id=a.tenant_id AND e.project_id=a.project_id)) THEN
        RAISE EXCEPTION 'insufficient_evidence' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER answer_support AFTER INSERT OR UPDATE ON ai_answers DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION changeguard_answer_support()"
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM evidence_links WHERE subject_type NOT IN ('risk','change_order') OR source_type='site_photo') OR EXISTS (SELECT 1 FROM claims) OR EXISTS (SELECT 1 FROM ai_answers) OR EXISTS (SELECT 1 FROM site_photos) THEN
        RAISE EXCEPTION 'Cannot downgrade without losing evidence domain records';
      END IF;
    END $$""")
    op.execute("DROP TRIGGER evidence_immutable ON evidence_links")
    op.execute("DROP TRIGGER evidence_insert ON evidence_links")
    for table in (SUBJECTS | SOURCES).values():
        op.execute(f"DROP TRIGGER evidence_reference ON {table}")
        op.execute(f"DROP TRIGGER evidence_no_truncate ON {table}")
    for column in LEGACY:
        op.add_column("evidence_links", sa.Column(column, sa.Uuid()))
        target = {
            "change_order_id": "change_orders",
            "risk_id": "risks",
            "document_id": "documents",
            "document_chunk_id": "document_chunks",
            "project_event_id": "project_events",
            "boq_item_id": "boq_items",
            "contract_clause_id": "contract_clauses",
        }[column]
        op.create_foreign_key(
            f"fk_evidence_links_{column}_{target}",
            "evidence_links",
            target,
            [column, "project_id", "tenant_id"],
            ["id", "project_id", "tenant_id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_evidence_links_{column}", "evidence_links", [column])
    for kind in ["change_order", "risk"]:
        op.execute(f"UPDATE evidence_links SET {kind}_id=subject_id WHERE subject_type='{kind}'")
    for kind in ["document", "document_chunk", "project_event", "boq_item", "contract_clause"]:
        op.execute(f"UPDATE evidence_links SET {kind}_id=source_id WHERE source_type='{kind}'")
    for name in [
        "subject_type",
        "source_type",
        "relevance_range",
        "confidence_range",
        "source_page_positive",
    ]:
        op.drop_constraint(op.f(f"ck_evidence_links_{name}"), "evidence_links", type_="check")
    for column in [
        "subject_type",
        "subject_id",
        "source_type",
        "source_id",
        "relevance",
        "source_page",
        "source_text_snippet",
        "created_by",
    ]:
        op.execute(f"ALTER TABLE evidence_links DROP COLUMN {column} CASCADE")
    op.create_check_constraint(
        "exactly_one_claim", "evidence_links", "num_nonnulls(change_order_id,risk_id)=1"
    )
    op.create_check_constraint(
        "exactly_one_source",
        "evidence_links",
        "num_nonnulls(document_id,document_chunk_id,project_event_id,boq_item_id,contract_clause_id)=1",
    )
    for table in ["claims", "site_photos", "ai_answers"]:
        op.drop_table(table)
    for function in [
        "changeguard_claim_support",
        "changeguard_answer_support",
        "changeguard_evidence_insert",
        "changeguard_evidence_immutable",
        "changeguard_evidence_reference",
    ]:
        op.execute(f"DROP FUNCTION {function}()")
