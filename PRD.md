# ChangeGuard — Product Requirements Document (PRD)

**Version:** 0.1  
**Date:** October 27, 2026  
**Owner:** Mutassim Al Shahriar Zeem  
**Status:** Draft for validation  

---

## 1. Product summary

**ChangeGuard** is an AI-powered change-order, claim, and project-risk intelligence platform for mid-sized construction contractors.

It ingests fragmented project evidence—contracts, RFIs, drawings, BOQs, daily reports, site photos, emails, quotations, and approvals—then builds an evidence-linked timeline of scope, cost, schedule, and responsibility.

The product does **not** merely summarize documents. It helps project teams:

- Detect potential change orders earlier.
- Connect claims to contractual and site evidence.
- Identify missing documentation before disputes occur.
- Track pending financial and schedule exposure.
- Reduce approval delays.
- Produce review-ready change-order packages.

### One-line positioning

> ChangeGuard turns scattered construction project records into evidence-backed change-order and risk intelligence.

---

## 2. Problem statement

Construction teams lose money because project information is fragmented across email, WhatsApp, PDFs, drawings, spreadsheets, and disconnected systems.

Typical failure modes:

- A scope change is discussed in email but never converted into a formal change order.
- A delay is visible in daily reports but is not linked to the responsible supplier or subcontractor.
- A change-order claim lacks supporting drawings, RFIs, photos, or approval records.
- Duplicate or conflicting claims are discovered only during a dispute.
- Approval deadlines are missed because nobody has a consolidated view.
- Managers cannot see total pending cost and schedule exposure across projects.

These problems are expensive because they affect margin, cash flow, dispute outcomes, and project delivery.

---

## 3. Target customer

### Initial beachhead

**Mid-sized construction contractors** handling 5–30 active projects.

Priority sub-segments:

- General contractors.
- MEP contractors.
- Fit-out contractors.
- Civil contractors working on commercial or residential projects.

### Buyer and user personas

| Persona | Role | Primary need |
|---|---|---|
| Managing director / owner | Commercial buyer | Protect margin, reduce disputes, see exposure |
| Project manager | Primary user | Track changes, risks, approvals, and evidence |
| Commercial manager / QS | Heavy user | Validate cost, scope, and claims |
| Site engineer | Data contributor | Upload reports, photos, and site updates |
| Document controller | Operations user | Organize documents and approvals |
| Finance / accounts | Secondary user | Understand approved and pending financial exposure |

---

## 4. Goals and non-goals

### Goals for MVP

1. Allow users to upload and organize project documents.
2. Automatically classify documents and extract key structured fields.
3. Link documents and events to a project knowledge model.
4. Detect high-value risks using deterministic rules.
5. Build evidence-backed change-order drafts.
6. Provide a project dashboard showing pending exposure and overdue actions.
7. Maintain a complete audit trail for every AI-generated conclusion.

### Non-goals for MVP

- Full ERP or accounting replacement.
- Autonomous contract signing or payment execution.
- Fully autonomous client communication.
- Direct control of construction equipment or site systems.
- Support for every construction document format on day one.
- Multi-language support beyond English and Bengali where practical.

---

## 5. Core user journeys

### Journey 1: Upload project evidence

1. Project manager creates a project.
2. User uploads contract, BOQ, drawings, RFIs, daily reports, photos, and email exports.
3. System assigns each file a document ID, hash, project, uploader, and processing status.
4. System extracts text, classifies the document, and extracts structured fields.
5. User reviews low-confidence extractions.

**Success criterion:** At least 90% of supported document types are correctly classified in the pilot dataset.

### Journey 2: Detect a potential change

1. A site engineer uploads a daily report and site photos.
2. System detects a possible scope change or delay event.
3. System links the event to relevant drawings, RFIs, contract clauses, and previous reports.
4. System creates a “potential change” with evidence and confidence.
5. Project manager reviews and converts it into a formal change order.

**Success criterion:** The system surfaces a potential change before it is manually entered as a change order in at least 3 pilot cases.

### Journey 3: Build a change-order package

1. User selects a potential change.
2. System retrieves supporting evidence: emails, drawings, RFIs, photos, daily reports, and cost records.
3. System drafts a structured change-order package.
4. Commercial manager edits and approves the draft.
5. System stores the final package with immutable evidence links.

