"""Protect all workspace decisions and command receipts at the database boundary."""

from alembic import op

revision = "0018_review_workspace"
down_revision = "0017_review_queue_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION changeguard_review_audit_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'review_audit_events_are_append_only' USING ERRCODE='23514';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER review_audit_immutable BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW WHEN (OLD.entity_type IN ('approval', 'document_review_task'))
        EXECUTE FUNCTION changeguard_review_audit_immutable()
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_review_command_key ON audit_events
        (tenant_id, project_id, entity_type, entity_id, actor_id, (details->>'key'))
        WHERE action IN ('review.command','review.add_note','review.assign_owner')
    """)


def downgrade():
    op.execute("DROP INDEX uq_review_command_key")
    op.execute("DROP TRIGGER review_audit_immutable ON audit_events")
    op.execute("DROP FUNCTION changeguard_review_audit_immutable()")
