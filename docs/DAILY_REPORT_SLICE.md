# Daily report vertical slice

Implemented 2026-11-10. Plan: [tasks/plan.md](../tasks/plan.md).

## Existing functionality reused

The starting repository already contained project APIs, the document registry,
create-only S3-compatible originals (`IfNoneMatch="*"`), checksum verification,
Celery dispatch/recovery and durable stage checkpoints, PDF/image text extraction,
rule-first classification, strict grounded document fields, potential-change
events, evidence links, deterministic risk storage and audited human decisions.
Migrations 0001–0014 provide those foundations. This change connects them rather
than introducing another upload service, worker or model integration.

## Changes and file map

| Area | Files | Behavior |
| --- | --- | --- |
| Project persistence | `backend/alembic/versions/0015_project_metadata.py`, `backend/app/domain/models/foundation.py`, `backend/app/domain/schemas/project.py`, `backend/app/domain/services/project_service.py` | Persist client, contract value and stakeholders; serialize timestamps correctly; scoped reload after update; creator membership and audit. |
| Event contract | `backend/app/domain/services/potential_changes.py` | Closed, strict Pydantic `ExtractedEvent`; validate the whole batch before persistence; existing grounded detector and evidence links retained. |
| Delay rule | `backend/app/domain/services/risk_engine.py`, `backend/app/domain/services/risks.py` | `daily_report_delay_without_link`; attach event and original evidence, leave impacts null, prevent acceptance of insufficient evidence. All new review-only findings retain a link to their triggering original. |
| Auditing | `backend/app/domain/services/audit.py`, `backend/app/domain/services/document_service.py`, `backend/app/document_processing/pipeline.py`, `backend/app/policy/scope.py`, `backend/app/api/v1/routes/documents.py` | Narrowly checked user audit appends; upload/delete, every executed stage outcome and risk creation; server request ID crosses the worker boundary; no source text in these audit details. |
| Timeline API | `backend/app/domain/schemas/timeline.py`, `backend/app/domain/services/timeline.py`, `backend/app/api/v1/routes/timeline.py`, `backend/app/api/v1/router.py` | Chronological events and risks with actual source snippets/pages; tenant, membership and complete-source visibility checks. |
| Frontend | `frontend/src/components/project-timeline.tsx`, `frontend/src/app/projects/[projectId]/page.tsx`, `frontend/src/lib/contracts.ts`, `frontend/src/lib/api/resources.ts` | Live API timeline, five-second polling, evidence disclosure, signed-original action, pagination and loading/error/empty states; removes fabricated contract verification text. |
| Tests | `backend/tests/test_daily_report_slice.py`, `backend/tests/test_daily_report_integration.py`, `frontend/src/test/timeline.test.ts` | Rule boundaries, schema rejection, owner/PM create-upload flow, PDF/image worker checkpoints, replay, audits, source access and wire contracts. |
| Documentation | `tasks/plan.md`, `tasks/todo.md`, `MEMORY.md`, this file | Scope, implementation, verification and remaining work. `.gitignore` excludes local `.tmp/` validation artifacts. |

## Data flow and risk semantics

1. The authenticated creator becomes a member of the new project.
2. Upload reserves a tenant/project-scoped registry row and writes the original
   once. A failed queue publish leaves a recoverable queued row.
3. Celery runs the existing extraction/classification/validation/index/link/risk
   stages. Rule-first event extraction uses text blocks with original page numbers.
4. A daily report delay event with no linked RFI/change order produces the rule.
   A change order whose `source_event_id` is that event also suppresses the rule.
5. Source quotations and a page plus confidence of at least 0.7 are required for
   an open delay risk. Otherwise it is `insufficient_evidence`, links the original
   for review, and cannot be accepted or overridden as supported evidence.
6. Cost/schedule suggestions in existing events are copied only from explicit
   source labels by deterministic code. The new delay risk estimates neither
   financial exposure nor schedule impact. Models only classify/explain.

The absence statement concerns linked records in ChangeGuard at processing time.
It does not assert that no RFI or change order exists outside the system.

## API contract

`GET /api/v1/projects/{project_id}/timeline?offset=0&limit=50`

Requires authentication, project access, `documents.read` and `financial.read`,
consistent with existing risk/potential-change APIs. Another tenant or unassigned
user receives 404. Restricted or deleted evidence hides the entire derived item.

The response contains `items`, `offset`, `limit`, `has_more`. Items contain:
`id`, `kind` (`event` or `risk`), `occurred_at`, `title`, `description`, `event_type`,
`status`, `confidence`, `severity`, `evidence_status` and `evidence`.
Evidence uses the existing `EvidenceRead` contract, including `evidence_link_id`,
`source_type`, `source_id`, `source_page`, `source_text_snippet` and ownership.
Ordering is ascending by time, kind and UUID. Limits are 1–100; offset is at most
10,000. Pagination advances over candidate records; hidden entries can leave a
shorter or empty page. No hidden IDs or source content is returned.

## Migration and compatibility

Run `.venv/Scripts/python.exe -m alembic upgrade head` from `backend`.
Migration `0015_project_metadata` adds `client_name`, `contract_value` and
`stakeholders`. Existing projects receive `client_name="Unspecified"`; historical
client/value/stakeholder inputs were not persisted and cannot be reconstructed.
Apply the migration before deploying the backend; restart API and workers.
Downgrade removes these three fields and loses their data.

The timeline endpoint is additive. Existing upload, risk and potential-change
routes remain available. Project timestamps remain ISO datetime strings on the
wire. Contract value remains permission-protected and is null for nonfinancial
readers. The client now needs the timeline endpoint deployed with it.

## Manual verification

