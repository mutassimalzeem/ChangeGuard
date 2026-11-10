"""Versioned deterministic rules. No model calls, inferred totals, or currency conversion."""

import hashlib
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.document_processing.structured.schemas import schema_for
from app.domain.models import (
    Approval,
    AuditEvent,
    ChangeOrder,
    Document,
    DocumentEntityLink,
    EventEntityLink,
    EvidenceLink,
    ProjectEvent,
    Risk,
)


@dataclass(frozen=True)
class Source:
    document_id: UUID
    page: int | None = None
    snippet: str | None = None


@dataclass
class Finding:
    risk_type: str
    key: str
    description: str
    recommended_action: str
    sources: list[Source] = field(default_factory=list)
    financial_exposure: Decimal | None = None
    currency: str | None = None
    schedule_impact_days: int | None = None
    responsible_party: str | None = None
    severity: str = "medium"
    confidence: Decimal = Decimal("1")
    insufficient: bool = False

    @property
    def status(self):
        return "open" if self.sources and not self.insufficient else "insufficient_evidence"


def money(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or abs(amount) > Decimal("9999999999999999.99"):
        return None
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalized(value):
    return " ".join((value or "").casefold().split())


def entity_rules(change, approvals, peers, sources, as_of):
    """Entity facts come from project records; sources must be linked documents."""
    findings = []
    amount = money(change.amount) if change.amount is not None and change.amount >= 0 else None
    for approval in approvals:
        if (
            approval.status == "pending"
            and approval.decided_at is None
            and approval.due_at is not None
            and approval.due_at < as_of
            and change.status not in {"approved", "executed", "rejected", "cancelled"}
        ):
            findings.append(
                Finding(
                    "overdue_approval",
                    str(approval.id),
                    f"Pending approval was due {approval.due_at.isoformat()}.",
                    "Obtain an approval decision from the assigned reviewer.",
                    sources,
                    amount,
                    change.currency if amount is not None else None,
                    responsible_party=str(approval.assigned_to_id)
                    if approval.assigned_to_id
                    else None,
                    severity="high",
                )
            )
    if (
        change.status in {"submitted", "approved", "executed"}
        and (change.time_impact_days or 0) > 0
    ):
        findings.append(
            Finding(
                "schedule_impact_signal",
                str(change.id),
                "The linked change order records a positive schedule impact. "
                "Critical-path effects require programme review.",
                "Validate the recorded days against the approved programme.",
                sources,
                schedule_impact_days=change.time_impact_days,
                responsible_party=str(change.created_by_id) if change.created_by_id else None,
            )
        )
    if change.status not in {"submitted", "approved", "executed"}:
        return findings
    for peer, peer_sources in peers:
        # Matching text alone is insufficient: require the same RFI, contract and money.
        if (
            peer.id != change.id
            and change.rfi_id
            and change.contract_id
            and peer.rfi_id == change.rfi_id
            and peer.contract_id == change.contract_id
            and peer.status in {"submitted", "approved", "executed"}
            and normalized(change.description)
            and normalized(change.description) == normalized(peer.description)
            and amount is not None
            and amount > 0
            and peer.amount == change.amount
            and peer.currency == change.currency
        ):
            findings.append(
                Finding(
                    "duplicate_change_order_claim",
                    ":".join(sorted([str(change.id), str(peer.id)])),
                    "Two distinct change orders claim the same amount for the same RFI, "
                    "contract and work description.",
                    "Reconcile the two claims before certifying payment.",
                    sources + peer_sources if sources and peer_sources else [],
                    amount,
                    change.currency,
                    severity="high",
                )
            )
    return findings


def document_rules(document, comparisons):
    """Use only validated, grounded extraction envelopes; never read raw LLM output."""
    result = document.structured_extraction
    if not result or result.get("schema_version") != 1:
        return [
            Finding(
                "missing_required_evidence",
                str(document.id),
                "Validated field-level evidence is unavailable.",
                "Review and extract the required source facts.",
            )
        ]
    schema = schema_for(result["document_type"])
    if schema is None:
        return []
    facts = schema.model_validate(result["fields"])
    missing = [
        name
        for name in schema.required_facts
        if not getattr(facts, name) or getattr(getattr(facts, name), "missing", False)
    ]
    findings = []
    if missing:
        findings.append(
            Finding(
                "missing_required_evidence",
                str(document.id),
                "Required extracted facts are missing: " + ", ".join(missing),
                "Supply the missing facts and their source evidence.",
                [Source(document.id)],
            )
        )
    # Compare item rates, never unrelated document totals. Explicit item code, unit,
    # currency and description must match. Historical records must predate this file.
    for index, item in enumerate(getattr(facts, "items", [])):
        if any(
            getattr(item, name).missing for name in ("code", "description", "quantity", "unit_rate")
        ):
            continue
        candidates = []
        for other in comparisons:
            other_result = other.structured_extraction
            if not other_result or other_result.get("schema_version") != 1:
                continue
            if other_result["document_type"] not in {"boq", "quotation"}:
                continue
            if other.created_at >= document.created_at:
                continue
            other_facts = schema_for(other_result["document_type"]).model_validate(
                other_result["fields"]
            )
            for baseline in other_facts.items:
                if any(
                    getattr(baseline, name).missing
                    for name in ("code", "description", "quantity", "unit_rate")
                ):
                    continue
                if (
                    baseline.code.value == item.code.value
                    and normalized(baseline.description.value) == normalized(item.description.value)
                    and baseline.quantity.value.unit == item.quantity.value.unit
                    and baseline.unit_rate.value.currency == item.unit_rate.value.currency
                    and baseline.unit_rate.value.amount > 0
                ):
                    candidates.append((baseline.unit_rate.value.amount, other, baseline))
        if candidates and item.quantity.value.amount > 0:
            # Highest comparable rate is conservative and avoids median ambiguity.
            rate, other, baseline = max(candidates, key=lambda entry: entry[0])
            current = item.unit_rate.value.amount
            if current > rate * Decimal("1.20"):
                findings.append(
                    Finding(
                        "cost_outlier",
                        f"{document.id}:{index}",
                        "Item rate exceeds the highest comparable BOQ/historical rate "
                        "by more than 20%.",
                        "Reconcile the item rate with the comparable source record.",
                        [
                            Source(
                                document.id,
                                item.unit_rate.source_page,
                                item.unit_rate.source_text_snippet,
                            ),
                            Source(
                                other.id,
                                baseline.unit_rate.source_page,
                                baseline.unit_rate.source_text_snippet,
                            ),
                        ],
                        money((current - rate) * item.quantity.value.amount),
                        item.unit_rate.value.currency,
                        confidence=Decimal(
                            str(min(item.unit_rate.confidence, baseline.unit_rate.confidence))
                        ),
                    )
                )
    identities = {
        "change_order": "co_number",
        "rfi": "rfi_number",
        "contract": "reference",
        "drawing": "drawing_number",
        "quotation": "reference",
    }
    identity = identities.get(result["document_type"])
    if not identity or getattr(facts, identity).missing:
        return findings
    for other in comparisons:
        previous = other.structured_extraction
        if (
            not previous
            or previous.get("schema_version") != 1
            or previous["document_type"] != result["document_type"]
            or document.document_version != other.document_version
        ):
            continue
        other_facts = schema.model_validate(previous["fields"])
        if (
            getattr(other_facts, identity).missing
            or getattr(facts, identity).value != getattr(other_facts, identity).value
        ):
            continue
        # Different issues/revisions are normal lifecycle changes, not contradictions.
        guards = ("revision", "issue_date", "status")
        if any(
            getattr(facts, name, None) != getattr(other_facts, name, None)
            and (
                getattr(getattr(facts, name, None), "value", None)
                != getattr(getattr(other_facts, name, None), "value", None)
            )
            for name in guards
        ):
            continue
        for name in ("amount", "contract_value", "stated_total", "due_date"):
            left, right = getattr(facts, name, None), getattr(other_facts, name, None)
            if (
                left is None
                or right is None
                or left.missing
                or right.missing
                or left.value == right.value
            ):
                continue
            if hasattr(left.value, "currency") and left.value.currency != right.value.currency:
                continue
            exposure = (
                money(abs(left.value.amount - right.value.amount))
                if hasattr(left.value, "amount")
                else None
            )
            findings.append(
                Finding(
                    "conflicting_information",
                    f"{document.id}:{other.id}:{name}",
                    f"Same entity and issue have conflicting {name} values.",
                    "Resolve the conflicting values with the document issuer.",
                    [
                        Source(document.id, left.source_page, left.source_text_snippet),
                        Source(other.id, right.source_page, right.source_text_snippet),
                    ],
                    exposure,
                    left.value.currency if exposure is not None else None,
                    confidence=Decimal(str(min(left.confidence, right.confidence))),
                )
            )
    return findings


def daily_report_delay_rules(document, events, evidence, links, changes, event_links=()):
    """A recorded delay without an explicit same-project RFI/CO relationship.

    Absence means absence in ChangeGuard's linked records, never a claim about
    all project correspondence. Financial and programme effects remain unknown.
    """
    if document.document_type != "daily_report":
        return []
    if any(
        link.document_id == document.id and (link.rfi_id or link.change_order_id) for link in links
    ):
        return []
    findings = []
    for event in events:
        if event.document_id != document.id or event.event_type != "delay":
            continue
        if any(link.event_id == event.id for link in event_links):
            continue
        if any(change.source_event_id == event.id for change in changes):
            continue
        sources = [
            Source(document.id, link.source_page, link.source_text_snippet)
            for link in evidence
            if link.subject_id == event.id
            and link.source_type == "document"
            and link.source_id == document.id
            and link.source_page
            and link.source_text_snippet
            and link.source_text_snippet.strip()
        ]
        sufficient = (
            bool(sources) and event.confidence is not None and event.confidence >= Decimal("0.7")
        )
        findings.append(
            Finding(
                "daily_report_delay_without_link",
                str(event.id),
                "Daily report indicates delay, but no linked RFI or change order exists in ChangeGuard."
                if sufficient
                else "Daily report delay signal needs source evidence review.",
                "Review the report and link the relevant RFI or change order.",
                sources if sufficient else [Source(document.id)],
                confidence=event.confidence or Decimal("0"),
                insufficient=not sufficient,
            )
        )
    return findings


async def run_risk_checks(document, session):
    # Serialize shared entity findings when different documents finish together.
    lock = int.from_bytes(
        hashlib.sha256(document.project_id.bytes).digest()[:8], "big", signed=True
    )
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})

    def scoped(model):
        return select(model).where(
            model.tenant_id == document.tenant_id, model.project_id == document.project_id
        )

    documents = list(
        await session.scalars(
            scoped(Document).where(
                Document.deleted_at.is_(None), Document.status.notin_(["quarantined", "failed"])
            )
        )
    )
    # Only fully validated predecessors may serve as comparison evidence.
    comparisons = [
        d
        for d in documents
        if d.id != document.id and d.processing_status in {"completed", "review_required"}
    ]
    findings = document_rules(document, comparisons)
    links = list(await session.scalars(scoped(DocumentEntityLink)))
    visible_ids = {d.id for d in documents}

    def sources(change_id):
        return [
            Source(link.document_id)
            for link in links
            if link.change_order_id == change_id and link.document_id in visible_ids
        ]

    changes = list(await session.scalars(scoped(ChangeOrder)))
    events = list(
        await session.scalars(
            scoped(ProjectEvent)
            .where(ProjectEvent.document_id == document.id)
            .order_by(ProjectEvent.id)
            .with_for_update()
        )
    )
    event_evidence = list(
        await session.scalars(
            scoped(EvidenceLink).where(EvidenceLink.subject_type == "project_event")
        )
    )
    event_links = list(
        await session.scalars(
            scoped(EventEntityLink).where(
                EventEntityLink.event_id.in_([event.id for event in events])
            )
        )
    )
    findings.extend(
        daily_report_delay_rules(document, events, event_evidence, links, changes, event_links)
    )
    approvals = list(await session.scalars(scoped(Approval)))
    for change in changes:
        if not any(
            link.document_id == document.id and link.change_order_id == change.id for link in links
        ):
            continue
        findings.extend(
            entity_rules(
                change,
                [a for a in approvals if a.change_order_id == change.id],
                [(p, sources(p.id)) for p in changes],
                sources(change.id),
                document.created_at,
            )
        )
    ids = []
    for finding in findings:
        key = f"v1:{document.tenant_id}:{document.project_id}:{finding.risk_type}:{finding.key}"
        # Hash bounded keys; keep human-readable rule identity in the type and description.
        key = hashlib.sha256(key.encode()).hexdigest()
        risk = await session.scalar(scoped(Risk).where(Risk.rule_key == key))
        if risk is None:
            risk = Risk(
                id=uuid4(),
                tenant_id=document.tenant_id,
                project_id=document.project_id,
                document_id=document.id,
                project_event_id=UUID(finding.key)
                if finding.risk_type == "daily_report_delay_without_link"
                else None,
                rule_key=key,
                risk_type=finding.risk_type,
                category="deterministic_v1",
                title=finding.risk_type.replace("_", " ").capitalize(),
                description=finding.description,
                severity=finding.severity,
                status=finding.status,
                exposure_amount=finding.financial_exposure,
                currency=finding.currency or "USD",
                schedule_impact_days=finding.schedule_impact_days,
                responsible_party=finding.responsible_party,
                recommended_action=finding.recommended_action,
                confidence=finding.confidence,
            )
            session.add(risk)
            await session.flush()
            # A review-only finding still points to the triggering original;
            # that link does not upgrade insufficient evidence to a supported risk.
            for source in dict.fromkeys(finding.sources or [Source(document.id)]):
                session.add(
                    EvidenceLink(
                        tenant_id=document.tenant_id,
                        project_id=document.project_id,
                        subject_type="risk",
                        subject_id=risk.id,
                        source_type="document",
                        source_id=source.document_id,
                        source_page=source.page,
                        source_text_snippet=source.snippet,
                        confidence=finding.confidence,
                        rationale=finding.description,
                    )
                )
            session.add(
                AuditEvent(
                    tenant_id=document.tenant_id,
                    project_id=document.project_id,
                    action="risk.create",
                    entity_type="risk",
                    entity_id=risk.id,
                    request_id=(document.processing_data or {}).get("request_id"),
                    details={
                        "rule": finding.risk_type,
                        "status": finding.status,
                        "document_id": str(document.id),
                    },
                )
            )
        ids.append(str(risk.id))
    return ids
