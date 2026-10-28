"""Refresh sessions, reset grants, durable limits, and system authentication audits."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.models.foundation import Record, Tenant, TenantRecord, User, user_reference


class AuthSession(TenantRecord, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), user_reference("user_id"))
    user_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    family_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], backref="auth_sessions")


class PasswordResetGrant(TenantRecord, Base):
    __tablename__ = "password_reset_grants"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), user_reference("user_id"))
    user_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], backref="password_reset_grants"
    )


class AuthRateLimit(Record, Base):
    """System-owned: limits must also cover identifiers with no tenant/account."""

    __tablename__ = "auth_rate_limits"
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthenticationEvent(Record, Base):
    """System-owned audit stream, including failures for nonexistent tenants."""

    __tablename__ = "authentication_events"
    __table_args__ = (
        user_reference("user_id"),
        CheckConstraint("user_id IS NULL OR tenant_id IS NOT NULL", name="user_requires_tenant"),
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    identifier_hash: Mapped[str | None] = mapped_column(String(64))
    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant", foreign_keys=[tenant_id], backref="authentication_events"
    )
    user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[user_id], backref="authentication_events"
    )
