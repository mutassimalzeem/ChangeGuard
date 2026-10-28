"""Explicit project assignments; membership never grants a role or changes tenant."""

from uuid import UUID

from sqlalchemy import Boolean, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.models.foundation import ProjectRecord, User, project_constraints, user_reference


class ProjectMembership(ProjectRecord, Base):
    __tablename__ = "project_memberships"
    __table_args__ = project_constraints(
        user_reference("user_id"),
        UniqueConstraint("tenant_id", "project_id", "user_id"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    user: Mapped["User"] = relationship(foreign_keys=[user_id], backref="project_memberships")
