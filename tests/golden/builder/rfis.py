"""RFI golden test cases definition."""

def get_rfi_cases():
    return [
        {
            "id": "DOC-RFI-001",
            "title": "Clash between Chilled Water Riser and Transfer Girder TG-04",
            "category": "rfi",
            "input": {
                "filename": "RFI-2026-001_MEP_Girder_Clash.pdf",
                "document_type_hint": "rfi",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 2,
                    "author": "Horizon Engineering Site Team",
                },
                "extracted_text": (
                    "REQUEST FOR INFORMATION (RFI)\n"
                    "RFI Number: RFI-2026-001\n"
                    "Subject: Clash between 600mm Chilled Water Riser and Transfer Girder TG-04 at Level 02\n"
                    "Contract Reference: CON-2026-CS-001\n"
                    "Drawing Reference: DR-S-201, DR-M-402\n"
                    "Raised Date: 2026-02-10\n"
                    "Due Date: 2026-02-17\n"
                    "Status: answered\n\n"
                    "QUESTION:\n"
                    "Coordinated BIM model review reveals that the 600mm diameter chilled water supply/return risers "
                    "shown on DR-M-402 physically intersect post-tensioned transfer girder TG-04 (Gridline 4-D) shown on DR-S-201. "
                    "Core drilling through girder TG-04 is prohibited due to high post-tensioning tendon congestion. "
                    "Please provide engineering direction on riser diversion or structural sleeve allowance.\n\n"
                    "RESPONSE:\n"
                    "Response Date: 2026-02-14\n"
                    "Confirmed: Do not sleeve or drill transfer girder TG-04. Offset chilled water risers 1200mm westward into "
                    "adjacent service riser shaft S-02 per structural sketch SK-S-201-A. "
                    "Mechanical subcontractor to submit revision for additional 90-degree elbows and pipe length."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "rfi",
                    "confidence": 0.99,
                    "reasoning": "Standard Request for Information containing technical question, drawing references, and answered response.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "rfi_number": {
                        "value": "RFI-2026-001",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "RFI Number: RFI-2026-001",
                        "missing": False,
                    },
                    "subject": {
                        "value": "Clash between 600mm Chilled Water Riser and Transfer Girder TG-04 at Level 02",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Subject: Clash between 600mm Chilled Water Riser and Transfer Girder TG-04 at Level 02",
                        "missing": False,
                    },
                    "question": {
                        "value": (
                            "Coordinated BIM model review reveals that the 600mm diameter chilled water supply/return risers "
                            "shown on DR-M-402 physically intersect post-tensioned transfer girder TG-04 (Gridline 4-D) shown on DR-S-201. "
                            "Core drilling through girder TG-04 is prohibited due to high post-tensioning tendon congestion. "
                            "Please provide engineering direction on riser diversion or structural sleeve allowance."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Coordinated BIM model review reveals that the 600mm diameter chilled water supply/return risers",
                        "missing": False,
                    },
                    "response": {
                        "value": (
                            "Confirmed: Do not sleeve or drill transfer girder TG-04. Offset chilled water risers 1200mm westward into "
                            "adjacent service riser shaft S-02 per structural sketch SK-S-201-A. "
                            "Mechanical subcontractor to submit revision for additional 90-degree elbows and pipe length."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Confirmed: Do not sleeve or drill transfer girder TG-04. Offset chilled water risers 1200mm westward",
                        "missing": False,
                    },
                    "raised_date": {
                        "value": "2026-02-10",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Raised Date: 2026-02-10",
                        "missing": False,
                    },
                    "due_date": {
                        "value": "2026-02-17",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Due Date: 2026-02-17",
                        "missing": False,
                    },
                    "status": {
                        "value": "answered",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Status: answered",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-CS-001"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-CS-001",
                            "missing": False,
                        },
                        {
                            "value": {"kind": "drawing", "reference": "DR-S-201"},
                            "confidence": 0.94,
                            "source_page": 1,
                            "source_text_snippet": "DR-S-201",
                            "missing": False,
                        },
                    ],
                },
                "entities": [
                    {"kind": "rfi", "reference": "RFI-2026-001"},
                    {"kind": "contract", "reference": "CON-2026-CS-001"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "rfi",
                "required_fields_present": ["rfi_number", "subject", "question"],
                "value_assertions": {
                    "rfi_number": "RFI-2026-001",
                    "status": "answered",
                    "raised_date": "2026-02-10",
                },
            },
        },
        {
            "id": "DOC-RFI-002",
            "title": "Unforeseen Groundwater Table Elevation at Basement B3",
            "category": "rfi",
            "input": {
                "filename": "RFI-2026-002_Groundwater_Table.pdf",
                "document_type_hint": "rfi",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 2,
                    "author": "GeoFoundation Site Engineering",
                },
                "extracted_text": (
                    "REQUEST FOR INFORMATION\n"
                    "RFI Number: RFI-2026-002\n"
                    "Subject: Unforeseen High Water Table Elevation during Basement Level 3 Excavation\n"
                    "Contract Reference: CON-2026-GEO-004\n"
                    "Raised Date: 2026-02-18\n"
                    "Due Date: 2026-02-25\n"
                    "Status: open\n\n"
                    "QUESTION:\n"
                    "During final bulk excavation to formation level -11.50m ECD for Basement Level 3, continuous water seepage "
                    "was encountered at elevation -9.80m ECD, which is 1.70m above the historical water table noted in Geotechnical Report GT-BOR-01. "
                    "Current 4-inch sump pumps are overwhelmed. We request immediate authorization for continuous perimeter deep well dewatering."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "rfi",
                    "confidence": 0.99,
                    "reasoning": "RFI detailing geotechnical groundwater condition without final response yet (status open).",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "rfi_number": {
                        "value": "RFI-2026-002",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "RFI Number: RFI-2026-002",
                        "missing": False,
                    },
                    "subject": {
                        "value": "Unforeseen High Water Table Elevation during Basement Level 3 Excavation",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Subject: Unforeseen High Water Table Elevation during Basement Level 3 Excavation",
                        "missing": False,
                    },
                    "question": {
                        "value": (
                            "During final bulk excavation to formation level -11.50m ECD for Basement Level 3, continuous water seepage "
                            "was encountered at elevation -9.80m ECD, which is 1.70m above the historical water table noted in Geotechnical Report GT-BOR-01. "
                            "Current 4-inch sump pumps are overwhelmed. We request immediate authorization for continuous perimeter deep well dewatering."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "During final bulk excavation to formation level -11.50m ECD for Basement Level 3",
                        "missing": False,
                    },
                    "response": {
                        "value": None,
                        "confidence": 0.0,
                        "source_page": None,
                        "source_text_snippet": None,
                        "missing": True,
                    },
                    "raised_date": {
                        "value": "2026-02-18",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Raised Date: 2026-02-18",
                        "missing": False,
                    },
                    "due_date": {
                        "value": "2026-02-25",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Due Date: 2026-02-25",
                        "missing": False,
                    },
                    "status": {
                        "value": "open",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Status: open",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-GEO-004"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-GEO-004",
                            "missing": False,
                        }
                    ],
                },
                "entities": [
                    {"kind": "rfi", "reference": "RFI-2026-002"},
                    {"kind": "contract", "reference": "CON-2026-GEO-004"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "rfi",
                "value_assertions": {
                    "rfi_number": "RFI-2026-002",
                    "status": "open",
                },
            },
        },
        {
            "id": "DOC-RFI-003",
            "title": "Curtain Wall Seismic Joint Displacement Clearance",
            "category": "rfi",
            "input": {
                "filename": "RFI-2026-003_CurtainWall_Seismic.pdf",
                "document_type_hint": "rfi",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 2,
                    "author": "Alumitech Technical Office",
                },
                "extracted_text": (
                    "TECHNICAL REQUEST FOR INFORMATION\n"
                    "RFI Number: RFI-2026-003\n"
                    "Subject: Curtain Wall Seismic Joint Displacement Clearance at Tower Expansion Joint\n"
                    "Contract Reference: CON-2026-FAC-005\n"
                    "Raised Date: 2026-03-05\n"
                    "Due Date: 2026-03-12\n"
                    "Status: answered\n\n"
                    "QUESTION:\n"
                    "Architectural detail 4/A-501 specifies a 50mm expansion joint between the Podium and Main Tower. "
                    "However, Structural General Notes S-001 indicate maximum inter-story drift under Seismic Design Category D of 75mm. "
                    "Please confirm whether the facade expansion joint width must be enlarged to 85mm to prevent glass shattering.\n\n"
                    "RESPONSE:\n"
                    "Response Date: 2026-03-09\n"
                    "Approved: Increase expansion joint width to 90mm at all tower interface lines. "
                    "Contractor to submit revised silicone bellows extrusion profile."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "rfi",
                    "confidence": 0.99,
                    "reasoning": "RFI resolving discrepancy between architectural joint detail and structural seismic drift criteria.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "rfi_number": {
                        "value": "RFI-2026-003",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "RFI Number: RFI-2026-003",
                        "missing": False,
                    },
                    "subject": {
                        "value": "Curtain Wall Seismic Joint Displacement Clearance at Tower Expansion Joint",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Subject: Curtain Wall Seismic Joint Displacement Clearance at Tower Expansion Joint",
                        "missing": False,
                    },
                    "question": {
                        "value": (
                            "Architectural detail 4/A-501 specifies a 50mm expansion joint between the Podium and Main Tower. "
                            "However, Structural General Notes S-001 indicate maximum inter-story drift under Seismic Design Category D of 75mm. "
                            "Please confirm whether the facade expansion joint width must be enlarged to 85mm to prevent glass shattering."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Architectural detail 4/A-501 specifies a 50mm expansion joint between the Podium and Main Tower",
                        "missing": False,
                    },
                    "response": {
                        "value": (
                            "Approved: Increase expansion joint width to 90mm at all tower interface lines. "
                            "Contractor to submit revised silicone bellows extrusion profile."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Approved: Increase expansion joint width to 90mm at all tower interface lines.",
                        "missing": False,
                    },
                    "raised_date": {
                        "value": "2026-03-05",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Raised Date: 2026-03-05",
                        "missing": False,
                    },
                    "due_date": {
                        "value": "2026-03-12",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Due Date: 2026-03-12",
                        "missing": False,
                    },
                    "status": {
                        "value": "answered",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Status: answered",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-FAC-005"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-FAC-005",
                            "missing": False,
                        }
                    ],
                },
                "entities": [
                    {"kind": "rfi", "reference": "RFI-2026-003"},
                    {"kind": "contract", "reference": "CON-2026-FAC-005"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "rfi",
                "value_assertions": {
                    "rfi_number": "RFI-2026-003",
                    "status": "answered",
                },
            },
        },
        {
            "id": "DOC-RFI-004",
            "title": "Rebar Lap Splice Length in High Moment Plastic Hinge Zone",
            "category": "rfi",
            "input": {
                "filename": "RFI-2026-004_Rebar_Lap_Splice.pdf",
                "document_type_hint": "rfi",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 2,
                    "author": "Titan Engineering Site Team",
                },
                "extracted_text": (
                    "REQUEST FOR INFORMATION\n"
                    "RFI Number: RFI-2026-004\n"
                    "Subject: Clarification on Column Rebar Lap Splice Length in Seismic Critical Region\n"
                    "Contract Reference: CON-2026-CS-001\n"
                    "Raised Date: 2026-03-15\n"
                    "Due Date: 2026-03-22\n"
                    "Status: answered\n\n"
                    "QUESTION:\n"
                    "Drawing S-104 shows lap splices of 32mm vertical rebar located at slab level in Column C-12. "
                    "Per ACI 318 Section 18.7.4.3, lap splices in special moment frames are prohibited within the plastic hinge region "
                    "(within 600mm or d of the joint face). Please confirm if mechanical type-2 couplers must be used instead.\n\n"
                    "RESPONSE:\n"
                    "Response Date: 2026-03-18\n"
                    "Confirmed: Replace all lap splices in Columns C-08 through C-16 at Levels 1-4 with Type 2 seismic mechanical couplers."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "rfi",
                    "confidence": 0.99,
                    "reasoning": "RFI clarifying seismic rebar splice code compliance.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "rfi_number": {
                        "value": "RFI-2026-004",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "RFI Number: RFI-2026-004",
                        "missing": False,
                    },
                    "subject": {
                        "value": "Clarification on Column Rebar Lap Splice Length in Seismic Critical Region",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Subject: Clarification on Column Rebar Lap Splice Length in Seismic Critical Region",
                        "missing": False,
                    },
                    "question": {
                        "value": (
                            "Drawing S-104 shows lap splices of 32mm vertical rebar located at slab level in Column C-12. "
                            "Per ACI 318 Section 18.7.4.3, lap splices in special moment frames are prohibited within the plastic hinge region "
                            "(within 600mm or d of the joint face). Please confirm if mechanical type-2 couplers must be used instead."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Drawing S-104 shows lap splices of 32mm vertical rebar located at slab level in Column C-12",
                        "missing": False,
                    },
                    "response": {
                        "value": "Confirmed: Replace all lap splices in Columns C-08 through C-16 at Levels 1-4 with Type 2 seismic mechanical couplers.",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Confirmed: Replace all lap splices in Columns C-08 through C-16 at Levels 1-4 with Type 2 seismic mechanical couplers.",
                        "missing": False,
                    },
                    "raised_date": {
                        "value": "2026-03-15",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Raised Date: 2026-03-15",
                        "missing": False,
                    },
                    "due_date": {
                        "value": "2026-03-22",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Due Date: 2026-03-22",
                        "missing": False,
                    },
                    "status": {
                        "value": "answered",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Status: answered",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-CS-001"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-CS-001",
                            "missing": False,
                        }
                    ],
                },
                "entities": [
                    {"kind": "rfi", "reference": "RFI-2026-004"},
                    {"kind": "contract", "reference": "CON-2026-CS-001"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "rfi",
                "value_assertions": {
                    "rfi_number": "RFI-2026-004",
                    "status": "answered",
                },
            },
        },
        {
            "id": "DOC-RFI-005",
            "title": "Discontinued UL-Listed Fire Damper Model Substitution",
            "category": "rfi",
            "input": {
                "filename": "RFI-2026-005_Fire_Damper_Model.pdf",
                "document_type_hint": "rfi",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 2,
                    "author": "Pioneer Thermal Field Staff",
                },
                "extracted_text": (
                    "REQUEST FOR INFORMATION\n"
                    "RFI Number: RFI-2026-005\n"
                    "Subject: Proposed Substitution for Discontinued Ruskin FSD-60 Fire/Smoke Dampers\n"
                    "Contract Reference: CON-2026-MEP-002\n"
                    "Raised Date: 2026-03-20\n"
                    "Due Date: 2026-03-27\n"
                    "Status: closed\n\n"
                    "QUESTION:\n"
                    "The specified motorized combination fire/smoke damper model Ruskin FSD-60 is discontinued by manufacturer. "
                    "We propose substituting Greenheck Model FSD-211 which meets identical 1-1/2 hour UL 555 and UL 555S Class II leakage ratings. "
                    "Please confirm acceptability.\n\n"
                    "RESPONSE:\n"
                    "Response Date: 2026-03-24\n"
                    "Accepted as equal. Submit formal material submittal SUB-MEP-088 for resident engineer stamp."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "rfi",
                    "confidence": 0.99,
                    "reasoning": "RFI detailing equipment product substitution with closed resolution.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "rfi_number": {
                        "value": "RFI-2026-005",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "RFI Number: RFI-2026-005",
                        "missing": False,
                    },
                    "subject": {
                        "value": "Proposed Substitution for Discontinued Ruskin FSD-60 Fire/Smoke Dampers",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Subject: Proposed Substitution for Discontinued Ruskin FSD-60 Fire/Smoke Dampers",
                        "missing": False,
                    },
                    "question": {
                        "value": (
                            "The specified motorized combination fire/smoke damper model Ruskin FSD-60 is discontinued by manufacturer. "
                            "We propose substituting Greenheck Model FSD-211 which meets identical 1-1/2 hour UL 555 and UL 555S Class II leakage ratings. "
                            "Please confirm acceptability."
                        ),
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "The specified motorized combination fire/smoke damper model Ruskin FSD-60 is discontinued by manufacturer",
                        "missing": False,
                    },
                    "response": {
                        "value": "Accepted as equal. Submit formal material submittal SUB-MEP-088 for resident engineer stamp.",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Accepted as equal. Submit formal material submittal SUB-MEP-088 for resident engineer stamp.",
                        "missing": False,
                    },
                    "raised_date": {
                        "value": "2026-03-20",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Raised Date: 2026-03-20",
                        "missing": False,
                    },
                    "due_date": {
                        "value": "2026-03-27",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Due Date: 2026-03-27",
                        "missing": False,
                    },
                    "status": {
                        "value": "closed",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Status: closed",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-MEP-002"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-MEP-002",
                            "missing": False,
                        }
                    ],
                },
                "entities": [
                    {"kind": "rfi", "reference": "RFI-2026-005"},
                    {"kind": "contract", "reference": "CON-2026-MEP-002"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "rfi",
                "value_assertions": {
                    "rfi_number": "RFI-2026-005",
                    "status": "closed",
                },
            },
        },
    ]

