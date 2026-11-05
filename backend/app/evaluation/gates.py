"""CI quality gates enforcement."""

from typing import Any

from app.evaluation.config import (
    MAX_UNSUPPORTED_FACTUAL_CLAIMS,
    MIN_CITATION_COVERAGE,
    MIN_CLASSIFICATION_ACCURACY,
    MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY,
)


def evaluate_ci_gates(evaluation_results: dict[str, Any]) -> dict[str, Any]:
    """Evaluate quality thresholds and return pass/fail status for CI."""
    gates = []
    overall_pass = True

    # 1. Classification accuracy gate (>= 90%)
    cls_metrics = evaluation_results.get("classification", {})
    actual_cls_acc = cls_metrics.get("accuracy", 0.0)
    cls_passed = actual_cls_acc >= MIN_CLASSIFICATION_ACCURACY
    gates.append({
        "name": "classification_accuracy",
        "threshold": f">= {MIN_CLASSIFICATION_ACCURACY:.0%}",
        "actual": f"{actual_cls_acc:.2%}",
        "passed": cls_passed,
        "description": "Document classification accuracy across all golden cases",
    })
    if not cls_passed:
        overall_pass = False

    # 2. Critical field extraction accuracy gate (>= 85%)
    ext_metrics = evaluation_results.get("extraction", {})
    actual_crit_acc = ext_metrics.get("critical_field_accuracy", 0.0)
    crit_passed = actual_crit_acc >= MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY
    gates.append({
        "name": "critical_field_extraction_accuracy",
        "threshold": f">= {MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY:.0%}",
        "actual": f"{actual_crit_acc:.2%}",
        "passed": crit_passed,
        "description": "Accuracy on critical legal, financial, and identifying fields",
    })
    if not crit_passed:
        overall_pass = False

    # 3. Citation coverage gate (>= 95%)
    cit_metrics = evaluation_results.get("citations", {})
    actual_cit_cov = cit_metrics.get("citation_coverage", 0.0)
    cit_passed = actual_cit_cov >= MIN_CITATION_COVERAGE
    gates.append({
        "name": "citation_coverage",
        "threshold": f">= {MIN_CITATION_COVERAGE:.0%}",
        "actual": f"{actual_cit_cov:.2%}",
        "passed": cit_passed,
        "description": "Percentage of extracted facts with valid page and source snippet citation",
    })
    if not cit_passed:
        overall_pass = False

    # 4. Zero unsupported factual claims gate (== 0)
    actual_unsupported = cit_metrics.get("unsupported_factual_claims", 0)
    claims_passed = actual_unsupported <= MAX_UNSUPPORTED_FACTUAL_CLAIMS
    gates.append({
        "name": "zero_unsupported_factual_claims",
        "threshold": f"== {MAX_UNSUPPORTED_FACTUAL_CLAIMS}",
        "actual": f"{actual_unsupported} claims",
        "passed": claims_passed,
        "description": "Prohibits any hallucinated or unevidenced factual claims",
    })
    if not claims_passed:
        overall_pass = False

    return {
        "passed": overall_pass,
        "total_gates": len(gates),
        "passed_gates": sum(1 for g in gates if g["passed"]),
        "failed_gates": sum(1 for g in gates if not g["passed"]),
        "gates": gates,
    }
