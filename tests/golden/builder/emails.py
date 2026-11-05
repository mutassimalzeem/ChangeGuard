"""Email thread golden test cases definition (10 cases)."""

def get_email_cases():
    cases_meta = [
        ("DOC-EML-001", "re: urgent mep riser relocation direction", "pm.marcus@apexventures.test", "director.david@horizon-struct.test",
         "2026-02-15", "Proceed with urgent MEP riser relocation per sketch SK-S-201-A immediately to avoid framing delay. We will formalize change order CO-2026-002 upon receipt of priced breakdown.",
         "sent", "CON-2026-CS-001", "RFI-2026-001"),
        ("DOC-EML-002", "notice of weather delay claim rejection", "contracts@apexventures.test", "commercial@horizon-struct.test",
         "2026-02-23", "Your notice of adverse weather delay dated Feb 20 is rejected. National weather service data confirms rainfall was 14mm, well below the contractual 30mm force majeure threshold in Clause 8.4.",
         "received", "CON-2026-CS-001", None),
        ("DOC-EML-003", "confirmation of revised footing depth for grid c-3", "lead.structural@metroconsult.test", "site.eng@geofoundation.test",
         "2026-02-26", "Based on geotechnical core samples, the founding depth for pile cap PC-03 is revised from -6.50m to -7.80m ECD. Approved for immediate rebar placement.",
         "sent", "CON-2026-GEO-004", "RFI-2026-002"),
        ("DOC-EML-004", "formal notice of delayed site possession - zone c", "commercial@horizon-struct.test", "pm.marcus@apexventures.test",
         "2026-03-01", "We hereby serve formal notice under Clause 2.1 that access to Zone C has been obstructed by ongoing municipal utility work. We reserve all rights to time and financial compensation.",
         "sent", "CON-2026-CS-001", None),
        ("DOC-EML-005", "steel mill material price escalation notification", "sales.mgr@titansteel.test", "procurement@apexventures.test",
         "2026-03-06", "Global raw materials surcharge has increased European heavy flange beams by 12.5%. Attached mill index certificates validate this adjustment. Current quotation prices hold for 14 days.",
         "received", "CON-2026-STL-003", None),
        ("DOC-EML-006", "authorization for emergency dewatering pump deployment", "resident.eng@apexventures.test", "operations@geofoundation.test",
         "2026-03-10", "This email confirms verbal site authorization given today for GeoFoundation to mobilize three additional 6-inch submersible pumps with temporary generators. Log hours separately under CO-2026-005.",
         "sent", "CON-2026-GEO-004", "RFI-2026-002"),
        ("DOC-EML-007", "architectural instruction - executive suite ceiling finish", "lead.architect@zenithstudio.test", "pm.david@apexventures.test",
         "2026-03-14", "Per client preference, replace specified acoustic wood baffles in the Boardroom with seamless monolithic micro-perforated gypsum ceiling system. Requesting cost delta.",
         "sent", "CON-2026-CS-001", None),
        ("DOC-EML-008", "dispute notice regarding crane back-charges", "finance@titansteel.test", "commercial@horizon-struct.test",
         "2026-03-18", "We dispute your back-charge invoice #BC-044 for tower crane shared usage ($14,500). Contract Sub-clause 6.2 states crane hook time is provided by main contractor without surcharge.",
         "received", "CON-2026-STL-003", None),
        ("DOC-EML-009", "employer request for schedule acceleration proposal", "director.project@apexventures.test", "exec.team@horizon-struct.test",
         "2026-03-22", "Apex invites Horizon to submit a fast-track acceleration proposal to bring forward Substantial Completion of Podium Retail by 45 calendar days. Include double-shifting cost breakdown.",
         "sent", "CON-2026-CS-001", None),
        ("DOC-EML-010", "commissioning defect - fire damper smoke seal failure", "commissioning.agent@safetysystems.test", "mep.lead@pioneerthermal.test",
         "2026-03-27", "During today's pre-functional pressurization test on Stair Core B, fire damper FD-B-04 failed to close within 15 seconds due to actuator torque deficiency. Replacement required before re-test.",
         "received", "CON-2026-MEP-002", "RFI-2026-005"),
    ]

    result = []
    for doc_id, subj, sender, recip, sent_dt, body, status, contract_ref, rfi_ref in cases_meta:
        text_lines = [
            f"Subject: {subj}",
            f"From: {sender}",
            f"To: {recip}",
            f"Date: {sent_dt}",
            f"Status: {status}",
            f"Contract Reference: {contract_ref}",
        ]
        if rfi_ref:
            text_lines.append(f"Referenced RFI: {rfi_ref}")
        text_lines.append(f"\n{body}")

        doc_refs = [
            {
                "value": {"kind": "contract", "reference": contract_ref},
                "confidence": 0.95,
                "source_page": 1,
                "source_text_snippet": f"Contract Reference: {contract_ref}",
                "missing": False,
            }
        ]
        if rfi_ref:
            doc_refs.append({
                "value": {"kind": "rfi", "reference": rfi_ref},
                "confidence": 0.95,
                "source_page": 1,
                "source_text_snippet": f"Referenced RFI: {rfi_ref}",
                "missing": False,
            })

        result.append({
            "id": doc_id,
            "title": f"Email: {subj}",
            "category": "email",
            "input": {
                "filename": f"{doc_id}_{sent_dt}.eml",
                "document_type_hint": "email",
                "metadata": {
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "file_type": "eml",
                    "page_count": 1,
                    "author": sender,
                },
                "extracted_text": "\n".join(text_lines),
            },
            "expected_output": {
                "classification": {
                    "document_type": "email",
                    "confidence": 0.99,
                    "reasoning": "Project correspondence email thread with valid sender, recipient, timestamp and message body.",
                    "model_or_rule_used": "rules_with_llm_fallback",
                },
                "extraction": {
                    "subject": {
                        "value": subj,
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": f"Subject: {subj}",
                        "missing": False,
                    },
                    "sender": {
                        "value": sender,
                        "confidence": 0.99,
                        "source_page": 1,
                        "source_text_snippet": f"From: {sender}",
                        "missing": False,
                    },
                    "recipient": {
                        "value": recip,
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": f"To: {recip}",
                        "missing": False,
                    },
                    "sent_date": {
                        "value": sent_dt,
                        "confidence": 0.98,
                        "source_page": 1,
                        "source_text_snippet": f"Date: {sent_dt}",
                        "missing": False,
                    },
                    "body": {
                        "value": body,
                        "confidence": 0.97,
                        "source_page": 1,
                        "source_text_snippet": body[:80],
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
                "entities": [
                    {"kind": "contract", "reference": contract_ref},
                ],
            },
            "evaluation_criteria": {
                "classification_metric": "exact_match",
                "classification_target": "email",
                "required_fields_present": ["subject", "sender", "recipient", "body"],
                "value_assertions": {
                    "subject": subj,
                    "sender": sender,
                    "recipient": recip,
                    "sent_date": sent_dt,
                },
            },
        })
    return result

