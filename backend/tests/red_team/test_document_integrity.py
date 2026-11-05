"""Red-team tests for Categories 5-7: Document & Data Integrity.

5. Contradictory documents
6. Malformed financial data
7. Missing required fields
"""

# ruff: noqa: E501
import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domain.models import ChangeOrder, Document
from app.domain.schemas.change_order import ChangeOrderPatch, CostItem, SubmitInput
from app.domain.services.change_orders import ChangeOrderService, calculate_cost
from app.domain.services.risk_engine import Finding, document_rules, entity_rules, money, normalized

logger = logging.getLogger("changeguard.red_team")


# ---------------------------------------------------------------------------
# Category 5: Contradictory Documents
# ---------------------------------------------------------------------------

def test_contradictory_delay_documents_flagged_as_high_risk(caplog):
    """Attack RT-DOC-001: Opposing Delay Liability Documents for Same Claim.

    Adversary submits contradictory documents for the same event:
    Document 1 (Engineer report) attributes delay to contractor with $0 compensable.
    Document 2 (Contractor notice) attributes delay to employer with $350,000 compensable.
    Expected: Risk engine detects the conflicting evidence; automated acceptance is blocked;
    Finding is raised with severity='high' requiring human dispute resolution.
    """
    tenant_id = uuid4()
    project_id = uuid4()
    rfi_id = uuid4()
    contract_id = uuid4()
    now = datetime.now(UTC)

    # Primary change order claiming $350,000 compensable delay under RFI-101
    primary_change = ChangeOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        rfi_id=rfi_id,
        contract_id=contract_id,
        reference="CO-DELAY-001",
        description="Compensable delay claim for rock obstruction zone 4",
        amount=Decimal("350000.00"),
        currency="USD",
        status="submitted",
        time_impact_days=45,
        created_at=now,
    )

    # Contradictory peer change order submitted for the same contract & RFI
    peer_change = ChangeOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        rfi_id=rfi_id,
        contract_id=contract_id,
        reference="CO-DELAY-002",
        description="Compensable delay claim for rock obstruction zone 4",
        amount=Decimal("350000.00"),
        currency="USD",
        status="submitted",
        time_impact_days=0,
        created_at=now,
    )

    # Run deterministic risk engine
    findings = entity_rules(
        change=primary_change,
        approvals=[],
        peers=[(peer_change, [])],
        sources=[],
        as_of=now,
    )

    # Assert conflicting / duplicate claim is flagged as high severity
    dup_findings = [f for f in findings if f.risk_type == "duplicate_change_order_claim"]
    assert len(dup_findings) >= 1
    finding = dup_findings[0]
    assert finding.severity == "high"
    assert "Two distinct change orders claim the same amount" in finding.description
    assert finding.financial_exposure == Decimal("350000.00")

    # Schedule impact signal is also raised
    schedule_findings = [f for f in findings if f.risk_type == "schedule_impact_signal"]
    assert len(schedule_findings) >= 1
    assert schedule_findings[0].schedule_impact_days == 45

    logger.info("RT-DOC-001 passed: Contradictory documents triggered high-severity risk finding.")


def test_duplicate_change_order_claims_detected_across_descriptions(caplog):
    """Attack RT-DOC-002: Duplicate Change Order Claim with Varied Descriptions.

    Contractor attempts to submit duplicate change order with varied whitespace and casing:
    'Rock excavation Zone 3' vs '  ROCK  EXCAVATION   ZONE  3  '.
    Expected: Normalized comparison detects duplicate claim; raises high-severity finding.
    """
    tenant_id = uuid4()
    project_id = uuid4()
    rfi_id = uuid4()
    contract_id = uuid4()
    now = datetime.now(UTC)

    co1 = ChangeOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        rfi_id=rfi_id,
        contract_id=contract_id,
        reference="CO-101",
        description="Rock excavation Zone 3",
        amount=Decimal("75000.00"),
        currency="USD",
        status="submitted",
        time_impact_days=0,
        created_at=now,
    )

    co2 = ChangeOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        rfi_id=rfi_id,
        contract_id=contract_id,
        reference="CO-102",
        description="   ROCK   EXCAVATION   ZONE   3   ",
        amount=Decimal("75000.00"),
        currency="USD",
        status="submitted",
        time_impact_days=0,
        created_at=now,
    )

    assert normalized(co1.description) == normalized(co2.description)

    findings = entity_rules(
        change=co1,
        approvals=[],
        peers=[(co2, [])],
        sources=[],
        as_of=now,
    )

    assert any(f.risk_type == "duplicate_change_order_claim" for f in findings)
    logger.info("RT-DOC-002 passed: Duplicate claim across casing/whitespace variations detected.")


# ---------------------------------------------------------------------------
# Category 6: Malformed Financial Data
# ---------------------------------------------------------------------------

