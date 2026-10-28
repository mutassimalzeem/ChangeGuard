# Celery document processing (Feature 3.1)

Apply `alembic upgrade head` before starting API, workers or Beat. Migration 0005
adds processing checkpoints, entity links, review tasks, a durable dead-letter
outbox, and PostgreSQL GIN/HNSW chunk indexes. Existing registry `status` values
remain valid. The API now reports the precise `processing_status` separately
from the coarse registry `status`; clients must accept stage names in that field.
Raw text, extracted fields, and embeddings are never returned by registry reads.

## Run

```sh
celery -A app.core.celery_app.celery_app worker -Q celery,ingestion,document_processing,ai,workflow
celery -A app.core.celery_app.celery_app beat
```

Run one Beat scheduler. Compose includes both services and enables Redis AOF.
Configure `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and
`OBJECT_STORAGE_*`. Provision the private object bucket before uploading.
Set `LLM_PROVIDER=openai` and `LLM_API_KEY` for classification, structured
extraction and embeddings. There is no fabricated local AI fallback: missing
providers send the job to the operator queue with its partial results intact.
Embeddings use the configured model with 1536 dimensions, matching the existing
database column. `PROCESSING_REVIEW_THRESHOLD` defaults to 0.8.

Text adapters handle PDF, DOCX (including tables), XLSX, EML plain-text bodies,
MSG plain-text bodies, images and validated ZIP members. Nested ZIPs and
unsupported archive members require an adapter and fail explicitly. Scanned and
mixed PDFs render with Poppler and OCR every page; the runtime image includes
Poppler and Tesseract. Use `OCR_PROVIDER=tesseract` for local OCR; otherwise
image transcription uses the configured OpenAI vision model. AWS Textract and
Azure OCR adapters are not included. Native Windows workers require the
corresponding binaries on PATH; Linux containers are the deployment target.
OCR is limited to 100 pages; extracted text to 2 million characters; chunk count
to `MAX_CHUNKS_PER_DOCUMENT`. Provider I/O has explicit timeouts.

## Stages and recovery

Each delivery runs one stage, then publishes a continuation containing only
document and tenant IDs. The worker loads the project from the tenant-matched
document rather than trusting a project supplied in a message.

| Stage | Durable output |
| --- | --- |
| `validate_file` | Verified format and SHA-256 |
| `store_original` | Verified immutable original key and checksum |
| `extract_text` | Text/OCR output |
| `classify_document` | Pydantic-validated document type and confidence |
| `extract_fields` | Raw structured provider output |
| `validate_extraction` | Pydantic-validated fields and combined confidence |
| `create_chunks` | Ordered, overlapping document chunk records |
| `generate_embeddings` | Validated finite vectors on chunks |
| `index_chunks` | Verified complete chunks in transactional PostgreSQL indexes |
| `link_entities` | Tenant/project constrained links to existing contracts, RFIs, change orders |
| `risk_checks` | Deterministic risk records |
| `create_review_task` | One pending review if confidence is low or risk checks flag a concern |

The upload API validates and creates the immutable original **before** queueing;
the first two asynchronous stages revalidate it and confirm storage without
overwriting it. No file bytes or provider output enter Celery messages/results.
Matching entities uses exact references and never creates or approves domain
records from AI output. Missing entities are retained as unresolved references.
Risk checks cover negative amounts, missing currency, dates overdue at receipt,
and unresolved references. They do not make probabilistic risk decisions.

`processing_status` is the stage name while running and `<stage>_done` after
success. Terminal values are `completed`, `review_required`, and `dead_letter`.
Each stage logs its start and result with document, tenant, project, attempt and
duration. Exception messages and document text are excluded from worker logs.

Each worker invocation pins a PostgreSQL connection and holds a document advisory
lock across commits. Status and attempt count commit before provider I/O.
Stage output, side effects, and checkpoint commit atomically. A duplicate delivery
skips completed stages; a concurrent delivery skips a locked document. Provider
calls may be repeated after a process dies before committing, but durable chunk,
link, risk and review records are not duplicated. Successful earlier stages stay
intact if later ones fail. Raw extraction output survives schema rejection.

Transient connection, storage, provider 429/5xx and timeout failures retry at
30, 60, and 120 seconds (four total attempts). Retry eligibility and next-attempt
time live in PostgreSQL, so duplicate messages and worker restarts cannot reset
the budget or bypass backoff. Invalid content/schema and missing provider
configuration go directly to the dead-letter queue. Interrupted attempts consume
the same budget. Beat republishes stale stored, queued or processing documents
after five minutes and dispatches pending dead letters every minute.

## Dead letters and review

`processing_dead_letters` is the authoritative durable operator queue. Beat
publishes identifier-only notifications to Redis queue `document_dead_letter`
and marks outbox entries published. Publication can repeat after a crash between
send and commit: consumers must deduplicate by `dead_letter_id`. Default workers
explicitly exclude this queue; do not subscribe a general worker to it.
The notification task name is an operator envelope, without an automatic task
consumer or automatic replay. A broker outage leaves the durable entry pending.

Operators can inspect the stage, attempt count and safe error type alongside
the retained document checkpoint. Resolve the cause before replaying. Replay
must run under the same document lock, clear only the failed stage's attempt/
retry metadata, set the document to queued, and republish its IDs. Invalid
provider output may require re-running extraction as well as validation.
Earlier chunk/link/risk side effects must not be discarded without reconciling
their checkpoints. There is no public replay endpoint in this feature.

Low-confidence/risk review tasks are persisted in `document_review_tasks` with
tenant/project/document ownership and a pending status. Assignment and review
UI are subsequent workflow features.

## Validation

```sh
DEBUG=false TEST_DATABASE_ADMIN_URL=postgresql+asyncpg://USER:PASS@HOST:PORT/postgres pytest tests/test_processing_pipeline.py
```

The fixtures create and drop a disposable UUID-named PostgreSQL database.
OCR, classifier, extractor and embedding services are mocked. Tests cover all
stages, duplicate/concurrent delivery, tenant isolation, partial resume, invalid
schemas, exponential backoff, interrupted attempts, deterministic risks,
review creation, stage logs, queue recovery and dead-letter outbox failure.

A separate broker smoke test starts a real Celery solo worker and runs all twelve
stages through disposable Redis with mocked providers:

```sh
DEBUG=false TEST_DATABASE_ADMIN_URL=postgresql+asyncpg://USER:PASS@HOST:PORT/postgres TEST_REDIS_URL=redis://127.0.0.1:56379/1 CELERY_BROKER_URL=redis://127.0.0.1:56379/1 CELERY_RESULT_BACKEND=redis://127.0.0.1:56379/2 pytest tests/test_processing_redis.py
```

Use an isolated Redis instance; the worker consumes its ingestion queue. This
verifies real broker delivery and continuation, not provider accuracy or native
OCR quality. Live model calls and OCR binaries are not exercised by mock tests.
