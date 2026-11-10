"""Persist the metadata required by project create/read contracts."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0015_project_metadata"
down_revision = "0014_pilot_onboarding"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects",
        sa.Column("client_name", sa.String(255), nullable=False, server_default="Unspecified"),
    )
    op.add_column("projects", sa.Column("contract_value", sa.Numeric(18, 2)))
    op.add_column("projects", sa.Column("stakeholders", postgresql.JSONB()))


def downgrade():
    op.drop_column("projects", "stakeholders")
    op.drop_column("projects", "contract_value")
    op.drop_column("projects", "client_name")