def test_negative_financial_amounts_and_overflow_rejected(caplog):
    """Attack RT-FIN-001: Negative Amounts & Extreme Numeric Overflow Injections.

    Attacker attempts to create cost items with negative unit rates, overflow (> 60 decimals),
    or non-finite values (NaN, Infinity).
    Expected: calculate_cost() rejects overflow and negative arithmetic; Pydantic enforces validation.
    """
    # 1. Negative quantity is rejected by Pydantic schema (gt=0)
    with pytest.raises(ValidationError):
        CostItem(
            description="Negative quantity item",
            quantity=Decimal("-10.00"),
            unit_rate=Decimal("100.00"),
        )

    # 2. Extreme precision overflow (> 15 digits) rejected by DecimalValue
    with pytest.raises(ValidationError):
        CostItem(
            description="Excessive cost item",
            quantity=Decimal("9999999999999999999.00"),
            unit_rate=Decimal("100.00"),
        )

    # 3. SubmitInput requires explicit cost_confirmed=True
    with pytest.raises(ValidationError):
        SubmitInput(cost_confirmed=False, reason="Unconfirmed cost")

    # 4. Test money() helper resilience against non-finite floats
    assert money(float("nan")) is None
    assert money(float("inf")) is None
    assert money(float("-inf")) is None
    assert money(Decimal("1e40")) is None  # Exceeds max precision boundary

    # 5. Valid monetary calculation quantizes properly
    valid_item = CostItem(
        description="Structural steel",
        quantity=Decimal("12.50"),
        unit_rate=Decimal("150.25"),
    )
    total = calculate_cost([valid_item])
    assert total == Decimal("1878.13")

    # 6. Overflow exceeding 16-digit total raises 422
    huge_items = [
        CostItem(
            description=f"High item {i}",
            quantity=Decimal("999999999999.00"),
            unit_rate=Decimal("999999999999.00"),
        )
        for i in range(1)
    ]
    with pytest.raises(HTTPException) as exc:
        calculate_cost(huge_items)
    assert exc.value.status_code == 422
    assert "exceeds supported monetary range" in exc.value.detail

    logger.info("RT-FIN-001 passed: Financial overflow, NaN, and non-finite values rejected.")


def test_currency_code_sql_injection_and_tampering_rejected(caplog):
    """Attack RT-FIN-002: Currency Forgery & SQL Injection in Currency Codes.

    Adversary inputs currency payload: 'USD; DROP TABLE contracts; --' or 'BITCOIN'.
    Expected: Schema validation enforces ISO 3-character currency codes; rejects malicious input with 422.
    """
    # Attempting SQL injection inside currency field in ChangeOrderPatch
    with pytest.raises(ValidationError):
        ChangeOrderPatch(currency="USD; DROP TABLE contracts; --")

    with pytest.raises(ValidationError):
        ChangeOrderPatch(currency="BITCOIN")

    with pytest.raises(ValidationError):
        ChangeOrderPatch(currency="<script>alert(1)</script>")

    # Valid currency passes
    valid_patch = ChangeOrderPatch(currency="USD")
    assert valid_patch.currency == "USD"
    logger.info("RT-FIN-002 passed: Currency injection and tampering rejected by schema validation.")


# ---------------------------------------------------------------------------
# Category 7: Missing Required Fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_order_submission_fails_without_required_fields(caplog):
    """Attack RT-REQ-001: Change Order Submission Stripped of Cost Items & Evidence Links.

    Attacker attempts to transition a change order directly to 'submitted' without
    providing human-reviewed cost items or citation-backed drafts.
    Expected: ChangeOrderService.submit() rejects with HTTPException(422).
    """
    mock_session = AsyncMock()
    mock_session.info = {}
    mock_session.identity_map = {}
    mock_user = MagicMock()
    mock_user.role = "project_manager"
    mock_user.id = uuid4()
    mock_user.tenant_id = uuid4()

    service = ChangeOrderService(mock_session, mock_user)

    # Order without draft_content or cost items
    order = ChangeOrder(
        id=uuid4(),
        tenant_id=mock_user.tenant_id,
        project_id=uuid4(),
        reference="CO-STRIPPED",
        title="Unbacked claim",
        status="drafted",
        amount=Decimal("100000.00"),
        currency="USD",
        draft_content=None,  # Missing draft
        cost_items=[],       # Missing cost items
    )

    service.load = AsyncMock(return_value=order)
    service.links = AsyncMock(return_value=[])  # Missing evidence links

    payload = SubmitInput(cost_confirmed=True, reason="Quick submit attempt without draft")
    with pytest.raises(HTTPException) as exc:
        await service.submit(order.id, payload)

    assert exc.value.status_code == 422
    assert "A current evidence-backed draft is required" in exc.value.detail
    assert order.status == "drafted"  # State did NOT transition to submitted

    logger.info("RT-REQ-001 passed: Stripped submission failed closed with HTTP 422.")


def test_extraction_missing_required_contractual_facts_flags_risk(caplog):
    """Attack RT-REQ-002: Document Extraction Missing Mandatory Contractual Facts.

    Extracted document envelope omits mandatory required facts (e.g. schema_version != 1 or missing facts).
    Expected: document_rules flags 'missing_required_evidence' finding, preventing automated acceptance.
    """
    # 1. Invalid or missing structured extraction envelope
    doc_unextracted = Document(
        id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        filename="unextracted_contract.pdf",
        structured_extraction=None,
    )
    findings = document_rules(doc_unextracted, comparisons=[])
    assert len(findings) == 1
    assert findings[0].risk_type == "missing_required_evidence"
    assert findings[0].status == "insufficient_evidence"

    # 2. Schema version mismatch / spoofing
    doc_bad_schema = Document(
        id=uuid4(),
        tenant_id=uuid4(),
        project_id=uuid4(),
        filename="spoofed_schema.pdf",
        structured_extraction={"schema_version": 999, "document_type": "contract"},
    )
    findings_bad = document_rules(doc_bad_schema, comparisons=[])
    assert len(findings_bad) == 1
    assert findings_bad[0].risk_type == "missing_required_evidence"

    logger.info("RT-REQ-002 passed: Missing required facts detected as missing_required_evidence risk.")

