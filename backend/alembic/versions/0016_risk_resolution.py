"""Explicit event relationships and immutable, audited risk resolution."""

import sqlalchemy as sa
from alembic import op

revision = "0016_risk_resolution"
down_revision = "0015_project_metadata"
branch_labels = None
depends_on = None

RESOLUTION_CHECK = (
    "(resolution_link_id IS NULL AND resolved_by_id IS NULL AND resolved_at IS NULL AND resolution_reason IS NULL "
    "AND (risk_type IS DISTINCT FROM 'daily_report_delay_without_link' OR status <> 'resolved')) OR "
    "(resolution_link_id IS NOT NULL AND resolved_by_id IS NOT NULL AND resolved_at IS NOT NULL "
    "AND resolution_reason IS NOT NULL AND length(btrim(resolution_reason)) > 0 AND project_event_id IS NOT NULL "
    "AND risk_type IS NOT DISTINCT FROM 'daily_report_delay_without_link' AND status = 'resolved')"
)


def upgrade():
    op.create_table(
        "event_entity_links",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("rfi_id", sa.Uuid()),
        sa.Column("change_order_id", sa.Uuid()),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("id", "tenant_id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id"),
        sa.UniqueConstraint("id", "event_id", "project_id", "tenant_id"),
        sa.UniqueConstraint("event_id", "rfi_id"),
        sa.UniqueConstraint("event_id", "change_order_id"),
        sa.CheckConstraint("num_nonnulls(rfi_id, change_order_id) = 1", name="one_entity"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_required"),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "project_id", "tenant_id"],
            ["project_events.id", "project_events.project_id", "project_events.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rfi_id", "project_id", "tenant_id"],
            ["rfis.id", "rfis.project_id", "rfis.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["change_order_id", "project_id", "tenant_id"],
            ["change_orders.id", "change_orders.project_id", "change_orders.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id", "tenant_id"], ["users.id", "users.tenant_id"], ondelete="RESTRICT"
        ),
    )
    for name in ("tenant_id", "project_id", "event_id", "created_at"):
        op.create_index("ix_event_entity_links_" + name, "event_entity_links", [name])
    op.execute(
        "CREATE TRIGGER trg_event_entity_links_updated_at BEFORE UPDATE ON event_entity_links FOR EACH ROW EXECUTE FUNCTION changeguard_set_updated_at()"
    )
    for column in (
        sa.Column("resolution_link_id", sa.Uuid()),
        sa.Column("resolved_by_id", sa.Uuid()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_reason", sa.String(2000)),
    ):
        op.add_column("risks", column)
    op.create_foreign_key(
        "fk_risks_resolution_event",
        "risks",
        "event_entity_links",
        ["resolution_link_id", "project_event_id", "project_id", "tenant_id"],
        ["id", "event_id", "project_id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_risks_resolved_by_id_users",
        "risks",
        "users",
        ["resolved_by_id", "tenant_id"],
        ["id", "tenant_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint("resolution_complete", "risks", RESOLUTION_CHECK)
    op.execute("""CREATE FUNCTION changeguard_event_link_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'event_links_are_append_only' USING ERRCODE='23514'; END $$""")
    op.execute(
        "CREATE TRIGGER event_link_immutable BEFORE UPDATE OR DELETE ON event_entity_links FOR EACH ROW EXECUTE FUNCTION changeguard_event_link_immutable()"
    )
    op.execute(
        "CREATE TRIGGER event_link_no_truncate BEFORE TRUNCATE ON event_entity_links FOR EACH STATEMENT EXECUTE FUNCTION changeguard_event_link_immutable()"
    )
    op.execute("""CREATE FUNCTION changeguard_resolution_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.resolution_link_id IS NOT NULL AND (NEW.resolution_link_id IS DISTINCT FROM OLD.resolution_link_id
            OR NEW.resolved_by_id IS DISTINCT FROM OLD.resolved_by_id OR NEW.resolved_at IS DISTINCT FROM OLD.resolved_at
            OR NEW.resolution_reason IS DISTINCT FROM OLD.resolution_reason OR NEW.status IS DISTINCT FROM OLD.status) THEN
            RAISE EXCEPTION 'risk_resolution_is_immutable' USING ERRCODE='23514'; END IF;
        RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER risk_resolution_immutable BEFORE UPDATE ON risks FOR EACH ROW EXECUTE FUNCTION changeguard_resolution_immutable()"
    )
    op.execute("""CREATE FUNCTION changeguard_resolution_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.resolution_link_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM audit_events a WHERE
            a.tenant_id=NEW.tenant_id AND a.project_id=NEW.project_id AND a.entity_type='risk'
            AND a.entity_id=NEW.id AND a.action='risk.resolve' AND a.actor_id=NEW.resolved_by_id
            AND a.details->>'event_link_id'=NEW.resolution_link_id::text
            AND a.details->>'reason'=NEW.resolution_reason
            AND (a.details->>'resolved_at')::timestamptz=NEW.resolved_at) THEN
            RAISE EXCEPTION 'risk_resolution_requires_audit' USING ERRCODE='23514'; END IF;
        RETURN NULL; END $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER risk_resolution_audit AFTER INSERT OR UPDATE ON risks DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION changeguard_resolution_audit()"
    )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM event_entity_links) OR EXISTS (SELECT 1 FROM risks WHERE resolution_link_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Cannot discard event-link or resolution history'; END IF; END $$""")
    op.execute("DROP TRIGGER risk_resolution_audit ON risks")
    op.execute("DROP FUNCTION changeguard_resolution_audit()")
    op.execute("DROP TRIGGER risk_resolution_immutable ON risks")
    op.execute("DROP FUNCTION changeguard_resolution_immutable()")
    op.drop_constraint(op.f("ck_risks_resolution_complete"), "risks", type_="check")
    op.drop_constraint("fk_risks_resolution_event", "risks", type_="foreignkey")
    op.drop_constraint("fk_risks_resolved_by_id_users", "risks", type_="foreignkey")
    for name in ("resolution_reason", "resolved_at", "resolved_by_id", "resolution_link_id"):
        op.drop_column("risks", name)
    op.drop_table("event_entity_links")
    op.execute("DROP FUNCTION changeguard_event_link_immutable()")