1. Configure PostgreSQL with pgvector, Redis/Celery, an S3-compatible bucket and
   the existing OCR/model/embedding providers using `.env.example`. Use a free
   PostgreSQL port if a native server already occupies 5432. Create the configured
   bucket through the storage console. See document-processing/extraction and
   gateway READMEs for native OCR dependencies and provider configuration.
2. Apply migrations with `.venv/Scripts/python.exe -m alembic upgrade head` from
   `backend`. Start the API and the existing Celery worker plus beat/recovery as
   described in the root README / Docker Compose configuration.
3. Start the frontend with `npm run dev`. Sign in as an owner or project manager.
   Create a project with client, currency and contract value. Reload and verify
   those fields survive. Do not use the frontend's demo login for live backend tests.
4. Upload a PDF or an image containing a clear daily report, for example:

   ```text
   Daily Report
   Report date: 2026-11-10
   Activities: Steel erection.
   Work was delayed by late steel delivery.
   ```

5. Verify the object key is under the correct tenant/project and its SHA-256
   matches the registry. Attempting a second create at the same key must fail.
   Re-uploading identical bytes to the same project should return 409.
6. Watch document status progress asynchronously. A detected risk intentionally
   ends in `review_required`. Open the project's Timeline tab; it refreshes every
   five seconds and should show a delay event and the unlinked-delay risk.
7. Expand **Inspect evidence**. Confirm the quotation matches the original and
   the page is correct. **Open original** obtains a permission-checked signed URL.
   No invented amount, schedule effect or contract verification should appear.
8. Repeat with “No delay occurred” and a hypothetical “Work might be delayed”.
   Neither should produce a deterministic delay assertion. Low/uncertain evidence
   should enter review. A page-less delay signal must be `insufficient_evidence`.
9. In a fresh processing case, link the report to an RFI/change order (or create
   a change order from the event); verify the rule is suppressed. Existing risk
   snapshots still need human review; automatic resolution is not included.
10. Try another tenant, a project nonmember and a member without access to a
    restricted report. Confirm no derived event, risk or quotation leaks.
11. Inspect audit records as an authorized auditor: `project.create`,
    `document.upload`, `document.processing`, `risk.create`, existing risk decision
    events, and `document.delete` when applicable. Correlate worker audit request IDs
    with the upload response's server-generated `X-Request-ID`.

## Automated verification

Use a disposable test server via `TEST_DATABASE_ADMIN_URL`; tests create/drop a
UUID-named database and run the full migration chain. Provider and object-storage
boundaries in the new worker test are fakes; PostgreSQL/checkpoints/access controls
are real. The test covers both PDFs and images and terminal duplicate delivery.

```powershell
# From backend, with TEST_DATABASE_ADMIN_URL set to the disposable pgvector server:
.venv/Scripts/python.exe -m pytest tests/test_daily_report_integration.py tests/test_daily_report_slice.py tests/test_risk_engine.py tests/test_risks.py tests/test_processing_pipeline.py tests/test_documents.py tests/test_authorization.py -q
.venv/Scripts/python.exe -m pip check
# From frontend:
npm test
npm run typecheck
npm run lint
npm run build
```

Validation performed on 2026-11-10:

- Full backend suite: **914 passed, 13 skipped, 10 failed**, no fixture errors.
  Temporary files were directed into the workspace to avoid Windows sandbox
  permissions on the default pytest temp directory.
- All 10 failing test IDs also fail on unchanged starting commit
  `9184f006027d32ffd0947557ce1639457bee843f` (19 failed, 14 passed in its project
  test module). Remaining failures concern error-envelope expectations, project
  list fixtures without membership, creation in the authenticated user's own
  tenant, deletion without human approval, date strings assigned directly to ORM
  Date fields and audit queries made without audit-read permission. The baseline
  comparison used an archived checkout and the same disposable PostgreSQL server.
- Focused backend checks: **136 passed**; the final new integration module,
  including an additional insufficient-evidence decision regression, **7 passed**.
- Frontend: **20 tests passed**, typecheck, lint and production build passed.
- Isolated Chrome checked production-page login, timeline navigation, risk text,
  evidence disclosure, stored quotation and page number with controlled API
  fixtures: **passed, zero runtime/console errors**.
- Focused Ruff, `pip check` and `git diff --check`: passed.

Live PostgreSQL/pgvector ran in a disposable container. The existing developer
database was not migrated or modified. Temporary test servers were stopped after
verification. These results do not claim a live external-provider/broker/storage
end-to-end deployment test.

## Known limitations

- Live OpenAI/embedding/OCR-provider calls, a real Celery broker delivery and live
  MinIO/S3 were not exercised by the new integration test. Their boundaries use
  controlled fakes; separate deployment verification remains necessary.
- Browser verification uses the production frontend with intercepted API fixtures,
  not a live authenticated backend. It checks timeline/evidence interaction and
  runtime console errors; backend contracts/access are tested separately.
- Rule extraction is conservative English pattern matching with the existing
  optional model fallback. It does not infer missing delays, identify critical
  path effects or calculate exposure.
- Links are explicit document/entity relationships or change orders sourced from
  events. No fuzzy matching of unlinked RFIs/change orders is added.
- Risks are processing-time snapshots. Later linking does not automatically close
  an existing risk; use the audited review flow. Historical documents need
  deliberate reprocessing/backfill to acquire this new rule's risks and audits.
- Timeline follows existing financial-read permission requirements. Site engineers
  can upload, but risk/timeline review needs a permitted commercial role.
- Create-only application storage prevents overwrites through this application;
  bucket administration, retention and Object Lock policies remain deployment work.
- Existing project tests contain baseline failures; they are documented with an
  unchanged-starting-commit comparison. No access controls or tests were weakened.
