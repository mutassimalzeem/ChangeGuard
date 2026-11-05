"""Change order golden test cases definition (10 cases)."""

def get_change_order_cases():
    cases_meta = [
        ("DOC-CO-001", "CO-2026-001", "Sub-base Stabilization over Unsuitable Clay Formation",
         "Excavation and replacement of 1,200m3 of soft marine clay with compacted crushed stone and blinding concrete.",
         "2026-02-28", "142500.00", "USD", "approved", "CON-2026-CS-001", "RFI-2026-001", 6),
        ("DOC-CO-002", "CO-2026-002", "33kV Feeder Cable Diversion around Uncharted Heritage Duct",
         "Rerouting of primary 33kV high voltage duct bank around discovered historical masonry conduit.",
         "2026-03-04", "88750.00", "USD", "submitted", "CON-2026-MEP-002", "RFI-2026-002", 4),
        ("DOC-CO-003", "CO-2026-003", "Level 04 Structural Slab Post-Tensioning Upgrade for MRI Suite",
         "Addition of bonded post-tensioned tendons and drop panels to support tenant heavy MRI imaging scanner.",
         "2026-03-12", "215000.00", "USD", "approved", "CON-2026-CS-001", "RFI-2026-004", 12),
        ("DOC-CO-004", "CO-2026-004", "Fire-Rated Acoustic Door Package Upgrade in Stair Cores",
         "Upgrade of 42 emergency exit doors to 90-minute fire rating with acoustic seals per revised life safety code.",
         "2026-03-16", "64200.00", "USD", "draft", "CON-2026-CS-001", "RFI-2026-005", 0),
        ("DOC-CO-005", "CO-2026-005", "Emergency Wellpoint Dewatering and Sheet Piling Stabilization",
         "Continuous 24/7 deep wellpoint pumping and installation of 45 lin.m sheet piles following monsoon flooding.",
         "2026-03-22", "118900.00", "USD", "executed", "CON-2026-GEO-004", "RFI-2026-002", 8),
        ("DOC-CO-006", "CO-2026-006", "Large-Format Calacatta Porcelain Tile Concourse Finish",
         "Substitution of basic ceramic tile with 1200x2400mm rectified porcelain slabs in main entrance lobby.",
         "2026-03-25", "95400.00", "USD", "submitted", "CON-2026-CS-001", None, 3),
        ("DOC-CO-007", "CO-2026-007", "Rooftop Cooling Tower Low-Profile Acoustic Reconfiguration",
         "Modification of cooling tower mounting steelwork and installation of low-noise discharge attenuators.",
         "2026-03-28", "134800.00", "USD", "approved", "CON-2026-MEP-002", None, 7),
        ("DOC-CO-008", "CO-2026-008", "Two-Hour Fire Wrap Insulation on Emergency Smoke Exhaust Ducts",
         "Application of certified high-temperature ceramic fire blanket insulation on vertical smoke exhaust riser shafts.",
         "2026-04-02", "76500.00", "USD", "submitted", "CON-2026-MEP-002", "RFI-2026-005", 5),
        ("DOC-CO-009", "CO-2026-009", "Carbon Fiber (CFRP) Strengthening at Level 02 Transfer Girders",
         "Installation of carbon fiber reinforced polymer laminate strips to compensate for revised MEP core penetrations.",
         "2026-04-05", "52300.00", "USD", "draft", "CON-2026-CS-001", "RFI-2026-001", 4),
        ("DOC-CO-010", "CO-2026-010", "Scope Reduction Credit for Omission of Perimeter Security Fencing",
         "Deductive change order for deleting 320 lin.m of galvanized steel security fencing from contractor scope.",
         "2026-04-08", "-48000.00", "USD", "approved", "CON-2026-CS-001", None, 0),
    ]

    result = []
    for doc_id, co_num, title, desc, issue_dt, amount_str, curr, status, contract_ref, rfi_ref, days in cases_meta:
        text_lines = [
            "CHANGE ORDER",
            f"Change Order Number: {co_num}",
            f"Title: {title}",
            f"Description: {desc}",
            f"Issue Date: {issue_dt}",
            f"Amount: {curr} {amount_str}",
            f"Status: {status}",
            f"Schedule Impact: {days} calendar days",
            f"Contract Reference: {contract_ref}",
        ]
        if rfi_ref:
            text_lines.append(f"Referenced RFI: {rfi_ref}")

        doc_refs = [
            {
                "value": {"kind": "contract", "reference": contract_ref},
                "confidence": 0.96,
                "source_page": 1,
                "source_text_snippet": f"Contract Reference: {contract_ref}",
                "missing": False,
            }
        ]
        entities = [
            {"kind": "change_order", "reference": co_num},
            {"kind": "contract", "reference": contract_ref},
        ]
        if rfi_ref:
            doc_refs.append({
                "value": {"kind": "rfi", "reference": rfi_ref},
                "confidence": 0.95,
                "source_page": 1,
                "source_text_snippet": f"Referenced RFI: {rfi_ref}",
                "missing": False,
            })
            entities.append({"kind": "rfi", "reference": rfi_ref})

        result.append({
            "id": doc_id,
            "title": f"Change Order {co_num} - {title}",
            "category": "change_order",
            "input": {
                "filename": f"{co_num}_{status}.pdf",
                "document_type_hint": "change_order",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 3,
                    "author": "Change Control Board",
                },
                "extracted_text": "\n".join(text_lines),
            },
            "expected_output": {
                "classification": {
                    "document_type": "change_order",
                    "confidence": 0.99,
                    "reasoning": f"Formal change order with agreed financial consideration of {curr} {amount_str} and schedule adjustments.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "co_number": {
                        "value": co_num,
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": f"Change Order Number: {co_num}",
                        "missing": False,
                    },
                    "title": {
                        "value": title,
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": f"Title: {title}",
                        "missing": False,
                    },
                    "description": {
                        "value": desc,
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": f"Description: {desc}",
                        "missing": False,
                    },
                    "issue_date": {
                        "value": issue_dt,
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": f"Issue Date: {issue_dt}",
                        "missing": False,
                    },
                    "amount": {
                        "value": {"amount": amount_str, "currency": curr},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": f"Amount: {curr} {amount_str}",
                        "missing": False,
                    },
                    "status": {
                        "value": status,
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": f"Status: {status}",
                        "missing": False,
                    },
                    "document_references": doc_refs,
                },
                "entities": entities,
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "change_order",
                "required_fields_present": ["co_number", "title", "description", "amount", "status"],
                "value_assertions": {
                    "co_number": co_num,
                    "amount.amount": amount_str,
                    "status": status,
                },
            },
        })
    return result

