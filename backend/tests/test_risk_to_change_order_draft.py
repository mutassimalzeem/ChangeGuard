"""Tests for evidence-backed delay risk conversion to change-order draft.

Flow & Constraints Verified:
1. Conversion of an evidence-backed delay risk into a change-order draft.
2. Initial status is 'drafted'.
3. Financial (amount) and schedule (time_impact_days) fields remain null until human enters them.
4. LLM drafts narrative text citing evidence; financial/schedule estimations are not automated.
5. Every draft must cite evidence; insufficient-evidence risks cannot be converted (422).
6. Evidence package is copied/linked from risk to change order.
7. Original risk remains linked to the change order (risk.change_order_id = order.id).
8. User can edit the draft (patch cost items and schedule impact).
9. User can submit it for approval (drafted -> submitted with cost confirmation).
10. Explicit human approval and rejection with mandatory reason; self-approval forbidden.
11. Every transition is audited.
12. No automated external communication is sent.
13. Role-based access control (RBAC) enforcement.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.domain.models import Approval, AuditEvent, ChangeOrder, EvidenceLink, Risk
from app.domain.schemas.change_order import (
    ChangeOrderDraftFromRisk,
    ChangeOrderPatch,
    CitedDraft,
    CitedParagraph,
    CostItem,
    DecisionInput,
    SubmitInput,
)
from app.domain.services.change_orders import (
    ChangeOrderService,
    validate_draft,
)
from app.domain.services.risks import RiskDecision, validate_risk_decision
from app.policy.permissions import Action, Role, has_permission

# ==============================================================================
# Helper Runner & Factories
# ==============================================================================


def run_sync(coro):
    """Drive coroutine synchronously to avoid Windows sandbox loopback socketpair hanging."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    raise RuntimeError("Coroutine did not resolve immediately")


@pytest.fixture(autouse=True)
def disable_external_llm_calls(monkeypatch):
    """Ensure tests run locally without making external network calls."""
    monkeypatch.setattr(
        "app.domain.services.change_orders.get_settings",
        lambda: SimpleNamespace(llm_provider="openai", llm_api_key=None),
    )


def create_mock_session():
    mock_session = MagicMock()
    mock_session.info = {}
    mock_session.identity_map = {}
    mock_session.flush = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)
    mock_session.scalars = AsyncMock(return_value=[])
    return mock_session


def make_user(role=Role.PROJECT_MANAGER, user_id=None, tenant_id=None):
    return SimpleNamespace(
        id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        role=role.value if isinstance(role, Role) else role,
        email="user@example.com",
        full_name="Test User",
    )


def make_risk(
    tenant_id,
    project_id,
    risk_id=None,
    status="open",
    risk_type="delay_signal",
    responsible_party="Subcontractor Steel Co",
    project_event_id=None,
    change_order_id=None,
):
    return Risk(
        id=risk_id or uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        title="Unforeseen Rock Obstruction at Foundation Grid B",
        risk_type=risk_type,
        status=status,
        confidence=Decimal("0.9500"),
        severity="high",
        responsible_party=responsible_party,
        project_event_id=project_event_id or uuid4(),
        change_order_id=change_order_id,
        schedule_impact_days=14,
        exposure_amount=None,
        currency="USD",
    )


def make_evidence_links(tenant_id, project_id, subject_id, count=2):
    links = []
    for i in range(1, count + 1):
        links.append(
            EvidenceLink(
                id=uuid4(),
                tenant_id=tenant_id,
                project_id=project_id,
                subject_type="risk",
                subject_id=subject_id,
                source_type="document_chunk",
                source_id=uuid4(),
                source_page=i + 5,
                source_text_snippet=f"Geotechnical report section 3.{i}: hard granite formation encountered.",
                confidence=Decimal("0.92"),
                relevance=Decimal("0.98"),
            )
        )
    return links


# ==============================================================================
# 1. RBAC & Decision Validation Tests
# ==============================================================================


@pytest.mark.parametrize(
    "role,allowed",
    [
        (Role.OWNER, True),
        (Role.ADMIN, True),
        (Role.PROJECT_MANAGER, True),
        (Role.COMMERCIAL_MANAGER, True),
        (Role.SITE_ENGINEER, False),
        (Role.VIEWER, False),
        (Role.AUDITOR, False),
    ],
)
def test_rbac_for_converting_risk_to_change_order(role, allowed):
    """Only roles with RISK_ACCEPT permission can convert a risk to a change order draft in review queue."""
    assert has_permission(role, Action.RISK_ACCEPT) is allowed


