"""Persist validated structured facts without inventing historical provenance."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0008_structured_extraction"
down_revision = "0007_document_classification"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("structured_extraction", JSONB))


def downgrade():
    op.drop_column("documents", "structured_extraction")