**Success criterion:** Draft preparation reduces manual evidence-gathering time by at least 50% in pilot feedback.

### Journey 4: Track exposure

1. System aggregates approved, pending, disputed, and rejected change orders.
2. Dashboard shows financial exposure, schedule impact, responsible parties, and overdue approvals.
3. User filters by project, subcontractor, cost code, status, or date.
4. System alerts users when an approval deadline is approaching.

**Success criterion:** Users can answer “What is our current pending change-order exposure?” in under 30 seconds.

---

## 6. MVP feature requirements

### F1. Project and document management

| Requirement | Priority |
|---|---|
| Create projects with client, contract value, dates, and stakeholders | P0 |
| Upload PDF, DOCX, XLSX, JPG, PNG, and email exports | P0 |
| Store original files immutably | P0 |
| Assign document metadata: type, version, uploader, date, project, status | P0 |
| Prevent duplicate uploads using file hash | P1 |
| Support document versioning | P1 |
| Allow manual tagging and correction | P0 |

### F2. Document intelligence

| Requirement | Priority |
|---|---|
| OCR and text extraction for supported documents | P0 |
| Classify documents into known types | P0 |
| Extract structured fields using strict schemas | P0 |
| Assign extraction confidence | P0 |
| Flag low-confidence fields for human review | P0 |
| Preserve source page and location references | P0 |
| Detect duplicate or near-duplicate documents | P1 |

### F3. Project knowledge model

| Requirement | Priority |
|---|---|
| Model projects, contracts, clauses, drawings, BOQs, RFIs, change orders, approvals, and events | P0 |
| Link documents to domain entities | P0 |
| Maintain event timeline | P0 |
| Support entity resolution across documents | P1 |
| Maintain evidence links between claims and sources | P0 |

### F4. Risk and anomaly detection

| Requirement | Priority |
|---|---|
| Detect overdue approvals | P0 |
| Detect missing required evidence | P0 |
| Detect duplicate change-order claims | P1 |
| Detect cost outliers against BOQ or historical records | P1 |
| Detect schedule-impact signals | P1 |
| Detect conflicting information across documents | P1 |
| Allow human override with reason | P0 |

### F5. Change-order workflow

| Requirement | Priority |
|---|---|
| Create potential change from evidence | P0 |
| Convert potential change into formal change order | P0 |
| Assign owner, status, cost impact, schedule impact, and deadline | P0 |
| Generate evidence-backed draft package | P0 |
| Support human review and edit | P0 |
| Track approval history | P0 |
| Maintain immutable audit trail | P0 |

### F6. Dashboard and reporting

| Requirement | Priority |
|---|---|
| Project-level risk dashboard | P0 |
| Pending financial exposure view | P0 |
| Overdue and upcoming approval view | P0 |
| Evidence-linked event timeline | P0 |
| Export change-order package as PDF | P1 |
| Export project risk report | P1 |

### F7. AI assistance

| Requirement | Priority |
|---|---|
| Answer project questions using retrieved evidence | P1 |
| Cite every factual answer | P0 |
| Refuse unsupported conclusions | P0 |
| Draft change-order narratives | P1 |
| Summarize evidence packages | P1 |
| Recommend next investigation steps | P2 |

---

## 7. Functional requirements

### Document types supported in MVP

| Type | Examples | Extracted fields |
|---|---|---|
| Contract | Main contract, subcontract | Parties, value, dates, key clauses |
| BOQ | Bill of quantities | Item, description, unit, quantity, rate, amount |
| Drawing | Architectural, structural, MEP | Drawing number, revision, title, date |
| RFI | Request for information | RFI number, subject, question, response, status |
| Change order | CO, variation order | Number, description, cost, schedule impact, status |
| Daily report | Site diary | Date, weather, workforce, activities, delays |
| Site photo | Site image | Date, location, visible issue, linked report |
| Email | Project communication | Sender, recipients, date, subject, extracted events |
| Quotation | Supplier or subcontractor quote | Supplier, items, quantities, rates, validity |

### Change-order statuses

- `potential`
- `under_review`
- `drafted`
- `submitted`
- `approved`
- `rejected`
- `disputed`
- `closed`

### Risk severity

- `low`
- `medium`
- `high`
- `critical`

### Evidence confidence

- `verified`
- `high`
- `medium`
- `low`
- `insufficient`

---