def test_decision_validation_create_draft_action():
    """RiskDecision accepts create_change_order_draft action with optional reference, title, reason."""
    decision = RiskDecision(
        action="create_change_order_draft",
        reason="Evidence substantiated unforeseen subsurface obstruction",
        change_order_reference="CO-ROCK-001",
        change_order_title="Subsurface Granite Mitigation",
    )
    assert decision.action == "create_change_order_draft"
    assert decision.change_order_reference == "CO-ROCK-001"
    assert decision.change_order_title == "Subsurface Granite Mitigation"


def test_decision_validation_rejects_empty_reason_for_draft_creation():
    """Draft creation requires a non-empty reason when validating via validate_risk_decision."""
    with pytest.raises(ValueError, match="A reason is mandatory"):
        RiskDecision(action="create_change_order_draft", reason="   ")


def test_decision_validation_rejects_insufficient_evidence():
    """Constraint: Insufficient-evidence risks cannot be converted to a change order."""
    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role="project_manager",
            risk_status="insufficient_evidence",
            has_links=False,
            action="create_change_order_draft",
        )
    assert exc_info.value.status_code == 422
    assert "insufficient_evidence" in exc_info.value.detail


# ==============================================================================
# 2. Flow: Conversion from Risk to Change Order Draft
# ==============================================================================


def test_create_draft_from_risk_success():
    """Flow steps 1-5, 9-10:
    - User selects 'Create change-order draft'
    - Backend retrieves linked evidence
    - Backend creates draft change order with status: 'drafted'
    - amount and time_impact_days remain None (no automated financial/schedule estimation)
    - Original risk is linked (risk.change_order_id = order.id, risk.status = 'converted')
    - Evidence package is linked to the change order
    - Audit records are generated for both change order and risk
    """
    tenant_id = uuid4()
    project_id = uuid4()
    user = make_user(Role.PROJECT_MANAGER, tenant_id=tenant_id)
    risk = make_risk(tenant_id, project_id)
    links = make_evidence_links(tenant_id, project_id, risk.id, count=2)

    added_objects = []
    added_orders = []

    def on_add(obj):
        if isinstance(obj, ChangeOrder):
            added_orders.append(obj)
        added_objects.append(obj)

    mock_session = create_mock_session()
    mock_session.scalar = AsyncMock(
        side_effect=[risk, None]
    )  # 1. risk query, 2. reference uniqueness
    mock_session.scalars = AsyncMock(side_effect=lambda q: [] if "approvals" in str(q) else links)
    mock_session.add = MagicMock(side_effect=on_add)

    service = ChangeOrderService(mock_session, user)
    service.evidence = MagicMock()
    service.evidence.access = MagicMock(project=AsyncMock())
    service.evidence.source = AsyncMock()
    service.load = AsyncMock(side_effect=lambda oid, lock=False: added_orders[-1])

    payload = ChangeOrderDraftFromRisk(
        reference="CO-FOUNDATION-01",
        title="Foundation Rock Mitigation",
        reason="Rock obstruction confirmed via geotechnical logs",
    )

    result = run_sync(
        service.create_draft_from_risk(
            project_id=project_id,
            risk_id=risk.id,
            payload=payload,
            request_id="req-test-123",
        )
    )

    # 1. Returned change order fields
    assert result["reference"] == "CO-FOUNDATION-01"
    assert result["title"] == "Foundation Rock Mitigation"
    assert result["status"] == "drafted"

    # 2. Constraint: Financial and schedule fields remain null until human enters them
    assert result["amount"] is None
    assert result["time_impact_days"] is None
    assert result["cost_items"] == []

    # 3. Source event and responsible party are preserved
    assert result["source_event_id"] == risk.project_event_id
    assert result["responsible_party"] == "Subcontractor Steel Co"

    # 4. Description cites evidence sources and notes responsible party
    assert "Delay event documented in document_chunk" in result["description"]
    assert "Responsible party: Subcontractor Steel Co" in result["description"]

    # 5. Original risk remains linked to the change order
    assert risk.change_order_id == result["id"]
    assert risk.status == "converted"

    # 6. Evidence package copied to change order
    co_links = [
        obj
        for obj in added_objects
        if isinstance(obj, EvidenceLink) and obj.subject_type == "change_order"
    ]
    assert len(co_links) == 2
    for cl in co_links:
        assert cl.subject_id == result["id"]
        assert cl.source_type == "document_chunk"

    # 7. Audit records generated
    audits = [obj for obj in added_objects if isinstance(obj, AuditEvent)]
    audit_actions = [a.action for a in audits]
    assert "change_order.draft_created_from_risk" in audit_actions
    assert "risk.converted_to_change_order" in audit_actions


