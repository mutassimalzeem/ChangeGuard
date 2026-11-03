# Bounded investigation agent (5.4)

`InvestigationAgent` is an I/O-free orchestration loop. It has a planner and a
fixed capability adapter, not a database session, SQL/code execution, email client
or approval capability. Read capabilities use the authenticated tenant and a fixed
project. Writes delegate to checked application services inside a savepoint; the
agent itself never inserts/updates/deletes database rows.

## API and activation

- `POST /api/v1/projects/{project_id}/investigations`
- `GET /api/v1/projects/{project_id}/investigations/tool-schemas`

Both require authenticated project access, document read and financial read
permission. Write actions additionally enforce the relevant application permission.
The request cannot choose a tenant or another project in tool arguments.

```json
{
  "document_id": "DOCUMENT_UUID",
  "question": "Investigate the unresolved drainage instruction",
  "max_tool_depth": 6,
  "max_seconds": 20
}
```

The server first reads up to eight visible chunks from the anchored document. The
existing rule classifier must identify ambiguous wording, or a pending low-confidence/
unresolved-classification review must exist. Clear/routine cases return `not_required`
without constructing/calling the model. Questions cannot override this gate. Missing
readable evidence returns `insufficient_evidence` without invented conclusions.

Comparable typed amount/due-date facts and explicit opposing instructions are checked
deterministically. Preflight checks at most 32 recent project documents when comparable
anchor facts exist. Known conflicts return both evidence sources without invoking the
model. If later reads uncover a recognized conflict, the loop stops before another
model decision. Matching excludes different issues/revisions/statuses and currencies;
equivalent Decimal representations compare equally.

## Capabilities and schemas

`schemas.py` defines closed Pydantic schemas, also exposed by the schema endpoint.
Unknown tools, extra fields, tenant/project selectors, executable code/SQL fields,
recipients, statuses and monetary write fields are rejected before dispatch.

| Capability | Arguments | Behavior |
| --- | --- | --- |
| search_project_documents | query, limit (1–8) | Permission-filtered lexical/exact-identifier project retrieval |
| get_document_chunk | record_id | Current visible chunk and available typed source facts |
| get_contract_clause | record_id | Scoped clause and source visibility checks |
| get_boq_item | record_id | Recorded quantity/rate/currency; no derived total |
| get_change_order | record_id | Scoped recorded details; no mutations |
| get_approval_history | record_id (order ID) | Up to eight existing approval records, with order/source checks |
| get_project_timeline | limit (1–8) | Recent visible events in the anchored project |
| find_similar_past_cases | query, limit (1–8) | Keyword similarity over decided cases in the same project |
| create_draft_change_order | observed evidence_ids | Terminal application action; unknown cost, no submission or approval |
| request_human_review | observed evidence_ids | Terminal application action; audited pending document-review task |

All reads disable autoflush. Record access repeats tenant, project, membership and
source visibility checks. Hidden/deleted/failed/quarantined document chunks cannot
be used. Past-case lookup intentionally does not search other projects or tenants.
No external URLs or messages can be sent by a capability.

## Conclusions, conflicts and financial authority

The model can select only a conclusion kind, a permitted recommendation, evidence
IDs and exact quotations. It cannot supply arbitrary conclusion prose, costs,
quantities/rates for writes, recipients or approval decisions. Quotes are checked
against observed excerpts. Unknown citations, invented text and extra output fields
are rejected. If a final recommendation omits observed evidence, the server returns
all sources as insufficient evidence for human review instead. Every returned
conclusion carries structured `evidence_links` (source type/ID, page and quotation).

Recognized conflicts always override a proposed one-sided conclusion. Draft creation
is blocked for conflicts, omitted source chunks or mixed non-document resource
evidence. Model-reported conflicts require at least two source IDs and human review.
Free-text contradictions outside the explicit detectors still require model/human
interpretation; valid citations are not proof that every source fact is true. The
agent never selects a contractual winner or authorizes commercial action.

