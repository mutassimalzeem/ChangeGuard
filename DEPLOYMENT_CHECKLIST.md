# ChangeGuard Pilot Deployment Checklist & Runbook

This document serves as the mandatory pre-flight verification checklist, operational runbook, and disaster recovery guide for deploying **ChangeGuard** to staging and pilot production environments.

> [!IMPORTANT]
> **Strict Deployment Gate**: Do not deploy to any environment until all CI pipeline checks and local automated verification suites (lint, type check, unit tests, integration tests, golden evaluation gates, and red-team security suites) have passed without errors.

---

## 1. Pre-Deployment Configuration & Secret Management

Ensure all production secrets are loaded from a secure secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault, or environment injection) and **never** hardcoded or committed to version control.

### Mandatory Environment Variables

| Variable | Description | Validation Rule |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Target environment (`staging` or `production`) | Must not be `development` |
| `DATABASE_URL` | PostgreSQL connection string with `asyncpg` | Must use non-default credentials and dedicated user |
| `JWT_SECRET` | Secret key for signing and verifying JWT tokens | Minimum 32 cryptographically random characters |
| `REDIS_URL` | Redis broker and cache connection string | Must include authentication (`redis://:password@host:port/0`) |
| `SENTRY_DSN` | Sentry error tracking endpoint | Valid URL starting with `https://` |
| `S3_ENDPOINT_URL` | S3-compatible object storage endpoint | e.g., `https://s3.amazonaws.com` or MinIO URL |
| `S3_ACCESS_KEY` | Object storage access key ID | Non-empty string |
| `S3_SECRET_KEY` | Object storage secret key | Non-empty string |
| `S3_BUCKET_NAME` | Dedicated bucket for ChangeGuard evidence | Must exist with server-side encryption enabled |
| `CELERY_WORKER_CONCURRENCY` | Maximum concurrent task processing threads | Integer between 1 and 64 (default: `4`) |
| `REQUEST_TIMEOUT_SECONDS` | API request timeout threshold before HTTP 504 | Integer between 1 and 300 (default: `60`) |

---

## 2. Infrastructure & Staging Deployment

### Staging Verification with Docker Compose

A production-parity staging environment is defined in `docker-compose.staging.yml`.

1. **Verify configuration and environment variable substitutions:**
   ```bash
   docker-compose -f docker-compose.staging.yml config
   ```

2. **Boot staging environment:**
   ```bash
   docker-compose -f docker-compose.staging.yml up -d
   ```

3. **Verify container runtime statuses:**
   ```bash
   docker-compose -f docker-compose.staging.yml ps
   ```
   *Confirm all services (`postgres`, `redis`, `minio`, `api`, `worker`, `beat`, `frontend`) report `healthy`.*

4. **Verify container logs for startup errors:**
   ```bash
   docker-compose -f docker-compose.staging.yml logs -f api worker
   ```

---

## 3. Database Migration & Schema Verification

Database migrations must run before traffic reaches newly deployed application containers.

1. **Execute schema migrations:**
   ```bash
   # Inside the API container or migration runner:
   alembic upgrade head
   ```

2. **Confirm pgvector extension and table migration status:**
   ```sql
   SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
   SELECT version_num FROM alembic_version;
   ```

---

## 4. Health Checks & Readiness Probes

ChangeGuard provides fine-grained, dependency-specific health endpoints under `/api/v1/health/` and root `/health/`.

### Health Endpoints Reference

| Endpoint | Target Component | Success Criteria |
| :--- | :--- | :--- |
| `GET /health/live` | API Process Liveness | HTTP 200 `{"status": "alive"}` |
| `GET /api/v1/health/db` | PostgreSQL (`asyncpg` probe) | HTTP 200 `{"database": "healthy"}` |
| `GET /api/v1/health/redis` | Redis Cache & Broker ping | HTTP 200 `{"redis": "healthy"}` |
| `GET /api/v1/health/storage` | S3 / MinIO HeadBucket probe | HTTP 200 `{"storage": "healthy"}` |
| `GET /api/v1/health/worker` | Celery Worker inspect ping | HTTP 200 `{"worker": "healthy", "registered_workers": [...]}` |
| `GET /api/v1/health/ready?strict=true` | Full Aggregated Readiness | HTTP 200 `{"status": "ready"}` with all sub-checks healthy |

### Worker Container Internal Health Probe

Celery worker containers run periodic background probes via:
```bash
python -m app.core.worker_health
```
*Exits with code `0` on healthy broker connectivity and active worker ping; exits with code `1` otherwise.*

---

## 5. Error Tracking & Observability Verification

1. **Sentry Error Tracking Hook:**
   - ChangeGuard initializes Sentry in `app/core/sentry.py` on startup if `SENTRY_DSN` is configured.
   - Sentry hook automatically scrubs Authorization headers, cookies, passwords, and tokens from error payloads.
   - Celery `task_failure` signals are intercepted and forwarded with full task metadata.
   - If Sentry is disabled or unreachable, errors fall back to local structured JSON logging without crashing.

