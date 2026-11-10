"""Rule-first change signals with source-grounded, classification-only model fallback."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.ai.gateway.types import GatewayError
from app.domain.models import DocumentReviewTask, EvidenceLink, ProjectEvent

EventType = Literal[
    "scope_change",
    "delay",
    "additional_work",
    "site_instruction",
    "material_issue",
    "design_conflict",
]
SUPPORTED = {"daily_report", "email", "correspondence", "rfi", "site_photo", "drawing"}
RULES = {
    "scope_change": (
        r"\b(?:scope (?:has been |was |is )?(?:changed|revised|increased|"
        r"reduced)|outside (?:the )?(?:original |contract )?scope|"
        r"not included in (?:the )?(?:original |contract )?scope)\b"
    ),
    "delay": (
        r"\b(?:delayed|delay(?:ed)? (?:by|of)|work (?:was |is )?(?:stopped|"
        r"suspended)|unable to (?:proceed|continue)|programme slippage)\b"
    ),
    "additional_work": (
        r"\b(?:additional (?:work|excavation|concrete|steel|labour)|"
        r"extra (?:work|excavation|concrete)|rework (?:is |"
        r"was )?required)\b"
    ),
    "site_instruction": (
        r"\b(?:(?:engineer|consultant|client|architect) (?:has |"
        r"had )?instructed|site instruction (?:issued|received)|"
        r"instructed (?:us |the contractor )?to)\b"
    ),
    "material_issue": (
        r"\b(?:material shortage|(?:materials?|delivery) (?:was |is |"
        r"were )?(?:rejected|damaged|late|unavailable)|(?:concrete|steel|"
        r"cement) (?:delivery )?(?:rejected|shortage|failed)|"
        r"failed (?:concrete|material) test)\b"
    ),
    "design_conflict": (
        r"\b(?:design conflict|drawing (?:conflict|discrepancy)|"
        r"drawings? (?:do not|does not) match|clash between|"
        r"conflicting (?:drawings|dimensions)|dimension mismatch)\b"
    ),
}
NEGATION = re.compile(r"\b(?:no|not|without|never|resolved|cancelled|avoided)\b", re.I)
HYPOTHETICAL = re.compile(
    r"\b(?:if|hypothetical|example|template|should|could|may|might|risk of)\b|\?", re.I
)
AMBIGUOUS = re.compile(
    (
        r"\b(?:clarification|unexpected|obstruction|awaiting|concern|"
        r"affect|discrepancy|possible|may|might|could)\b"
    ),
    re.I,
)


class AmbiguousEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event_type: EventType | None
    explanation: str = Field(min_length=1, max_length=1500)
    source_quote: str = Field(max_length=2000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


@dataclass(frozen=True)
class Signal:
    event_type: str
    quote: str
    page: int | None
    confidence: Decimal
    method: str
    explanation: str
    owner: str | None = None
    cost: Decimal | None = None
    currency: str | None = None
    days: int | None = None


class ExtractedEvent(BaseModel):
    """Closed event contract; impacts can only be copied by deterministic parsers."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    event_type: EventType
    quote: str = Field(min_length=1, max_length=2000)
    page: int | None = Field(ge=1)
    confidence: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    method: Literal["rules:v1", "llm:v1", "vision:v1"]
    explanation: str = Field(min_length=1, max_length=1500)
    owner: str | None = Field(default=None, max_length=100)
    cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    days: int | None = Field(default=None, ge=0, le=36500)


def suggestions(text):
    """Copy only explicitly labelled positive suggestions. Never estimate or sum."""
    costs = re.findall(
        (
            r"\b(?:estimated|additional|extra) cost\s*[:=]?\s*(USD|BDT|EUR|GBP|"
            r"AED)\s*((?:\d{1,16}|"
            r"[1-9]\d{0,2}(?:,\d{3}){1,4})(?:\.\d{1,2})?)(?!\d|[.,]\d)"
        ),
        text,
        re.I,
    )
    cost = currency = None
    if len(costs) == 1:
        currency, raw = costs[0]
        value = Decimal(raw.replace(",", ""))
        if 0 < value <= Decimal("9999999999999999.99"):
            cost, currency = value, currency.upper()
    delays = re.findall(
        r"\b(?:delay(?:ed)?(?: by| of)?|schedule impact)\s*[:=]?\s*(\d+)\s*(?:calendar )?days?\b",
        text,
        re.I,
    )
    days = int(delays[0]) if len(delays) == 1 and 0 < int(delays[0]) <= 36500 else None
    owner = re.search(r"\b(?:action owner|responsible party)\s*:\s*([^;\n.]{1,100})", text, re.I)
    return cost, currency, days, owner[1].strip() if owner else None


def classify_rules(text):
    matches = [kind for kind, pattern in RULES.items() if re.search(pattern, text, re.I)]
    # Negations before a signal suppress assertions, except the explicit scope and
    # drawing mismatch phrases whose negation carries the change meaning.
    meaningful_negative = bool(
        re.search(r"not included in|do not match|does not match", text, re.I)
    )
    if NEGATION.search(text) and not meaningful_negative:
        return [], False
    ambiguous = bool(matches and HYPOTHETICAL.search(text)) or bool(
        not matches and AMBIGUOUS.search(text)
    )
    return ([] if ambiguous else matches), ambiguous


