# ChangeGuard — Project Memory

**Version:** 0.1  
**Date:** October 27, 2026  
**Purpose:** Preserve product context, decisions, constraints, and lessons so future development remains coherent.

This file is the project’s long-term memory. Update it after every major decision, interview, pilot, failure, or architecture change.

---

## 1. Project identity

**Project name:** ChangeGuard  
**Working tagline:** Evidence-backed change-order and project-risk intelligence for construction teams.

**What it is:**

An AI-powered system that ingests fragmented construction project evidence and turns it into a traceable timeline of scope, cost, schedule, and responsibility.

**What it is not:**

- Not a generic document chatbot.
- Not a legal-advice tool.
- Not an ERP replacement.
- Not an autonomous contract-approval system.
- Not a generic research agent.

---

## 2. Founder context

**Builder:** Mutassim Al Shahriar Zeem  
**Background:** EEE student with Python, ML, backend, and AI Development.  
**Strategic advantage:** Combining electrical/embedded systems knowledge with AI systems engineering.

**Career positioning:**

> AI Systems Engineer specializing in agentic automation, AI reliability, and edge/industrial intelligence.

**Portfolio goal:**

Build one deep, commercially valuable system that proves the ability to take a messy real-world problem from discovery to deployed, evaluated, and measurable AI system.

---

## 3. Core product thesis

Construction contractors lose money because project evidence is fragmented.

The expensive problem is not document storage. It is:

> “Can we detect what is changing, connect it to evidence, understand its cost and schedule impact, and act before it becomes a dispute?”

ChangeGuard’s value comes from:

- Early detection of potential changes.
- Evidence-linked change-order packages.
- Missing-document detection.
- Duplicate and conflict detection.
- Approval-deadline tracking.
- Pending financial and schedule exposure.
- Human-approved workflows.

---

## 4. Target customer

### Initial beachhead

Mid-sized construction contractors in Bangladesh.

Priority segments:

- General contractors.
- MEP contractors.
- Fit-out contractors.
- Civil contractors.

### Ideal pilot customer

- 5–30 active projects.
- Multiple project managers and site engineers.
- Frequent RFIs, change orders, subcontractor coordination, and approvals.
- Existing pain from delayed approvals, missed changes, or disputes.
- Willing to provide anonymized project documents for a pilot.

---

## 5. Product boundaries

### In scope

- Project and document management.
- OCR and document extraction.
- Document classification.
- Structured field extraction.
- Entity and event extraction.
- Evidence-linked retrieval.
- Risk detection.
- Change-order workflow.
- Human approval.
- Audit trail.
- Project dashboard.
- Evidence-grounded Q&A.

### Out of scope for MVP

- Full ERP replacement.
- Autonomous client communication.
- Autonomous approval.
- Legal advice.
- Equipment control.
- Full accounting.
- Every document format.
- Enterprise SSO and compliance certifications.

---

## 6. Non-negotiable product principles

1. **Evidence first.** No claim without a source.
2. **No silent AI errors.** Low confidence enters review.
3. **Humans approve consequential actions.**
4. **Deterministic systems calculate money and deadlines.**
5. **Tenant isolation is absolute.**
6. **Original evidence is immutable.**
7. **Every AI action is traceable.**
8. **The system must say “insufficient evidence” when appropriate.**
9. **The workflow must be useful even if AI accuracy is imperfect.**
10. **Pilot before deep build.**

---

## 7. Current strategic decision

The current primary product bet is:

> **AI evidence-and-change-order intelligence for mid-sized construction contractors.**

Secondary candidate:

> **Freight exception and document-reconciliation copilot for small and mid-sized freight brokerages.**

Do not switch direction without:

- At least 20 discovery interviews.
- Evidence of willingness to pay.
- Access to real workflow data.
- A clear reason the current direction cannot work.

---

## 8. Discovery questions

Use these during customer interviews.

### Workflow questions

