"""Backend authorization and constraint tests for ChangeGuard Review Queue."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domain.services.risks import RiskDecision, validate_risk_decision
from app.policy.permissions import Action, Role, has_permission

# ==============================================================================
# 1. Role Permission Matrix Tests
# ==============================================================================


@pytest.mark.parametrize(
    "role,expected_accept",
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
def test_risk_accept_permission_enforcement(role, expected_accept):
    """Only commercial roles can accept, dismiss, override, or decide risks."""
    assert has_permission(role, Action.RISK_ACCEPT) is expected_accept


@pytest.mark.parametrize(
    "role,expected_change_write",
    [
        (Role.OWNER, True),
        (Role.ADMIN, True),
        (Role.PROJECT_MANAGER, True),
        (Role.COMMERCIAL_MANAGER, True),
        (Role.SITE_ENGINEER, True),
        (Role.VIEWER, False),
        (Role.AUDITOR, False),
    ],
)
def test_change_write_permission_enforcement(role, expected_change_write):
    """Change order creation/conversion requires CHANGE_WRITE permission."""
    assert has_permission(role, Action.CHANGE_WRITE) is expected_change_write


@pytest.mark.parametrize(
    "role,expected_financial_read",
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
def test_financial_read_permission_enforcement(role, expected_financial_read):
    """Review queue items contain commercial figures and require FINANCIAL_READ."""
    assert has_permission(role, Action.FINANCIAL_READ) is expected_financial_read


# ==============================================================================
# 2. Risk Decision Validation Tests (Mandatory Reasons & Mutually Exclusive Fields)
# ==============================================================================


def test_dismissal_requires_non_empty_reason():
    """Dismissal requires a non-empty, non-whitespace justification reason."""
    with pytest.raises((ValueError, Exception)):
        RiskDecision(action="dismiss", reason="")

    with pytest.raises(ValueError, match="A reason is mandatory"):
        RiskDecision(action="dismiss", reason="   \t\n  ")

    valid = RiskDecision(action="dismiss", reason="Duplicate scope already captured under CO-012")
    assert valid.reason == "Duplicate scope already captured under CO-012"


def test_override_requires_reason_and_modifications():
    """Override requires a reason and at least one modified parameter."""
    with pytest.raises(ValueError, match="At least one change"):
        RiskDecision(action="override", reason="Schedule updated")

    valid = RiskDecision(
        action="override",
        reason="Mitigated by secondary batch delivery",
        severity="medium",
        schedule_impact_days=5,
    )
    assert valid.severity == "medium"
    assert valid.schedule_impact_days == 5


def test_non_override_rejects_severity_and_schedule_fields():
    """Accept, dismiss, and request_evidence cannot alter severity or schedule fields."""
    with pytest.raises(ValueError, match="Only override accepts"):
        RiskDecision(action="accept", reason="Approved", severity="low")

    with pytest.raises(ValueError, match="Only override accepts"):
        RiskDecision(action="dismiss", reason="Dismissed", schedule_impact_days=10)


def test_request_evidence_requires_reason():
    """Requesting more evidence requires a justification reason."""
    with pytest.raises((ValueError, Exception)):
        RiskDecision(action="request_evidence", reason="")

    with pytest.raises(ValueError, match="A reason is mandatory"):
        RiskDecision(action="request_evidence", reason="   ")

    valid = RiskDecision(
        action="request_evidence",
        reason="Requesting certified mill test reports and delivery weighbridge tickets",
    )
    assert valid.action == "request_evidence"


def test_convert_to_change_order_requires_reason():
    """Converting a risk to change order requires a mandatory reason."""
    with pytest.raises((ValueError, Exception)):
        RiskDecision(action="convert_to_change_order", reason="")

    with pytest.raises(ValueError, match="A reason is mandatory"):
        RiskDecision(action="convert_to_change_order", reason="   ")

    valid = RiskDecision(
        action="convert_to_change_order",
        reason="Unforeseen boulder obstruction requires formal variation under clause 13.1",
        change_order_reference="CO-2026-088",
    )
    assert valid.action == "convert_to_change_order"
    assert valid.change_order_reference == "CO-2026-088"


# ==============================================================================
# 3. Insufficient-Evidence Constraints & Authorization Rejections
# ==============================================================================


def test_insufficient_evidence_risk_cannot_be_accepted():
    """Constraint: Insufficient-evidence risks CANNOT be accepted as supported evidence."""
    # Attempting to accept with no evidence links or status insufficient_evidence
    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role="commercial_manager",
            risk_status="insufficient_evidence",
            has_links=False,
            action="accept",
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "insufficient_evidence"

    # Status open but no evidence links also rejected
    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role="commercial_manager",
            risk_status="open",
            has_links=False,
            action="accept",
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "insufficient_evidence"

    # Override and convert also forbidden on insufficient evidence
    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role="commercial_manager",
            risk_status="insufficient_evidence",
            has_links=False,
            action="override",
        )
    assert exc_info.value.status_code == 422

    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role="commercial_manager",
            risk_status="insufficient_evidence",
            has_links=False,
            action="convert_to_change_order",
        )
    assert exc_info.value.status_code == 422


def test_insufficient_evidence_risk_allows_dismiss_and_request_evidence():
    """Insufficient-evidence risks can be dismissed or have additional evidence requested."""
    # Dismissal is permitted for commercial roles
    validate_risk_decision(
        role="commercial_manager",
        risk_status="insufficient_evidence",
        has_links=False,
        action="dismiss",
    )

    # Requesting evidence is permitted for commercial roles
    validate_risk_decision(
        role="commercial_manager",
        risk_status="insufficient_evidence",
        has_links=False,
        action="request_evidence",
    )


def test_supported_risk_allows_acceptance_and_conversion():
    """Supported risks with valid evidence allow accept, convert, dismiss, and override."""
    for action in ["accept", "dismiss", "override", "request_evidence", "convert_to_change_order"]:
        validate_risk_decision(
            role="commercial_manager",
            risk_status="open",
            has_links=True,
            action=action,
        )


@pytest.mark.parametrize("unauthorized_role", ["viewer", "site_engineer", "auditor"])
@pytest.mark.parametrize(
    "action", ["accept", "dismiss", "override", "request_evidence", "convert_to_change_order"]
)
def test_unauthorized_roles_cannot_decide_risks(unauthorized_role, action):
    """Roles without RISK_ACCEPT (viewer, site_engineer, auditor) are forbidden from deciding risks."""
    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role=unauthorized_role,
            risk_status="open",
            has_links=True,
            action=action,
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Access denied"


def test_resolved_risk_cannot_be_reopened():
    """Resolved risks cannot be reopened by a review decision."""
    with pytest.raises(HTTPException) as exc_info:
        validate_risk_decision(
            role="commercial_manager",
            risk_status="open",
            has_links=True,
            action="dismiss",
            resolution_link_id=uuid4(),
        )
    assert exc_info.value.status_code == 409
    assert "Resolved risk history cannot be reopened" in str(exc_info.value.detail)
