"""Deterministic project pilot metrics; unknown measurements remain explicit."""

from datetime import UTC, datetime
from decimal import Decimal
from math import floor


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def ratio(numerator, denominator):
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }


def timestamp(value):
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
        return result.astimezone(UTC) if isinstance(result, datetime) and result.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def facts(fields, path=""):
    """Compare factual values and missing flags, independent of confidence/evidence edits."""
    output = {}
    if isinstance(fields, dict):
        if "value" in fields and "missing" in fields:
            output[path] = (fields["value"], fields["missing"])
        else:
            for key, value in fields.items():
                output.update(facts(value, f"{path}.{key}"))
    elif isinstance(fields, list):
        for index, value in enumerate(fields):
            output.update(facts(value, f"{path}[{index}]"))
    return output


def cost_metric(traces, key):
    selected = [t for t in traces if (t.attributes or {}).get(key)]
    resources = {(t.attributes or {})[key] for t in selected}
    known = [
        t
        for t in selected
        if t.cost is not None and (t.attributes or {}).get("usage_complete", True)
    ]
    subtotal = sum((Decimal(str(t.cost)) for t in known), Decimal(0))
    complete = bool(selected) and len(known) == len(selected)
    return {
        "value": str(subtotal / len(resources)) if complete else None,
        "currency": "USD",
        "known_subtotal": str(subtotal),
        "total": str(subtotal) if complete else None,
        "resources": len(resources),
        "calls": len(selected),
        "known_cost_calls": len(known),
    }


