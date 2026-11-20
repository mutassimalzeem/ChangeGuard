# Review Queue query profile

## Starting point and implementation plan

Inspection began at `ad94a6f` on `origin/main`. PR #30 had introduced draft conversion from the queue. PR #31 had already added the operational workspace, commercial approvals, assignment, notes, explicit per-currency thresholds and paginated responses. GitHub had no open PRs at inspection. The feature work used a separate worktree on `perf/review-visibility`.

1. Measure the merged API on synthetic PostgreSQL data with real JWT authentication, counting SQL statements per request.
2. Trace list construction, document access, linked commercial records, audit overlays, sort and pagination. Compare candidate hydration with a set-based source predicate in a single database snapshot.
3. Reuse project roles, domain workflow commands, extraction validation and the existing page contract. Recheck the same predicate for detail reads and locked commands.
4. Verify projection parity, revocation, pagination and audit behavior. Enforce latency and statement counts on the migrated database in CI.

## Profile

| Workload | Before, 500 items | After, 500 items | After, 10,000 items | Target at 500 |
| --- | ---: | ---: | ---: | ---: |
| First page | 30,059.28 ms / 3,861 SQL | 120.55 ms / 2 SQL | 300.18 ms / 2 SQL | <500 ms |
| Severity and confidence filter | 9,480.15 ms / 1,336 SQL | 196.06 ms / 2 SQL | 271.76 ms / 2 SQL | <750 ms |
| Inspect one risk with two citations | 103.60 ms / 11 SQL | 38.77 ms / 2 SQL | 120.35 ms / 2 SQL | <750 ms |

Timings are local HTTP p95 from a Windows Python 3.12 ASGI client and disposable PostgreSQL with pgvector. They include request authorization and response validation. Each operation had one warm-up, then three baseline samples (p95 is the maximum) or twenty optimized samples (nearest rank). Baseline inspection used the existing risk detail resource. Optimized inspection used the new workspace detail resource. Both returned the two expected quotations. Timings cover warm reads on a shared development host and exclude seed creation, external network latency, and browser rendering.

Each ten seeded items comprise six risks, two extraction tasks, a manually valued change order and its pending approval. Two documents and two chunks per item yield 1,000 documents at 500 items or 20,000 at 10,000. The seed includes restricted documents and chunks, soft deletions, indirect links, ties in creation time, structured extraction and audit notes. Each risk/order has two evidence links across separate documents. The benchmark independently derives the expected visible totals from the seed. The SQL count excludes fixture savepoint management.

**Before.** The workspace enumerated candidate IDs, called risk or commercial services per subject, checked individual sources, and resolved those sources again for quotations. Commercial reads also fetched and validated links more than once. Python sorted the resulting objects, including off-page evidence, before slicing. More selective filters reduced the number of candidates but preserved repeated reads.

**After.** One authentication read and one bound projection serve a request. The projection groups every linked source per subject, then filters and counts authorized candidates. It loads snippets, validated extraction evidence and audit history only for page subjects. A source that no longer resolves causes its subject to fail visibility. The 10,000-item first-page `EXPLAIN (ANALYZE, BUFFERS)` recorded 8.89 ms planning, 192.90 ms execution, 8,092 shared-buffer hits and zero temporary blocks read or written. Broad scans/hash joins process project-wide visibility once. Existing composite membership and evidence-subject indexes, source indexes and primary keys cover the joins. The profile did not justify an additional composite sort index or migration.

## Changed files

| Files | Responsibility |
| --- | --- |
| `backend/app/policy/review_page.sql`, `backend/app/policy/review_page.py`, `backend/app/policy/scope.py` | Fixed query, authenticated parameter binding and scope guard |
| `backend/app/domain/services/review_read.py`, `review_queue.py`, `review_workspace.py` (same directory) | Shared projection, extraction validation, legacy reads and locked command checks |
| `backend/app/api/v1/routes/review_queue.py` | Single-item workspace inspection |
| `backend/tests/conftest.py`, `backend/tests/test_review_visibility.py`, `backend/tests/test_review_queue.py` | Disposable committed transactions, access parity, filtering, stable pagination and workflow regression tests |
| `backend/tests/test_review_queue_performance.py`, `.github/workflows/ci.yml` | Seeded measurements and CI gates at both scales |
| `ARCHITECTURE.md`, `TEST_PLAN.md`, `DECISIONS.md`, `MEMORY.md`, `docs/REVIEW_QUEUE_PERFORMANCE.md` | Design, ADR-023, verification and results |

## Reproduce and verify

From `backend`, activate the backend environment and set `TEST_DATABASE_ADMIN_URL` to a disposable PostgreSQL/pgvector instance using the `postgresql+asyncpg` driver and an account with CREATEDB. Tests create and drop unique databases. PowerShell commands for the regression suites and both benchmarks follow.

```powershell
python -m pytest tests/test_review_visibility.py tests/test_review_queue.py tests/test_review_queue_authorization.py -q
$env:REVIEW_BENCHMARK = '1'
$env:REVIEW_SAMPLES = '20'
$env:REVIEW_ITEMS = '500'
python -m pytest tests/test_review_queue_performance.py -qs
$env:REVIEW_ITEMS = '10000'
python -m pytest tests/test_review_queue_performance.py -qs
```

Set `REVIEW_EXPLAIN_DIR` to an existing local directory to capture PostgreSQL JSON plans for synthetic data. To repeat the baseline, copy the benchmark file alone into a separate checkout at `ad94a6f`, set `REVIEW_BASELINE=1`, `REVIEW_ITEMS=500` and `REVIEW_SAMPLES=3`, then run it there. Clear baseline mode for the optimized gates.

1. In a test project, sign in as a manager with active membership. Load the workspace, inspect a quotation and its audit history, then compare with `GET /api/v1/projects/{project_id}/review-queue/workspace/{kind}/{item_id}`.
2. From a separate session, restrict one of two source documents uploaded by another user. Refresh the list and detail. Verify that the whole subject disappears, its count falls, and inspection returns 404. Repeat with a soft deletion. The regression suite also holds the writer transaction open to verify visibility before and after commit.
3. Remove the manager's membership and retry with the same token. Project reads return 404. Restore membership and downgrade the role to viewer. Commercial review returns 403.
4. With tied values and more than one page, filter by category or severity, change sort direction and step through the pages. Check exact totals, missing values last, and stable kind/UUID order for ties. Add a note to an authorized item and retry with the same command key. History contains one note.

## Deployment and limits

Deploy the backend normally. Existing workspace clients keep their page and inline quotation contracts. The projection uses the existing migrated schema. There is no backfill or authorization cache.

Statement count is bounded at both measured scales. An exact count still requires work proportional to matching project metadata and links. Inspections can also evaluate project-wide visibility metadata. Quotation and audit cost depends on the selected items' fan-out, and the legacy list can return every matching item. Separate offset-page requests can shift after a concurrent edit. Production latency under cold caches or sustained concurrent traffic was outside this benchmark. The next measurement should use pilot distributions across tenants, deep pages, long histories and high citation counts.
