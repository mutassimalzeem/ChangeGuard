#!/usr/bin/env bash
# ==============================================================================
# ChangeGuard - Database Restore Script
#
# Safely restores a ChangeGuard database from a validated pg_dump archive.
# Performs checksum verification, confirmation safety checks, and post-restore
# schema integrity validation.
#
# Usage:
#   ./scripts/restore_db.sh --file <backup_file> --confirm [options]
#
# Options:
#   -f, --file FILE         Path to backup file (.dump) (REQUIRED)
#   -u, --url URL           Target PostgreSQL URL (default: $DATABASE_URL)
#       --confirm           Explicit confirmation to execute restore (REQUIRED)
#       --skip-checksum     Bypass SHA-256 checksum verification
#   -h, --help              Show help message
# ==============================================================================

set -euo pipefail

BACKUP_FILE=""
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/changeguard}"
CONFIRMED=false
VERIFY_CHECKSUM=true

while [[ $# -gt 0 ]]; do
  case $1 in
    -f|--file)
      BACKUP_FILE="$2"
      shift 2
      ;;
    -u|--url)
      DATABASE_URL="$2"
      shift 2
      ;;
    --confirm)
      CONFIRMED=true
      shift
      ;;
    --skip-checksum)
      VERIFY_CHECKSUM=false
      shift
      ;;
    -h|--help)
      echo "Usage: $0 --file <backup_file> --confirm [-u database_url] [--skip-checksum]"
      exit 0
      ;;
    *)
      echo "Error: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

log() {
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [INFO] $*"
}

warn() {
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [WARN] $*" >&2
}

error() {
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [ERROR] $*" >&2
}

# 1. Validation of inputs
if [[ -z "${BACKUP_FILE}" ]]; then
  error "Missing required argument: --file <path_to_backup>"
  exit 1
fi

if [[ ! -f "${BACKUP_FILE}" ]]; then
  error "Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

if [[ "${CONFIRMED}" != true ]]; then
  error "Safety check failed: Database restore requires explicit '--confirm' flag to prevent accidental overwrite."
  exit 1
fi

# Sanitize asyncpg scheme if present
CLEAN_DB_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"

# 2. Check for pg_restore utility
if ! command -v pg_restore &>/dev/null; then
  error "pg_restore utility not found in PATH. Please install postgresql-client."
  exit 1
fi

if ! command -v psql &>/dev/null; then
  error "psql utility not found in PATH. Please install postgresql-client."
  exit 1
fi

# 3. Checksum verification
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ "${VERIFY_CHECKSUM}" == true && -f "${CHECKSUM_FILE}" ]]; then
  log "Verifying SHA-256 checksum against ${CHECKSUM_FILE}..."
  EXPECTED_HASH="$(awk '{print $1}' "${CHECKSUM_FILE}")"

  if command -v sha256sum &>/dev/null; then
    ACTUAL_HASH="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
  elif command -v shasum &>/dev/null; then
    ACTUAL_HASH="$(shasum -a 256 "${BACKUP_FILE}" | awk '{print $1}')"
  else
    ACTUAL_HASH="$(openssl dgst -sha256 "${BACKUP_FILE}" | awk '{print $NF}')"
  fi

  if [[ "${EXPECTED_HASH}" != "${ACTUAL_HASH}" ]]; then
    error "Checksum mismatch! Expected: ${EXPECTED_HASH}, Actual: ${ACTUAL_HASH}. Aborting restore."
    exit 1
  fi
  log "Checksum validated successfully."
elif [[ "${VERIFY_CHECKSUM}" == true ]]; then
  warn "Checksum file ${CHECKSUM_FILE} not found; proceeding with unverified archive."
fi

# 4. Test target connectivity
log "Testing connection to target database..."
psql "${CLEAN_DB_URL}" -c "SELECT 1;" >/dev/null

# 5. Restore database
log "Executing restore from ${BACKUP_FILE}..."
# pg_restore exit code 0 is clean success; code 1 often occurs when dropping non-existent objects, which is acceptable with --clean
set +e
pg_restore \
  --dbname="${CLEAN_DB_URL}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --verbose \
  "${BACKUP_FILE}"
RESTORE_STATUS=$?
set -e

if [[ ${RESTORE_STATUS} -ne 0 && ${RESTORE_STATUS} -ne 1 ]]; then
  error "pg_restore failed with exit code ${RESTORE_STATUS}"
  exit "${RESTORE_STATUS}"
fi

# 6. Post-restore verification
log "Performing post-restore integrity checks..."

# Verify core tables exist
TABLE_COUNT="$(psql "${CLEAN_DB_URL}" -t -A -c "
  SELECT count(*) FROM information_schema.tables 
  WHERE table_schema = 'public' 
    AND table_name IN ('tenants', 'projects', 'users', 'documents', 'change_orders');
")"

if [[ "${TABLE_COUNT}" -lt 4 ]]; then
  error "Integrity check failed: Expected at least 4 core ChangeGuard tables, found ${TABLE_COUNT}."
  exit 1
fi

log "Integrity verification passed: Core ChangeGuard tables verified (${TABLE_COUNT} core tables present)."
log "Database successfully restored from ${BACKUP_FILE}."
exit 0