def calculate_metrics(
    *,
    documents,
    reviews,
    risks,
    changes,
    approvals,
    tasks,
    traces,
    covered_document_ids,
    start,
    end,
):
    def in_window(value):
        date = timestamp(value)
        return date is not None and (start is None or start <= date) and date < end

    docs = [d for d in documents if in_window(d.created_at)]
    by_id = {str(d.id): d for d in documents if timestamp(d.created_at) < end}
    events = sorted(
        [r for r in reviews if in_window(r.created_at)], key=lambda r: (r.created_at, str(r.id))
    )
    type_reviews, extraction_reviews = {}, {}
    overrides = 0
    review_events = []
    for event in events:
        if event.action in {"risk.accept", "risk.dismiss", "risk.override"}:
            review_events.append(event)
            overrides += event.action == "risk.override"
            continue
        if event.action != "pilot.review":
            continue
        doc_id = str(event.details.get("document_id", ""))
        doc = by_id.get(doc_id)
        if doc is None:
            continue
        after = event.details.get("after", {})
        changed = False
        measured = False
        if event.details.get("type_reviewed"):
            predicted = (doc.classification_result or {}).get("document_type")
            corrected = after.get("document_type")
            if predicted and corrected:
                measured = True
                type_reviews[doc_id] = predicted == corrected
                changed |= predicted != corrected
        if event.details.get("extraction_reviewed"):
            original = doc.structured_extraction or {}
            corrected = after.get("extraction", {})
            if original.get("document_type") and original.get("document_type") == corrected.get(
                "document_type"
            ):
                original_fields = facts(original.get("fields", {}))
                corrected_fields = facts(corrected.get("fields", {}))
                paths = original_fields.keys() | corrected_fields.keys()
                if paths:
                    measured = True
                    comparisons = [original_fields.get(p) == corrected_fields.get(p) for p in paths]
                    extraction_reviews[doc_id] = comparisons
                    changed |= not all(comparisons)
        if measured:
            review_events.append(event)
            overrides += changed
    comparisons = [value for values in extraction_reviews.values() for value in values]
    successful = [d for d in docs if d.status == "linked" and d.processing_status == "completed"]
    failed = [d for d in docs if d.status == "failed" or d.processing_status == "dead_letter"]
    latencies = []
    for doc in successful:
        timing = (doc.processing_data or {}).get("metrics") or {}
        started, finished = (
            timestamp(timing.get("started_at")),
            timestamp(timing.get("finished_at")),
        )
        if started and finished and started <= finished < end:
            latencies.append((finished - started).total_seconds())
    cycle_times = []
    for approval in approvals:
        if approval.status in {"approved", "rejected"} and in_window(approval.decided_at):
            seconds = (approval.decided_at - approval.created_at).total_seconds()
            if seconds >= 0:
                cycle_times.append(seconds)
    queue_times, open_ages = [], []
    review_times = {}
    for review in reviews:
        if review.action == "pilot.review" and review.created_at < end:
            review_times.setdefault(str(review.details.get("document_id")), []).append(
                review.created_at
            )
    for task in tasks:
        if not in_window(task.created_at):
            continue
        decisions = [
            date for date in review_times.get(str(task.document_id), []) if task.created_at <= date
        ]
        if decisions:
            queue_times.append((min(decisions) - task.created_at).total_seconds())
        elif task.status == "pending":
            open_ages.append((end - task.created_at).total_seconds())

    def duration(values):
        return {
            "value": sum(values) / len(values) if values else None,
            "samples": len(values),
            "unit": "seconds",
        }

    selected_traces = [
        t for t in traces if in_window(t.created_at) and t.operation != "investigation_run"
    ]
    return {
        "documents_uploaded": len(docs),
        "documents_processed_successfully": len(successful),
        "documents_failed": len(failed),
        "documents_quarantined": sum(d.status == "quarantined" for d in docs),
        "documents_awaiting_review": sum(d.status == "review_required" for d in docs),
        "processing_failure_rate": ratio(len(failed), len(successful) + len(failed)),
        "classification_accuracy": ratio(sum(type_reviews.values()), len(type_reviews)),
        "extraction_accuracy": ratio(sum(comparisons), len(comparisons)),
        "evidence_link_coverage": ratio(sum(d.id in covered_document_ids for d in docs), len(docs)),
        "risks_detected": sum(in_window(r.detected_at) for r in risks),
        "risks_accepted": len({r.entity_id for r in events if r.action == "risk.accept"}),
        "risks_dismissed": len({r.entity_id for r in events if r.action == "risk.dismiss"}),
        "human_override_rate": ratio(overrides, len(review_events)),
        "change_orders_created": sum(in_window(c.created_at) for c in changes),
        "approval_cycle_time": duration(cycle_times),
        "time_in_review_queue": duration(queue_times),
        "open_review_queue_age": duration(open_ages),
        "ai_cost_per_document": cost_metric(selected_traces, "document_id"),
        "ai_cost_per_investigation": cost_metric(selected_traces, "investigation_id"),
        "processing_latency_seconds": {
            **{f"p{p}": percentile(latencies, p / 100) for p in (50, 90, 95)},
            "samples": len(latencies),
            "eligible": len(successful),
        },
    }


