#!/bin/bash
# pg_dump backup script — register as daily cron job on the VPS:
#   0 3 * * * /path/to/backup.sh >> /var/log/predicto-backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups/predicto}"
KEEP_DAYS="${KEEP_DAYS:-14}"
DB_URL="${DATABASE_URL:?DATABASE_URL env var is required}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/predicto_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."
pg_dump "$DB_URL" | gzip > "$BACKUP_FILE"
echo "[$(date)] Backup written to $BACKUP_FILE"

# Rotate: remove files older than KEEP_DAYS days
find "$BACKUP_DIR" -name "predicto_*.sql.gz" -mtime +"$KEEP_DAYS" -delete
echo "[$(date)] Rotated backups older than $KEEP_DAYS days."
echo "[$(date)] Done."
