# Potential change detection (5.2)

Potential changes are evidence-backed `ProjectEvent` rows with a non-null
`detection_key` and `status=potential_change`. They are suggestions for human review,
not approved change orders, claims, liabilities or programme commitments.

The supported document types are daily reports, emails/correspondence, RFIs,
site photos and drawings. The normal processing pipeline detects changes after
entity linking and checkpoints the IDs in `link_entities.potential_changes`.
Site photos use their existing classification/review checkpoint: visual detection
runs before processing pauses for mandatory image review. A caption/text source
uses the same rules as other documents; an image without text is an ambiguous input
for the existing vision-capable model gateway. No visual content is invented when
the model provider is unavailable.

## Rules and model boundaries

Rules match explicit scope revisions, delayed/suspended work, additional work,
issued site instructions, material shortages/rejections and drawing/design clashes.
Negated/resolved statements are suppressed. Routine observations create no record.
Questions, conditional statements and vague concerns are ambiguous. Only ambiguous
clauses invoke the classification gateway, with at most eight text calls per file.
Clear rule matches make no model calls. The model returns a constrained event type,
explanation, quote and confidence; it cannot return prices, durations or owners.
Text quotes must occur verbatim in the supplied source. Invalid, refused, low-confidence
or unavailable model output creates no record and does not discard rule findings.
Ambiguities beyond the model budget, unavailable classifiers and unsupported output
queue a manual document review task; detection is not a completeness guarantee.

Rule confidence is 0.95. Text model output requires at least 0.7 confidence and is
capped at 0.85. Photo classifications require at least 0.7 and persist at 0.65,
always with human review required. Photo evidence links to the original image and
never fabricates a text quotation. A model explanation of visible conditions is
not proof of cause, contractual entitlement, quantities or monetary exposure.

All detected records have a title, description, detection date, event type,
evidence links, confidence and nullable owner/cost/schedule suggestions. Detection
date is the date of first persistence in UTC; occurrence time currently retains
document receipt time. Evidence preserves document ID, page (when known), quoted
text (for text sources), confidence and rationale. Deterministic identity keys
prevent repeat records/evidence on replay, while retaining separate source events
and event types. Existing transaction checkpoints and per-document locks provide
atomic persistence and prevent concurrent processing of the same file.

## Impact suggestions and review

Amounts are copied only from explicit `estimated/additional/extra cost CURRENCY amount`
wording using Decimal. Supported currency labels are USD, BDT, EUR, GBP and AED.
Multiple amounts, negative amounts, malformed grouping, excessive precision and
unlabelled arithmetic produce unknown suggestions. Schedule suggestions copy a
single explicit delay or schedule-impact day count; no working-day/calendar or
critical-path calculation is performed. Owners copy explicit `Action owner:` or
`Responsible party:` labels. Missing suggestions remain null, never guessed zero.
Suggestions are local to the supporting clause; the detector does not associate
costs in unrelated paragraphs with an event.

Every record exposes `human_review_required=true`. There is no acceptance,
payment, claim submission or automatic promotion to a change order in this feature.
Financial suggestions must be independently reviewed before any commercial use.
Different event types can describe the same incident; their suggestions must not
be summed as independent costs.

## API and deployment

- `GET /api/v1/projects/{project_id}/potential-changes?offset=0&limit=50`
- `GET /api/v1/projects/{project_id}/potential-changes/{event_id}`

Both endpoints require project access, document read and financial read permission.
Financial ORM fields are deferred for callers without financial permission.
Each evidence source is checked before exposing the record. Restricted/deleted
sources or missing evidence hide the whole record; filtered pages can contain fewer
than `limit` results. Evidence details use the existing evidence endpoint with
subject type `project_event`. Monetary API values are decimal strings.

Run `alembic upgrade head` before API/worker deployment. Migration
`0012_potential_changes` adds nullable columns and a unique detection key to existing
project events without changing their IDs or evidence references. There is no
automatic historical backfill. Already completed processing checkpoints are retained.
The detector is English-language MVP logic; OCR quality, quoted email history,
missing source context and ambiguous wording can require manual review. Frontend
review workflows, cross-document incident merging and approved impact calculations
are outside this feature.

## Validation

The completed backend run passed 630 tests, skipped 13 optional integrations, and
reported the same 20 existing project-management failures reproduced on unchanged
`origin/main` earlier in this session. All 32 new detector tests passed, including
daily-report/email fixtures, rule false positives, model grounding/budgets,
manual-review fallback, pipeline replay, photo evidence and API financial access.
Database foundation tests verified full migration upgrade/downgrade and metadata
drift against disposable PostgreSQL 16 with pgvector. Ruff E/F/I checks on the new
and affected processing/route modules, dependency consistency and whitespace
checks passed. Live model calls, actual photo interpretation and external OCR/
MinIO/Redis integrations were not exercised.

Full-suite command (with `DEBUG=false` and an isolated `TEST_DATABASE_ADMIN_URL`):

```text
backend/.venv/Scripts/python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=backend/.venv/potential-complete-temp
```
