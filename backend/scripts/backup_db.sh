#!/usr/bin/env bash
# ==============================================================================
# ChangeGuard - Automated Database Backup Script
#
# Generates compressed, checksummed PostgreSQL backups with metadata manifests
# and automatic retention pruning.
#
# Usage:
#   ./scripts/backup_db.sh [options]
#
# Options:
#   -d, --dir DIR           Backup directory (default: ./backups)
#   -u, --url URL           PostgreSQL connection URL (default: $DATABASE_URL)
#   -r, --retention DAYS    Days of backups to keep (default: 7)
#   -h, --help              Show help message
# ==============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/changeguard}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%SZ)"
APP_VERSION="${APP_VERSION:-0.1.0}"

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -d|--dir)
      BACKUP_DIR="$2"
      shift 2
      ;;
    -u|--url)
      DATABASE_URL="$2"
      shift 2
      ;;
    -r|--retention)
      RETENTION_DAYS="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [-d backup_dir] [-u database_url] [-r retention_days]"
      exit 0
      ;;
    *)
      echo "Error: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

BACKUP_FILE="${BACKUP_DIR}/changeguard_backup_${TIMESTAMP}.dump"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
MANIFEST_FILE="${BACKUP_DIR}/changeguard_backup_${TIMESTAMP}.meta.json"

log() {
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [INFO] $*"
}

warn() {
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [WARN] $*" >&2
}

error() {
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] [ERROR] $*" >&2
}

cleanup_on_failure() {
  if [[ -f "${BACKUP_FILE}" ]]; then
    warn "Removing partial backup file due to error: ${BACKUP_FILE}"
    rm -f "${BACKUP_FILE}" "${CHECKSUM_FILE}" "${MANIFEST_FILE}"
  fi
}
trap cleanup_on_failure ERR

# Sanitize asyncpg scheme if present
CLEAN_DB_URL="${DATABASE_URL/postgresql+asyncpg:\/\//postgresql:\/\/}"

log "Starting ChangeGuard database backup..."
log "Target directory: ${BACKUP_DIR}"

# Check for pg_dump availability
if ! command -v pg_dump &>/dev/null; then
  error "pg_dump utility not found in PATH. Please install postgresql-client."
  exit 1
fi

PG_VERSION="$(pg_dump --version)"
log "Using ${PG_VERSION}"

# Execute pg_dump in custom archive format (-Fc)
# -Fc includes compression, table metadata, and supports selective/parallel restore
log "Dumping database schema and data..."
pg_dump \
  --dbname="${CLEAN_DB_URL}" \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-privileges \
  --file="${BACKUP_FILE}"

BACKUP_SIZE="$(wc -c < "${BACKUP_FILE}" | tr -d ' ')"
log "Dump completed. Size: ${BACKUP_SIZE} bytes"

# Generate SHA-256 checksum
log "Generating SHA-256 checksum..."
if command -v sha256sum &>/dev/null; then
  sha256sum "${BACKUP_FILE}" | awk '{print $1}' > "${CHECKSUM_FILE}"
elif command -v shasum &>/dev/null; then
  shasum -a 256 "${BACKUP_FILE}" | awk '{print $1}' > "${CHECKSUM_FILE}"
else
  openssl dgst -sha256 "${BACKUP_FILE}" | awk '{print $NF}' > "${CHECKSUM_FILE}"
fi
CHECKSUM="$(cat "${CHECKSUM_FILE}")"
log "SHA-256: ${CHECKSUM}"

# Generate metadata manifest JSON
cat > "${MANIFEST_FILE}" <<EOF
{
  "application": "ChangeGuard",
  "version": "${APP_VERSION}",
  "timestamp": "${TIMESTAMP}",
  "backup_file": "$(basename "${BACKUP_FILE}")",
  "size_bytes": ${BACKUP_SIZE},
  "sha256": "${CHECKSUM}",
  "pg_dump_version": "${PG_VERSION}",
  "format": "pg_custom_archive",
  "status": "completed"
}
EOF
log "Wrote metadata manifest: ${MANIFEST_FILE}"

# Prune old backups older than RETENTION_DAYS
if [[ "${RETENTION_DAYS}" -gt 0 ]]; then
  log "Pruning backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
  find "${BACKUP_DIR}" -type f \( -name "changeguard_backup_*.dump" -o -name "changeguard_backup_*.sha256" -o -name "changeguard_backup_*.meta.json" \) -mtime +"${RETENTION_DAYS}" -exec rm -f {} + || true
  log "Retention pruning complete."
fi

log "Backup successfully created: ${BACKUP_FILE}"
exit 0
