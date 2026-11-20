# ChangeGuard — System Architecture

**Version:** 0.1  
**Date:** October 27, 2026  
**Status:** MVP architecture  

---

## 1. Architectural goal

ChangeGuard must be a **vertical AI system**, not a generic document chatbot.

The system must:

- Ingest messy construction evidence.
- Convert it into a domain-native project model.
- Retrieve only permission-checked evidence.
- Use AI for interpretation, extraction, classification, and drafting.
- Use deterministic code for calculations, deadlines, permissions, and state changes.
- Require human approval for consequential actions.
- Preserve an immutable audit trail.

### Core rule

> Deterministic systems own facts and actions.  
> AI owns interpretation and explanation.  
> Humans own high-risk decisions.

---

## 2. High-level architecture

```text
+------------------------------------------------------------+
|                     CLIENT INTERFACES                      |
|  Web dashboard | Mobile upload | Email ingest | REST API   |
+----------------------------+-------------------------------+
                             |
+----------------------------v-------------------------------+
|                 API GATEWAY / IDENTITY                     |
| Auth | RBAC | tenant isolation | rate limits | audit       |
+----------------------------+-------------------------------+
                             |
+----------------------------v-------------------------------+
|                 DOMAIN WORKFLOW ENGINE                     |
| Projects | change orders | approvals | tasks | deadlines   |
+---------+----------------------------------+---------------+
          |                                  |
+---------v----------------+     +-----------v---------------+
|   INGESTION LAYER        |     |   AI REASONING LAYER      |
| Upload | email | OCR     |---->| Extract | classify | link |
| Files | queue            |     | Retrieve | reason | draft |
+---------+----------------+     +-----------+---------------+
          |                                  |
+---------v----------------+     +-----------v---------------+
|  DOMAIN DATA MODEL       |<--->|   EVIDENCE / RETRIEVAL    |
| PostgreSQL               |     | Hybrid search + citations |
+---------+----------------+     +-----------+---------------+
          |                                  |
+---------v----------------------------------v---------------+
|       POLICY, GUARDRAILS, EVALUATION, OBSERVABILITY        |
| Validation | permissions | confidence | traces | audits    |
+------------------------------------------------------------+
```

---

## 3. Service decomposition

For the MVP, deploy as a modular monolith. Do not begin with microservices.

### Modules

| Module | Responsibility |
|---|---|
| `api` | HTTP API, authentication, request validation, authorization |
| `ingestion` | File upload, email ingestion, preprocessing, queueing |
| `document_processing` | OCR, text extraction, classification, structured extraction |
| `domain` | Projects, contracts, change orders, approvals, risks, events |
| `retrieval` | Hybrid search, reranking, permission filtering, citations |
| `ai` | LLM calls, prompt management, model routing, structured output |
| `workflow` | State machines, approvals, notifications, deadlines |
| `policy` | Access control, action authorization, guardrails |
| `evaluation` | Golden datasets, test runners, quality metrics |
| `observability` | Logs, traces, metrics, audit events |

### Why modular monolith

- Faster solo development.
- Easier debugging.
- Lower infrastructure cost.
- Clear module boundaries allow later extraction into services.

---

## 4. Ingestion architecture

### Inputs

MVP ingestion sources:

1. Manual upload through web UI.
2. Email forwarding or IMAP/Graph API ingestion.
3. REST API upload.
4. Mobile photo upload.
5. Bulk ZIP upload.

### Processing pipeline

```text
File received
   |
   v
Virus / file-type validation
   |
   v
Store original in object storage
   |
   v
Create document registry record
   |
   v
Queue processing job
   |
   v
Extract text / OCR
   |
   v
Classify document
   |
   v
Extract structured fields
   |
   v
Validate output schema
   |
   v
Create embeddings and search index
   |
   v
Link to domain entities
   |
   v
Run deterministic risk checks
   |
   v
Create human-review tasks if confidence is low
```

### Document registry

Every document must have:

- `document_id`
- `tenant_id`
- `project_id`
- `original_file_key`
- `file_hash`
- `file_type`
- `uploaded_by`
- `uploaded_at`
- `source`
- `processing_status`
- `document_type`
- `document_version`
- `access_policy`
- `extraction_confidence`

### Processing states

- `received`
- `validating`
- `stored`
- `queued`
- `processing`
- `extracted`
- `classified`
- `indexed`
- `linked`
- `review_required`
- `failed`
- `quarantined`

