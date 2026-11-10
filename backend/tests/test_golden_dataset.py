"""Unit and integration test suite for ChangeGuard Golden Evaluation Dataset."""

# ruff: noqa: PLR2004, E501
import json
from pathlib import Path

import pytest

from app.document_processing.schema import Classification
from app.document_processing.structured.schemas import schema_for

# Golden dataset root path (works whether run from repo root or backend/)
REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ROOT = REPO_ROOT / "tests/golden"


@pytest.fixture(scope="session")
def manifest():
    manifest_file = GOLDEN_ROOT / "manifest.json"
    assert manifest_file.exists(), f"Golden manifest not found at {manifest_file}"
    return json.loads(manifest_file.read_text(encoding="utf-8"))


def test_manifest_categories_and_counts(manifest):
    """Verify all 13 required categories meet or exceed specified minimum counts."""
    expected_categories = {
        "contracts": 5,
        "boqs": 5,
        "rfis": 5,
        "change_orders": 10,
        "daily_reports": 10,
        "emails": 10,
        "site_photos": 10,
        "duplicate_detection": 5,
        "missing_evidence": 5,
        "conflicting_evidence": 5,
        "permission_isolation": 10,
        "prompt_injection": 10,
        "end_to_end_workflows": 5,
    }

    categories = manifest["categories"]
    assert set(expected_categories.keys()).issubset(set(categories.keys()))

    total_cases = 0
    for cat_name, min_count in expected_categories.items():
        actual_count = categories[cat_name]["count"]
        assert actual_count >= min_count, f"{cat_name} count {actual_count} < minimum {min_count}"
        total_cases += actual_count

    assert manifest["total_cases"] == total_cases
    assert manifest["total_cases"] >= 95


def test_all_document_files_exist_and_have_required_structure():
    """Verify every document file exists under tests/golden/documents and contains required sections."""
    doc_dirs = [
        "contracts",
        "boqs",
        "rfis",
        "change_orders",
        "daily_reports",
        "emails",
        "site_photos",
        "duplicate_detection",
        "missing_evidence",
        "conflicting_evidence",
        "permission_isolation",
        "prompt_injection",
        "e2e_workflows",
    ]
    for sub in doc_dirs:
        folder = GOLDEN_ROOT / "documents" / sub
        assert folder.exists() and folder.is_dir(), f"Missing document directory {folder}"
        files = list(folder.glob("*.json"))
        assert len(files) > 0, f"No json files found in {folder}"

        for doc_file in files:
            data = json.loads(doc_file.read_text(encoding="utf-8"))
            assert "id" in data, f"Missing 'id' in {doc_file}"
            assert "input" in data, f"Missing 'input' in {doc_file}"
            assert "expected_output" in data, f"Missing 'expected_output' in {doc_file}"
            assert "evaluation_criteria" in data, f"Missing 'evaluation_criteria' in {doc_file}"


def test_expected_classifications_schema_compliance():
    """Verify all classifications strictly validate against Classification Pydantic model."""
    cls_file = GOLDEN_ROOT / "expected_classifications/all_classifications.json"
    assert cls_file.exists(), "Missing all_classifications.json"
    cases = json.loads(cls_file.read_text(encoding="utf-8"))
    assert len(cases) >= 55  # 5+5+5+10+10+10+10

    for c in cases:
        # Validate Pydantic model
        validated = Classification.model_validate(c["expected"])
        assert validated.confidence >= 0.0
        assert validated.confidence <= 1.0
        assert len(validated.reasoning) > 0
        assert len(validated.model_or_rule_used) > 0


def test_expected_extractions_schema_compliance():
    """Verify all structured extractions strictly validate against SCHEMAS."""
    groups = [
        ("contracts.json", "contract"),
        ("boqs.json", "boq"),
        ("rfis.json", "rfi"),
        ("change_orders.json", "change_order"),
        ("daily_reports.json", "daily_report"),
        ("emails.json", "email"),
    ]

    for filename, doc_type in groups:
        path = GOLDEN_ROOT / "expected_extractions" / filename
        assert path.exists(), f"Missing {filename}"
        cases = json.loads(path.read_text(encoding="utf-8"))
        schema = schema_for(doc_type)
        assert schema is not None, f"No schema for {doc_type}"

        for c in cases:
            ext_dict = c["expected"]
            # Validate through Pydantic model
            validated = schema.model_validate(ext_dict)
            assert validated is not None


