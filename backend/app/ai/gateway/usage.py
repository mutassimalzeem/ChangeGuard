"""Durable allowlisted gateway summaries, written independently of business rollbacks."""

from functools import lru_cache
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url

from app.domain.models import AITrace, Document, Project


@lru_cache(maxsize=1)
def usage_engine():
    from app.core.config import get_settings

    url = make_url(str(get_settings().database_url)).set(drivername="postgresql+psycopg2")
    return create_engine(
        url,
        hide_parameters=True,
        pool_size=2,
        max_overflow=2,
        pool_timeout=3,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=3000 -c lock_timeout=1000",
        },
        pool_pre_ping=True,
    )


def persist_usage(summary, *, engine=None):
    """Accept only server-attributed calls; raw prompts/outputs never enter this record."""
    tenant_id, project_id = UUID(summary["tenant_id"]), UUID(summary["project_id"])
    with (engine or usage_engine()).begin() as connection:
        if summary.get("document_id"):
            found = connection.scalar(
                select(Document.id).where(
                    Document.id == UUID(summary["document_id"]),
                    Document.tenant_id == tenant_id,
                    Document.project_id == project_id,
                )
            )
        else:
            found = connection.scalar(
                select(Project.id).where(Project.id == project_id, Project.tenant_id == tenant_id)
            )
        if found is None:
            raise ValueError("Usage attribution not found")
        row = dict(
            id=UUID(summary["trace_id"]),
            tenant_id=tenant_id,
            project_id=project_id,
            operation=summary["task_type"],
            provider="openai",
            model=summary["model"],
            prompt_version=summary["prompt_version"],
            status=summary["validation_result"],
            input_tokens=summary["usage"]["input_tokens"],
            output_tokens=summary["usage"]["output_tokens"],
            duration_ms=summary["latency_ms"],
            cost=summary["cost_estimate"],
            attributes={
                key: summary.get(key)
                for key in (
                    "document_id",
                    "investigation_id",
                    "usage_complete",
                    "attempts",
                    "cost_currency",
                )
            },
        )
        connection.execute(
            insert(AITrace).values(**row).on_conflict_do_nothing(index_elements=["id"])
        )
