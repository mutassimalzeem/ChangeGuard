# Database foundation (Feature 1.1)

PostgreSQL 16 and the pgvector extension are required (the repository's
`pgvector/pgvector:pg16` image includes it). Schema changes are managed by Alembic;
API startup checks connectivity and does not create tables or extensions.

From `backend`, with the virtual environment active and `DATABASE_URL` configured:

```powershell
alembic upgrade head
alembic current
```

For a new environment, the migration role needs permission to install `vector`,
create tables, and create trigger functions. Runtime roles need ordinary data
access only. The initial migration is a frozen schema, independent of future
model changes. `alembic downgrade base` removes the 16 application tables and the
timestamp trigger function; it deliberately leaves the shared vector extension.
Do not downgrade a database containing data you need.

Feature 1.2 additionally introduces authentication state and system audit tables;
see [authentication documentation](../services/AUTHENTICATION.md) for their lifecycle.
System-owned authentication events and limits also cover unknown accounts and are
intentionally distinct from tenant-owned domain records.

All records have UUID primary keys (Python and PostgreSQL defaults), timezone-aware
`created_at`/`updated_at`, and database triggers that maintain `updated_at` for SQL
and ORM writers. All domain tables except `tenants` have a non-null tenant foreign key.
Project-scoped records also enforce `(project_id, tenant_id)` ownership, and links
to project records include both project and tenant in their foreign keys. User
references include tenant ownership. Parent deletion is restricted to protect
evidence and history. Explicit removal/retention workflows are future features.

## Tables and relationships

| Table | Parent relationships / purpose |
| --- | --- |
| tenants | Customer organization; unique slug |
| users | Tenant; email unique within a tenant, password hash, initial role |
| projects | Tenant; project code unique within a tenant |
| documents | Project, optional uploader; object-storage metadata |
| document_chunks | Document; unique chunk index, text, 1536-dimensional embedding |
| project_events | Project, optional source document; event time and type |
| contracts | Project, optional document; reference, value, dates |
| contract_clauses | Contract; clause number and text |
| boq_items | Project, optional contract; quantity and unit rate |
| rfis | Project, optional source document and requesting user |
| change_orders | Project, optional contract, RFI, and creator |
| risks | Project, optional change order, document, event, and owner |
| approvals | Exactly one change order or risk; optional assignee and decision maker |
| evidence_links | Immutable typed subject/source reference with provenance and scores |
| claims | Factual assertion; AI-generated and verified claims require evidence |
| ai_answers | Grounded answer or insufficient_evidence status |
| site_photos | Project photo backed by a document |
| audit_events | Tenant, optional project/actor; action and entity reference |
| ai_traces | Tenant, optional project; provider/model, operation, usage, timing |

Typed evidence sources are documents (including uploaded images), document chunks,
site photos, project events, BOQ items, or contract clauses. Checked PostgreSQL
triggers enforce reference ownership, immutability, and factual support. See
[the evidence service contract](../services/EVIDENCE.md). Audit entity references remain generic identifiers;
they are not polymorphic foreign keys. JSON attributes are stored in the database,
not automatically logged. Do not store credentials in these attributes.

Indexes cover tenant IDs, project IDs, foreign keys, statuses, creation timestamps,
and operational dates; audit/AI history also has tenant-plus-creation-time indexes.
Money uses fixed-precision numeric columns. Status/role strings deliberately avoid
database enums while subsequent workflow and authorization features are defined.

Users belong to one tenant. Authentication is implemented in Feature 1.2;
project memberships, role enforcement, and scoped query filtering are implemented
in Feature 1.3; see [the permission matrix and integration guide](../../policy/README.md).
Composite keys protect links while the authenticated session protects reads.
PostgreSQL row-level security and audit immutability/retention policies remain
outside this foundation; direct database connections are trusted infrastructure.

## Isolated PostgreSQL tests

Set `TEST_DATABASE_ADMIN_URL` to a disposable PostgreSQL server using the asyncpg
driver. The role needs `CREATEDB` and extension-install privileges. Tests create a
new `changeguard_test_<uuid>` database, apply the real migration, and drop only
that generated database on teardown. No developer/application database is migrated
or cleared. Missing test-server configuration skips database-dependent tests;
connection or migration failures with a configured server fail the tests.

```powershell
$env:TEST_DATABASE_ADMIN_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
python -m pytest tests -v
```

`test_session` binds each test to an outer transaction with nested savepoints, so
application commits cannot leak rows into later tests. Fixtures for tenants,
projects, users, and a FastAPI client are available. The client overrides the
existing `get_session` dependency. Unit/schema/offline-SQL tests need no server.