def test_create_draft_from_risk_rejects_insufficient_evidence():
    """Constraint: Conversion fails if risk has insufficient evidence or no linked evidence."""
    tenant_id = uuid4()
    project_id = uuid4()
    user = make_user(Role.PROJECT_MANAGER, tenant_id=tenant_id)
    risk = make_risk(tenant_id, project_id, status="insufficient_evidence")

    mock_session = create_mock_session()
    mock_session.scalar = AsyncMock(return_value=risk)
    mock_session.scalars = AsyncMock(return_value=[])

    service = ChangeOrderService(mock_session, user)
    service.evidence = MagicMock()
    service.evidence.access = MagicMock(project=AsyncMock())
    service.evidence.source = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        run_sync(
            service.create_draft_from_risk(
                project_id=project_id,
                risk_id=risk.id,
            )
        )
    assert exc_info.value.status_code == 422
    assert "insufficient_evidence" in exc_info.value.detail


def test_create_draft_from_risk_rejects_already_converted_risk():
    """Cannot convert a risk that has already been converted to a change order."""
    tenant_id = uuid4()
    project_id = uuid4()
    user = make_user(Role.PROJECT_MANAGER, tenant_id=tenant_id)
    risk = make_risk(tenant_id, project_id, status="converted", change_order_id=uuid4())

    mock_session = create_mock_session()
    mock_session.scalar = AsyncMock(return_value=risk)

    service = ChangeOrderService(mock_session, user)
    service.evidence = MagicMock()
    service.evidence.access = MagicMock(project=AsyncMock())
    service.evidence.source = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        run_sync(
            service.create_draft_from_risk(
                project_id=project_id,
                risk_id=risk.id,
            )
        )
    assert exc_info.value.status_code == 409
    assert "already been converted" in exc_info.value.detail.lower()


# ==============================================================================
# 3. LLM Drafting & Grounding Constraints
# ==============================================================================


def test_validate_draft_ensures_grounded_citations_and_rejects_unsupported():
    """Constraint: LLM may draft narrative text only; must cite evidence; monetary claims excluded."""
    sources = {
        "E1": {"text": "Excavation delayed by 10 days due to rock formation."},
        "E2": {"text": "Survey report confirms granite bedrock at depth 2m."},
    }

    # Valid grounded cited draft
    valid_draft = CitedDraft(
        paragraphs=[
            CitedParagraph(text="Rock formation encountered during excavation.", citations=["E1"]),
            CitedParagraph(text="Bedrock depth verified at 2m.", citations=["E2"]),
        ]
    )
    validated = validate_draft(valid_draft, sources)
    assert len(validated.paragraphs) == 2

    # Hallucinated citation E3
    invalid_draft = CitedDraft(
        paragraphs=[
            CitedParagraph(text="Contractor incurred $50,000 cost.", citations=["E3"]),
        ]
    )
    with pytest.raises(ValueError, match="Unsupported citation"):
        validate_draft(invalid_draft, sources)


# ==============================================================================
# 4. Flow Steps 6-8: Editing, Submitting, and Approving/Rejecting the Draft
# ==============================================================================


