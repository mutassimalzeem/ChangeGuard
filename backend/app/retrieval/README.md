# Hybrid retrieval (feature 4.2)

`POST /api/v1/retrieval/search` accepts an authenticated request:

```json
{
  "query": "DRG-STR-001",
  "filters": {
    "project_id": "00000000-0000-0000-0000-000000000001",
    "document_type": "drawing",
    "date_from": "2026-01-01",
    "date_to": "2026-12-31",
    "status": "indexed",
    "access_level": "project",
    "revision": "B"
  },
  "limit": 20,
  "semantic": true,
  "rerank": false
}
```

All filters are optional; the query must contain a letter or number, and the
result limit is 1–100. An optional `tenant_id` filter must match the authenticated
tenant (otherwise 403); it can never expand the scope. A specified inaccessible
project returns 404. Without a project filter, only accessible projects are
searched. The endpoint requires `documents.read`.

Date bounds are inclusive and apply to the extracted chunk's source date, not the
upload timestamp; undated chunks do not match a date bound. `document_type` and
`status` refer to the parent document. `revision` refers to the source chunk.
`access_level` is the effective source access: restricted when either the chunk
or its document is restricted, otherwise project.

Both retrieval queries join on document ID, tenant and project. They enforce the
authenticated tenant, active project membership (or the existing owner/admin
tenant-wide privilege), document and chunk access, soft deletion, and metadata
filters in SQL before ordering or limiting candidates. Restricted content is
available to owner/admin or the document uploader. Failed/quarantined documents
are excluded even when explicitly requested by a status filter. Rerankers receive
only the resulting authorized text. No opaque document JSON, storage keys, or
embedding arrays are serialized.

Keyword retrieval uses PostgreSQL `plainto_tsquery` against both the existing
English GIN expression index (stemming) and a new `simple` GIN expression index
(identifier-friendly tokens). User text is bound as data, never interpreted as
SQL or tsquery operators. Single-token identifiers containing digits also get a
bound, escaped literal regex check and exact-match ranking bonus, retaining
punctuation and token boundaries for drawing numbers and BOQ codes. The regex
fallback can require scanning filtered text when FTS cannot represent an identifier.

Semantic retrieval uses pgvector cosine distance, the same configured embedding
model and 1536 dimensions as ingestion. It excludes null vectors and vectors from
other model versions. Candidates must meet `min_similarity_threshold` (default
0.65). Exact vector ordering deliberately avoids the existing approximate HNSW
index: permission/metadata filtering cannot lose eligible matches to an ANN
candidate budget. This favors correctness for the current corpus; large projects
may need a separately evaluated filtered ANN strategy.

Both branches retrieve at most `max(50, 4 * limit)` candidates. Reciprocal-rank
fusion sums `1 / (60 + rank)` per channel and deduplicates by chunk ID. An exact
identifier match gets an additional `1 / 61` in the final score, so it beats an
otherwise tied semantic-only hit. Scores are ranking signals, not probabilities.

With `rerank: true`, the default optional local reranker orders candidates by
query-token coverage and uses fusion scores to break ties. It is a deterministic
lexical heuristic, not a trained semantic cross-encoder. A server-side `Reranker`
adapter can replace it using a score-only interface; returned candidates always
remain the authorized original set. Invalid score counts or nonfinite scores
produce 503. An explicitly requested but absent reranker also produces 503.

The API reuses ingestion's OpenAI embedding adapter when `LLM_PROVIDER=openai` and
`LLM_API_KEY` are configured, with `EMBEDDING_MODEL` selecting the model. Synchronous
provider work runs in a threadpool. If the provider is absent, fails, or returns
invalid vectors, keyword retrieval remains available and `semantic_status` is
`unavailable`; provider errors and request details are not exposed. Setting
`semantic: false` skips embedding entirely and reports `disabled`. Otherwise a
completed vector query reports `used`, including when it finds no matching vector.
Ingestion must already have populated matching embeddings for semantic matches.

Responses return `status: matched` and results containing `chunk_id`, `text`,
`document_id`, `page_number`, `score`, `fusion_score`, `exact_identifier_match`,
per-channel metrics and typed `source_metadata`. Metadata includes tenant/project,
filename, document type, source date, document status, effective/document/chunk
access levels, revision, section, author, language, embedding model and chunk hash.
When reranking is enabled, `score` is the reranker score and `fusion_score` retains
the original RRF value. There is no generated answer or implied factual verification.

No relevant authorized candidates returns an explicit response:

```json
{
  "status": "insufficient_evidence",
  "results": [],
  "semantic_status": "used",
  "reranked": false
}
```

Run `alembic upgrade head` before deployment to build index
`ix_document_chunks_identifiers` (migration 0010). It changes no chunk text,
embeddings, ownership or existing evidence. Downgrade removes only the new index.
No new Python dependencies or external reranking service are required.

Tests exercise actual PostgreSQL full-text parsing and pgvector distance queries.
Fixed embedding fixtures isolate retrieval from paid/live provider variability;
the query adapter is separately tested against the ingestion interface. Coverage
includes drawing/BOQ identifiers, English stemming, semantic-only delay retrieval,
all filters in both branches, fusion, reranking, foreign tenants, owner isolation,
restricted parents/chunks, uploaders, inactive/unassigned membership, deleted and
quarantined documents, provider failures and malformed inputs. An adversarial
corpus has more hidden high-ranked matches than the candidate cap, ensuring
permission filtering occurs before that cap and before reranking.

Implementation references: [PostgreSQL text search controls](https://www.postgresql.org/docs/current/textsearch-controls.html)
and [pgvector filtering and exact search](https://github.com/pgvector/pgvector#filtering).