Draft creation delegates to the 5.3 workflow: create potential, convert to under_review,
then build a deterministic cited synopsis from **all selected observed chunks**. It
does not invoke another drafting model. The order ends at `drafted` with no cost
items and `amount=null`; humans must supply/review financial inputs before submission.
The model may copy a recorded monetary quotation, but cannot return a calculated
financial value. Review requests use the existing unique per-document task and an
audited application service; they do not approve/reject anything. At most one write
action executes per run, and it terminates the loop. Repeated runs can create distinct
drafts; there is no cross-run draft idempotency key supplied by a caller.

## Bounds and cancellation

Operator settings `INVESTIGATION_MAX_TOOL_DEPTH=6` and `INVESTIGATION_MAX_SECONDS=20`
cap client budgets. Settings/request hard limits are 12 calls and 60 seconds; clients
can reduce but cannot increase the operator limits. All read and write calls count
toward the sequential tool depth. One final model response is allowed after the last
permitted read; another proposed call is logged and denied. There are at most depth+1
model turns. Each turn uses the existing gateway with provider retries/fallback off,
bounded response tokens and an HTTP timeout derived from remaining time. The gateway
may perform its existing single schema-repair attempt within the run's deadline.

The deadline covers preflight, model waiting and capability execution. Async reads
and actions are cancelled at the deadline; incomplete application writes roll back
their savepoint, and timed-out requests roll back the request transaction before
the dependency can commit it. Transaction cleanup/HTTP transport overhead may finish
after the reasoning budget. A cancelled synchronous model request can finish in its
read-only worker thread until its HTTP timeout; it has no action executor or database
session, and its late result is ignored.

Evidence is limited to 64 unique excerpts, each at most 2,000 characters. Retrieval
and collection tools cap their results. Exhaustion returns partial evidence for human
review; it cannot authorize another action. Model/provider unavailability is reported
separately from invalid model output. Recommendations to request review are not
claimed as executed unless an `action.review_task_id` is returned.

## Trace logging

Every proposed call (including denied tool/schema attempts), observation, model step,
policy rejection, cancellation and final recommendation emits an `investigation_trace`
event. Events contain UTC time, run/request/tenant/project/user IDs, sequence, tool,
depth/outcome, evidence labels, action resource ID when applicable, coded final
recommendations and a SHA-256 content digest. Raw source text, queries, provider
output, credentials and quoted conclusions are **not** emitted to shared logs. The
authenticated response contains the evidence quotations and a safe metadata trace.
Application writes retain their own audit events; review audit evidence uses IDs and
quotation hashes. Configure the existing INFO log collector for retention of these
events. There is no new database trace table or raw-provider-output archive.

## Deployment

No new dependencies or migration are required; deploy on the 5.3 schema and install
the updated settings. The existing gateway/provider configuration is used. This feature
does not automatically invoke investigations from document processing, backfill old
cases, create a frontend, send notifications or grant approval authority. Invocation
is explicit through the authenticated endpoint, with deterministic eligibility checks.

## Validation

All 64 new agent/capability tests pass, including prompt/tool injection, SQL/email/
approval misuse, extra scope/financial arguments, quote grounding, omitted-source
handling, comparable/opposing-instruction conflicts, tool and model deadlines,
read-only adapter behavior, cross-project/tenant isolation, server budget caps,
transaction cancellation rollback and workflow-delegated writes. The final backend
run reports **802 passed, 13 skipped, 20 failed**. All 20 failures match the existing
project-management baseline previously reproduced on unchanged `origin/main`.
Targeted Ruff E/F/I, `pip check` and whitespace checks pass. Validation used an
isolated PostgreSQL 16/pgvector container. Live model/provider behavior and external
OCR/object-storage/Redis integrations were not exercised; adversarial model steps
are simulated to verify application enforcement independently of prompt compliance.

```text
backend/.venv/Scripts/python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp=backend/.venv/investigation-final-full-temp
```

Use `DEBUG=false` and `TEST_DATABASE_ADMIN_URL` pointing to an isolated test server.