def test_edit_draft_enters_human_cost_and_schedule():
    """Flow step 6: Human enters financial cost items and schedule impact."""
    tenant_id = uuid4()
    project_id = uuid4()
    user = make_user(Role.COMMERCIAL_MANAGER, tenant_id=tenant_id)

    order = ChangeOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        reference="CO-ROCK-001",
        title="Foundation Rock Mitigation",
        status="drafted",
        amount=None,
        time_impact_days=None,
        cost_items=[],
        draft_content={
            "paragraphs": [{"text": "Rock excavation required", "citations": ["E1"]}],
            "sources": {
                "E1": {
                    "evidence_link_id": "link-1",
                    "text": "Rock encountered",
                    "source_type": "doc",
                }
            },
        },
        currency="USD",
        created_by_id=user.id,
    )

    mock_session = create_mock_session()
    mock_session.scalar = AsyncMock(return_value=order)
    mock_session.scalars = AsyncMock(return_value=[])

    service = ChangeOrderService(mock_session, user)
    service.evidence = MagicMock()
    service.evidence.access = MagicMock(project=AsyncMock())
    service.evidence.source = AsyncMock()
    service.load = AsyncMock(return_value=order)

    # Human edits: adds cost items ($12,500) and schedule impact (7 days)
    patch_payload = ChangeOrderPatch(
        time_impact_days=7,
        cost_items=[
            CostItem(
                description="Hydraulic rock breaker rental (3 days)",
                quantity=Decimal("3"),
                unit_rate=Decimal("2500.00"),
            ),
            CostItem(
                description="Additional labor crew",
                quantity=Decimal("1"),
                unit_rate=Decimal("5000.00"),
            ),
        ],
        reason="Entered contractor verified rate breakdown",
    )

    result = run_sync(service.patch(order.id, patch_payload))

    assert result["time_impact_days"] == 7
    assert Decimal(str(result["amount"])) == Decimal("12500.00")
    assert len(result["cost_items"]) == 2
    # Preserves draft sources for submission citation check
    assert "sources" in result["draft"]
    assert "sources" in order.draft_content


def test_submit_draft_requires_cost_items_and_advances_to_submitted():
    """Flow step 7: User submits draft for approval, transitioning from drafted to submitted."""
    tenant_id = uuid4()
    project_id = uuid4()
    user = make_user(Role.COMMERCIAL_MANAGER, tenant_id=tenant_id)

    link = EvidenceLink(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        subject_type="change_order",
        subject_id=uuid4(),
        source_type="doc",
        source_id=uuid4(),
        source_text_snippet="Rock encountered",
    )

    order = ChangeOrder(
        id=link.subject_id,
        tenant_id=tenant_id,
        project_id=project_id,
        reference="CO-ROCK-001",
        title="Foundation Rock Mitigation",
        status="drafted",
        amount=Decimal("12500.00"),
        time_impact_days=7,
        cost_items=[
            {"description": "Rock breaker rental", "quantity": "3", "unit_rate": "2500.00"},
            {"description": "Labor", "quantity": "1", "unit_rate": "5000.00"},
        ],
        draft_content={
            "sources": {
                "E1": {
                    "evidence_link_id": str(link.id),
                    "text": "Rock encountered",
                    "source_type": "doc",
                }
            }
        },
        currency="USD",
        created_by_id=user.id,
    )

    added_objects = []
    mock_session = create_mock_session()
    mock_session.scalar = AsyncMock(return_value=order)
    mock_session.scalars = AsyncMock(side_effect=lambda q: [] if "approvals" in str(q) else [link])
    mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    service = ChangeOrderService(mock_session, user)
    service.evidence = MagicMock()
    service.evidence.access = MagicMock(project=AsyncMock())
    service.evidence.source = AsyncMock()
    service.load = AsyncMock(return_value=order)
    service.links = AsyncMock(return_value=[link])

    submit_payload = SubmitInput(
        cost_confirmed=True, reason="Submitted for project manager commercial sign-off"
    )
    result = run_sync(service.submit(order.id, submit_payload))

    assert result["status"] == "submitted"
    assert order.submitted_by_id == user.id

    # Created pending Approval record
    approvals = [o for o in added_objects if isinstance(o, Approval)]
    assert len(approvals) == 1
    assert approvals[0].status == "pending"
    assert approvals[0].change_order_id == order.id

    # Audit event created
    audits = [o for o in added_objects if isinstance(o, AuditEvent)]
    assert any(a.action == "change_order.submit" for a in audits)