2. **Test Error Capture:**
   - Trigger a controlled test exception or verify initialization in startup logs:
     ```json
     {"action": "sentry_initialized", "environment": "staging", "traces_sample_rate": 0.1}
     ```

---

## 6. Database Backup & Disaster Recovery Procedures

ChangeGuard includes automated PostgreSQL backup and restore scripts supporting custom directory formats, SHA-256 integrity verification, and metadata manifests.

### Automated Database Backup

- **Linux / macOS (Bash):**
  ```bash
  # Execute backup with default 14-day retention pruning:
  ./scripts/backup_db.sh

  # Or specify target output directory:
  ./scripts/backup_db.sh /var/backups/changeguard
  ```

- **Windows (PowerShell):**
  ```powershell
  .\scripts\backup_db.ps1 -BackupDir "C:\backups\changeguard" -RetentionDays 14
  ```

- **Output Artifacts:**
  1. `changeguard_backup_<timestamp>.dump` (PostgreSQL custom compressed format `-Fc`)
  2. `changeguard_backup_<timestamp>.dump.sha256` (SHA-256 cryptographic checksum)
  3. `changeguard_backup_<timestamp>.meta.json` (Manifest with host, database, user, size, and timestamp)

### Database Restore Procedure

> [!CAUTION]
> Restoring a database overwrites existing data. The restore script requires an explicit `--confirm` flag and verifies the SHA-256 checksum prior to execution.

1. **Execute restore with checksum verification:**
   ```bash
   ./scripts/restore_db.sh --file /var/backups/changeguard/changeguard_backup_<timestamp>.dump --confirm
   ```

2. **Windows PowerShell restore:**
   ```powershell
   .\scripts\restore_db.ps1 -BackupFile "C:\backups\changeguard\changeguard_backup_<timestamp>.dump" -Confirm
   ```

3. **Post-restore validation:**
   - The script outputs the restored table counts automatically.
   - Run the readiness probe:
     ```bash
     curl -f http://localhost:8000/api/v1/health/ready?strict=true
     ```

---

## 7. Graceful Shutdown & Worker Lifecycle

ChangeGuard enforces graceful termination to prevent truncated in-flight requests and orphaned Celery tasks:

1. **FastAPI Web Server:**
   - Lifespan context manager (`app/main.py`) handles `SIGTERM`/`SIGINT`.
   - Flushes pending Sentry events (`flush_sentry(timeout=5.0)`).
   - Closes database connection pools gracefully (`close_db()`).
   - Uvicorn timeout graceful shutdown configured to `30s`.

2. **Celery Background Worker:**
   - Workers hook into `worker_shutting_down` and `worker_shutdown` signals (`app/core/celery_app.py`).
   - Active tasks are allowed up to the graceful shutdown window to complete or cleanly retry before termination.

---

## 8. Rollback Plan

In the event of an unrecoverable failure during deployment:

1. **Revert Routing / DNS:**
   - Direct ingress traffic back to the previous stable container image or blue/green cluster.

2. **Roll Back Database Schema (if applicable):**
   ```bash
   # Revert the last applied migration:
   alembic downgrade -1
   ```
   *If schema modifications were destructive, restore from the pre-deployment backup created in Step 6.*

3. **Restart Workers with Previous Image:**
   ```bash
   docker-compose -f docker-compose.staging.yml down
   # Update image tag to previous release
   docker-compose -f docker-compose.staging.yml up -d
   ```

---

## 9. Pilot Onboarding Sign-off Matrix

Before handing over the environment to pilot users, verify and sign off on each item:

- [ ] **CI Pipeline Passed**: All 7 CI jobs (`lint`, `typecheck`, `unit-tests`, `integration-tests`, `golden-evaluation`, `security-tests`, `docker-build`) green on main branch.
- [ ] **Golden Evaluation Gates Passed**: 100% classification accuracy, 100% field extraction accuracy, 100% citation coverage, 0 unsupported claims.
- [ ] **Red-Team Security Tests Passed**: All prompt injection and document integrity attack vectors rejected.
- [ ] **Non-Root Containers Verified**: Containers run as non-root `appuser` (backend UID 10001) and `nextjs` (frontend UID 10001).
- [ ] **Staging Readiness Probe**: `GET /api/v1/health/ready?strict=true` returns HTTP 200 with all dependencies healthy.
- [ ] **Sentry Error Reporting**: Test exception captured and verified in Sentry dashboard with scrubbed credentials.
- [ ] **Backup Script Scheduled**: Cron job / scheduled task configured to execute `backup_db.sh` daily with automated retention pruning.
- [ ] **Pilot Admins Provisioned**: Owner and Admin tenant accounts created with strong credentials and verified login.