### Failure handling

- Retry transient failures with exponential backoff.
- Send repeated failures to a dead-letter queue.
- Quarantine unsupported or corrupted files.
- Never delete original files automatically.
- Surface processing failures in the UI.

---

## 5. Domain data model

Use PostgreSQL as the primary system of record.

### Core entities

```text
Tenant
 |-- User
 |-- Project
      |-- Contract
      |    |-- ContractClause
      |-- Drawing
      |    |-- DrawingRevision
      |-- BOQ
      |    |-- BOQItem
      |-- RFI
      |-- ChangeOrder
      |-- DailyReport
      |-- SitePhoto
      |-- EmailThread
      |-- Quotation
      |-- ProjectEvent
      |-- Risk
      |-- Approval
      |-- EvidenceLink
```

### Important tables

| Table | Purpose |
|---|---|
| `tenants` | Customer organization |
| `users` | People with access |
| `projects` | Construction project |
| `documents` | Original uploaded files and metadata |
| `document_chunks` | Searchable extracted text chunks |
| `project_events` | Normalized operational events |
| `contracts` | Contract metadata |
| `contract_clauses` | Individual clauses and obligations |
| `boq_items` | Cost and quantity records |
| `rfis` | Requests for information |
| `change_orders` | Potential and formal change orders |
| `risks` | Detected risks and exposure |
| `approvals` | Human decisions |
| `evidence_links` | Claim-to-source mappings |
| `audit_events` | Immutable action history |
| `ai_traces` | Model, prompt, retrieval, and tool-call traces |

### Key relationships

- A `ChangeOrder` belongs to one `Project`.
- A `ChangeOrder` may have many `EvidenceLink` records.
- An `EvidenceLink` points to a `Document`, `DocumentChunk`, `SitePhoto`, `ProjectEvent`, or `BOQItem`.
- A `Risk` may reference one or more `ChangeOrder`, `Document`, or `ProjectEvent` records.
- An `Approval` belongs to a `ChangeOrder` or `Risk`.
- Every AI conclusion must have at least one `EvidenceLink` or be explicitly marked `insufficient_evidence`.

---

## 6. AI reasoning architecture

Do not build one large prompt that does everything.

### Task pipeline

```text
Document input
   |
   v
Document classification
   |
   v
Field extraction
   |
   v
Entity extraction
   |
   v
Entity resolution
   |
   v
Event extraction
   |
   v
Relationship linking
   |
   v
Risk detection
   |
   v
Evidence retrieval
   |
   v
Draft generation
   |
   v
Human review
```

### AI task ownership

| Task | Method |
|---|---|
| OCR | Specialized OCR / document-processing service |
| Classification | Small model, rules, or fine-tuned classifier |
| Structured extraction | Schema-constrained LLM |
| Entity extraction | LLM + rules |
| Entity resolution | Embeddings + deterministic matching |
| Event extraction | LLM with strict event schema |
| Cost calculations | Python / SQL |
| Deadline checks | Rules engine |
| Duplicate detection | Hash + embeddings |
| Risk scoring | Rules first, ML second |
| Narrative drafting | LLM with citations |
| Q&A | Retrieval-augmented generation |

### Model routing

Use a model gateway so models can be changed without rewriting business logic.

| Workload | Model class |
|---|---|
| Cheap classification | Small / fast model |
| Field extraction | Mid-tier model with JSON schema |
| Complex reasoning | Strong frontier model |
| Embeddings | Dedicated embedding model |
| Image understanding | Vision-capable model |
| Drafting | Strong language model |

### Structured output

Every extraction task must return validated JSON.

Example:

```json
{
  "document_type": "change_order",
  "change_order_number": "CO-014",
  "title": "Additional waterproofing at basement level",
  "requested_by": "Main Contractor",
  "cost_impact": {
    "amount": 185000,
    "currency": "BDT",
    "basis": "Item rate + additional quantity"
  },
  "schedule_impact_days": 7,
  "status": "submitted",
  "confidence": 0.82,
  "source_pages": [3, 4]
}
```

If validation fails, retry with a repair prompt or send to human review.

---

## 7. Retrieval architecture

Use hybrid retrieval.

### Retrieval flow

```text
User question / investigation task
   |
   v
Query understanding
   |
   v
Permission filter
   |
   v
Keyword search
   +
Vector search
   |
   v
Candidate fusion
   |
   v
Reranking
   |
   v
Evidence selection
   |
   v
Answer / draft generation with citations
```

