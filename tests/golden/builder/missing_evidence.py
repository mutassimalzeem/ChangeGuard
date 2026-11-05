"""Missing evidence golden test cases definition (5 cases)."""

def get_missing_evidence_cases():
    return [
        {
            "id": "MISS-001",
            "title": "Rock Excavation Change Order Lacking Borehole Logs & Cross Sections",
            "category": "missing_evidence",
            "input": {
                "document_id": "co-rock-unsubstantiated",
                "filename": "CO-2026-ROCK-01_Claim.pdf",
                "document_type": "change_order",
                "extracted_fields": {
                    "co_number": {"value": "CO-2026-ROCK-01", "missing": False},
                    "title": {"value": "Extra Hard Rock Excavation at Core B", "missing": False},
                    "description": {"value": "Claim for 1,200m3 unexpected igneous basalt requiring continuous hydraulic breakers.", "missing": False},
                    "amount": {"value": {"amount": "85000.00", "currency": "USD"}, "missing": False},
                    "status": {"value": "submitted", "missing": False},
                    "document_references": [],  # Missing survey drawing and geotechnical borehole references!
                },
                "required_supporting_documents": [
                    "Geotechnical Borehole Log GT-BOR",
                    "Licensed Surveyor Pre/Post Volume Cross-Sections",
                    "Inspector Daily Sign-Off Verification",
                ],
            },
            "expected_output": {
                "risk_detected": True,
                "risk_type": "missing_required_evidence",
                "severity": "high",
                "status": "insufficient_evidence",
                "missing_facts": ["document_references", "geotechnical_baseline", "survey_cross_sections"],
                "refusal_behavior": {
                    "refuse_approval": True,
                    "refusal_reason": "Change order claim exceeds $50,000 threshold and lacks required geotechnical survey cross-sections.",
                },
                "recommended_action": "Supply the missing facts and their source evidence.",
            },
            "evaluation_criteria": {
                "metric": "deterministic_rule_match",
                "rule_name": "missing_required_evidence",
                "assertions": {
                    "refuse_approval": True,
                    "status": "insufficient_evidence",
                    "missing_evidence_flag": True,
                },
            },
        },
        {
            "id": "MISS-002",
            "title": "Weekend Overtime Acceleration Claim Lacking Signed Timesheets",
            "category": "missing_evidence",
            "input": {
                "document_id": "co-accel-overtime",
                "filename": "CO-2026-ACCEL-02_Overtime.pdf",
                "document_type": "change_order",
                "extracted_fields": {
                    "co_number": {"value": "CO-2026-ACCEL-02", "missing": False},
                    "title": {"value": "Weekend Overtime Shift Acceleration for Slab Handover", "missing": False},
                    "description": {"value": "240 journeyman carpenter hours performed over two weekends to achieve milestone.", "missing": False},
                    "amount": {"value": {"amount": "28800.00", "currency": "USD"}, "missing": False},
                    "status": {"value": "submitted", "missing": False},
                    "document_references": [],
                },
                "required_supporting_documents": [
                    "Resident Engineer Overtime Pre-Approval Form",
                    "Security Turnstile Biometric Gate In/Out Logs",
                    "Signed Daily Foreman Timesheets",
                ],
            },
            "expected_output": {
                "risk_detected": True,
                "risk_type": "missing_required_evidence",
                "severity": "medium",
                "status": "insufficient_evidence",
                "missing_facts": ["supervisor_signed_timesheets", "turnstile_gate_logs"],
                "refusal_behavior": {
                    "refuse_approval": True,
                    "refusal_reason": "Claim cannot be audited: daily signed timesheets and biometric gate logs are missing.",
                },
                "recommended_action": "Upload signed timesheets matching claimed operative names and dates.",
            },
            "evaluation_criteria": {
                "metric": "deterministic_rule_match",
                "rule_name": "missing_required_evidence",
                "assertions": {
                    "refuse_approval": True,
                    "status": "insufficient_evidence",
                },
            },
        },
        {
            "id": "MISS-003",
            "title": "Drawing Revision Delay Claim Lacking Formal RFI Submission Receipt",
            "category": "missing_evidence",
            "input": {
                "document_id": "clm-drawing-delay",
                "filename": "CLM-2026-009_DesignDelay.pdf",
                "document_type": "change_order",
                "extracted_fields": {
                    "co_number": {"value": "CLM-2026-009", "missing": False},
                    "title": {"value": "Time Extension Claim for Late Architectural Detailing", "missing": False},
                    "description": {"value": "Claiming 14 calendar days critical path delay due to late issuance of revised lobby layout.", "missing": False},
                    "amount": {"value": {"amount": "42000.00", "currency": "USD"}, "missing": False},
                    "status": {"value": "submitted", "missing": False},
                    "document_references": [],
                },
                "required_supporting_documents": [
                    "Formally Transmitted RFI Document",
                    "Document Transmittal Submittal Log",
                    "Primavera P6 Critical Path Delay Fragnet",
                ],
            },
            "expected_output": {
                "risk_detected": True,
                "risk_type": "missing_required_evidence",
                "severity": "high",
                "status": "insufficient_evidence",
                "missing_facts": ["rfi_reference", "schedule_fragnet"],
                "refusal_behavior": {
                    "refuse_approval": True,
                    "refusal_reason": "Time extension claim rejected: no logged RFI or contemporaneous schedule fragnet cited.",
                },
                "recommended_action": "Supply the missing facts and their source evidence.",
            },
            "evaluation_criteria": {
                "metric": "deterministic_rule_match",
                "rule_name": "missing_required_evidence",
                "assertions": {
                    "refuse_approval": True,
                    "status": "insufficient_evidence",
                },
            },
        },
        {
            "id": "MISS-004",
            "title": "Expedited Air Freight Surcharge Lacking Waybill and Customs Proof",
            "category": "missing_evidence",
            "input": {
                "document_id": "co-freight-claim",
                "filename": "CO-2026-FRT-01_ExpeditedChiller.pdf",
                "document_type": "change_order",
                "extracted_fields": {
                    "co_number": {"value": "CO-2026-FRT-01", "missing": False},
                    "title": {"value": "Emergency Air Freight for Chiller Replacement Rotor", "missing": False},
                    "description": {"value": "Air freight from Munich factory to prevent commissioning delay.", "missing": False},
                    "amount": {"value": {"amount": "38500.00", "currency": "USD"}, "missing": False},
                    "status": {"value": "submitted", "missing": False},
                    "document_references": [],
                },
                "required_supporting_documents": [
                    "Air Waybill (AWB) Bill of Lading",
                    "Airport Customs Duty & Clearance Receipt",
                    "Client Prior Written Expedited Delivery Authorization",
                ],
            },
            "expected_output": {
                "risk_detected": True,
                "risk_type": "missing_required_evidence",
                "severity": "medium",
                "status": "insufficient_evidence",
                "missing_facts": ["air_waybill_number", "commercial_invoice"],
                "refusal_behavior": {
                    "refuse_approval": True,
                    "refusal_reason": "Freight premium claim requires original airway bill and airline carrier payment receipt.",
                },
                "recommended_action": "Upload certified freight carrier waybill and port clearance voucher.",
            },
            "evaluation_criteria": {
                "metric": "deterministic_rule_match",
                "rule_name": "missing_required_evidence",
                "assertions": {
                    "refuse_approval": True,
                    "status": "insufficient_evidence",
                },
            },
        },
        {
            "id": "MISS-005",
            "title": "Thermal Cracking Repair Claim Lacking Batch Tickets & Curing Logs",
            "category": "missing_evidence",
            "input": {
                "document_id": "co-crack-repair",
                "filename": "CO-2026-CRK-01_EpoxyInjection.pdf",
                "document_type": "change_order",
                "extracted_fields": {
                    "co_number": {"value": "CO-2026-CRK-01", "missing": False},
                    "title": {"value": "Epoxy Resin Injection for Thermal Cracking in Raft Pour 3", "missing": False},
                    "description": {"value": "Pressure injection of low-viscosity structural epoxy along 45m of surface cracks.", "missing": False},
                    "amount": {"value": {"amount": "19400.00", "currency": "USD"}, "missing": False},
                    "status": {"value": "submitted", "missing": False},
                    "document_references": [],
                },
                "required_supporting_documents": [
                    "Concrete Batch Plant Delivery Tickets",
                    "7-Day Thermocouple Core Temperature Differential Logs",
                    "Post-Crack Core Compressive Strength Test Results",
                ],
            },
            "expected_output": {
                "risk_detected": True,
                "risk_type": "missing_required_evidence",
                "severity": "medium",
                "status": "insufficient_evidence",
                "missing_facts": ["batch_tickets", "thermocouple_temperature_logs"],
                "refusal_behavior": {
                    "refuse_approval": True,
                    "refusal_reason": "Thermal cracking defect liability cannot be determined without contemporaneous temperature differential records.",
                },
                "recommended_action": "Provide 7-day temperature curing logs and supplier batch certificates.",
            },
            "evaluation_criteria": {
                "metric": "deterministic_rule_match",
                "rule_name": "missing_required_evidence",
                "assertions": {
                    "refuse_approval": True,
                    "status": "insufficient_evidence",
                },
            },
        },
    ]

