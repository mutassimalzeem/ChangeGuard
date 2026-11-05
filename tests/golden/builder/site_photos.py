"""Site photo golden test cases definition (10 cases)."""

def get_site_photo_cases():
    cases_meta = [
        ("DOC-PHO-001", "PHO-2026-001", "Basement Retaining Wall Water Ingress & Efflorescence",
         "Basement Level B3, Gridline A-04, North diaphragm wall cold joint",
         "Severe water seepage observed emerging through vertical construction cold joint. White crystalline efflorescence staining visible across 3.5m length. Damp patch spreading toward elevator sump.",
         "Water Ingress / Waterproofing Defect", "2026-02-14T09:15:00Z", "CON-2026-CS-001", "RFI-2026-002"),
        ("DOC-PHO-002", "PHO-2026-002", "Uncharted Historical Masonry Duct Discovered in Trench",
         "External Utilities Corridor, Chainage 0+085, depth 1.8m",
         "Excavator teeth exposed arched brickwork conduit dating to early 20th century municipal stormwater network. Structural integrity undisturbed but blocking planned 33kV high voltage electrical duct bank route.",
         "Unforeseen Site Obstruction", "2026-02-19T14:30:00Z", "CON-2026-MEP-002", "RFI-2026-002"),
        ("DOC-PHO-003", "PHO-2026-003", "Misaligned Baseplate Anchor Bolts on Gridline D-8 Column",
         "Podium Level 01, Structural Grid D-8, Column Base C-14",
         "Cast-in Grade 8.8 anchor bolt cluster displaced 45mm south of theoretical centerline. Structural steel baseplate cannot be seated without oblong slot enlargement or anchor re-engineering.",
         "Structural Dimensional Non-Conformance", "2026-02-24T11:00:00Z", "CON-2026-CS-001", "RFI-2026-004"),
        ("DOC-PHO-004", "PHO-2026-004", "Severe Honeycombing and Segregation in Stripped Column C-04",
         "Level 02, Column C-04 bottom 1200mm zone above slab",
         "Extensive honeycombing and voiding with exposed deformed rebar ties following formwork stripping. Insufficient internal mechanical vibrator compaction during high slump pour.",
         "Concrete Pour Defect / Honeycombing", "2026-03-02T16:20:00Z", "CON-2026-CS-001", None),
        ("DOC-PHO-005", "PHO-2026-005", "Flooded Elevator Lift Pit Excavation with Submerged Rebars",
         "Tower Core Elevator Pit B, Formation Level -12.4m ECD",
         "Turbid standing groundwater completely submerging foundation raft bottom rebar matting up to 800mm depth following mechanical failure of primary dewatering pump.",
         "Excavation Flooding / Dewatering Stoppage", "2026-03-07T08:45:00Z", "CON-2026-GEO-004", "RFI-2026-002"),
        ("DOC-PHO-006", "PHO-2026-006", "Fire Sprinkler Main Clashing with Steel Transfer Beam Web Stiffener",
         "Level 03 Ceiling Void, Corridor C-102",
         "Installed 150mm fire sprinkler supply pipe physically jammed against welded web stiffener plate of 700mm structural transfer beam. Zero clearance for seismic pipe sway bracing.",
         "MEP vs Structural Physical Clash", "2026-03-11T13:10:00Z", "CON-2026-MEP-002", "RFI-2026-001"),
        ("DOC-PHO-007", "PHO-2026-007", "Damaged Intumescent Fireproofing on Girder G-12",
         "Level 04 Main Auditorium, Girder G-12 bottom flange",
         "Ductwork installation crew mechanically gouged off 1.8m length of newly applied two-hour thin-film intumescent coating while hoisting galvanized sheet metal ducts without protective lagging.",
         "Fireproofing Coating Damage", "2026-03-17T15:05:00Z", "CON-2026-STL-003", None),
        ("DOC-PHO-008", "PHO-2026-008", "Combustible Solvent Drums Blocking Emergency Egress Stairwell",
         "Stair Core 1, Ground Floor Exit Discharge Vestibule",
         "Six 200L drums of solvent-based curing compound and polyurethane adhesive stored directly in exit passageway. Clear breach of OSHA and NFPA Life Safety egress standards.",
         "HSE Fire & Life Safety Violation", "2026-03-21T10:40:00Z", "CON-2026-CS-001", None),
        ("DOC-PHO-009", "PHO-2026-009", "Delivered 800TR Chiller with Crushed Heat Exchanger Fins",
         "Site Laydown Yard 2, Offloading Crane Bay",
         "Forklift impact during transit cracked protective crating and crushed approximately 300x500mm area of aluminum heat transfer condenser coils on Chiller Unit CH-02.",
         "Equipment Transit Delivery Damage", "2026-03-26T12:00:00Z", "CON-2026-MEP-002", "RFI-2026-005"),
        ("DOC-PHO-010", "PHO-2026-010", "Satisfactory QA/QC Rebar Inspection Tag on Column C-18",
         "Level 05, Column C-18 Rebar Cage",
         "Green QA/QC Approved for Concrete Pour tag signed by Supervising Resident Engineer attached to 32mm vertical rebar cage. Mechanical couplers and stirrup spacing verified.",
         "QA/QC Verification Milestone Pass", "2026-03-30T17:15:00Z", "CON-2026-CS-001", "RFI-2026-004"),
    ]

    result = []
    for doc_id, pho_num, title, loc, obs, defect_cat, timestamp, contract_ref, rfi_ref in cases_meta:
        text_lines = [
            "CONSTRUCTION SITE INSPECTION PHOTOGRAPH",
            f"Photo ID: {pho_num}",
            f"Title: {title}",
            f"Timestamp: {timestamp}",
            f"Location: {loc}",
            f"Observed Scene: {obs}",
            f"Classification: site_photo",
            f"Defect Category: {defect_cat}",
            f"Contract Reference: {contract_ref}",
        ]
        if rfi_ref:
            text_lines.append(f"Referenced RFI: {rfi_ref}")

        doc_refs = [
            {
                "value": {"kind": "contract", "reference": contract_ref},
                "confidence": 0.95,
                "source_page": 1,
                "source_text_snippet": f"Contract Reference: {contract_ref}",
                "missing": False,
            }
        ]
        entities = [
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
            "title": f"Site Photo: {title}",
            "category": "site_photo",
            "input": {
                "filename": f"{pho_num}_{defect_cat.replace(' ', '_').replace('/', '_')}.jpg",
                "document_type_hint": "site_photo",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "jpeg",
                    "dimensions": "4032x3024",
                    "camera_model": "Trimble SiteVision Rugged / iPhone 15 Pro Max",
                    "gps_latitude": 25.1972,
                    "gps_longitude": 55.2744,
                    "timestamp": timestamp,
                    "author": "Site QA/QC Field Engineer",
                },
                "extracted_text": "\n".join(text_lines),
            },
            "expected_output": {
                "classification": {
                    "document_type": "site_photo",
                    "confidence": 0.98,
                    "reasoning": f"Site inspection photograph capturing field visual evidence of {defect_cat}.",
                    "model_or_rule_used": "vision_rules_with_llm",
                },
                "extraction": {
                    "title": {
                        "value": title,
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": f"Title: {title}",
                        "missing": False,
                    },
                    "description": {
                        "value": obs,
                        "confidence": 0.96,
                        "source_page": 1,
                        "source_text_snippet": obs[:80],
                        "missing": False,
                    },
                    "document_references": doc_refs,
                },
                "entities": entities,
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "site_photo",
                "required_fields_present": ["title", "description"],
                "value_assertions": {
                    "title": title,
                },
            },
        })
    return result

