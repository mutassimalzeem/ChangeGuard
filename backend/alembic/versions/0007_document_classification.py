"""Persist classifier confidence, reasoning and provenance without relabelling history."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0007_document_classification"
down_revision = "0006_text_extraction"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("classification_result", JSONB))


def downgrade():
    op.drop_column("documents", "classification_result")
