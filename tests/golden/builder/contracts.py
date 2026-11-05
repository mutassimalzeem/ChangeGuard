"""Contract golden test cases definition."""

def get_contract_cases():
    return [
        {
            "id": "DOC-CON-001",
            "title": "FIDIC Red Book Subcontract - Core & Shell Concrete Package",
            "category": "contract",
            "input": {
                "filename": "CON-2026-CS-001_Executed_Agreement.pdf",
                "document_type_hint": "contract",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 14,
                    "author": "Apex Legal & Commercial",
                },
                "extracted_text": (
                    "SUBCONTRACT AGREEMENT\n"
                    "Contract Reference: CON-2026-CS-001\n"
                    "Title: Subcontract Agreement for Core & Shell Reinforced Concrete Structure\n"
                    "Project: Apex Horizon Commercial Center, Zone 1\n"
                    "Employer: Apex Real Estate Ventures Ltd\n"
                    "Contractor: Horizon Structural Engineering LLC\n"
                    "Effective Date: 2026-01-15\n"
                    "Expiry Date: 2027-06-30\n"
                    "Contract Value: USD 4850000.00 (Four Million Eight Hundred Fifty Thousand US Dollars)\n"
                    "Contract Form: FIDIC Conditions of Subcontract for Construction (First Edition 2011)\n"
                    "Status: signed\n\n"
                    "1. SCOPE OF WORKS\n"
                    "The Contractor shall execute all substructure and superstructure reinforced concrete works "
                    "in accordance with drawing series DR-S-100 and Bill of Quantities BOQ-2026-CS-01.\n\n"
                    "2. PAYMENT TERMS & REMEASUREMENT\n"
                    "Interim valuations shall be submitted monthly. Retainage of 5% shall apply.\n"
                    "Referenced RFI: RFI-2026-001.\n\n"
                    "IN WITNESS WHEREOF the parties have executed this Agreement as of 15 January 2026.\n"
                    "Signed for Employer: Marcus Vance, Managing Director\n"
                    "Signed for Contractor: David K. Chen, Operations Director"
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "contract",
                    "confidence": 0.98,
                    "reasoning": "Standard construction subcontract agreement with executed clauses, parties, scope, and contract sum.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "reference": {
                        "value": "CON-2026-CS-001",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contract Reference: CON-2026-CS-001",
                        "missing": False,
                    },
                    "title": {
                        "value": "Subcontract Agreement for Core & Shell Reinforced Concrete Structure",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Title: Subcontract Agreement for Core & Shell Reinforced Concrete Structure",
                        "missing": False,
                    },
                    "employer": {
                        "value": "Apex Real Estate Ventures Ltd",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Employer: Apex Real Estate Ventures Ltd",
                        "missing": False,
                    },
                    "contractor": {
                        "value": "Horizon Structural Engineering LLC",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contractor: Horizon Structural Engineering LLC",
                        "missing": False,
                    },
                    "effective_date": {
                        "value": "2026-01-15",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Effective Date: 2026-01-15",
                        "missing": False,
                    },
                    "expiry_date": {
                        "value": "2027-06-30",
                        "confidence": 0.95,
                        "source_page": 1,
                        "source_text_snippet": "Expiry Date: 2027-06-30",
                        "missing": False,
                    },
                    "contract_value": {
                        "value": {"amount": "4850000.00", "currency": "USD"},
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Contract Value: USD 4850000.00",
                        "missing": False,
                    },
                    "status": {
                        "value": "signed",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "Status: signed",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "boq", "reference": "BOQ-2026-CS-01"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Bill of Quantities BOQ-2026-CS-01",
                            "missing": False,
                        },
                        {
                            "value": {"kind": "rfi", "reference": "RFI-2026-001"},
                            "confidence": 0.94,
                            "source_page": 1,
                            "source_text_snippet": "Referenced RFI: RFI-2026-001",
                            "missing": False,
                        },
                    ],
                },
                "entities": [
                    {"kind": "contract", "reference": "CON-2026-CS-001"},
                    {"kind": "boq", "reference": "BOQ-2026-CS-01"},
                    {"kind": "rfi", "reference": "RFI-2026-001"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "contract",
                "required_fields_present": ["reference", "title", "employer", "contractor", "contract_value"],
                "value_assertions": {
                    "reference": "CON-2026-CS-001",
                    "contract_value.amount": "4850000.00",
                    "contract_value.currency": "USD",
                    "status": "signed",
                },
                "evidence_grounding": {
                    "require_source_snippets": True,
                    "require_source_page": True,
                },
            },
        },
        {
            "id": "DOC-CON-002",
            "title": "AIA A401 Standard Subcontract - Mechanical & Chilled Water Plant",
            "category": "contract",
            "input": {
                "filename": "CON-2026-MEP-002_Executed.pdf",
                "document_type_hint": "contract",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 22,
                    "author": "Metro Transit Authority",
                },
                "extracted_text": (
                    "AIA DOCUMENT A401-2017\n"
                    "Standard Form of Agreement Between Contractor and Subcontractor\n"
                    "Contract Reference: CON-2026-MEP-002\n"
                    "Title: Subcontract Agreement for Central Chilled Water Plant and Primary MEP Distribution\n"
                    "Employer: Metro Transit Infrastructure Authority\n"
                    "Contractor: Pioneer Thermal Dynamics Corp\n"
                    "Effective Date: 2026-02-01\n"
                    "Expiry Date: 2026-12-31\n"
                    "Contract Value: USD 2420000.00\n"
                    "Status: signed\n\n"
                    "ARTICLE 1 THE SUBCONTRACT DOCUMENTS\n"
                    "The Subcontract Documents consist of this Agreement and BOQ Reference BOQ-2026-MEP-02.\n"
                    "Executed as of February 1, 2026."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "contract",
                    "confidence": 0.97,
                    "reasoning": "AIA A401 Standard Subcontract for MEP works with explicit consideration and parties.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "reference": {
                        "value": "CON-2026-MEP-002",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contract Reference: CON-2026-MEP-002",
                        "missing": False,
                    },
                    "title": {
                        "value": "Subcontract Agreement for Central Chilled Water Plant and Primary MEP Distribution",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Title: Subcontract Agreement for Central Chilled Water Plant and Primary MEP Distribution",
                        "missing": False,
                    },
                    "employer": {
                        "value": "Metro Transit Infrastructure Authority",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Employer: Metro Transit Infrastructure Authority",
                        "missing": False,
                    },
                    "contractor": {
                        "value": "Pioneer Thermal Dynamics Corp",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contractor: Pioneer Thermal Dynamics Corp",
                        "missing": False,
                    },
                    "effective_date": {
                        "value": "2026-02-01",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Effective Date: 2026-02-01",
                        "missing": False,
                    },
                    "expiry_date": {
                        "value": "2026-12-31",
                        "confidence": 0.95,
                        "source_page": 1,
                        "source_text_snippet": "Expiry Date: 2026-12-31",
                        "missing": False,
                    },
                    "contract_value": {
                        "value": {"amount": "2420000.00", "currency": "USD"},
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Contract Value: USD 2420000.00",
                        "missing": False,
                    },
                    "status": {
                        "value": "signed",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "Status: signed",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "boq", "reference": "BOQ-2026-MEP-02"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "BOQ Reference BOQ-2026-MEP-02",
                            "missing": False,
                        },
                    ],
                },
                "entities": [
                    {"kind": "contract", "reference": "CON-2026-MEP-002"},
                    {"kind": "boq", "reference": "BOQ-2026-MEP-02"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "contract",
                "required_fields_present": ["reference", "title", "employer", "contractor", "contract_value"],
                "value_assertions": {
                    "reference": "CON-2026-MEP-002",
                    "contract_value.amount": "2420000.00",
                    "status": "signed",
                },
                "evidence_grounding": {"require_source_snippets": True, "require_source_page": True},
            },
        },
        {
            "id": "DOC-CON-003",
            "title": "NEC4 Engineering and Construction Subcontract - Structural Steel Frame",
            "category": "contract",
            "input": {
                "filename": "CON-2026-STL-003_Executed.pdf",
                "document_type_hint": "contract",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 18,
                    "author": "Highline Commercial",
                },
                "extracted_text": (
                    "NEC4 ENGINEERING AND CONSTRUCTION SUBCONTRACT\n"
                    "Subcontract Reference: CON-2026-STL-003\n"
                    "Title: Engineering and Construction Subcontract for Structural Steel Frame & Composite Decking\n"
                    "Employer: Highline Tower Development Corp\n"
                    "Contractor: Titan Metalwork Specialists\n"
                    "Effective Date: 2026-03-01\n"
                    "Expiry Date: 2026-11-15\n"
                    "Contract Value: USD 3150000.00\n"
                    "Status: signed\n\n"
                    "Subcontract Data Part One:\n"
                    "Priced contract with bill of quantities (Option B).\n"
                    "Subcontractor shall supply and erect all steel elements referenced in BOQ-2026-STL-03."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "contract",
                    "confidence": 0.98,
                    "reasoning": "NEC4 ECS priced subcontract agreement with bill of quantities option B.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "reference": {
                        "value": "CON-2026-STL-003",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Subcontract Reference: CON-2026-STL-003",
                        "missing": False,
                    },
                    "title": {
                        "value": "Engineering and Construction Subcontract for Structural Steel Frame & Composite Decking",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Title: Engineering and Construction Subcontract for Structural Steel Frame & Composite Decking",
                        "missing": False,
                    },
                    "employer": {
                        "value": "Highline Tower Development Corp",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Employer: Highline Tower Development Corp",
                        "missing": False,
                    },
                    "contractor": {
                        "value": "Titan Metalwork Specialists",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contractor: Titan Metalwork Specialists",
                        "missing": False,
                    },
                    "effective_date": {
                        "value": "2026-03-01",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Effective Date: 2026-03-01",
                        "missing": False,
                    },
                    "expiry_date": {
                        "value": "2026-11-15",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Expiry Date: 2026-11-15",
                        "missing": False,
                    },
                    "contract_value": {
                        "value": {"amount": "3150000.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contract Value: USD 3150000.00",
                        "missing": False,
                    },
                    "status": {
                        "value": "signed",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "Status: signed",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "boq", "reference": "BOQ-2026-STL-03"},
                            "confidence": 0.96,
                            "source_page": 1,
                            "source_text_snippet": "referenced in BOQ-2026-STL-03",
                            "missing": False,
                        },
                    ],
                },
                "entities": [
                    {"kind": "contract", "reference": "CON-2026-STL-003"},
                    {"kind": "boq", "reference": "BOQ-2026-STL-03"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "contract",
                "required_fields_present": ["reference", "title", "employer", "contractor", "contract_value"],
                "value_assertions": {
                    "reference": "CON-2026-STL-003",
                    "contract_value.amount": "3150000.00",
                },
                "evidence_grounding": {"require_source_snippets": True, "require_source_page": True},
            },
        },
        {
            "id": "DOC-CON-004",
            "title": "Subcontract for Deep Foundations, Shoring & Dewatering",
            "category": "contract",
            "input": {
                "filename": "CON-2026-GEO-004_Signed.pdf",
                "document_type_hint": "contract",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 16,
                    "author": "Waterfront Development PM",
                },
                "extracted_text": (
                    "FOUNDATION WORKS SUBCONTRACT\n"
                    "Contract Reference: CON-2026-GEO-004\n"
                    "Title: Specialized Subcontract for Secant Piling, Foundation Bored Piles and Dewatering\n"
                    "Employer: Waterfront Logistics Park LLC\n"
                    "Contractor: GeoFoundation Engineering Ltd\n"
                    "Effective Date: 2026-01-10\n"
                    "Expiry Date: 2026-08-30\n"
                    "Contract Value: USD 1875000.00\n"
                    "Status: active\n\n"
                    "Works include installation of bored cast-in-place piles per geotechnical specification GT-BOR-01 "
                    "and Bill of Quantities BOQ-2026-GEO-04."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "contract",
                    "confidence": 0.98,
                    "reasoning": "Subcontract agreement for geotechnical and deep foundation works with clear active status.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "reference": {
                        "value": "CON-2026-GEO-004",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contract Reference: CON-2026-GEO-004",
                        "missing": False,
                    },
                    "title": {
                        "value": "Specialized Subcontract for Secant Piling, Foundation Bored Piles and Dewatering",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Title: Specialized Subcontract for Secant Piling, Foundation Bored Piles and Dewatering",
                        "missing": False,
                    },
                    "employer": {
                        "value": "Waterfront Logistics Park LLC",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Employer: Waterfront Logistics Park LLC",
                        "missing": False,
                    },
                    "contractor": {
                        "value": "GeoFoundation Engineering Ltd",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contractor: GeoFoundation Engineering Ltd",
                        "missing": False,
                    },
                    "effective_date": {
                        "value": "2026-01-10",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Effective Date: 2026-01-10",
                        "missing": False,
                    },
                    "expiry_date": {
                        "value": "2026-08-30",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Expiry Date: 2026-08-30",
                        "missing": False,
                    },
                    "contract_value": {
                        "value": {"amount": "1875000.00", "currency": "USD"},
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Contract Value: USD 1875000.00",
                        "missing": False,
                    },
                    "status": {
                        "value": "active",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "Status: active",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "boq", "reference": "BOQ-2026-GEO-04"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "Bill of Quantities BOQ-2026-GEO-04",
                            "missing": False,
                        },
                    ],
                },
                "entities": [
                    {"kind": "contract", "reference": "CON-2026-GEO-004"},
                    {"kind": "boq", "reference": "BOQ-2026-GEO-04"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "contract",
                "required_fields_present": ["reference", "title", "employer", "contractor", "contract_value"],
                "value_assertions": {
                    "reference": "CON-2026-GEO-004",
                    "contract_value.amount": "1875000.00",
                    "status": "active",
                },
                "evidence_grounding": {"require_source_snippets": True, "require_source_page": True},
            },
        },
        {
            "id": "DOC-CON-005",
            "title": "Subcontract for Architectural Facade & Unitized Curtain Wall Package",
            "category": "contract",
            "input": {
                "filename": "CON-2026-FAC-005_Execution_Copy.pdf",
                "document_type_hint": "contract",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 26,
                    "author": "Zenith Commercial Legal",
                },
                "extracted_text": (
                    "LUMP SUM FACADE SUBCONTRACT\n"
                    "Contract Reference: CON-2026-FAC-005\n"
                    "Title: Subcontract Agreement for External Building Envelope & Unitized Glazing System\n"
                    "Employer: Zenith Commercial Towers Ltd\n"
                    "Contractor: Alumitech Glazing Systems Inc\n"
                    "Effective Date: 2026-04-01\n"
                    "Expiry Date: 2027-08-15\n"
                    "Contract Value: USD 5600000.00\n"
                    "Status: signed\n\n"
                    "1.1 The Contractor shall engineer, test, fabricate and install the unitized curtain wall "
                    "in accordance with BOQ-2026-FAC-05."
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "contract",
                    "confidence": 0.98,
                    "reasoning": "Lump sum building envelope subcontract with signed execution terms.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "reference": {
                        "value": "CON-2026-FAC-005",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contract Reference: CON-2026-FAC-005",
                        "missing": False,
                    },
                    "title": {
                        "value": "Subcontract Agreement for External Building Envelope & Unitized Glazing System",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Title: Subcontract Agreement for External Building Envelope & Unitized Glazing System",
                        "missing": False,
                    },
                    "employer": {
                        "value": "Zenith Commercial Towers Ltd",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Employer: Zenith Commercial Towers Ltd",
                        "missing": False,
                    },
                    "contractor": {
                        "value": "Alumitech Glazing Systems Inc",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contractor: Alumitech Glazing Systems Inc",
                        "missing": False,
                    },
                    "effective_date": {
                        "value": "2026-04-01",
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": "Effective Date: 2026-04-01",
                        "missing": False,
                    },
                    "expiry_date": {
                        "value": "2027-08-15",
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": "Expiry Date: 2027-08-15",
                        "missing": False,
                    },
                    "contract_value": {
                        "value": {"amount": "5600000.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Contract Value: USD 5600000.00",
                        "missing": False,
                    },
                    "status": {
                        "value": "signed",
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": "Status: signed",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "boq", "reference": "BOQ-2026-FAC-05"},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": "BOQ-2026-FAC-05",
                            "missing": False,
                        },
                    ],
                },
                "entities": [
                    {"kind": "contract", "reference": "CON-2026-FAC-005"},
                    {"kind": "boq", "reference": "BOQ-2026-FAC-05"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "contract",
                "required_fields_present": ["reference", "title", "employer", "contractor", "contract_value"],
                "value_assertions": {
                    "reference": "CON-2026-FAC-005",
                    "contract_value.amount": "5600000.00",
                    "contract_value.currency": "USD",
                },
                "evidence_grounding": {"require_source_snippets": True, "require_source_page": True},
            },
        },
    ]

