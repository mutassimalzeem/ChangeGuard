"""Evidence-backed potential changes reuse project events."""

import sqlalchemy as sa

from alembic import op

revision = "0012_potential_changes"
down_revision = "0011_deterministic_risks"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("detection_key", sa.String(64)),
        sa.Column("detected_date", sa.Date()),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("suggested_owner", sa.String(255)),
        sa.Column("suggested_cost_impact", sa.Numeric(18, 2)),
        sa.Column("suggested_currency", sa.String(3)),
        sa.Column("suggested_schedule_impact", sa.Integer()),
    ):
        op.add_column("project_events", column)
    op.create_unique_constraint(
        "uq_project_events_detection_key", "project_events", ["detection_key"]
    )


def downgrade():
    op.drop_constraint("uq_project_events_detection_key", "project_events", type_="unique")
    for name in (
        "detection_key",
        "detected_date",
        "confidence",
        "suggested_owner",
        "suggested_cost_impact",
        "suggested_currency",
        "suggested_schedule_impact",
    ):
        op.drop_column("project_events", name)
