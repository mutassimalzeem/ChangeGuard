"""PostgreSQL domain schema. Composite foreign keys enforce ownership boundaries."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.core.database import Base


class Record:
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, server_default=sql_text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantRecord(Record):
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    @declared_attr
    def tenant(cls):
        return relationship("Tenant", foreign_keys=[cls.tenant_id], backref=cls.__tablename__)

    @declared_attr.directive
    def __table_args__(cls):
        return (UniqueConstraint("id", "tenant_id"),)


class ProjectRecord(TenantRecord):
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)

    @declared_attr
    def project(cls):
        return relationship("Project", foreign_keys=[cls.project_id], backref=cls.__tablename__)


def project_constraints(*extra):
    """Every project reference must belong to the same tenant."""
    return (
        UniqueConstraint("id", "tenant_id"),
        UniqueConstraint("id", "project_id", "tenant_id"),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        *extra,
    )


def project_reference(column: str, table: str):
    """Related records must belong to both the same project and the same tenant."""
    return ForeignKeyConstraint(
        [column, "project_id", "tenant_id"],
        [f"{table}.id", f"{table}.project_id", f"{table}.tenant_id"],
        ondelete="RESTRICT",
    )


def user_reference(column: str):
    return ForeignKeyConstraint(
        [column, "tenant_id"], ["users.id", "users.tenant_id"], ondelete="RESTRICT"
    )


class Tenant(Record, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(32), server_default="active", index=True)


class User(TenantRecord, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), UniqueConstraint("tenant_id", "email"))
    email: Mapped[str] = mapped_column(String(320))
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, server_default="0")
    role: Mapped[str] = mapped_column(String(32), server_default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Project(TenantRecord, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), UniqueConstraint("tenant_id", "code"))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), server_default="active", index=True)
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")


class Document(ProjectRecord, Base):
    __tablename__ = "documents"
    __table_args__ = project_constraints(user_reference("uploaded_by_id"))
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), server_default="uploaded", index=True)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    uploaded_by: Mapped["User | None"] = relationship(foreign_keys=[uploaded_by_id])
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sql_text("'{}'::jsonb")
    )


class DocumentChunk(ProjectRecord, Base):
    __tablename__ = "document_chunks"
    __table_args__ = project_constraints(
        project_reference("document_id", "documents"),
        UniqueConstraint("document_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sql_text("'{}'::jsonb")
    )
    document: Mapped["Document"] = relationship(foreign_keys=[document_id], backref="chunks")


class ProjectEvent(ProjectRecord, Base):
    __tablename__ = "project_events"
    __table_args__ = project_constraints(project_reference("document_id", "documents"))
    document_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), server_default="recorded", index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sql_text("'{}'::jsonb")
    )
    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id], backref="events")


class Contract(ProjectRecord, Base):
    __tablename__ = "contracts"
    __table_args__ = project_constraints(
        project_reference("document_id", "documents"),
        UniqueConstraint("tenant_id", "project_id", "reference"),
    )
    document_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    reference: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), server_default="draft", index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    effective_date: Mapped[date | None] = mapped_column(Date, index=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    document: Mapped["Document | None"] = relationship(
        foreign_keys=[document_id], backref="contracts"
    )


class ContractClause(ProjectRecord, Base):
    __tablename__ = "contract_clauses"
    __table_args__ = project_constraints(
        project_reference("contract_id", "contracts"),
        UniqueConstraint("contract_id", "clause_number"),
    )
    contract_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    clause_number: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    clause_type: Mapped[str | None] = mapped_column(String(64), index=True)
    contract: Mapped["Contract"] = relationship(foreign_keys=[contract_id], backref="clauses")


class BOQItem(ProjectRecord, Base):
    __tablename__ = "boq_items"
    __table_args__ = project_constraints(
        project_reference("contract_id", "contracts"),
        UniqueConstraint("tenant_id", "project_id", "item_code"),
        CheckConstraint("quantity >= 0", name="quantity_nonnegative"),
    )
    contract_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    item_code: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    contract: Mapped["Contract | None"] = relationship(
        foreign_keys=[contract_id], backref="boq_items"
    )


class RFI(ProjectRecord, Base):
    __tablename__ = "rfis"
    __table_args__ = project_constraints(
        project_reference("document_id", "documents"),
        user_reference("requested_by_id"),
        UniqueConstraint("tenant_id", "project_id", "reference"),
    )
    reference: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(255))
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), server_default="open", index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    requested_by_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id], backref="rfis")
    requested_by: Mapped["User | None"] = relationship(
        foreign_keys=[requested_by_id], backref="rfis"
    )


class ChangeOrder(ProjectRecord, Base):
    __tablename__ = "change_orders"
    __table_args__ = project_constraints(
        project_reference("contract_id", "contracts"),
        project_reference("rfi_id", "rfis"),
        user_reference("created_by_id"),
        UniqueConstraint("tenant_id", "project_id", "reference"),
    )
    reference: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), server_default="draft", index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    time_impact_days: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    contract_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    rfi_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    created_by_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    contract: Mapped["Contract | None"] = relationship(
        foreign_keys=[contract_id], backref="change_orders"
    )
    rfi: Mapped["RFI | None"] = relationship(foreign_keys=[rfi_id], backref="change_orders")
    created_by: Mapped["User | None"] = relationship(
        foreign_keys=[created_by_id], backref="change_orders"
    )


class Risk(ProjectRecord, Base):
    __tablename__ = "risks"
    __table_args__ = project_constraints(
        project_reference("change_order_id", "change_orders"),
        project_reference("document_id", "documents"),
        project_reference("project_event_id", "project_events"),
        user_reference("owner_id"),
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), server_default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), server_default="open", index=True)
    exposure_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    change_order_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    document_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    project_event_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    change_order: Mapped["ChangeOrder | None"] = relationship(
        foreign_keys=[change_order_id], backref="risks"
    )
    document: Mapped["Document | None"] = relationship(foreign_keys=[document_id], backref="risks")
    project_event: Mapped["ProjectEvent | None"] = relationship(
        foreign_keys=[project_event_id], backref="risks"
    )
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id], backref="risks")


class Approval(ProjectRecord, Base):
    __tablename__ = "approvals"
    __table_args__ = project_constraints(
        project_reference("change_order_id", "change_orders"),
        project_reference("risk_id", "risks"),
        user_reference("assigned_to_id"),
        user_reference("decided_by_id"),
        CheckConstraint("num_nonnulls(change_order_id, risk_id) = 1", name="exactly_one_subject"),
    )
    change_order_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    risk_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    assigned_to_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    decided_by_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(32), server_default="pending", index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    change_order: Mapped["ChangeOrder | None"] = relationship(
        foreign_keys=[change_order_id], backref="approvals"
    )
    risk: Mapped["Risk | None"] = relationship(foreign_keys=[risk_id], backref="approvals")
    assigned_to: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_to_id], backref="assigned_approvals"
    )
    decided_by: Mapped["User | None"] = relationship(
        foreign_keys=[decided_by_id], backref="decided_approvals"
    )


class EvidenceLink(ProjectRecord, Base):
    __tablename__ = "evidence_links"
    __table_args__ = project_constraints(
        project_reference("change_order_id", "change_orders"),
        project_reference("risk_id", "risks"),
        project_reference("document_id", "documents"),
        project_reference("document_chunk_id", "document_chunks"),
        project_reference("project_event_id", "project_events"),
        project_reference("boq_item_id", "boq_items"),
        project_reference("contract_clause_id", "contract_clauses"),
        CheckConstraint("num_nonnulls(change_order_id, risk_id) = 1", name="exactly_one_claim"),
        CheckConstraint(
            "num_nonnulls(document_id, document_chunk_id, project_event_id, boq_item_id, contract_clause_id) = 1",
            name="exactly_one_source",
        ),
    )
    change_order_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    risk_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    document_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    document_chunk_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    project_event_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    boq_item_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    contract_clause_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    change_order: Mapped["ChangeOrder | None"] = relationship(
        foreign_keys=[change_order_id], backref="evidence_links"
    )
    risk: Mapped["Risk | None"] = relationship(foreign_keys=[risk_id], backref="evidence_links")
    document: Mapped["Document | None"] = relationship(
        foreign_keys=[document_id], backref="evidence_links"
    )
    document_chunk: Mapped["DocumentChunk | None"] = relationship(
        foreign_keys=[document_chunk_id], backref="evidence_links"
    )
    project_event: Mapped["ProjectEvent | None"] = relationship(
        foreign_keys=[project_event_id], backref="evidence_links"
    )
    boq_item: Mapped["BOQItem | None"] = relationship(
        foreign_keys=[boq_item_id], backref="evidence_links"
    )
    contract_clause: Mapped["ContractClause | None"] = relationship(
        foreign_keys=[contract_clause_id], backref="evidence_links"
    )


class AuditEvent(TenantRecord, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id"),
        user_reference("actor_id"),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sql_text("'{}'::jsonb"))
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id], backref="audit_events")
    project: Mapped["Project | None"] = relationship(
        foreign_keys=[project_id], backref="audit_events"
    )


class AITrace(TenantRecord, Base):
    __tablename__ = "ai_traces"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id"),
        ForeignKeyConstraint(
            ["project_id", "tenant_id"], ["projects.id", "projects.tenant_id"], ondelete="RESTRICT"
        ),
        Index("ix_ai_traces_tenant_created", "tenant_id", "created_at"),
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(100), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), server_default="pending", index=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=sql_text("'{}'::jsonb")
    )
    project: Mapped["Project | None"] = relationship(foreign_keys=[project_id], backref="ai_traces")
