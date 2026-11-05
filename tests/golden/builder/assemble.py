"""Master assembler and validator for ChangeGuard Golden Evaluation Dataset."""

import json
import sys
from pathlib import Path

# Add backend directory to sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.document_processing.schema import Classification
from app.document_processing.structured.schemas import SCHEMAS, schema_for

from tests.golden.builder.boqs import get_boq_cases
from tests.golden.builder.change_orders import get_change_order_cases
from tests.golden.builder.conflicting_evidence import get_conflicting_evidence_cases
from tests.golden.builder.contracts import get_contract_cases
from tests.golden.builder.daily_reports import get_daily_report_cases
from tests.golden.builder.duplicate_detection import get_duplicate_detection_cases
from tests.golden.builder.e2e_workflows import get_e2e_workflow_cases
from tests.golden.builder.emails import get_email_cases
from tests.golden.builder.entities import get_entities_manifest
from tests.golden.builder.missing_evidence import get_missing_evidence_cases
from tests.golden.builder.permission_isolation import get_permission_isolation_cases
from tests.golden.builder.prompt_injection import get_prompt_injection_cases
from tests.golden.builder.retrieval import get_retrieval_cases
from tests.golden.builder.rfis import get_rfi_cases
from tests.golden.builder.site_photos import get_site_photo_cases

GOLDEN_DIR = REPO_ROOT / "tests/golden"

def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

def validate_extraction(doc_type: str, extraction_dict: dict):
    schema = schema_for(doc_type)
    if schema:
        # Validate through Pydantic model
        schema.model_validate(extraction_dict)
    return True

def validate_classification(cls_dict: dict):
    Classification.model_validate(cls_dict)
    return True

