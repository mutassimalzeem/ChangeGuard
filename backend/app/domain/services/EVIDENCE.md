# Evidence links (feature 4.1)

One immutable EvidenceLink joins a typed subject to one source. Multiple rows
provide multiple sources. Subjects are `claim`, `risk`, `project_event`,
`change_order`, and `ai_answer`; sources are `document`, `document_chunk`,
`site_photo`, `project_event`, `boq_item`, and `contract_clause`.

`evidence_link_id` is a queryable ORM alias for the repository's UUID `id` primary
key. Responses include tenant/project IDs, subject/source types and IDs,
relevance and confidence (nullable scores from 0 to 1), source page (positive),
source text snippet, creator, and creation timestamp. Unknown historical scores
and creators remain null. SitePhoto references an existing document; this feature
does not add photo upload or AI generation endpoints.

Authenticated API:

- `GET /api/v1/projects/{project_id}/evidence/{subject_type}/{subject_id}`
- `POST /api/v1/projects/{project_id}/evidence/{subject_type}/{subject_id}`

GET returns `{ "status": "supported", "evidence": [...] }` or
`{ "status": "insufficient_evidence", "evidence": [] }` when there are no visible
links in the requested page. `offset` defaults to 0; `limit` defaults to 50 and
cannot exceed 100. A missing/inaccessible subject returns 404. This covers change
orders, risks, and AI answers as well as claims and events.

POST appends an array of 1–100 source objects. Creator and ownership come from the
authenticated session. It requires change-write permission. GET requires document
read permission and project access. Reads and writes check source document
visibility, including documents behind chunks, photos, events, clauses and BOQ
items. BOQ evidence also requires financial-read permission. Hidden/deleted
sources do not expose their snippets. There are no update/delete endpoints.

AI generation callers must use `EvidenceService.save_answer(project_id, facts)`
with a sequence of `(factual assertion, evidence list)` pairs. Every assertion
must have evidence. An empty or partially unsupported result returns
`insufficient_evidence` and persists no answer or claims. Supported answers,
per-assertion Claim records, and their links are saved atomically.
`save_claim` also rejects every unsupported AI-generated claim and every
unsupported request to save a verified claim. Human draft claims may exist
without evidence.

PostgreSQL deferred constraint triggers enforce support at transaction completion,
so a claim/answer and its links can be inserted together. Direct SQL cannot save
an unsupported AI claim, verify an unsupported human claim, or mark an unsupported
AI answer as supported. Checked polymorphic references validate existence and
matching tenant/project with row locks. References cannot be deleted or moved
across ownership boundaries. Evidence UPDATE, DELETE and TRUNCATE are rejected;
source/subject TRUNCATE is also blocked to preserve references.

Deploy with `alembic upgrade head` before starting the new application. Migration
0009 backfills existing change-order/risk evidence without changing IDs,
timestamps, confidence, or rationale. Legacy rationale remains separately stored;
it is not presented as a source quotation. Existing ORM callers must switch from
legacy typed FK columns/relationships to subject/source fields and the evidence
service. Downgrade restores representable legacy links but refuses to discard new
claim, answer, photo, or otherwise unrepresentable evidence records.

Validation uses disposable UUID-named PostgreSQL databases via
`TEST_DATABASE_ADMIN_URL`, never the application database. Tests cover all 30
subject/source pairs, migrations, direct SQL integrity, unsupported verification,
partial AI answers, append-only behavior, source visibility and required read APIs.
