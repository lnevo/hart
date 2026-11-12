#!/usr/bin/env bash
# Copy the live STS's data off the Pi's SD card onto the Mac (ADR-020).
# Run after an operating session. It only reads on the Pi.
#
#   - STS backups taken in the web app: ~/sts/sts-docker-data/backups, copied
#     into external/sts-docker-data/pi/backups (nothing is ever deleted here)
#   - a dump of the whole live database, kept as
#     external/sts-docker-data/pi/db/sts_db3_<time>.sql.gz
#
# The files go to the main checkout's gitignored data folder, also when this
# runs from a worktree. They are kept apart from the Mac copy's own backups.
# A dump is a plain SQL file: to look at one, load it into the sandbox stack,
# never into the Pi.
set -euo pipefail

HOST="${PI_HOST:-pi}"
MAIN="$(cd "$(git -C "$(dirname "$0")" rev-parse --git-common-dir)/.." && pwd)"
DEST="${STS_PI_COPY:-$MAIN/external/sts-docker-data/pi}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DEST/backups" "$DEST/db"

rsync -a "$HOST:sts/sts-docker-data/backups/" "$DEST/backups/"
echo "backups: $(find "$DEST/backups" -maxdepth 1 -type f | wc -l | tr -d ' ') files in $DEST/backups"

dump="$DEST/db/sts_db3_$STAMP.sql.gz"
# --single-transaction reads a consistent snapshot without locking the tables.
ssh "$HOST" 'docker exec sts-docker-db-1 mariadb-dump -usts_user -psts_password --single-transaction --routines sts_db3' \
  | gzip -9 > "$dump.part"
# A dump that did not finish has no trailer line; refuse it.
if ! gzip -dc "$dump.part" | tail -1 | grep -q '^-- Dump completed'; then
  rm -f "$dump.part"
  echo "database dump incomplete; nothing kept" >&2
  exit 1
fi
mv "$dump.part" "$dump"
echo "database: $dump ($(du -h "$dump" | cut -f1))"
