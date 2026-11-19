"""Preserve insufficient-evidence findings across human review decisions."""

import sqlalchemy as sa

from alembic import op

revision = "0017_review_queue_evidence"
down_revision = "0016_risk_resolution"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "risks",
        sa.Column(
            "evidence_review_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute("""
        UPDATE risks SET evidence_review_required = true
        WHERE status = 'insufficient_evidence' OR EXISTS (
            SELECT 1 FROM audit_events
            WHERE entity_type = 'risk' AND entity_id = risks.id
              AND tenant_id = risks.tenant_id AND project_id = risks.project_id
              AND (details->'before'->>'status' = 'insufficient_evidence'
                   OR (action = 'risk.create' AND details->>'status' = 'insufficient_evidence'))
        )
    """)


def downgrade():
    op.drop_column("risks", "evidence_review_required")