### Indexing strategy

- Store extracted text in PostgreSQL.
- Use PostgreSQL full-text search for exact terms.
- Add `pgvector` for semantic search.
- Chunk by logical structure, not fixed character count.
- Preserve metadata on every chunk.

### Chunk metadata

Each chunk should include:

- `document_id`
- `project_id`
- `document_type`
- `page_number`
- `section`
- `revision`
- `date`
- `author`
- `access_level`
- `language`
- `embedding_model`
- `chunk_hash`

### Retrieval rules

- Always apply tenant and project access filters before retrieval.
- Never retrieve across tenants.
- Prefer exact identifiers: clause number, drawing number, BOQ code, CO number.
- Return source spans, not just document names.
- If evidence is insufficient, return an explicit insufficient-evidence response.

---

## 8. Agent and orchestration design

Use deterministic workflows for predictable processes. Use an investigation agent only for ambiguous cases.

### Standard flow

```text
New document
   |
   v
Deterministic processing
   |
   v
Rule-based checks
   |
   v
If confident: create structured record
   |
   v
If ambiguous: investigation agent
   |
   v
Agent retrieves evidence
   |
   v
Agent proposes conclusion
   |
   v
Human review
```

### Agent tools

The investigation agent may use read-only tools:

- `search_project_documents`
- `get_document_chunk`
- `get_contract_clause`
- `get_boq_item`
- `get_change_order`
- `get_approval_history`
- `get_project_timeline`
- `find_similar_past_cases`
- `create_draft_change_order`
- `request_human_review`

### Agent restrictions

The agent must not:

- Write directly to financial tables.
- Approve change orders.
- Send external emails autonomously.
- Delete evidence.
- Modify approvals.
- Access another tenant’s data.
- Make financial calculations itself.

All state-changing operations go through the workflow and policy layers.

---

## 9. Human-in-the-loop design

### Autonomy matrix

| Action | Autonomy |
|---|---|
| Read documents | Automatic |
| Extract fields | Automatic |
| Classify documents | Automatic |
| Flag risk | Automatic |
| Draft change order | Automatic |
| Send email to client | Human approval |
| Change financial exposure | Human approval |
| Approve claim | Human approval |
| Modify contract status | Human approval |
| Delete evidence | Human approval + audit |

### Review queue

A review item should contain:

- What the system found.
- Confidence score.
- Evidence links.
- Missing information.
- Recommended action.
- Financial or schedule impact.
- Reviewer decision.
- Reviewer rationale.

---

## 10. Security and multi-tenancy

### Isolation model

Every query and background job must include `tenant_id`.

Enforce isolation at:

- API authorization layer.
- Database query layer.
- Object-storage key structure.
- Search filter layer.
- Background-worker context.

Example object-storage path:

```text
s3://changeguard-env/tenant_id/project_id/documents/document_id/original.pdf
```

### Access control

Use role-based access control:

- `owner`
- `admin`
- `project_manager`
- `commercial_manager`
- `site_engineer`
- `viewer`

Permissions must be checked before:

- Retrieval.
- Document download.
- Financial data display.
- Approval action.
- Export.
- AI response generation.

---

## 11. Observability

### Trace every AI decision

Each AI request should log:

- `trace_id`
- `tenant_id`
- `project_id`
- `user_id`
- `task_type`
- `model`
- `prompt_version`
- `input_hash`
- `retrieved_document_ids`
- `tool_calls`
- `output`
- `validation_result`
- `latency`
- `token_usage`
- `cost`
- `error`

### Metrics

Track:

- Documents processed per day.
- Processing failure rate.
- Classification accuracy.
- Extraction field accuracy.
- Retrieval precision and recall.
- Citation coverage.
- Human override rate.
- p50 / p90 / p95 latency.
- Cost per document.
- Cost per investigation.
- Approval cycle time.

---

## 12. MVP technology stack

| Layer | MVP choice |
|---|---|
| Language | Python 3.12+ |
| API | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Background jobs | Celery + Redis |
| Object storage | S3-compatible storage |
| Search | PostgreSQL full-text search |
| Vector search | pgvector |
| Frontend | Next.js + React |
| Auth | JWT + session or OAuth where appropriate |
| Validation | Pydantic v2 |
| Testing | Pytest |
| LLM access | Provider SDK behind internal model gateway |
| Observability | Structured logs + OpenTelemetry |
| Deployment | Docker Compose first, then cloud deployment |

