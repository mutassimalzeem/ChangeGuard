"""Deterministic risk results; retain legacy risk records unchanged."""

import sqlalchemy as sa

from alembic import op

revision = "0011_deterministic_risks"
down_revision = "0010_hybrid_retrieval"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("risk_type", sa.String(64)),
        sa.Column("rule_key", sa.String(255)),
        sa.Column("schedule_impact_days", sa.Integer()),
        sa.Column("responsible_party", sa.String(255)),
        sa.Column("recommended_action", sa.Text()),
        sa.Column("confidence", sa.Numeric(5, 4)),
    ):
        op.add_column("risks", column)
    op.create_unique_constraint("uq_risks_rule_key", "risks", ["rule_key"])
    op.execute("""CREATE FUNCTION changeguard_audit_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP = 'TRUNCATE' OR OLD.entity_type = 'risk' THEN
            RAISE EXCEPTION 'risk_audit_events_are_append_only' USING ERRCODE='23514';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE
        ON audit_events FOR EACH ROW EXECUTE FUNCTION changeguard_audit_immutable()""")
    op.execute("""CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE
        ON audit_events FOR EACH STATEMENT EXECUTE FUNCTION changeguard_audit_immutable()""")


def downgrade():
    op.execute("DROP TRIGGER audit_no_truncate ON audit_events")
    op.execute("DROP TRIGGER audit_immutable ON audit_events")
    op.execute("DROP FUNCTION changeguard_audit_immutable()")
    op.drop_constraint("uq_risks_rule_key", "risks", type_="unique")
    for name in (
        "confidence",
        "recommended_action",
        "responsible_party",
        "schedule_impact_days",
        "rule_key",
        "risk_type",
    ):
        op.drop_column("risks", name)