## 8. User stories

### Project manager

- As a project manager, I want to see all pending change orders in one place so that I can prevent delays.
- As a project manager, I want overdue approvals highlighted so that I can act before deadlines.
- As a project manager, I want each risk linked to evidence so that I can trust the alert.

### Commercial manager / QS

- As a QS, I want cost impacts linked to BOQ items so that I can validate claims.
- As a QS, I want duplicate claims flagged so that I do not approve the same cost twice.
- As a QS, I want a draft change-order package so that I spend less time collecting evidence.

### Site engineer

- As a site engineer, I want to upload photos and daily reports quickly so that site events are recorded.
- As a site engineer, I want the system to link my report to the relevant project activity so that later claims are easier to support.

### Owner

- As an owner, I want to see total pending exposure across projects so that I can understand commercial risk.
- As an owner, I want to know which projects have the highest unresolved change-order risk.

---

## 9. Success metrics

### Product metrics

| Metric | MVP target |
|---|---|
| Document classification accuracy | >= 90% |
| Critical field extraction accuracy | >= 85% |
| Evidence-link coverage for generated risks | >= 95% |
| Unsupported AI factual claims | 0 |
| Human override rate | Track and reduce over time |
| Median time to build change-order package | Reduce by 50% |
| Pilot user retention after 30 days | >= 60% |

### Business metrics

| Metric | Target |
|---|---|
| Paid pilot customers | 2–3 |
| Projects onboarded | 3–5 |
| Documented time saved per project per week | >= 2 hours |
| Missed or late change-order events identified | Track case studies |
| Pilot-to-paid conversion | >= 1 customer |

---

## 10. Pricing hypothesis

Do not finalize pricing before validation. Test the following models:

### Option A: Project-based subscription

- BDT 15,000–40,000 per active project per month.
- Includes document processing, risk dashboard, and change-order workflow.

### Option B: Company subscription

- BDT 50,000–150,000 per month depending on number of projects and users.
- Includes multi-project dashboard, roles, reporting, and support.

### Option C: Pilot pricing

- Fixed-price 30-day pilot for one project.
- Includes onboarding, document ingestion, risk review, and a final report.
- Converts into subscription if measurable value is demonstrated.

---

## 11. MVP acceptance criteria

The MVP is complete when:

1. A user can create a project and upload supported documents.
2. Documents are processed, classified, and indexed with source references.
3. The system creates a project timeline from extracted events.
4. The system detects at least five categories of risk.
5. Every AI-generated risk includes evidence links.
6. The system can generate a human-reviewable change-order draft.
7. Users can approve, reject, or edit system recommendations.
8. All approvals and AI decisions are recorded in an audit trail.
9. The dashboard shows pending exposure and overdue actions.
10. The system passes the MVP test plan with no critical security or data-integrity defects.

---

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Poor-quality scans and photos | Low extraction accuracy | Human review queue, image preprocessing, confidence thresholds |
| Inconsistent construction terminology | Wrong entity linking | Domain dictionary, synonyms, human corrections, feedback loop |
| LLM hallucination | Loss of trust | Citation enforcement, schema validation, deterministic calculations |
| Sensitive commercial data | Security and trust risk | Tenant isolation, encryption, access control, audit logs |
| Users unwilling to change workflow | Low adoption | Start with upload + dashboard, avoid forcing full workflow replacement |
| No access to real project data | Product becomes theoretical | Secure pilot agreements, anonymized datasets, synthetic-but-realistic fixtures |
| Overbuilding before validation | Wasted year | Validate with 20 interviews and 2–3 pilot commitments before deep build |

---

## 13. Open questions

1. Which contractor segment has the fastest willingness to pay?
2. What is the minimum document set required to produce useful change-order intelligence?
3. Should the MVP begin with email ingestion or manual upload only?
4. Should cost calculations be visible to all project users or restricted to commercial roles?
5. Which existing tools must the system integrate with first?
6. What is the acceptable latency for processing a 100-page contract?
7. What evidence is legally required for a claim in the target market?

---

## 14. Immediate next actions

1. Interview 20 construction professionals.
2. Collect 3–5 anonymized project document samples.
3. Define the exact MVP document types.
4. Validate pricing with 5 potential buyers.
5. Build the ingestion and document-registry foundation.
6. Create 20 golden test cases from real or realistic project packets.
