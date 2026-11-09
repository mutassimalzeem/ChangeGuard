"""Public metric contracts, units and sample coverage."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Rate(BaseModel):
    value: float | None
    numerator: int
    denominator: int


class Duration(BaseModel):
    value: float | None
    samples: int
    unit: str = "seconds"


class Cost(BaseModel):
    value: str | None
    currency: str = "USD"
    known_subtotal: str
    total: str | None
    resources: int
    calls: int
    known_cost_calls: int


class Latency(BaseModel):
    p50: float | None
    p90: float | None
    p95: float | None
    samples: int
    eligible: int


class PilotMetrics(BaseModel):
    documents_uploaded: int
    documents_processed_successfully: int
    documents_failed: int
    documents_quarantined: int
    documents_awaiting_review: int
    processing_failure_rate: Rate
    classification_accuracy: Rate
    extraction_accuracy: Rate
    evidence_link_coverage: Rate
    risks_detected: int
    risks_accepted: int
    risks_dismissed: int
    human_override_rate: Rate
    change_orders_created: int
    approval_cycle_time: Duration
    time_in_review_queue: Duration
    open_review_queue_age: Duration
    ai_cost_per_document: Cost
    ai_cost_per_investigation: Cost
    processing_latency_seconds: Latency


class MetricsReport(BaseModel):
    schema_version: int = 1
    project_id: UUID
    start: datetime | None
    end: datetime
    generated_at: datetime
    metrics: PilotMetrics
    limitations: list[str]


class Dashboard(BaseModel):
    report: MetricsReport
    sections: dict[str, list[str]]
