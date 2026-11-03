# Deterministic risk engine (5.1)

The `risk_checks` pipeline stage runs after validated extraction and entity linking.
It makes no model calls. Version 1 findings are persisted atomically with evidence
links and the stage checkpoint. Entity findings use project-scoped stable rule keys;
document findings also include their source IDs. A project transaction advisory lock
and unique rule key prevent duplicate insertions across concurrent deliveries.
Replays preserve human decisions and do not overwrite findings.

| Rule | Trigger and false-positive guards | Financial exposure | Schedule days |
| --- | --- | --- | --- |
| Overdue approval | Linked change has a pending, undecided approval strictly before document receipt; exclude approved/executed/rejected/cancelled changes | Nonnegative recorded claim amount | Unknown |
| Missing required evidence | Validated schema has missing `required_facts`; legacy/unvalidated extraction is insufficient evidence | Unknown | Unknown |
| Duplicate change-order claim | Distinct submitted/approved/executed changes have the same nonempty RFI, contract, normalized description, positive amount and currency; evidence required from both | One repeated claim amount | Unknown |
| Cost outlier | Item rate is strictly more than 120% of the highest comparable rate in an earlier validated BOQ or quotation; match item code, normalized description, unit and currency | `(current rate - comparison rate) * current quantity` | Unknown |
| Schedule-impact signal | Submitted/approved/executed linked change has positive recorded days | Unknown | Recorded change days |
| Conflicting information | Documents describe the same typed entity and version with matching status/issue/revision; conflicting explicit amount or due date; exclude different currencies and missing facts | Absolute difference of explicit monetary values | Unknown |

Financial calculations use Decimal with half-up rounding to two decimal places.
Missing/negative monetary operands and results beyond the database monetary range
produce unknown exposure (`null`), never guessed zero. Credits alone are not risks.
Currencies are never converted or combined. Unknown schedule days are `null`.
Receipt time is the evaluation clock, so replaying an old file does not invent a
new overdue finding. There is no periodic deadline scan in this feature.

Overdue and duplicate findings have high severity; other findings default to medium.
Validated field comparisons use the minimum operand confidence. Record-based rules
use confidence 1 for their exact predicates, not a prediction of commercial liability.
The approval assignee or change creator is the responsible party when available;
other responsibility remains unknown. No risk is auto-accepted.

Missing required evidence currently means the extraction schema's required facts,
not a configurable contractual submission checklist. BOQ/historical rate comparisons
use validated item-level document snapshots; entity-only BOQ rows have no guaranteed
source document or compatible claim-item mapping. These rules deliberately avoid
fuzzy matching, revision inference, unrelated totals and critical-path forecasts.

## API and review

- `GET /api/v1/projects/{project_id}/risks?offset=0&limit=50`
- `GET /api/v1/projects/{project_id}/risks/{risk_id}`
- `POST /api/v1/projects/{project_id}/risks/{risk_id}/decisions`

All routes require project access, document read and financial read permission,
because risk descriptions and evidence can contain commercial facts. Review also
requires `risks.accept`. A hidden/deleted evidence source hides the entire risk;
list pagination can therefore return fewer than `limit` visible results. Evidence
IDs resolve through the existing project evidence endpoint using subject `risk`.
Financial exposure is returned as a decimal string and unknown amounts as null.

Examples:

```json
{"action":"accept","reason":"Confirmed against signed instruction"}
```

```json
{"action":"dismiss","reason":"Claims cover different work packages"}
```

```json
{"action":"override","reason":"Programme review confirms eight days","severity":"high","schedule_impact_days":8}
```

Override permits severity and schedule-day changes. Original calculated values
are retained in the audit before-image; monetary estimates are not editable through
this endpoint. All three actions require a nonblank reason, lock the risk row, and
persist actor, project, request ID, reason and before/after values in the same
transaction. Risk audit events are append-only at the database level. Unsupported risks
can be dismissed but cannot be accepted or overridden until evidence is supplied.
Risk reads with no evidence always report `insufficient_evidence`.

## Deployment

Run `alembic upgrade head` before deploying workers or API processes. Migration
`0011_deterministic_risks` adds nullable fields and a unique rule key to existing
risks; historical rows remain readable. It also prevents update/delete of risk audit events and truncation of the audit table. Downgrade removes these additions and their audit immutability guard.
Already completed processing checkpoints are retained; there is no automatic
historical backfill, periodic reevaluation, frontend or notification work in 5.1.
Do not add exposures from duplicate or conflicting findings as if they were
independent project losses.
