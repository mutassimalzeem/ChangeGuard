# Document upload and registry (Feature 2.3)

Apply `alembic upgrade head` before starting the API and workers. Migration 0004
extends the existing document table without changing IDs or related foreign keys.
Existing non-pipeline statuses become `review_required`. If legacy rows have
duplicate non-null checksums within a tenant/project, reconcile those records
before upgrading; the migration deliberately refuses to discard their hashes.

## API

All endpoints require a bearer token, tenant isolation, project membership
(owners/admins have tenant-wide project access), and `documents.read` or
`documents.write` as appropriate.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/v1/projects/{project_id}/documents` | Multipart `file`, optional `source` (default `upload`), `document_type`, `access_level` (`project` or `restricted`) |
| GET | `/api/v1/projects/{project_id}/documents` | Newest first, `offset=0`, `limit=50` (maximum 100) |
| GET | `/api/v1/documents/{document_id}` | Registry metadata |
| GET | `/api/v1/documents/{document_id}/download-url` | Signed URL and `expires_in=3600` |
| DELETE | `/api/v1/documents/{document_id}` | Soft delete, 204; preserve original and registry for retention |

`restricted` files are visible only to their uploader and tenant owners/admins,
who must still pass the tenant/project boundary. Hidden records return 404.

Successful uploads return 201 and the metadata. SHA-256 duplicates return 409
within the same tenant/project, including retained soft-deleted records; the
database uniqueness constraint also protects concurrent requests. Identical
bytes can be uploaded in different projects.

Invalid/unsupported uploads return **422 with retained document metadata** and
`processing_status=quarantined`. Oversized uploads return **413 with retained
metadata**. These are ingestion outcomes, not ordinary FastAPI validation errors.
Original bytes are preserved under the tenant/project quarantine prefix.
Quarantined, failed, or incomplete files cannot receive download URLs.
The limit is 50 MiB; oversized uploads are hashed and stored from the multipart
spooled file without loading the entire file into application memory. Configure
the ingress request limit and temporary disk capacity to permit retention of
the largest rejected upload you need to preserve.

MVP formats: pdf, docx, xlsx, jpg, jpeg, png, eml, msg, zip. Validation parses
PDFs, verifies images, checks archive CRCs and expansion limits, parses Office
XML with defusedxml, checks email headers, and validates MSG compound storage.
ZIPs are never extracted to disk; unsafe paths are quarantined. This is format
validation, not malware scanning. Encrypted/unreadable files are quarantined.

## Retention and processing

Configure the existing `OBJECT_STORAGE_*` settings and provision the private
bucket using `ObjectStorageService.ensure_bucket_exists()`. The registry uses
`If-None-Match: *` on every original write, so a repeated write cannot overwrite
an existing key. The application does not expose an original replacement API.
Use storage credentials/policies that prohibit external modification or deletion
if storage-level retention beyond this API is required.

Accepted uploads persist `received`, `validating`, `stored`, then `queued` around
the storage/queue boundaries. Celery runs `process_uploaded_file` with document
and tenant IDs after commit. Start the worker and Beat:

```sh
celery -A app.core.celery_app.celery_app worker -Q ingestion,document_processing
celery -A app.core.celery_app.celery_app beat
```

Feature 3.1 now runs the complete processing pipeline. See
[the pipeline operations guide](../app/document_processing/README.md) for stages,
provider configuration, retries, durable checkpoints and dead-letter handling.
`processing_status` reports each stage; `status` retains the coarse registry state.
Beat recovers interrupted processing and dispatches dead-letter notifications.

Processing failures preserve the immutable original and completed stage results.
Permanent/exhausted failures enter the dead-letter queue. Storage outages during
upload return 503
with a persisted `failed` registry record and an operator-facing error. An object
store that is unavailable cannot guarantee retention of bytes it did not accept;
operators must reconcile the key and retry from the source after recovery.
No failed or quarantined record is automatically removed. Storage-write failure
records remain in duplicate detection until explicitly reconciled by an operator.

## Verification

Use a disposable PostgreSQL server with pgvector and CREATEDB privileges:

```sh
DEBUG=false TEST_DATABASE_ADMIN_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/postgres pytest tests/test_documents.py tests/test_document_files.py
```

Fixtures create and destroy a unique database and apply real migrations. API
tests mock object storage and Celery publication. Worker tests run the actual
async worker logic against PostgreSQL with mocked storage. These checks do not
replace a deployment smoke test with real S3/MinIO and a running broker/worker.
