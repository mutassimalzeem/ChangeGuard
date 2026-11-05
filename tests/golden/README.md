# ChangeGuard Golden Evaluation Dataset

## 1. Overview

The **ChangeGuard Golden Evaluation Dataset** is a versioned, comprehensive evaluation benchmark for ChangeGuard's AI document processing, structured fact extraction, deterministic risk analysis, hybrid retrieval, and permission enforcement subsystems.

All test cases are constructed from **realistic synthetic construction data** across commercial, structural, civil, geotechnical, and MEP domains. **No real customer data is used.**

## 2. Dataset Structure

```text
tests/golden/
|-- documents/                      # Raw synthetic input documents & metadata
|   |-- contracts/                  # 5 Subcontract & prime agreement cases
|   |-- boqs/                       # 5 Bills of Quantities & schedules of rates
|   |-- rfis/                       # 5 Technical requests for information
|   |-- change_orders/              # 10 Variation claims & change directives
|   |-- daily_reports/              # 10 Superintendent field logs & shifts
|   |-- emails/                     # 10 Correspondence threads & notices
|   |-- site_photos/                # 10 Inspection photos with EXIF & damage context
|   |-- duplicate_detection/        # 5 Duplicate claim & double-billing cases
|   |-- missing_evidence/           # 5 Unsubstantiated claims & refusal triggers
|   |-- conflicting_evidence/       # 5 Field log vs claim contradiction cases
|   |-- permission_isolation/       # 10 Multi-tenant & RBAC security boundary cases
|   |-- prompt_injection/           # 10 Adversarial injection & jailbreak cases
|   `-- e2e_workflows/              # 5 Multi-step end-to-end lifecycle workflows
|-- expected_classifications/       # Ground-truth document classifications
|   |-- all_classifications.json    # Consolidated classification targets
|   |-- contracts.json
|   |-- boqs.json
|   |-- rfis.json
|   |-- change_orders.json
|   |-- daily_reports.json
|   |-- emails.json
|   `-- site_photos.json
|-- expected_extractions/           # Grounded structured extractions per Pydantic schema
|   |-- contracts.json
|   |-- boqs.json
|   |-- rfis.json
|   |-- change_orders.json
|   |-- daily_reports.json
|   |-- emails.json
|   `-- site_photos.json
|-- expected_entities/              # Master relational graph of synthetic entities
|   `-- entities.json               # Tenants, projects, employers, contractors, cross-links
|-- expected_risks/                 # Ground-truth deterministic risk findings
|   |-- risks.json                  # Master risk expectations
|   |-- duplicate_detection.json    # duplicate_change_order_claim evaluations
|   |-- missing_evidence.json       # missing_required_evidence & refusal evaluations
|   `-- conflicting_evidence.json   # conflicting_information & cost_outlier evaluations
|-- expected_retrieval/             # Hybrid search evaluation targets
|   `-- retrieval.json              # Exact ID match, semantic search, date & doc type filters
|-- expected_change_orders/         # Change order workflow & approval benchmarks
|   |-- change_orders.json          # 10 Variation lifecycle evaluations
|   `-- e2e_workflows.json          # 5 Complete chronological multi-turn workflows
|-- permission_isolation/           # Tenant & role enforcement evaluations
|   `-- permission_isolation.json   # 10 Isolation security assertions
|-- prompt_injection/               # Adversarial safety benchmarks
|   `-- prompt_injection.json       # 10 Attack vectors, defenses, and assertions
|-- evaluator.py                    # Dataset evaluation & metric reporting runner
`-- manifest.json                   # Master registry & case count specification
```

---

## 3. Case Taxonomy and Minimum Requirements

