#!/usr/bin/env bash
# Copy the live STS's data off the Pi's SD card onto the Mac (ADR-020).
# Run after an operating session. It only reads on the Pi.
#
#   - STS backups taken in the web app: ~/sts/sts-docker-data/backups, copied
#     into external/sts-docker-data/pi/backups (nothing is deleted there)
#   - a dump of the whole live database, kept as
#     external/sts-docker-data/pi/db/sts_db3_<time>.sql.gz; the newest
#     STS_PI_KEEP_DUMPS (default 30) are kept
#
# The files go to the main checkout's gitignored data folder, also when this
# runs from a worktree. They are kept apart from the Mac copy's own backups.
# A dump is a plain SQL file: to look at one, load it into the sandbox stack,
# never into the Pi.
set -euo pipefail

HOST="${PI_HOST:-pi}"
KEEP="${STS_PI_KEEP_DUMPS:-30}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
MAIN="$(dirname "$(git -C "$(dirname "$0")" rev-parse --path-format=absolute --git-common-dir)")"
DEST="${STS_PI_COPY:-$MAIN/external/sts-docker-data/pi}"
STAMP="$(date +%Y%m%d-%H%M%S)"
dump="$DEST/db/sts_db3_$STAMP.sql.gz"
trap 'rm -f "$dump.part"' EXIT

mkdir -p "$DEST/backups" "$DEST/db"

rsync -a -e "ssh ${SSH_OPTS[*]}" "$HOST:sts/sts-docker-data/backups/" "$DEST/backups/"
echo "backups: $(find "$DEST/backups" -maxdepth 1 -type f | wc -l | tr -d ' ') files in $DEST/backups"

# Credentials come from the db container's own environment, so none are
# written here or shown in ps. --single-transaction reads a consistent snapshot
# without locking the tables.
# shellcheck disable=SC2016  # expanded inside the container
ssh "${SSH_OPTS[@]}" "$HOST" \
  'docker exec sts-docker-db-1 sh -c '\''MYSQL_PWD="$MYSQL_PASSWORD" exec mariadb-dump -u"$MYSQL_USER" --single-transaction --routines "$MYSQL_DATABASE"'\''' \
  | gzip -9 > "$dump.part"
# A dump that did not finish has no trailer line; refuse it.
if ! gzip -dc "$dump.part" | tail -1 | grep -q '^-- Dump completed'; then
  echo "database dump incomplete; nothing kept" >&2
  exit 1
fi
mv "$dump.part" "$dump"
echo "database: $dump ($(du -h "$dump" | cut -f1))"

# Keep the newest dumps only (names sort by time).
find "$DEST/db" -maxdepth 1 -name 'sts_db3_*.sql.gz' | sort -r | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old"
done
