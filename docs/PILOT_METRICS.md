# 8.2 Pilot metrics

Build order: metric definitions and seeded calculator tests → durable attribution/timing → scoped service/API → weekly export and validation.

Endpoints: GET `/api/v1/projects/{project_id}/metrics`, `/metrics/dashboard`, `/metrics/weekly.csv?week_start=YYYY-MM-DD` (Monday UTC). Optional `start`/`end` UTC-aware timestamps on metrics/dashboard, half-open range, maximum 366 days. Default all-time through request time. Weekly CSV is an on-demand export, with no outbound delivery or scheduler.

Metrics use project-scoped source records and return values with sample counts/denominators. Access requires both `audit.read` and `financial.read` (currently owner/admin); no audit or financial permissions are broadened. No raw source text is returned. Nonmembers and other tenants cannot access metrics.

- Uploaded: documents created in range, including quarantined/failed and soft-deleted records for historical accounting.
- Processed successfully: upload cohort with processing_status=completed/status=linked. Failed: terminal failed/dead_letter; failure rate failed/(successful+failed). Quarantine and review-required reported separately, excluded from that denominator.
- Classification: original prediction versus latest human-confirmed type, reviewed within range and by report end. Extraction: original field values/missing flags versus latest explicitly reviewed extraction of the same schema, field-level equality. Confidence is not accuracy. Unknown without reviews.
- Evidence coverage: distinct cohort documents used as evidence sources / uploaded documents; direct document links and document-chunk source links resolve to their owning document, deduplicated.
- Risks detected/accepted/dismissed and change orders: created/detected cohorts; decisions use dated audit events. Override rate: explicit risk overrides or changed pilot type/extraction values / applicable human risk or document review events, never automated actions.
- Approval cycle: decision timestamp minus approval created_at for decided approvals in range, in seconds. Queue time: first pending review task created_at to its first subsequent human pilot review by report end; unresolved ages reported separately, never substitute mutable updated_at for decision timestamps.
- AI costs: durable final gateway-call records, including retry/fallback totals once per call; resource attribution uses trusted document/investigation IDs. USD Decimal amounts. Unknown cost traces make the complete total/mean unknown; known subtotal and sample coverage remain available. Historical log-only calls cannot be reconstructed.
- Processing latency: durable processing start-to-terminal timestamps for successful cohort documents, including retry wait; linear interpolated p50/p90/p95, seconds. Missing/invalid timestamps are excluded with sample coverage. No updated_at inference.

Historical ranges are cohort views using source state as of report read, with human reviews/audits/AI calls bounded by event timestamps. They are not immutable historic database snapshots. No invented baselines or imputed costs. Document lifecycle timing and gateway attribution are recorded prospectively; older records without measurements remain unknown.

## API use

All endpoints require a bearer access token. Access currently requires an owner/admin role because both audit and financial reads are required. Project IDs are checked against the authenticated tenant; the client cannot supply a tenant ID.

```
GET /api/v1/projects/{project_id}/metrics
GET /api/v1/projects/{project_id}/metrics?start=2026-11-02T00:00:00Z&end=2026-11-09T00:00:00Z
GET /api/v1/projects/{project_id}/metrics/dashboard
GET /api/v1/projects/{project_id}/metrics/weekly.csv?week_start=2026-11-02
```

The dashboard response groups the same typed report into processing, quality, commercial, review and AI-cost sections. No browser page is added. Reports are `Cache-Control: no-store`. Values for rates are fractions from 0 to 1; durations/latencies are seconds. CSV rows use `metric,statistic,value` with project and UTC bounds; an empty value means unknown. Inputs are validated, and future ends are capped at observation time so current-week exports are partial rather than counting future queue time. A wholly future range is rejected.

The AI cost mean uses distinct resource IDs with recorded calls as its denominator. `resources`, `calls`, `known_cost_calls`, `known_subtotal` and `total` expose coverage. A resource with no recorded calls has unmeasured cost; its cost is not assumed to be zero. `total` is complete only among recorded calls, not a reconciliation against a provider invoice. Model pricing must be configured in the existing `MODEL_GATEWAY_PRICES` setting; no rates are hardcoded or inferred. Amounts use the existing six-decimal USD trace storage.

## Instrumentation and deployment

No migration or new dependency is required; metrics reuse existing project source tables and `ai_traces`. Deploy API and workers together. Prospective processing runs save first-stage start and terminal timestamps inside `processing_data.metrics`. A legacy run resumed mid-pipeline does not get an invented start timestamp. Worker redelivery preserves the original timing checkpoint.

Gateway resource scope propagates through worker threads and nested model scopes, resets on exit, and never inherits a resource across tenants/projects. Final-call usage records include all retries/fallback attempts once per trace ID. The writer checks document/project ownership, stores an allowlist of IDs/usage/cost metadata, and commits independently of business transactions so rollbacks do not erase incurred costs. No prompts, provider output, source text or tokens are persisted. Pool acquisition, connection, statement and lock waits are bounded; a persistence failure emits `model_usage_persistence_failed` with safe correlation IDs and does not trigger another provider call. Such lost traces cannot be reconstructed from the database.

The metrics reader projects only needed columns and processing timing checkpoints, avoiding raw checkpoint text, evidence quotes, approval comments and risk narratives. Shared pilot database fixtures initialize once across onboarding and metrics tests. Normal CI uses the full migrated PostgreSQL schema. Local `PILOT_SCHEMA_ONLY=1` mode uses a disposable PostgreSQL instance without pgvector, creates unrelated parent tables from metadata, and applies migration 0014; it does not validate the earlier migrations, vector search, live MinIO/Redis, or real provider calls.

Rollback: deploy the previous API/workers; existing JSON timing and AI trace records can remain in place. No data needs to be deleted. Weekly exports are generated on demand; scheduling and external delivery are outside this feature.

## Validation

- Full backend suite without external services: **571 passed, 352 skipped** (database/provider/Redis/MinIO/OCR prerequisites).
- Combined focused suite: **131 passed**, including **15 seeded PostgreSQL metrics tests** plus the existing onboarding and investigation/gateway checks. The usage writer also exercised a separate real synchronous database connection and survived a business rollback.
- Seeded cases cover empty denominators, latest human reviews, factual extraction equality, terminal failure-rate exclusions, deduplicated evidence coverage, dated risk decisions, approval/review durations, unknown costs, Decimal totals, percentile interpolation, half-open time windows, partial current weeks, API/CSV contracts, and tenant/permission denial.
- Ruff, targeted mypy (seven source files), `pip check`, and Git whitespace checks passed.
- PostgreSQL used the explicit schema-only fixture described above. Live provider calls, object storage, Redis workers, vector search and the full online migration chain remain unverified. Existing offline schema/migration checks pass in the full suite.