def assemble():
    print(f"Assembling golden evaluation dataset into {GOLDEN_DIR}...")
    
    # 1. Collect core document cases
    contracts = get_contract_cases()
    boqs = get_boq_cases()
    rfis = get_rfi_cases()
    change_orders = get_change_order_cases()
    daily_reports = get_daily_report_cases()
    emails = get_email_cases()
    site_photos = get_site_photo_cases()

    # 2. Collect specialized evaluation cases
    duplicates = get_duplicate_detection_cases()
    missing_evidence = get_missing_evidence_cases()
    conflicting_evidence = get_conflicting_evidence_cases()
    permissions = get_permission_isolation_cases()
    prompt_injections = get_prompt_injection_cases()
    e2e_workflows = get_e2e_workflow_cases()
    retrievals = get_retrieval_cases()
    entities = get_entities_manifest()

    print("Loaded cases:")
    print(f" - Contracts: {len(contracts)}")
    print(f" - BOQs: {len(boqs)}")
    print(f" - RFIs: {len(rfis)}")
    print(f" - Change Orders: {len(change_orders)}")
    print(f" - Daily Reports: {len(daily_reports)}")
    print(f" - Emails: {len(emails)}")
    print(f" - Site Photos: {len(site_photos)}")
    print(f" - Duplicate Detection: {len(duplicates)}")
    print(f" - Missing Evidence: {len(missing_evidence)}")
    print(f" - Conflicting Evidence: {len(conflicting_evidence)}")
    print(f" - Permission Isolation: {len(permissions)}")
    print(f" - Prompt Injection: {len(prompt_injections)}")
    print(f" - E2E Workflows: {len(e2e_workflows)}")
    print(f" - Retrieval Queries: {len(retrievals)}")

    # Validate all core extractions and classifications
    doc_groups = [
        ("contract", contracts, "contracts"),
        ("boq", boqs, "boqs"),
        ("rfi", rfis, "rfis"),
        ("change_order", change_orders, "change_orders"),
        ("daily_report", daily_reports, "daily_reports"),
        ("email", emails, "emails"),
        ("site_photo", site_photos, "site_photos"),
    ]

    all_classifications = []
    
    for doc_type, cases, folder_name in doc_groups:
        cls_list = []
        ext_list = []
        for case in cases:
            # Validate classification
            cls = case["expected_output"]["classification"]
            validate_classification(cls)
            cls_entry = {
                "id": case["id"],
                "title": case["title"],
                "input": case["input"],
                "expected": cls,
                "evaluation_criteria": case["evaluation_criteria"],
            }
            cls_list.append(cls_entry)
            all_classifications.append(cls_entry)

            # Validate extraction if structured schema exists
            ext = case["expected_output"]["extraction"]
            if doc_type in SCHEMAS:
                validate_extraction(doc_type, ext)
            ext_list.append({
                "id": case["id"],
                "title": case["title"],
                "document_type": doc_type,
                "expected": ext,
                "entities": case["expected_output"].get("entities", []),
                "evaluation_criteria": case["evaluation_criteria"],
            })

            # Write document input file
            write_json(GOLDEN_DIR / f"documents/{folder_name}/{case['id']}.json", case)

        # Write grouped expected classification and extraction
        write_json(GOLDEN_DIR / f"expected_classifications/{folder_name}.json", cls_list)
        write_json(GOLDEN_DIR / f"expected_extractions/{folder_name}.json", ext_list)

    write_json(GOLDEN_DIR / "expected_classifications/all_classifications.json", all_classifications)

    # 3. Write specialized test cases to documents and expected folders
    # Duplicate detection
    for case in duplicates:
        write_json(GOLDEN_DIR / f"documents/duplicate_detection/{case['id']}.json", case)
    write_json(GOLDEN_DIR / "expected_risks/duplicate_detection.json", duplicates)

    # Missing evidence
    for case in missing_evidence:
        write_json(GOLDEN_DIR / f"documents/missing_evidence/{case['id']}.json", case)
    write_json(GOLDEN_DIR / "expected_risks/missing_evidence.json", missing_evidence)

    # Conflicting evidence
    for case in conflicting_evidence:
        write_json(GOLDEN_DIR / f"documents/conflicting_evidence/{case['id']}.json", case)
    write_json(GOLDEN_DIR / "expected_risks/conflicting_evidence.json", conflicting_evidence)

    # Consolidated expected risks
    risks_summary = {
        "duplicate_detection": duplicates,
        "missing_evidence": missing_evidence,
        "conflicting_evidence": conflicting_evidence,
    }
    write_json(GOLDEN_DIR / "expected_risks/risks.json", risks_summary)

    # Permission isolation
    for case in permissions:
        write_json(GOLDEN_DIR / f"documents/permission_isolation/{case['id']}.json", case)
    write_json(GOLDEN_DIR / "permission_isolation/permission_isolation.json", permissions)

    # Prompt injection
    for case in prompt_injections:
        write_json(GOLDEN_DIR / f"documents/prompt_injection/{case['id']}.json", case)
    write_json(GOLDEN_DIR / "prompt_injection/prompt_injection.json", prompt_injections)

    # E2E Workflows
    for case in e2e_workflows:
        write_json(GOLDEN_DIR / f"documents/e2e_workflows/{case['id']}.json", case)
    write_json(GOLDEN_DIR / "expected_change_orders/e2e_workflows.json", e2e_workflows)

    # Expected Change Orders workflow
    co_workflows = [
        {
            "id": c["id"],
            "co_number": c["expected_output"]["extraction"]["co_number"]["value"],
            "title": c["expected_output"]["extraction"]["title"]["value"],
            "amount": c["expected_output"]["extraction"]["amount"]["value"],
            "status": c["expected_output"]["extraction"]["status"]["value"],
            "document_references": c["expected_output"]["extraction"]["document_references"],
            "evaluation_criteria": c["evaluation_criteria"],
        }
        for c in change_orders
    ]
    write_json(GOLDEN_DIR / "expected_change_orders/change_orders.json", co_workflows)

    # Expected Entities
    write_json(GOLDEN_DIR / "expected_entities/entities.json", entities)

    # Expected Retrieval
    write_json(GOLDEN_DIR / "expected_retrieval/retrieval.json", retrievals)

    # Master Manifest
    total_cases_count = (
        len(contracts) + len(boqs) + len(rfis) + len(change_orders) +
        len(daily_reports) + len(emails) + len(site_photos) +
        len(duplicates) + len(missing_evidence) + len(conflicting_evidence) +
        len(permissions) + len(prompt_injections) + len(e2e_workflows)
    )

    manifest = {
        "version": "1.0.0",
        "dataset_name": "ChangeGuard Golden Evaluation Dataset",
        "total_cases": total_cases_count,
        "categories": {
            "contracts": {"count": len(contracts), "target_minimum": 5},
            "boqs": {"count": len(boqs), "target_minimum": 5},
            "rfis": {"count": len(rfis), "target_minimum": 5},
            "change_orders": {"count": len(change_orders), "target_minimum": 10},
            "daily_reports": {"count": len(daily_reports), "target_minimum": 10},
            "emails": {"count": len(emails), "target_minimum": 10},
            "site_photos": {"count": len(site_photos), "target_minimum": 10},
            "duplicate_detection": {"count": len(duplicates), "target_minimum": 5},
            "missing_evidence": {"count": len(missing_evidence), "target_minimum": 5},
            "conflicting_evidence": {"count": len(conflicting_evidence), "target_minimum": 5},
            "permission_isolation": {"count": len(permissions), "target_minimum": 10},
            "prompt_injection": {"count": len(prompt_injections), "target_minimum": 10},
            "end_to_end_workflows": {"count": len(e2e_workflows), "target_minimum": 5},
        },
        "directories": [
            "documents/",
            "expected_classifications/",
            "expected_extractions/",
            "expected_entities/",
            "expected_risks/",
            "expected_retrieval/",
            "expected_change_orders/",
            "prompt_injection/",
        ],
    }
    write_json(GOLDEN_DIR / "manifest.json", manifest)

    print(f"\nSuccessfully generated and validated {total_cases_count} golden test cases!")
    print(f"Master manifest written to {GOLDEN_DIR / 'manifest.json'}")

if __name__ == "__main__":
    assemble()