---

## 13. Deployment topology

### Local development

```text
Docker Compose
|-- api
|-- worker
|-- postgres
|-- redis
|-- minio
|-- frontend
```

### Production MVP

```text
Load balancer
   |
   v
API service
   |
   v
Worker service
   |
   v
Managed PostgreSQL
   |
   v
Managed Redis
   |
   v
Object storage
```

Use separate environments:

- `local`
- `staging`
- `production`

Never use production customer data in local development without anonymization.

---

## 14. Scalability path

Do not optimize prematurely. Add complexity only when needed.

| Trigger | Action |
|---|---|
| More than 10k documents per project | Add dedicated vector database |
| Complex multi-hop reasoning | Add graph database or graph layer |
| Long-running workflows | Adopt Temporal |
| Multiple AI providers | Expand model gateway |
| High ingestion volume | Add queue partitions and worker autoscaling |
| Enterprise customers | Add SSO, SCIM, detailed IAM, and data-residency controls |

---

## 15. Architecture acceptance criteria

The architecture is acceptable when:

1. Every document has provenance.
2. Every AI conclusion has evidence or explicitly states insufficient evidence.
3. No AI system can directly perform an irreversible financial or contractual action.
4. Tenant isolation is enforced at API, database, storage, and retrieval layers.
5. Every model call is traced.
6. Every approval is auditable.
7. The system can recover from worker, model, and storage failures.
8. The MVP can run locally with Docker Compose.

## Operational review workspace

Under `/api/v1/projects/{project_id}/review-queue`, `GET /workspace` returns a filtered, sorted page and its visible total. The default view is actionable. Page sizes range from 1 to 100. Dates are inclusive UTC calendar dates. Missing sort values fall last, with subject kind and UUID breaking ties. `GET /reviewers` returns eligible names and IDs. `POST /{kind}/{id}/commands` accepts a human action, reason, UUID retry key and the action-specific arguments. `POST /notes` applies a single note to up to 20 subjects in one transaction.

The workspace projects existing risks, extraction tasks, approvals and change orders. A subject row lock serializes commands. Approval decisions lock the change order first. Assignment events overlay the original owner. Note and assignment events carry their command keys. Other commands write a receipt alongside the domain audit in the same transaction. A replay with the same actor, subject, key and arguments returns the original result after checking current access. Different arguments with the same key return 409. Migration `0018_review_workspace` adds a unique receipt index and database guards for approval and extraction audit records.

### Review Queue visibility and pagination

The workspace list and `GET /workspace/{kind}/{item_id}` use the same PostgreSQL statement. The scoped session accepts that statement by object identity and supplies the authenticated tenant, actor and permissions. The statement verifies the current user, role, tenant status and project access. Inside this scope it resolves documents, chunks, photos, events, clauses and BOQ items through their parent records. A subject with any missing, restricted or deleted source is excluded before filtering and counting. Approvals inherit visibility from their subjects. Linked commercial records inherit their supporting document restrictions.

PostgreSQL selects a stable ordered page and hydrates its quotations, extraction payloads and chronological audit records in the same read-committed statement snapshot. A newly committed access change applies on the next read. Authorization cache TTL is zero. Commands repeat the read under the existing subject lock. The frontend keeps the existing page-number API and inline citations. The legacy list uses the same predicates with its existing unpaged shape. See the [query profile and verification procedure](docs/REVIEW_QUEUE_PERFORMANCE.md).

## Pilot value reporting

The pilot flow reuses the registry, processing pipeline, immutable review overlays, risk engine, Review Queue and change-order service. The existing pilot marker adds a queue category to visible risks and activates the pilot submission requirements. No new persistence is required. The Review Queue and pilot reports compose their fixed SQL projections from the same project, source and commercial visibility predicates. Readiness and metrics restrict documents, risks, linked changes and approvals using that projection before aggregation. Document-attributed usage is scoped to the visible document set.

The metrics router serves `GET /api/v1/projects/{id}/metrics/value/{json|csv|pdf}`. Each format uses the same aggregate rows, with an optional UTC-aware end timestamp. Notes explain denominators and missing measurements. Export reruns authorization and uses current source state, including deletions. These are on-demand reads. See [pilot metrics](docs/PILOT_METRICS.md).
