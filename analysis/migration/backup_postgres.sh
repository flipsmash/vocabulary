#!/usr/bin/env bash
# Dump the Supabase Postgres vocab schema to a timestamped archive.

set -euo pipefail

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump is not installed. Install the PostgreSQL client tools (e.g. 'sudo apt-get install postgresql-client')." >&2
  exit 1
fi

: "${PGHOST:=10.0.0.99}"
: "${PGPORT:=6543}"
: "${PGUSER:=postgres.your-tenant-id}"
: "${PGDATABASE:=postgres}"
: "${PGSCHEMA:=vocab}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "PGPASSWORD must be set in the environment (or use a ~/.pgpass entry)." >&2
  exit 1
fi

BACKUP_ROOT="${BACKUP_ROOT:-backups/postgres}"
mkdir -p "$BACKUP_ROOT"

timestamp=$(date -u +%Y%m%d_%H%M%S)
outfile="$BACKUP_ROOT/${PGDATABASE}_${PGSCHEMA}_${timestamp}.dump"

pg_dump \
  --format=custom \
  --host "$PGHOST" \
  --port "$PGPORT" \
  --username "$PGUSER" \
  --dbname "$PGDATABASE" \
  --schema "$PGSCHEMA" \
  --file "$outfile"

echo "Backup written to $outfile"

# Retain only the five most recent dumps
mapfile -t backups < <(ls -1t "$BACKUP_ROOT"/*.dump 2>/dev/null || true)
if (( ${#backups[@]} > 5 )); then
  for ((i=5; i<${#backups[@]}; i++)); do
    rm -f "${backups[$i]}"
  done
fi
