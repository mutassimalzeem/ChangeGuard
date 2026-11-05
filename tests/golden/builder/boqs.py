"""BOQ golden test cases definition."""

def get_boq_cases():
    return [
        {
            "id": "DOC-BOQ-001",
            "title": "Substructure & Bulk Earthworks Bill of Quantities",
            "category": "boq",
            "input": {
                "filename": "BOQ-2026-CS-01_Substructure.xlsx",
                "document_type_hint": "boq",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "xlsx",
                    "sheet_count": 3,
                    "author": "Apex Quantity Surveyors",
                },
                "extracted_text": (
                    "BILL OF QUANTITIES: SUBSTRUCTURE AND BULK EARTHWORKS\n"
                    "BOQ Reference: BOQ-2026-CS-01\n"
                    "Contract Reference: CON-2026-CS-001\n"
                    "Currency: USD\n\n"
                    "Item Code | Description | Quantity | Unit | Rate | Total\n"
                    "EX-01 | Bulk site excavation in general soil down to formation level | 14500.00 | m3 | 18.50 | 268250.00\n"
                    "EX-02 | Excavation in hard rock requiring pneumatic breakers | 2200.00 | m3 | 85.00 | 187000.00\n"
                    "ST-01 | Cast-in-place C40/50 sulfate-resisting foundation raft concrete | 3800.00 | m3 | 210.00 | 798000.00\n"
                    "ST-02 | High-yield deformed steel reinforcement bars Grade 500B | 480.00 | t | 1150.00 | 552000.00\n"
                    "WP-01 | Heavy-duty SBS bituminous tanking waterproofing membrane | 4200.00 | m2 | 34.00 | 142800.00\n\n"
                    "Total Bill of Quantities Amount: USD 1948050.00"
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "boq",
                    "confidence": 0.99,
                    "reasoning": "Tabular bill of quantities with item codes, descriptions, units, unit rates, and totals.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "title": {
                        "value": "Substructure and Bulk Earthworks Bill of Quantities",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "BILL OF QUANTITIES: SUBSTRUCTURE AND BULK EARTHWORKS",
                        "missing": False,
                    },
                    "stated_total": {
                        "value": {"amount": "1948050.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Total Bill of Quantities Amount: USD 1948050.00",
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
                    "items": [
                        {
                            "code": {"value": "EX-01", "confidence": 0.97, "source_page": 1, "source_text_snippet": "EX-01 | Bulk site excavation in general soil", "missing": False},
                            "description": {"value": "Bulk site excavation in general soil down to formation level", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Bulk site excavation in general soil down to formation level", "missing": False},
                            "quantity": {"value": {"amount": "14500.00", "unit": "m3"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "14500.00 | m3", "missing": False},
                            "unit_rate": {"value": {"amount": "18.50", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "18.50", "missing": False},
                            "stated_total": {"value": {"amount": "268250.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "268250.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        },
                        {
                            "code": {"value": "EX-02", "confidence": 0.97, "source_page": 1, "source_text_snippet": "EX-02 | Excavation in hard rock", "missing": False},
                            "description": {"value": "Excavation in hard rock requiring pneumatic breakers", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Excavation in hard rock requiring pneumatic breakers", "missing": False},
                            "quantity": {"value": {"amount": "2200.00", "unit": "m3"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "2200.00 | m3", "missing": False},
                            "unit_rate": {"value": {"amount": "85.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "85.00", "missing": False},
                            "stated_total": {"value": {"amount": "187000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "187000.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        },
                        {
                            "code": {"value": "ST-01", "confidence": 0.97, "source_page": 1, "source_text_snippet": "ST-01 | Cast-in-place C40/50 foundation raft", "missing": False},
                            "description": {"value": "Cast-in-place C40/50 sulfate-resisting foundation raft concrete", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Cast-in-place C40/50 sulfate-resisting foundation raft concrete", "missing": False},
                            "quantity": {"value": {"amount": "3800.00", "unit": "m3"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "3800.00 | m3", "missing": False},
                            "unit_rate": {"value": {"amount": "210.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "210.00", "missing": False},
                            "stated_total": {"value": {"amount": "798000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "798000.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        },
                    ],
                },
                "entities": [
                    {"kind": "boq", "reference": "BOQ-2026-CS-01"},
                    {"kind": "contract", "reference": "CON-2026-CS-001"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "boq",
                "required_fields_present": ["title", "stated_total", "items"],
                "item_count_minimum": 3,
                "item_assertions": [
                    {"code": "EX-01", "unit_rate": "18.50", "unit": "m3"},
                    {"code": "ST-01", "unit_rate": "210.00", "unit": "m3"},
                ],
                "evidence_grounding": {"require_source_snippets": True},
            },
        },
        {
            "id": "DOC-BOQ-002",
            "title": "HVAC Chilled Water System & Primary Plant BOQ",
            "category": "boq",
            "input": {
                "filename": "BOQ-2026-MEP-02_ChilledWater.xlsx",
                "document_type_hint": "boq",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "xlsx",
                    "sheet_count": 2,
                    "author": "Metro Mechanical Consultants",
                },
                "extracted_text": (
                    "BILL OF QUANTITIES: MECHANICAL CHILLED WATER PLANT\n"
                    "BOQ Reference: BOQ-2026-MEP-02\n"
                    "Contract Reference: CON-2026-MEP-002\n"
                    "Currency: USD\n\n"
                    "Item Code | Description | Quantity | Unit | Rate | Total\n"
                    "ME-01 | 800 TR Water-Cooled Centrifugal Chiller with VFD | 2.00 | each | 285000.00 | 570000.00\n"
                    "ME-02 | Induced draft crossflow cooling towers 2400 GPM capacity | 2.00 | each | 92000.00 | 184000.00\n"
                    "ME-03 | Schedule 40 seamless carbon steel chilled water pipe DN300 | 650.00 | m | 175.00 | 113750.00\n"
                    "ME-04 | Variable primary chilled water pumps with premium efficiency motors | 4.00 | each | 24500.00 | 98000.00\n\n"
                    "Total Mechanical Package: USD 965750.00"
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "boq",
                    "confidence": 0.99,
                    "reasoning": "Standard MEP schedule of items with quantities, units, and equipment rates.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "title": {
                        "value": "Mechanical Chilled Water Plant Bill of Quantities",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "BILL OF QUANTITIES: MECHANICAL CHILLED WATER PLANT",
                        "missing": False,
                    },
                    "stated_total": {
                        "value": {"amount": "965750.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Total Mechanical Package: USD 965750.00",
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
                    "items": [
                        {
                            "code": {"value": "ME-01", "confidence": 0.97, "source_page": 1, "source_text_snippet": "ME-01 | 800 TR Water-Cooled Centrifugal Chiller", "missing": False},
                            "description": {"value": "800 TR Water-Cooled Centrifugal Chiller with VFD", "confidence": 0.96, "source_page": 1, "source_text_snippet": "800 TR Water-Cooled Centrifugal Chiller with VFD", "missing": False},
                            "quantity": {"value": {"amount": "2.00", "unit": "each"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "2.00 | each", "missing": False},
                            "unit_rate": {"value": {"amount": "285000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "285000.00", "missing": False},
                            "stated_total": {"value": {"amount": "570000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "570000.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        },
                        {
                            "code": {"value": "ME-03", "confidence": 0.97, "source_page": 1, "source_text_snippet": "ME-03 | Schedule 40 seamless carbon steel chilled water pipe", "missing": False},
                            "description": {"value": "Schedule 40 seamless carbon steel chilled water pipe DN300", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Schedule 40 seamless carbon steel chilled water pipe DN300", "missing": False},
                            "quantity": {"value": {"amount": "650.00", "unit": "m"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "650.00 | m", "missing": False},
                            "unit_rate": {"value": {"amount": "175.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "175.00", "missing": False},
                            "stated_total": {"value": {"amount": "113750.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "113750.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        },
                    ],
                },
                "entities": [
                    {"kind": "boq", "reference": "BOQ-2026-MEP-02"},
                    {"kind": "contract", "reference": "CON-2026-MEP-002"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "boq",
                "required_fields_present": ["title", "stated_total", "items"],
                "item_assertions": [{"code": "ME-01", "unit_rate": "285000.00", "unit": "each"}],
            },
        },
        {
            "id": "DOC-BOQ-003",
            "title": "Structural Steel & Metal Decking Schedule of Rates",
            "category": "boq",
            "input": {
                "filename": "BOQ-2026-STL-03_Steelwork.xlsx",
                "document_type_hint": "boq",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "xlsx",
                    "sheet_count": 4,
                    "author": "Highline Commercial",
                },
                "extracted_text": (
                    "BILL OF QUANTITIES: STRUCTURAL STEEL FRAME\n"
                    "BOQ Reference: BOQ-2026-STL-03\n"
                    "Contract Reference: CON-2026-STL-003\n"
                    "Currency: USD\n\n"
                    "Item Code | Description | Quantity | Unit | Rate | Total\n"
                    "ST-10 | Grade S355JR structural steel fabrication and erection | 820.00 | t | 2650.00 | 2173000.00\n"
                    "ST-11 | Galvanized corrugated profiled steel decking 1.2mm thk | 7400.00 | m2 | 32.50 | 240500.00\n"
                    "ST-12 | Nelson type welded shear connector studs 19mm dia | 18500.00 | each | 4.80 | 88800.00\n"
                    "ST-13 | Two-hour intumescent thin-film fireproofing coating | 9200.00 | m2 | 45.00 | 414000.00\n\n"
                    "Total Structural Steel Package: USD 2916300.00"
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "boq",
                    "confidence": 0.99,
                    "reasoning": "Detailed steel fabrication schedule of rates with weight and area metrics.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "title": {
                        "value": "Structural Steel Frame Bill of Quantities",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "BILL OF QUANTITIES: STRUCTURAL STEEL FRAME",
                        "missing": False,
                    },
                    "stated_total": {
                        "value": {"amount": "2916300.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Total Structural Steel Package: USD 2916300.00",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-STL-003"},
                            "confidence": 0.96,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-STL-003",
                            "missing": False,
                        }
                    ],
                    "items": [
                        {
                            "code": {"value": "ST-10", "confidence": 0.97, "source_page": 1, "source_text_snippet": "ST-10 | Grade S355JR structural steel", "missing": False},
                            "description": {"value": "Grade S355JR structural steel fabrication and erection", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Grade S355JR structural steel fabrication and erection", "missing": False},
                            "quantity": {"value": {"amount": "820.00", "unit": "t"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "820.00 | t", "missing": False},
                            "unit_rate": {"value": {"amount": "2650.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "2650.00", "missing": False},
                            "stated_total": {"value": {"amount": "2173000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "2173000.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        }
                    ],
                },
                "entities": [
                    {"kind": "boq", "reference": "BOQ-2026-STL-03"},
                    {"kind": "contract", "reference": "CON-2026-STL-003"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "boq",
                "item_assertions": [{"code": "ST-10", "unit_rate": "2650.00", "unit": "t"}],
            },
        },
        {
            "id": "DOC-BOQ-004",
            "title": "Deep Foundation Bored Piling & Shoring Schedule",
            "category": "boq",
            "input": {
                "filename": "BOQ-2026-GEO-04_Piling.xlsx",
                "document_type_hint": "boq",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "xlsx",
                    "sheet_count": 2,
                    "author": "Waterfront QS",
                },
                "extracted_text": (
                    "BILL OF QUANTITIES: DEEP FOUNDATIONS AND PILING\n"
                    "BOQ Reference: BOQ-2026-GEO-04\n"
                    "Contract Reference: CON-2026-GEO-004\n"
                    "Currency: USD\n\n"
                    "Item Code | Description | Quantity | Unit | Rate | Total\n"
                    "PIL-01 | Bored cast-in-place concrete piles 900mm dia depth to 24m | 240.00 | each | 3400.00 | 816000.00\n"
                    "PIL-02 | Bored cast-in-place concrete piles 1200mm dia depth to 28m | 110.00 | each | 5200.00 | 572000.00\n"
                    "PIL-03 | Sonic logging integrity testing across pile cross-sections | 350.00 | each | 180.00 | 63000.00\n\n"
                    "Total Piling Package: USD 1451000.00"
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "boq",
                    "confidence": 0.99,
                    "reasoning": "Geotechnical piling bill of quantities with pile diameters, depths and testing items.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "title": {
                        "value": "Deep Foundations and Piling Bill of Quantities",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "BILL OF QUANTITIES: DEEP FOUNDATIONS AND PILING",
                        "missing": False,
                    },
                    "stated_total": {
                        "value": {"amount": "1451000.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Total Piling Package: USD 1451000.00",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-GEO-004"},
                            "confidence": 0.96,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-GEO-004",
                            "missing": False,
                        }
                    ],
                    "items": [
                        {
                            "code": {"value": "PIL-01", "confidence": 0.97, "source_page": 1, "source_text_snippet": "PIL-01 | Bored cast-in-place concrete piles 900mm", "missing": False},
                            "description": {"value": "Bored cast-in-place concrete piles 900mm dia depth to 24m", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Bored cast-in-place concrete piles 900mm dia depth to 24m", "missing": False},
                            "quantity": {"value": {"amount": "240.00", "unit": "each"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "240.00 | each", "missing": False},
                            "unit_rate": {"value": {"amount": "3400.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "3400.00", "missing": False},
                            "stated_total": {"value": {"amount": "816000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "816000.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        }
                    ],
                },
                "entities": [
                    {"kind": "boq", "reference": "BOQ-2026-GEO-04"},
                    {"kind": "contract", "reference": "CON-2026-GEO-004"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "boq",
                "item_assertions": [{"code": "PIL-01", "unit_rate": "3400.00", "unit": "each"}],
            },
        },
        {
            "id": "DOC-BOQ-005",
            "title": "Architectural Facade & Glazing Schedule of Quantities",
            "category": "boq",
            "input": {
                "filename": "BOQ-2026-FAC-05_Facade.xlsx",
                "document_type_hint": "boq",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "xlsx",
                    "sheet_count": 3,
                    "author": "Zenith Commercial QS",
                },
                "extracted_text": (
                    "BILL OF QUANTITIES: ARCHITECTURAL FACADE SYSTEM\n"
                    "BOQ Reference: BOQ-2026-FAC-05\n"
                    "Contract Reference: CON-2026-FAC-005\n"
                    "Currency: USD\n\n"
                    "Item Code | Description | Quantity | Unit | Rate | Total\n"
                    "GL-01 | Unitized double-glazed low-e curtain wall panels 1500x3800mm | 6200.00 | m2 | 480.00 | 2976000.00\n"
                    "GL-02 | Solid anodized aluminum composite spandrel panels | 2400.00 | m2 | 260.00 | 624000.00\n"
                    "GL-03 | Structural silicone sealant and continuous EPDM air/vapor barrier | 8500.00 | m | 28.00 | 238000.00\n\n"
                    "Total Facade Package: USD 3838000.00"
                ),
            },
            "expected_output": {
                "classification": {
                    "document_type": "boq",
                    "confidence": 0.99,
                    "reasoning": "Facade schedule of quantities with unitized curtain wall glazing line items.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "title": {
                        "value": "Architectural Facade System Bill of Quantities",
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "BILL OF QUANTITIES: ARCHITECTURAL FACADE SYSTEM",
                        "missing": False,
                    },
                    "stated_total": {
                        "value": {"amount": "3838000.00", "currency": "USD"},
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": "Total Facade Package: USD 3838000.00",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": "CON-2026-FAC-005"},
                            "confidence": 0.96,
                            "source_page": 1,
                            "source_text_snippet": "Contract Reference: CON-2026-FAC-005",
                            "missing": False,
                        }
                    ],
                    "items": [
                        {
                            "code": {"value": "GL-01", "confidence": 0.97, "source_page": 1, "source_text_snippet": "GL-01 | Unitized double-glazed low-e curtain wall", "missing": False},
                            "description": {"value": "Unitized double-glazed low-e curtain wall panels 1500x3800mm", "confidence": 0.96, "source_page": 1, "source_text_snippet": "Unitized double-glazed low-e curtain wall panels 1500x3800mm", "missing": False},
                            "quantity": {"value": {"amount": "6200.00", "unit": "m2"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "6200.00 | m2", "missing": False},
                            "unit_rate": {"value": {"amount": "480.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "480.00", "missing": False},
                            "stated_total": {"value": {"amount": "2976000.00", "currency": "USD"}, "confidence": 0.98, "source_page": 1, "source_text_snippet": "2976000.00", "missing": False},
                            "status": {"value": "planned", "confidence": 0.95, "source_page": 1, "source_text_snippet": "planned", "missing": False},
                        }
                    ],
                },
                "entities": [
                    {"kind": "boq", "reference": "BOQ-2026-FAC-05"},
                    {"kind": "contract", "reference": "CON-2026-FAC-005"},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "boq",
                "item_assertions": [{"code": "GL-01", "unit_rate": "480.00", "unit": "m2"}],
            },
        },
    ]