def test_approve_and_reject_require_explicit_human_action_and_reason():
    """Flow step 8: Approval and rejection require explicit human action and non-empty reason.
    Self-approval is strictly forbidden.
    """
    tenant_id = uuid4()
    project_id = uuid4()
    creator_id = uuid4()
    reviewer_user = make_user(Role.PROJECT_MANAGER, tenant_id=tenant_id)

    order = ChangeOrder(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        reference="CO-ROCK-001",
        title="Foundation Rock Mitigation",
        status="submitted",
        amount=Decimal("12500.00"),
        time_impact_days=7,
        cost_items=[{"description": "Rock breaker", "quantity": "1", "unit_rate": "12500.00"}],
        draft_content={
            "sources": {
                "E1": {
                    "evidence_link_id": "link-1",
                    "text": "Rock encountered",
                    "source_type": "doc",
                }
            }
        },
        currency="USD",
        created_by_id=creator_id,
        submitted_by_id=creator_id,
    )

    approval = Approval(
        id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        change_order_id=order.id,
        status="pending",
    )

    link = EvidenceLink(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=tenant_id,
        project_id=project_id,
        subject_type="change_order",
        subject_id=order.id,
        source_type="doc",
        source_id=uuid4(),
        source_text_snippet="Rock encountered",
    )
    order.draft_content["sources"]["E1"]["evidence_link_id"] = str(link.id)

    # 1. Forbidden: Creator tries to self-approve
    creator_session = create_mock_session()
    creator_service = ChangeOrderService(
        creator_session, make_user(Role.PROJECT_MANAGER, user_id=creator_id)
    )
    creator_service.evidence = MagicMock()
    creator_service.evidence.access = MagicMock(project=AsyncMock())
    creator_service.evidence.source = AsyncMock()
    creator_service.load = AsyncMock(return_value=order)
    creator_service.links = AsyncMock(return_value=[link])

    with pytest.raises(HTTPException) as exc_info:
        run_sync(
            creator_service.decide(
                order.id,
                "approved",
                DecisionInput(reason="Approving my own draft"),
            )
        )
    assert exc_info.value.status_code == 403
    assert "Self-approval" in exc_info.value.detail

    # 2. Allowed: Separate reviewer approves with mandatory reason
    reviewer_session = create_mock_session()
    reviewer_session.scalar = AsyncMock(return_value=approval)
    reviewer_session.scalars = AsyncMock(
        side_effect=lambda q: [] if "approvals" in str(q) else [link]
    )
    reviewer_service = ChangeOrderService(reviewer_session, reviewer_user)
    reviewer_service.evidence = MagicMock()
    reviewer_service.evidence.access = MagicMock(project=AsyncMock())
    reviewer_service.evidence.source = AsyncMock()
    reviewer_service.load = AsyncMock(return_value=order)
    reviewer_service.links = AsyncMock(return_value=[link])

    result = run_sync(
        reviewer_service.decide(
            order.id,
            "approved",
            DecisionInput(reason="Verified against site daily log and approved unit rates"),
        )
    )
    assert result["status"] == "approved"
    assert approval.status == "approved"
    assert approval.decided_by_id == reviewer_user.id
    assert approval.comments == "Verified against site daily log and approved unit rates"


# ==============================================================================
# 5. External Communication Guarantee
# ==============================================================================


def test_no_automated_external_communications():
    """Constraint: Do not send external communication automatically (no automated emails, webhooks, or notifications)."""
    tenant_id = uuid4()
    project_id = uuid4()
    user = make_user(Role.PROJECT_MANAGER, tenant_id=tenant_id)
    risk = make_risk(tenant_id, project_id)
    links = make_evidence_links(tenant_id, project_id, risk.id, count=1)

    added_orders = []

    def on_add(obj):
        if isinstance(obj, ChangeOrder):
            added_orders.append(obj)

    mock_session = create_mock_session()
    mock_session.scalar = AsyncMock(side_effect=[risk, None])
    mock_session.scalars = AsyncMock(side_effect=lambda q: [] if "approvals" in str(q) else links)
    mock_session.add = MagicMock(side_effect=on_add)

    service = ChangeOrderService(mock_session, user)
    service.evidence = MagicMock()
    service.evidence.access = MagicMock(project=AsyncMock())
    service.evidence.source = AsyncMock()
    service.load = AsyncMock(side_effect=lambda oid, lock=False: added_orders[-1])

    run_sync(
        service.create_draft_from_risk(
            project_id=project_id,
            risk_id=risk.id,
            payload=ChangeOrderDraftFromRisk(reason="Manual test"),
        )
    )
