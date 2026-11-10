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
