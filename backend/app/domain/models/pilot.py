"""Durable pilot template and checklist, scoped like other project records."""

from sqlalchemy import String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.models.foundation import ProjectRecord, project_constraints


class PilotOnboarding(ProjectRecord, Base):
    __tablename__ = "pilot_onboarding"
    __table_args__ = project_constraints(UniqueConstraint("project_id"))
    template: Mapped[str] = mapped_column(String(64))
    completed: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
