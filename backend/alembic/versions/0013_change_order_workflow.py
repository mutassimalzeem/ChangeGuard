"""Change-order workflow, exact cost inputs and immutable decision history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_change_order_workflow"
down_revision = "0012_potential_changes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("change_orders", sa.Column("source_event_id", sa.Uuid()))
    op.add_column("change_orders", sa.Column("submitted_by_id", sa.Uuid()))
    op.add_column(
        "change_orders",
        sa.Column(
            "cost_items", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column("change_orders", sa.Column("draft_content", postgresql.JSONB()))
    op.create_unique_constraint(
        "uq_change_orders_source_event_id", "change_orders", ["source_event_id"]
    )
    op.create_foreign_key(
        "fk_change_orders_source_event_id_project_events",
        "change_orders",
        "project_events",
        ["source_event_id", "project_id", "tenant_id"],
        ["id", "project_id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_change_orders_submitted_by_id_users",
        "change_orders",
        "users",
        ["submitted_by_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.execute("UPDATE change_orders SET status='drafted' WHERE status='draft'")
    op.execute("UPDATE change_orders SET status='closed' WHERE status='executed'")
    op.alter_column("change_orders", "status", server_default="potential")
    op.create_check_constraint(
        "workflow_status",
        "change_orders",
        "status IN ('potential','under_review','drafted','submitted',"
        "'approved','rejected','disputed','closed')",
    )
    op.execute("""CREATE FUNCTION changeguard_order_transition() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status = OLD.status THEN RETURN NEW; END IF;
      IF (OLD.status='potential' AND NEW.status='under_review')
        OR (OLD.status='under_review' AND NEW.status='drafted')
        OR (OLD.status='drafted' AND NEW.status='submitted')
        OR (OLD.status='submitted' AND NEW.status IN ('approved','rejected','disputed'))
        OR (OLD.status IN ('approved','rejected','disputed') AND NEW.status='closed')
      THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'invalid_change_order_transition' USING ERRCODE='23514';
    END $$""")
    op.execute("""CREATE TRIGGER change_order_transition BEFORE UPDATE OF status ON change_orders
        FOR EACH ROW EXECUTE FUNCTION changeguard_order_transition()""")
    op.execute("""CREATE OR REPLACE FUNCTION changeguard_audit_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP='TRUNCATE' OR OLD.entity_type IN ('risk','change_order') THEN
          RAISE EXCEPTION 'workflow_audit_events_are_append_only' USING ERRCODE='23514';
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
        END $$""")


def downgrade():
    op.execute("DROP TRIGGER change_order_transition ON change_orders")
    op.execute("DROP FUNCTION changeguard_order_transition()")
    op.drop_constraint(op.f("ck_change_orders_workflow_status"), "change_orders", type_="check")
    op.execute("UPDATE change_orders SET status='draft' WHERE status='drafted'")
    op.alter_column("change_orders", "status", server_default="draft")
    op.drop_constraint(
        "fk_change_orders_submitted_by_id_users", "change_orders", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_change_orders_source_event_id_project_events", "change_orders", type_="foreignkey"
    )
    op.drop_constraint("uq_change_orders_source_event_id", "change_orders", type_="unique")
    for column in ("draft_content", "cost_items", "submitted_by_id", "source_event_id"):
        op.drop_column("change_orders", column)
    op.execute("""CREATE OR REPLACE FUNCTION changeguard_audit_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP='TRUNCATE' OR OLD.entity_type='risk' THEN
          RAISE EXCEPTION 'risk_audit_events_are_append_only' USING ERRCODE='23514';
        END IF;
        IF TG_OP='DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
        END $$""")
