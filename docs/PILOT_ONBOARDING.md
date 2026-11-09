# 8.1 Pilot onboarding

Build order: template creation → bounded ZIP import → document review → readiness/PDF → customer UI.

- Create a new, empty construction pilot from a versioned template; never seed fake evidence.
- ZIP imports use the existing registry, duplicate detection, quarantine and queue. Limit compressed input to 50 MiB, 100 entries, 200 MiB expanded and 50 MiB per member. Reject unsafe paths, links, encrypted files and nested ZIPs before uploading anything. Return per-member outcomes; retry skips duplicates.
- Poll actual document processing states. Human type reviews preserve the original prediction. Extraction corrections are an audited human overlay with the original source envelope preserved; they do not silently rewrite downstream financial commitments.
- Accuracy = original prediction matches human-confirmed type / reviewed classifications. No reviews means unknown. Confidence remains model confidence, never raised by manual edits.
- Readiness includes processed/total, review coverage, accuracy, average extraction confidence, open risks, missing required document categories, overdue pending approvals and pending change-order exposure grouped by currency. Unknown amounts are counted separately.
- Report reads require financial.read; document operations require documents.read/write and existing project scope. Restricted documents retain their visibility rules.
- PDF uses the same report snapshot, escaped content and pagination. Checklist is stored server-side with actor audit, and customer guidance explains each step.

Validation: archive adversarial tests, report arithmetic/unknown-data tests, scoped API tests, PDF text verification, frontend contracts/typecheck/lint/build. No new dependencies. Apply migration 0014_pilot_onboarding before deployment.

## Customer walkthrough

1. Open **Pilot onboarding**, enter your project name and currency, and create from the construction template. Return to this page to continue an existing pilot.
2. Gather your signed contract, BOQ and current drawings. Confirm scope and participants with your team using the saved checklist.
3. Import a ZIP. Each member appears with its own processing state. A rejected file is quarantined; a duplicate is skipped. Correct the source file before uploading a replacement with different content.
4. When processing reaches `linked` or `review_required`, expand each document. Confirm its type, correct facts against the original, include the page and quotation, and explain your changes. A stale review is rejected: refresh and review the latest version.
5. Review readiness with your project/commercial manager, resolve missing evidence and approvals, then export the PDF and agree next steps. An unchecked checklist item or unknown metric is not a pass.

Type corrections preserve the classifier's prediction. Extraction corrections are a human-reviewed overlay, preserve the original output and confidence, and do not re-run linking/risk detection or change financial records. If the corrected type differs from the extraction schema, the old fields cannot be submitted under the new schema. Financial readers can inspect extraction fields; other document readers see processing/type metadata only.

Missing evidence currently means absent contract, BOQ or drawing documents among visible, non-failed/non-quarantined records. It is not a legal completeness assessment. Processing completion counts `linked`; `review_required` remains visibly pending human review. Readiness is a snapshot and does not assert that the project is approved to launch.

## API and deployment

- `GET /api/v1/pilot/templates`: versioned template catalog.
- `GET/POST /api/v1/pilot/projects`: resume accessible pilots (most recent 100) or create a project with creator membership.
- `POST /api/v1/pilot/projects/{id}/zip`: bounded import with per-member HTTP status outcomes; validates the archive before writing members. A disconnected request may have imported some members; retry safely skips duplicates.
- `GET /api/v1/pilot/projects/{id}/documents`: polling metadata and authorized extraction overlays.
- `PATCH /api/v1/pilot/documents/{id}/review`: optimistic document version, corrected type/typed fact fields, mandatory reason, and append-only actor/request audit.
- `GET/PUT /api/v1/pilot/projects/{id}/checklist`: durable shared checklist.
- `GET /api/v1/pilot/projects/{id}/readiness[.pdf]`: financial-reader report/PDF, currency-separated decimal exposure and explicit unknown amounts.

Apply `alembic upgrade head` before starting the new API. Migration `0014_pilot_onboarding` adds one tenant/project-scoped table and timestamp trigger. No dependencies or existing endpoint contracts change. Rollback: deploy the previous application version; retain pilot state, or downgrade to `0013_change_order_workflow` only after backing up the checklist data.

## Validation evidence

- Full backend run without external services: 558 passed, 336 skipped (database/integration dependencies unavailable); a later pilot-list test adds one additional database-dependent case.
- Focused pilot/schema suite on disposable PostgreSQL: includes the real 0014 migration, tenant/project membership, restricted documents, ZIP outcomes/retries, extraction overlays, report arithmetic and API financial denial. `PILOT_SCHEMA_ONLY=1` creates unrelated parent tables from metadata because local PostgreSQL lacks pgvector; this does not verify migrations 0001–0013.
- Frontend: 17 tests, TypeScript, ESLint and production build.
- Headless Chrome smoke check with mocked API: create pilot, document progress, readiness, saved checklist, extraction fields, mobile overflow and no runtime exceptions. PDF content is parsed with pypdf.
- Live MinIO, Celery/Redis processing and provider calls remain unverified. ZIP service tests mock storage and queue publication.
