# Explicit event linkage and risk resolution

`daily_report_delay_without_link` now resolves when an authorized caller explicitly
links an existing RFI or change order to that risk's exact `project_event_id`.
The relationship is a database record, not a text match or an LLM conclusion.

## API

```http
POST /api/v1/projects/{project_id}/events/{event_id}/links
Authorization: Bearer ...
Content-Type: application/json

{
  "entity_type": "rfi",
  "entity_id": "<existing-rfi-uuid>",
  "reason": "RFI formally records the reported delay."
}
```

`entity_type` is `rfi` or `change_order`. A nonblank reason is mandatory. Returns
200 with `link` and `resolved_risk_ids`; repeated linkage returns the same link
without rewriting its reason/actor or duplicating a resolution audit. A link to
another event remains a valid relationship but does not resolve this risk.

The caller needs `documents.read`, `financial.read`, `risks.accept` and the
applicable `rfis.write` / `change_orders.write` permission, plus project membership
unless they hold a tenant-wide role. Inaccessible projects, events, resolving
entities or original risk evidence return 404; insufficient role permission
returns 403. Both sides must belong to the same tenant and project.

Existing explicit change-order actions also use this operation:

- Creating a change order with `source_event_id` resolves matching risks for that
  event, with a server-recorded reason explaining the source-event creation.
- Appending a `project_event` as evidence of an existing change order resolves the
  matching risk, with a server-recorded explicit-evidence-link reason.

Copied provenance is excluded: copying an event's evidence package into a change
order does not create explicit relationships to other events inside that package.
Model tools do not acquire a new capability; the investigation draft tool supplies
document-chunk citations, not source-event relationships. No fuzzy match, vector
similarity, document-level association or model recommendation resolves a risk.

## State and audit history

Migration `0016_risk_resolution` adds append-only `event_entity_links` and the risk
fields `resolution_link_id`, `resolved_by_id`, `resolved_at`, `resolution_reason`.
A composite FK binds the resolution link to the exact source event, project and
tenant. Another FK preserves actor ownership. RFI/CO IDs are real composite FKs.

Linking appends `project_event.link_entity`; each first resolution appends
`risk.resolve`. The resolution audit records source event, resolving entity
type/ID, link ID, previous/new status, actor, timestamp and reason. Request IDs
propagate from the HTTP boundary. No raw document text is added to these audits.
Status becomes `resolved`; original description, exposure, confidence and evidence
remain intact. First resolution metadata is immutable and later links do not
replace it. The existing review-decision endpoint cannot reopen a resolved risk.

Resolution and its audit share the request transaction. A failed audit write
rolls back both the link and status change. PostgreSQL also enforces a deferred
resolution-audit constraint and rejects changes to resolution history or event
links. Existing risk audit and evidence immutability triggers remain active.
Source-event row locks serialize retries and competing links. Worker rule checks
use the same event lock and explicit link records to prevent re-creating a delay
risk after it has been addressed.

Risk detail and timeline APIs expose additive `resolution` metadata containing
`entity_type`, `entity_id`, `event_link_id`, `actor_id`, `resolved_at`, `reason`.
They recheck original evidence and resolving-entity visibility on every read. A
later restriction on the RFI/CO's evidence hides the derived risk rather than
leaking resolution metadata. Existing timeline status rendering shows `resolved`.

## Deployment and verification

Apply `.venv/Scripts/python.exe -m alembic upgrade head` from `backend` before
deploying/restarting API and workers. No frontend migration is needed. Downgrade
refuses to discard existing link/resolution history. No historical fuzzy backfill
is performed; replay an explicit linking action to reconcile a pre-deployment link.

Manual check: upload/process a daily report with a delay and no linked formal
record; save the risk ID and evidence IDs. Create an RFI in the project and POST
its ID to the source event's link endpoint. Confirm the same risk is `resolved`,
original evidence IDs are retained and `risk.resolve` contains the required
metadata. Repeat the POST and verify only one resolution audit exists. Repeat
with a change order and check unrelated events, nonmembers and restricted sources.

Automated coverage is in `backend/tests/test_risk_resolution.py`. It exercises real
PostgreSQL migrations and constraints, both entity kinds, existing CO paths,
unrelated/similar/copied evidence, roles/tenants/projects, restricted evidence,
idempotence, rollback and immutable audit history. Full-suite results are recorded
in repository MEMORY.md.