1. What takes the most time every week?
2. What information do you repeatedly search for?
3. Which decisions are difficult or delayed?
4. What work is still manual?
5. What gets copied between spreadsheets, email, and WhatsApp?
6. What information is trapped in PDFs, photos, or email threads?
7. What happens when someone misses a deadline or loses a document?

### Change-order questions

1. How many change orders do you handle per month?
2. How long does a typical approval take?
3. What causes delays in approval?
4. What documents are required to support a change?
5. What evidence is often missing?
6. How do you detect a scope change before it becomes formal?
7. Have you lost money because of a missed or poorly documented change?
8. How do you handle disputes?
9. Who owns change-order follow-up?
10. What tools do you currently use?

### Buying questions

1. Who would approve a purchase?
2. What budget exists for project-management or document tools?
3. What would make this worth paying for?
4. What would make you stop using it?
5. Would you participate in a 30-day pilot?
6. What outcome would justify renewal?

---

## 9. Validation log

| Date | Person / company | Segment | Key pain | Evidence | Willingness to pay | Next step |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

Add one row for every interview. Do not rely on memory.

---

## 10. Technical memory

### Current architecture decisions

- Modular monolith.
- FastAPI + PostgreSQL + Redis + Celery.
- PostgreSQL full-text search plus pgvector.
- Object storage for immutable originals.
- Background workers for document processing.
- Model gateway for LLM calls.
- Evidence links as first-class entities.
- Human approval workflow.
- Evaluation suite as release gate.

### Core domain entities

- Tenant.
- User.
- Project.
- Document.
- DocumentChunk.
- ProjectEvent.
- Contract.
- ContractClause.
- BOQItem.
- RFI.
- ChangeOrder.
- Risk.
- Approval.
- EvidenceLink.
- AuditEvent.
- AITrace.

### Core workflows

- Upload and process document.
- Extract and validate fields.
- Link document to project entities.
- Detect risk.
- Create potential change.
- Build evidence package.
- Generate draft.
- Human review.
- Approve or reject.
- Track exposure.

---

## 11. Known risks

| Risk | Current mitigation |
|---|---|
| No access to real project data | Conduct interviews and secure pilot agreements early |
| Poor document quality | Review queue, image preprocessing, confidence thresholds |
| LLM hallucination | Citations, validation, deterministic calculations |
| Prompt injection | Treat documents as untrusted data, restrict tools |
| Complex construction terminology | Domain dictionary, feedback loop, human corrections |
| Low adoption | Start with upload and dashboard, avoid forcing workflow replacement |
| Overbuilding | Pilot-first development plan |
| Security failure | Tenant isolation, RBAC, audit, security tests |

---

## 12. Lessons learned

Record lessons here as the project progresses.

| Date | Lesson | Evidence | Change made |
|---|---|---|---|
|  |  |  |  |
|  |  |  |  |
|  |  |  |  |

---

## 13. Weekly memory update template

Add this every Friday.

```text
## Week of YYYY-MM-DD

### What was built
-

### What was learned
-

### What failed
-

### Customer evidence
-

### Metrics
-

### Decisions made
-

### Next week
-
```

---

## 14. Pilot memory template

For each pilot customer, maintain:

```text
## Pilot: [Company]

### Contact
- Name:
- Role:
- Email:
- Decision maker:

### Projects onboarded
-

### Documents processed
-

### Key workflows
-

### Baseline metrics
- Manual evidence-gathering time:
- Approval cycle time:
- Missed change events:
- Dispute exposure:

### Pilot results
-

### Failures
-

### Customer quotes
-

### Renewal / payment signal
-

### Product changes required
-
```

---

## 15. Long-term ambition

By the end of the year, ChangeGuard should demonstrate:

1. A working product used by real construction teams.
2. Measurable time saved and risk visibility.
3. Evidence-backed AI outputs suitable for commercial review.
4. A defensible technical architecture.
5. At least 2–3 documented case studies.
6. A clear path from pilot to paid subscription.
7. A portfolio asset that proves advanced AI systems engineering ability.
