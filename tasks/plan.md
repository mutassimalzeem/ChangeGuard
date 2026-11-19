# Daily report to evidence-backed timeline

## Repository inspection (2026-11-10)

Read PRD, ARCHITECTURE, DESIGN, TEST_PLAN, SECURITY, DECISIONS and MEMORY.
Existing migrations 0001–0014 provide projects, immutable S3 originals, Celery
checkpoints/recovery, OCR, classification, grounded structured fields, project
events, evidence, deterministic risks and human review. Reuse these components.
The timeline currently reads potential changes and shows invented evidence text.
Project create/read schemas also require fields absent from the database model.

## Implementation order

1. Repair project persistence/serialization and narrowly authorize its audit and
   creator membership writes. Add migration 0015 for missing project metadata.
2. Validate extracted events with a strict closed Pydantic schema before writes.
   Detect a daily-report delay without a linked RFI/change order, using existing
   events and evidence. No estimated cost or schedule impact. Missing provenance
   yields insufficient_evidence with a link to the report for review.
3. Add bounded, chronological GET /projects/{id}/timeline. Reuse source visibility
   and financial permissions; hide the whole item if any evidence is inaccessible.
4. Replace the frontend timeline with this API and actual source quotations/page
   references. Poll for background results and retain loading/error/empty states.
5. Add upload, processing and risk creation audit events, preserving request IDs
   and excluding raw source text from audit details. Retain existing review audits.
6. Run backend unit/integration tests, frontend tests/typecheck/lint/build,
   dependency checks and whitespace review. Record results, manual steps and
   limitations in docs and repository MEMORY.md.

## Acceptance and boundaries

- A new project and uploaded PDF/image reach the existing worker stages and a
  delay risk is returned with real evidence through the timeline API.
- Retries do not duplicate events/risks; links to RFIs/change orders suppress the rule.
- Tenant/project membership and restricted/deleted sources are checked on reads.
- Negative/hypothetical delay statements do not create deterministic delay events.
- Insufficient provenance never becomes a confident alert. Unknown impact stays null.
- Existing original object immutability, gateway isolation and OCR providers remain.

## Verification

Use backend/.venv/Scripts/python.exe -m pytest and frontend npm scripts.
Integration tests use a UUID-named disposable PostgreSQL database and external
provider fakes. Live Celery/Redis/MinIO/provider verification is reported separately.
See docs/DAILY_REPORT_SLICE.md for the final file map and manual procedure.

## Operational Review Queue delivery

Inspection of main at `7e4a7d4` and closed PRs #29–30 found an existing project-scoped list, six risk/extraction categories, authorized evidence reads, risk decisions, change-order draft conversion and a separate approval workflow. The list had a client-side type filter and lacked paging, a reviewer roster, notes, assignments, high-value and approval rows and manager-facing history. A separate worktree preserves local daily-delay changes.

1. Extend the scoped projection, state model and command contract. Reuse risk, extraction, change-order, evidence and audit services.
2. Connect the page to server filters, history and role-appropriate actions. Limit bulk selection to notes.
3. Exercise the pgvector workflow, frontend components, deployment procedure and GitHub CI.

The receipt index also updates `backend/app/domain/models/foundation.py`. Both Compose manifests and `.env.example` expose the optional currency map. The PDF integration assertion in `backend/tests/test_change_order_workflow.py` normalizes wrapped whitespace when it checks the complete decision reason.

Implementation files are `backend/alembic/versions/0018_review_workspace.py`, `backend/app/core/config.py`, `backend/app/api/v1/routes/review_queue.py`, `backend/app/domain/schemas/review_workspace.py`, `backend/app/domain/services/{audit,change_orders,review_queue,review_workspace,risks}.py` and `backend/app/policy/scope.py`. Frontend files are `frontend/src/app/review-queue/page.tsx`, `frontend/src/components/review-controls.ts`, and `frontend/src/lib/{review-queue,review-workspace}.ts`. Verification uses `backend/tests/test_review_queue.py`, `frontend/src/test/review-workspace.test.ts` and `.github/workflows/ci.yml`. The product, architecture, design, test, security, decision, deployment and memory documents describe the shipped workflow.
