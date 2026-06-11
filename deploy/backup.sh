#!/bin/bash
# Nightly SQLite backup for the Cued Up backend.
#
# Uses sqlite3's online .backup command, which is safe while the API is
# running (plain `cp` of a live WAL-mode database is NOT safe).
# Keeps the last 14 days, gzipped.
#
# Install (as the user that owns the repo):
#   crontab -e
#   15 3 * * * /home/<you>/movie_tracker/deploy/backup.sh >> /home/<you>/backups/backup.log 2>&1
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/movie_tracker}"
DB_PATH="${DB_PATH:-$REPO_DIR/server/instance/watchlist.db}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/cuedup}"
KEEP_DAYS="${KEEP_DAYS:-14}"

if [ ! -f "$DB_PATH" ]; then
    echo "$(date -Is) ERROR: database not found at $DB_PATH" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/watchlist-$STAMP.db"

sqlite3 "$DB_PATH" ".backup '$OUT'"
gzip "$OUT"

# Prune old backups
find "$BACKUP_DIR" -name 'watchlist-*.db.gz' -mtime +"$KEEP_DAYS" -delete

echo "$(date -Is) OK: backed up to $OUT.gz ($(du -h "$OUT.gz" | cut -f1))"
