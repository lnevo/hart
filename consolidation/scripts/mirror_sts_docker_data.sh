#!/usr/bin/env bash
# Mirror live STS runtime data into consolidation/external/sts-docker-data/
# Read-only copy from ~/sts/ — does not modify source volumes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$ROOT/consolidation/external/sts-docker-data"
SRC_BACKUPS="${STS_BACKUPS:-$HOME/sts/sts-backups}"
SRC_DATABASE="${STS_DATABASE:-$HOME/sts/sts-database}"
SRC_IMAGES="${STS_IMAGES:-$HOME/sts/sts-images}"

mkdir -p "$DEST"

rsync -a --delete --stats \
  "$SRC_BACKUPS/" "$DEST/backups/"

rsync -a --delete --stats \
  "$SRC_DATABASE/" "$DEST/database/"

rsync -a --delete --stats \
  "$SRC_IMAGES/" "$DEST/Rolling Stock photos/"

MANIFEST="$DEST/MIRROR_MANIFEST.txt"
{
  echo "mirrored_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source_backups=$SRC_BACKUPS"
  echo "source_database=$SRC_DATABASE"
  echo "source_images=$SRC_IMAGES"
  echo "dest=$DEST"
  du -sh "$DEST/backups" "$DEST/database" "$DEST/Rolling Stock photos" 2>/dev/null || true
} > "$MANIFEST"

echo "STS data mirror complete → $DEST"
cat "$MANIFEST"
