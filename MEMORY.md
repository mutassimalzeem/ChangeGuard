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

## 2026-11-10: Daily report vertical slice

Repository inspection found uploads, immutable originals, Celery stages, OCR,
classification, strict grounded fields, potential-change events, evidence and a
deterministic risk engine already implemented. Reused those systems.

Implemented:

- Migration `0015_project_metadata`: persist client name, contract value and
  stakeholders; repair timestamp serialization and authenticated creator membership/
  audit handling. Financial fields remain permission-protected.
- Strict closed Pydantic event validation before event/evidence persistence.
- `daily_report_delay_without_link`: evidence-backed daily-report delay with no
  explicit linked RFI/change order. Links to the event and original, null impacts,
  insufficient_evidence when provenance/confidence is inadequate. Such risks cannot
  be accepted merely because an original-file link exists.
- `GET /api/v1/projects/{id}/timeline`: chronological events/risks with complete
  source visibility checks and pagination, plus the frontend timeline using real
  quotations/pages, signed-original access and five-second refresh.
- Audit records for upload, document deletion, processing outcomes and risk
  creation; server-generated upload request IDs propagate into worker audits.
- Unit/integration/contract tests including PDF/image worker stages, retries,
  tenant/project/restricted/deleted-source access and insufficient evidence.

Plan: `tasks/plan.md`. File map, deployment compatibility, manual verification and
known limitations: `docs/DAILY_REPORT_SLICE.md`.

Validation: full backend 914 passed / 13 skipped / 10 failed, with every failing
test ID reproduced on unchanged starting commit `9184f006` (its project module had
19 failures). No test/access controls were weakened. Focused backend 136 passed;
final new integration module 7 passed, including PDF/image worker execution and
insufficient-evidence rejection. Frontend 20 passed; typecheck/lint/production
build, focused Ruff, pip check and whitespace checks passed. Isolated Chrome
verified risk/evidence UI with intercepted API fixtures and zero runtime console
errors. PostgreSQL/pgvector was real; storage/model/OCR/broker boundaries were
faked in the new integration tests. Temporary test servers stopped afterward.

Remaining: live broker/storage/model/OCR deployment verification; automatic risk
resolution after later linking; deliberate historical backfill; broader language
and project-packet evaluation. Original create-only storage still requires bucket
retention/admin controls. Timeline follows existing commercial-read permissions.

## 2026-11-10: Backend contract and baseline-test repairs

Scope: repair the six reported failure areas without adding features or weakening
tenant, membership, financial, audit or human-approval controls. Reproduced the
starting project's 10 failures before editing.

| Area | Root cause | Fix and regression coverage |
| --- | --- | --- |
| Error envelopes | Domain exceptions used `error`, HTTP/framework validation used `detail`, and authentication constructed its own responses. Tests incorrectly treated a validation error list as a string. OpenAPI also advertised the old `HTTPValidationError` contract. | Shared `error_responses.py` supplies `{error: {code, message, details}}` for domain, HTTP, authentication and validation failures; OpenAPI 422 uses the same envelope. Preserve statuses and `WWW-Authenticate`/`Retry-After` headers. Generic validation details contain location/type and safe messages, never rejected input, body, context or custom exception text. Authentication responses remain generic and non-enumerating. Regression tests cover 401/404/405/409/422/429/500, header preservation, OpenAPI and secret reflection through custom validators. |
| Project list fixtures | Pagination/search/status fixtures inserted projects without assigning the non-admin caller. Correct membership filtering returned no rows, and the status test could pass vacuously on an empty list. | A fixture inserts active memberships in the proper tenant/project. Tests retain exact pagination/search assertions and now require an actual matching status result. Production membership filters are unchanged. |
| Own-tenant project creation | A test expected a caller from another fixture tenant to be forbidden from creating in their own authenticated tenant, despite the request containing no foreign tenant target. Its JWT helper also supplied token version in the roles argument. | Correct the helper to pass roles and keyword version. Assert creation in the caller's tenant and subsequent membership-protected access; add a rejected foreign `tenant_id` override case. Production tenant assignment remains derived exclusively from the authenticated user. |
| Project deletion | Tests expected project managers to hard-delete despite lacking delete permission and the policy/ORM requiring human approval. The service attempted a success audit/delete rather than reporting that policy outcome. | The service checks existing project policy before any mutation and returns 409 with `human_approval_required` for permitted owners/admins; unauthorized roles remain 403 and inaccessible/missing projects remain concealed. Keep the ORM guard. Tests verify project retention, no false success audit, rejection of self-declared confirmation, and service/ORM enforcement. No approval workflow was added: execution stays blocked until verified approval infrastructure exists. |
| Dates | A fixture assigned an ISO string directly to an ORM Date column. Pydantic already parses API dates, but PATCH validation only considered dates supplied together and missed conflicts with stored dates. | Convert fixture strings with `date.fromisoformat`. Before mutating a project, validate the merged incoming/persisted date pair. Tests verify typed ORM dates, start-only/end-only invalid ranges, atomic rejection and explicit null versus omitted dates. |
| Audit reads | Audit assertions queried using the request's project-manager session, which correctly lacks `audit.read`. | Read assertions through a separate, authenticated admin session on the test transaction, keeping the production audit guard unchanged. Add denial assertions for ORM rows, scalar IDs and aggregates from a project manager who otherwise has project access. Positive audit assertions still verify actor and recorded changes. |

Compatibility: clients must consume the canonical `error` envelope; validation
issues are under `error.details.errors`. The existing frontend recognizes the
`error` envelope. Authentication failure commits, no-store headers, rate limiting,
permissions and secret-redaction protections remain intact. No migration or new
feature is required.

Final validation: **942 passed, 13 skipped, zero failures** in the full backend
suite against a disposable pgvector PostgreSQL database, with all migrations
applied. The existing 13 skips cover unconfigured live MinIO/Redis integrations
and unavailable native OCR tools; no skip was added. Focused Ruff, `pip check`,
`git diff --check` and staged whitespace checks passed. Test temporary files used
the workspace `.tmp` directory. The disposable database container was stopped;
existing developer containers/databases were left unchanged.