| Category | Target Minimum | Included Cases | Description |
|---|:---:|:---:|---|
| **Contract extraction** | 5 | 5 | FIDIC Red Book, AIA A401, NEC4 ECS, unit rate piling, and lump sum facade agreements. |
| **BOQ extraction** | 5 | 5 | Earthworks, HVAC equipment, structural steelwork, deep piling, and architectural curtain wall BOQs. |
| **RFI extraction** | 5 | 5 | Structural-MEP clash, high water table, curtain wall drift, seismic rebar splices, and damper substitutions. |
| **Change-order extraction** | 10 | 10 | Clay sub-base, 33kV reroute, MRI slab upgrade, fire doors, dewatering, tile upgrade, cooling tower acoustics, fire wrap, CFRP strengthening, and credit variations. |
| **Daily report extraction** | 10 | 10 | Concrete pours, crane failure downtime, asbestos conduit discovery, waterproofing NCR, night beam erection, heat index stoppage, batch rejections, MEP clash, permit delay, and overtime burnishing. |
| **Email-thread extraction** | 10 | 10 | Urgent directives, weather claim rejections, footing depth confirmations, delayed possession notices, steel price escalation, pump authorization, ceiling redesign, crane back-charges, acceleration requests, and damper failure notices. |
| **Site photo analysis** | 10 | 10 | Water ingress efflorescence, uncharted duct bank, displaced anchor bolts, honeycombing, flooded pit, sprinkler beam clash, gouged fireproofing, blocked exit egress, transit damaged chiller, and QA/QC rebar tags. |
| **Duplicate detection** | 5 | 5 | Resubmitted identical change orders, double-billed scaffolding preliminaries, duplicate crane downtime, resubmitted rejected rock claim, and double-billed daywork timesheets. |
| **Missing-evidence detection** | 5 | 5 | Rock excavation without survey cross-sections, weekend overtime without signed timesheets, design delay without RFI transmittal, air freight without waybill, and thermal cracking without curing logs. |
| **Conflicting-evidence detection** | 5 | 5 | Sunny site report vs torrential rain claim, 4 fixers logged vs 16 billed, 500mm installed pipe vs 750mm billed, $45/m² quotation vs $95/m² change order, and disapproved status vs claimed approved. |
| **Permission isolation** | 10 | 10 | Cross-tenant block, cross-project block, Site Engineer approval block, PM financial release block, restricted document concealment, auditor read-only enforcement, quarantined document isolation, soft-deleted project tombstones, service key scoping, and chunk-level search redaction. |
| **Prompt-injection resistance** | 10 | 10 | Direct system overrides, delimiter forgery, roleplay jailbreaks, markdown image exfiltration, zero-width unicode smuggling, indirect email injections, base64 payloads, tool hijack attempts, context stuffing, and tenant bypass injections. |
| **End-to-end workflows** | 5 | 5 | Discovery-to-approval workflow, cost outlier renegotiation, insufficient evidence refusal & upload, conflicting evidence audit, and grounded investigation agent multi-turn queries. |
| **Total Cases** | **95** | **95** | **100% Validated against ChangeGuard Pydantic Schemas** |

---

## 4. Evaluation Criteria & Metrics

Each test case specifies explicit, automated evaluation criteria:

1. **Classification Accuracy**: Exact match against canonical document types (`contract`, `boq`, `drawing`, `rfi`, `daily_report`, `change_order`, `site_photo`, `email`, `quotation`, `other`).
2. **Field-Level Evidence Grounding**: Present facts require exact values, confidence scores, source page numbers, and verbatim source quotations. Missing facts must have `missing: True`, `value: None`, and `confidence: 0.0`.
3. **Deterministic Risk Rules**:
   - `cost_outlier`: Item rate > 20% higher than historical comparable BOQ item.
   - `duplicate_change_order_claim`: Identical contract, RFI, amount, and normalized description.
   - `missing_required_evidence`: Missing required facts or supporting documents; triggers `insufficient_evidence` status and refuses approval.
   - `conflicting_information`: Same entity and issue with contradictory values (weather, headcount, dimensions, rates, status).
4. **Security & Boundary Enforcement**:
   - Default-deny RBAC: HTTP 403 / 404 with zero data leakage.
   - Prompt Injection Resistance: Evasion attempts fail; model treats untrusted input strictly as data and adheres to system constraints.
5. **Grounded Retrieval**:
   - Exact identifier search triggers `exact_identifier_match: True`.
   - Semantic queries return relevant documents without hallucinating facts.
   - Out-of-domain queries return `status: insufficient_evidence`.

---

## 5. Running Evaluations

### Running the Evaluator CLI

```bash
# Run offline dataset verification and classifier baseline
python -m tests.golden.evaluator

# Run with output file export
python -m tests.golden.evaluator --output tests/golden/evaluation_report.json
```

### Running via Pytest

```bash
# Run the complete automated test suite
pytest backend/tests/test_golden_dataset.py -v
```
