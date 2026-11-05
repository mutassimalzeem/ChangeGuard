"""Daily report golden test cases definition (10 cases)."""

def get_daily_report_cases():
    cases_meta = [
        ("DOC-DR-001", "2026-02-12", "Daily Construction Log - Basement B2 Shear Wall Pour",
         "Clear and sunny, 24C, wind 8 km/h",
         "Placed 220 m3 of C40 concrete in shear walls SW-01 through SW-04. Slump testing passed at 160mm. Curing compound applied.",
         "280.00", "h", "approved", "CON-2026-CS-001"),
        ("DOC-DR-002", "2026-02-16", "Daily Progress Report - Tower Crane #2 Hydraulic Breakdown",
         "Overcast with light breeze, 19C",
         "Tower crane #2 hydraulic slew motor failed at 09:30. Steel fixers in Zone B idle for 4.5 hours awaiting mobile crane backup.",
         "195.00", "h", "approved", "CON-2026-CS-001"),
        ("DOC-DR-003", "2026-02-21", "Site Safety Log - Discovery of Asbestos Conduit in Trench T-4",
         "Sunny, 26C",
         "Encountered non-documented legacy asbestos-cement conduit at chainage 0+140. Work immediately halted. HSE perimeter erected.",
         "120.00", "h", "submitted", "CON-2026-CS-001"),
        ("DOC-DR-004", "2026-02-27", "Daily Quality Log - Basement Waterproofing Membrane NCR",
         "Cloudy, 21C, humidity 65%",
         "Inspection of SBS torch-applied membrane on east retaining wall revealed pinholes and unbonded laps. Issued NCR-012 for remedial priming.",
         "160.00", "h", "approved", "CON-2026-CS-001"),
        ("DOC-DR-005", "2026-03-03", "Daily Report - Night Shift Precast Beam Placement",
         "Clear night, 16C, road closure in effect",
         "Erected 4 precast prestressed bridge beams over arterial access road between 01:00 and 05:00 using 350t all-terrain crane.",
         "96.00", "h", "approved", "CON-2026-CS-001"),
        ("DOC-DR-006", "2026-03-08", "Daily Log - Extreme Heat Index Mandatory Work Stoppage",
         "Extreme heat, 39C ambient, WBGT 34.2C",
         "Mandatory midday heat stress stoppage enforced from 12:30 to 15:30. Operatives moved to air-conditioned rest shelters.",
         "180.00", "h", "approved", "CON-2026-CS-001"),
        ("DOC-DR-007", "2026-03-14", "Daily Material Log - Ready-Mix Concrete Batch Rejection",
         "Partly cloudy, 23C",
         "Rejected 3 transit mixer trucks (batch tickets #4901-#4903) due to slump test reading 65mm against required 150mm tolerance.",
         "210.00", "h", "submitted", "CON-2026-CS-001"),
        ("DOC-DR-008", "2026-03-19", "Daily Engineering Log - Level 06 Pre-Pour MEP Penetration Clash",
         "Sunny and dry, 25C",
         "Pre-pour survey revealed 150mm drain pipe clashed with structural PT anchor zone. Core drilling team mobilized to reposition sleeve.",
         "225.00", "h", "approved", "CON-2026-CS-001"),
        ("DOC-DR-009", "2026-03-24", "Daily Log - Delayed Hot Work Permit Clearance",
         "Breezy, 20C",
         "Structural steel welding crew delayed 3 hours awaiting client safety gas-free certification in confined shaft area.",
         "140.00", "h", "draft", "CON-2026-STL-003"),
        ("DOC-DR-010", "2026-03-29", "Daily Progress Report - Weekend Overtime Slab Burnishing",
         "Approaching evening thunderstorm, 22C",
         "Authorized weekend overtime shift completed ride-on power trowel surface burnishing on 1,400m2 slab prior to heavy evening rain.",
         "310.00", "h", "approved", "CON-2026-CS-001"),
    ]

    result = []
    for doc_id, dt, title, weather, activities, labour_val, labour_unit, status, contract_ref in cases_meta:
        text_lines = [
            "DAILY SITE REPORT",
            f"Title: {title}",
            f"Report Date: {dt}",
            f"Weather: {weather}",
            f"Activities: {activities}",
            f"Labour: {labour_val} {labour_unit}",
            f"Status: {status}",
            f"Contract Reference: {contract_ref}",
        ]

        result.append({
            "id": doc_id,
            "title": title,
            "category": "daily_report",
            "input": {
                "filename": f"DailyReport_{dt}.pdf",
                "document_type_hint": "daily_report",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "pdf",
                    "page_count": 2,
                    "author": "Site Superintendent",
                },
                "extracted_text": "\n".join(text_lines),
            },
            "expected_output": {
                "classification": {
                    "document_type": "daily_report",
                    "confidence": 0.99,
                    "reasoning": "Daily construction field report documenting weather, site activities, labour hours, and progress.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "report_date": {
                        "value": dt,
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": f"Report Date: {dt}",
                        "missing": False,
                    },
                    "title": {
                        "value": title,
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": f"Title: {title}",
                        "missing": False,
                    },
                    "weather": {
                        "value": weather,
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": f"Weather: {weather}",
                        "missing": False,
                    },
                    "activities": {
                        "value": activities,
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": f"Activities: {activities}",
                        "missing": False,
                    },
                    "labour_quantity": {
                        "value": {"amount": labour_val, "unit": labour_unit},
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": f"Labour: {labour_val} {labour_unit}",
                        "missing": False,
                    },
                    "status": {
                        "value": status,
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": f"Status: {status}",
                        "missing": False,
                    },
                    "document_references": [
                        {
                            "value": {"kind": "contract", "reference": contract_ref},
                            "confidence": 0.95,
                            "source_page": 1,
                            "source_text_snippet": f"Contract Reference: {contract_ref}",
                            "missing": False,
                        }
                    ],
                },
                "entities": [
                    {"kind": "contract", "reference": contract_ref},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "daily_report",
                "required_fields_present": ["report_date", "activities", "weather"],
                "value_assertions": {
                    "report_date": dt,
                    "status": status,
                },
            },
        })
    return result