class PilotMetricsService:
    """Read-only scoped analytics; never accepts a tenant identity from the client."""

    def __init__(self, session, user, *, clock=None):
        from app.domain.services.project_access import ProjectAccessService

        self.session, self.user = session, user
        self.access = ProjectAccessService(session, user)
        self.clock = clock or (lambda: datetime.now(UTC))

    async def report(self, project_id, start=None, end=None):
        from datetime import timedelta

        from fastapi import HTTPException
        from sqlalchemy import func, select

        from app.domain.models import (
            AITrace,
            Approval,
            AuditEvent,
            ChangeOrder,
            Document,
            DocumentChunk,
            DocumentReviewTask,
            EvidenceLink,
            Risk,
        )
        from app.domain.schemas.pilot_metrics import MetricsReport
        from app.policy.permissions import Action, has_permission

        if not all(
            has_permission(self.user.role, a) for a in (Action.AUDIT_READ, Action.FINANCIAL_READ)
        ):
            raise HTTPException(403, "Audit and financial read permissions required")
        await self.access.project(project_id)
        observed_at = self.clock()
        end = end or observed_at
        if timestamp(end) is None or (start is not None and timestamp(start) is None):
            raise HTTPException(422, "Timezone-aware start/end timestamps are required")
        if start is not None and (start >= end or end - start > timedelta(days=366)):
            raise HTTPException(422, "Range must be positive and at most 366 days")

        start, end = timestamp(start) if start is not None else None, timestamp(end)
        end = min(end, observed_at)
        if start is not None and start >= end:
            raise HTTPException(422, "Range begins after the observation time")

        async def rows(model, date_column, *columns, actions=None):
            query = select(*columns) if columns else select(model)
            query = query.where(
                model.tenant_id == self.user.tenant_id,
                model.project_id == project_id,
                date_column < end,
            )
            if actions is not None:
                query = query.where(model.action.in_(actions))
            result = await self.session.execute(query)
            return list(result) if columns else list(result.scalars())

        # Do not load checkpoint source text, approval comments, risk narratives or evidence quotations.
        documents = await rows(
            Document,
            Document.created_at,
            Document.id,
            Document.created_at,
            Document.status,
            Document.processing_status,
            Document.classification_result,
            Document.structured_extraction,
            func.jsonb_build_object("metrics", Document.processing_data["metrics"]).label(
                "processing_data"
            ),
        )
        reviews = await rows(
            AuditEvent,
            AuditEvent.created_at,
            AuditEvent.id,
            AuditEvent.created_at,
            AuditEvent.action,
            AuditEvent.entity_id,
            AuditEvent.details,
            actions={"pilot.review", "risk.accept", "risk.dismiss", "risk.override"},
        )
        links = await rows(
            EvidenceLink, EvidenceLink.created_at, EvidenceLink.source_id, EvidenceLink.source_type
        )
        covered = {link.source_id for link in links if link.source_type == "document"}
        chunk_ids = {link.source_id for link in links if link.source_type == "document_chunk"}
        if chunk_ids:
            chunks = await self.session.execute(
                select(DocumentChunk.id, DocumentChunk.document_id).where(
                    DocumentChunk.tenant_id == self.user.tenant_id,
                    DocumentChunk.project_id == project_id,
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.created_at < end,
                )
            )
            covered.update(row.document_id for row in chunks)
        metrics = calculate_metrics(
            documents=documents,
            reviews=reviews,
            risks=await rows(Risk, Risk.detected_at, Risk.id, Risk.detected_at),
            changes=await rows(
                ChangeOrder, ChangeOrder.created_at, ChangeOrder.id, ChangeOrder.created_at
            ),
            approvals=await rows(
                Approval,
                Approval.created_at,
                Approval.created_at,
                Approval.decided_at,
                Approval.status,
            ),
            tasks=await rows(
                DocumentReviewTask,
                DocumentReviewTask.created_at,
                DocumentReviewTask.document_id,
                DocumentReviewTask.created_at,
                DocumentReviewTask.status,
            ),
            traces=await rows(
                AITrace,
                AITrace.created_at,
                AITrace.created_at,
                AITrace.operation,
                AITrace.cost,
                AITrace.attributes,
            ),
            covered_document_ids=covered,
            start=start,
            end=end,
        )
        return MetricsReport(
            project_id=project_id,
            start=start,
            end=end,
            generated_at=observed_at,
            metrics=metrics,
            limitations=[
                "Cohort metrics use current record state; this is not an immutable historical snapshot.",
                "Accuracy uses human-reviewed factual values, not model confidence; unreviewed data is excluded.",
                "Timing and resource-attributed AI costs are prospective; historical missing measurements remain unknown.",
                "AI costs are USD estimates for persisted calls; persistence failures and legacy log-only calls cannot be reconstructed.",
                "Cost means cover resources with recorded calls; resources without calls have unmeasured cost.",
                "Queue time measures first review; reopened tasks are not separate episodes.",
                "The effective end is capped at observation time; the current week may be partial.",
            ],
        )


def weekly_csv(report):
    import csv
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["project_id", "start_utc", "end_utc", "metric", "statistic", "value"])
    for metric, value in report.metrics.model_dump().items():
        for statistic, item in value.items() if isinstance(value, dict) else [("count", value)]:
            writer.writerow(
                [
                    str(report.project_id),
                    report.start.isoformat() if report.start else "",
                    report.end.isoformat(),
                    metric,
                    statistic,
                    "" if item is None else item,
                ]
            )
    return output.getvalue()
