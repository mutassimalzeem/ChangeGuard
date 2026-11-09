"""Durable pilot onboarding state."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0014_pilot_onboarding"
down_revision = "0013_change_order_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pilot_onboarding",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column(
            "completed", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("project_id"),
        sa.UniqueConstraint("id", "tenant_id"),
        sa.UniqueConstraint("id", "project_id", "tenant_id"),
    )
    for column in ("tenant_id", "project_id", "created_at"):
        op.create_index("ix_pilot_onboarding_" + column, "pilot_onboarding", [column])

    op.execute(
        "CREATE TRIGGER trg_pilot_onboarding_updated_at BEFORE UPDATE ON pilot_onboarding FOR EACH ROW EXECUTE FUNCTION changeguard_set_updated_at()"
    )


def downgrade():
    op.drop_table("pilot_onboarding")