def test_duplicate_detection_cases():
    """Verify duplicate detection golden cases have matching fields and risk findings."""
    dup_file = GOLDEN_ROOT / "expected_risks/duplicate_detection.json"
    assert dup_file.exists()
    cases = json.loads(dup_file.read_text(encoding="utf-8"))
    assert len(cases) >= 5

    for c in cases:
        assert c["expected_output"]["is_duplicate"] is True
        assert c["expected_output"]["risk_type"] == "duplicate_change_order_claim"
        assert len(c["expected_output"]["sources"]) >= 2
        assert c["evaluation_criteria"]["metric"] == "deterministic_rule_match"


def test_missing_evidence_cases():
    """Verify missing evidence cases flag refusal and status insufficient_evidence."""
    miss_file = GOLDEN_ROOT / "expected_risks/missing_evidence.json"
    assert miss_file.exists()
    cases = json.loads(miss_file.read_text(encoding="utf-8"))
    assert len(cases) >= 5

    for c in cases:
        assert c["expected_output"]["risk_detected"] is True
        assert c["expected_output"]["status"] == "insufficient_evidence"
        assert c["expected_output"]["refusal_behavior"]["refuse_approval"] is True


def test_conflicting_evidence_cases():
    """Verify conflicting evidence cases identify contradictions with citations."""
    conf_file = GOLDEN_ROOT / "expected_risks/conflicting_evidence.json"
    assert conf_file.exists()
    cases = json.loads(conf_file.read_text(encoding="utf-8"))
    assert len(cases) >= 5

    for c in cases:
        assert c["expected_output"]["conflict_detected"] is True
        assert "contradiction_key" in c["expected_output"]
        assert len(c["expected_output"]["sources"]) >= 2


def test_permission_isolation_cases():
    """Verify permission isolation cases enforce default-deny and role boundaries."""
    perm_file = GOLDEN_ROOT / "permission_isolation/permission_isolation.json"
    assert perm_file.exists()
    cases = json.loads(perm_file.read_text(encoding="utf-8"))
    assert len(cases) >= 10

    for c in cases:
        if c["id"] != "PERM-010":  # PERM-010 allows filtered/redacted search
            assert c["expected_output"]["allowed"] is False
            assert c["expected_output"]["http_status"] in (403, 404, 423)
        else:
            assert c["expected_output"]["allowed"] is True
            assert len(c["expected_output"]["omitted_chunk_ids"]) > 0


def test_prompt_injection_cases():
    """Verify prompt injection cases prevent privilege escalation and system compromise."""
    inj_file = GOLDEN_ROOT / "prompt_injection/prompt_injection.json"
    assert inj_file.exists()
    cases = json.loads(inj_file.read_text(encoding="utf-8"))
    assert len(cases) >= 10

    for c in cases:
        expected = c["expected_output"]
        assert expected["injection_detected"] is True
        assert expected.get("privilege_escalated", False) is False
        assert expected.get("system_compromised", False) is False


def test_e2e_workflow_cases():
    """Verify end-to-end workflow cases have multi-stage sequences and completion criteria."""
    e2e_file = GOLDEN_ROOT / "expected_change_orders/e2e_workflows.json"
    assert e2e_file.exists()
    cases = json.loads(e2e_file.read_text(encoding="utf-8"))
    assert len(cases) >= 5

    for c in cases:
        stages = c["input"]["stages"]
        assert len(stages) >= 4
        assert c["evaluation_criteria"]["metric"] in (
            "e2e_workflow_completion",
            "investigation_agent_grounding",
        )


def test_entities_manifest_integrity():
    """Verify entity graph references valid projects, tenants, contracts, and contractors."""
    ent_file = GOLDEN_ROOT / "expected_entities/entities.json"
    assert ent_file.exists()
    data = json.loads(ent_file.read_text(encoding="utf-8"))

    assert len(data["tenants"]) >= 2
    assert len(data["projects"]) >= 3
    assert len(data["employers"]) >= 5
    assert len(data["contractors"]) >= 5
    assert len(data["contracts"]) >= 5
    assert len(data["rfis"]) >= 5
    assert len(data["change_orders"]) >= 10


def test_retrieval_cases_integrity():
    """Verify retrieval golden cases specify search filters, limits, and expected hits."""
    ret_file = GOLDEN_ROOT / "expected_retrieval/retrieval.json"
    assert ret_file.exists()
    cases = json.loads(ret_file.read_text(encoding="utf-8"))
    assert len(cases) >= 5

    for c in cases:
        assert "query" in c["input"]
        assert "status" in c["expected_output"]
        assert c["expected_output"]["status"] in ("matched", "insufficient_evidence")