async def detect(source, *, fallback=None, unresolved=None):
    signals = []
    model_calls = 0
    for block in source.blocks:
        for text in re.split(r"(?<=[.!?])\s+|\n+|;\s*|\s+but\s+", block.text):
            text = text.strip()
            if not text or len(text) > 2000:
                continue
            kinds, ambiguous = classify_rules(text)
            if ambiguous and (not fallback or model_calls >= 8) and unresolved is not None:
                unresolved.append(True)
            cost, currency, days, owner = suggestions(text)
            for kind in kinds:
                signals.append(
                    Signal(
                        kind,
                        text,
                        block.page_number,
                        Decimal("0.95"),
                        "rules:v1",
                        "Explicit construction change signal in source evidence.",
                        owner,
                        cost,
                        currency,
                        days,
                    )
                )
            if ambiguous and fallback and model_calls < 8:
                model_calls += 1
                try:
                    result = AmbiguousEvent.model_validate(await run_in_threadpool(fallback, text))
                    if (
                        result.event_type
                        and result.confidence >= 0.7
                        and result.source_quote.strip()
                        and result.source_quote in text
                    ):
                        signals.append(
                            Signal(
                                result.event_type,
                                result.source_quote,
                                block.page_number,
                                Decimal(str(min(result.confidence, 0.85))),
                                "llm:v1",
                                result.explanation,
                                owner,
                                cost,
                                currency,
                                days,
                            )
                        )
                    elif result.event_type is not None and unresolved is not None:
                        unresolved.append(True)
                except (GatewayError, ValueError, RuntimeError):
                    # An optional classifier cannot erase deterministic results or
                    # turn unsupported model assertions into evidence.
                    if unresolved is not None:
                        unresolved.append(True)
                    continue
    return signals


async def persist(document, signals, session):
    # Validate the entire batch before any database side effects.
    signals = [ExtractedEvent.model_validate(vars(signal)) for signal in signals]
    ids = []
    for signal in signals:
        source_key = signal.quote if signal.method != "vision:v1" else "image"
        key = hashlib.sha256(
            (
                f"v1:{document.tenant_id}:{document.project_id}:{document.id}:"
                f"{signal.event_type}:{signal.page}:{source_key}"
            ).encode()
        ).hexdigest()
        event = await session.scalar(
            select(ProjectEvent).where(
                ProjectEvent.tenant_id == document.tenant_id,
                ProjectEvent.project_id == document.project_id,
                ProjectEvent.detection_key == key,
            )
        )
        if event is None:
            now = datetime.now(UTC)
            event = ProjectEvent(
                id=uuid4(),
                tenant_id=document.tenant_id,
                project_id=document.project_id,
                document_id=document.id,
                detection_key=key,
                title="Potential " + signal.event_type.replace("_", " "),
                description=signal.explanation + "\nSource: " + signal.quote,
                event_type=signal.event_type,
                status="potential_change",
                occurred_at=document.created_at,
                detected_date=now.date(),
                confidence=signal.confidence,
                suggested_owner=signal.owner,
                suggested_cost_impact=signal.cost,
                suggested_currency=signal.currency,
                suggested_schedule_impact=signal.days,
                attributes={
                    "detector": signal.method,
                    "human_review_required": True,
                    "impact_basis": "explicit_source_suggestion",
                },
            )
            session.add(event)
            await session.flush()
            session.add(
                EvidenceLink(
                    tenant_id=document.tenant_id,
                    project_id=document.project_id,
                    subject_type="project_event",
                    subject_id=event.id,
                    source_type="document",
                    source_id=document.id,
                    source_page=signal.page,
                    source_text_snippet=signal.quote if signal.method != "vision:v1" else None,
                    confidence=signal.confidence,
                    rationale="Potential change requires human review",
                )
            )
        if str(event.id) not in ids:
            ids.append(str(event.id))
    return ids


async def process(document, source, session, services, *, image=None):
    if document.document_type not in SUPPORTED:
        return []
    fallback = None
    settings = getattr(services, "settings", None)
    if settings is not None and settings.llm_provider == "openai" and settings.llm_api_key:
        fallback = services.potential_change_classification
    unresolved = []
    signals = await detect(source, fallback=fallback, unresolved=unresolved)
    if document.document_type == "site_photo" and not source.text.strip() and image and fallback:
        try:
            result = AmbiguousEvent.model_validate(
                await run_in_threadpool(
                    fallback,
                    "Classify visible construction change evidence; use null when uncertain.",
                    image=image,
                    mime_type=document.mime_type,
                )
            )
            if result.event_type and result.confidence >= 0.7:
                signals.append(
                    Signal(
                        result.event_type,
                        result.explanation,
                        None,
                        Decimal("0.65"),
                        "vision:v1",
                        result.explanation,
                    )
                )
        except (GatewayError, ValueError, RuntimeError):
            pass
    ids = await persist(document, signals, session)
    if unresolved and document.document_type != "site_photo":
        review = await session.scalar(
            select(DocumentReviewTask).where(
                DocumentReviewTask.tenant_id == document.tenant_id,
                DocumentReviewTask.project_id == document.project_id,
                DocumentReviewTask.document_id == document.id,
            )
        )
        if review is None:
            session.add(
                DocumentReviewTask(
                    tenant_id=document.tenant_id,
                    project_id=document.project_id,
                    document_id=document.id,
                    reason="potential_change_classification_required",
                )
            )
            await session.flush()
    return ids
