#!/usr/bin/env bash
# Mirror live STS runtime data into consolidation/external/sts-docker-data/
# Read-only copy from live ~/sts/ — does not modify source volumes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../env/load_consolidation_env.sh
source "${SCRIPT_DIR}/../env/load_consolidation_env.sh"

DEST="$STS_DATA_ROOT"
SRC_BACKUPS="$MIRROR_STS_BACKUPS"
SRC_DATABASE="$MIRROR_STS_DATABASE"
SRC_IMAGES="$MIRROR_STS_IMAGES"

mkdir -p "$DEST"

rsync -a --delete --stats \
  "$SRC_BACKUPS/" "$DEST/backups/"

rsync -a --delete --stats \
  "$SRC_DATABASE/" "$DEST/database/"

rsync -a --delete --stats \
  "$SRC_IMAGES/" "$DEST/images/"

MANIFEST="$DEST/MIRROR_MANIFEST.txt"
{
  echo "mirrored_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source_backups=$SRC_BACKUPS"
  echo "source_database=$SRC_DATABASE"
  echo "source_images=$SRC_IMAGES"
  echo "dest=$DEST"
  du -sh "$DEST/backups" "$DEST/database" "$DEST/images" 2>/dev/null || true
} > "$MANIFEST"

echo "STS data mirror complete → $DEST"
cat "$MANIFEST"

bash "$(dirname "$0")/refresh_sts_docker_compose.sh"
