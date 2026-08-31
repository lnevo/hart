#!/usr/bin/env bash
# Mirror live hart layout ops tree into consolidation/external/hart-runtime/
# Read-only rsync from hart repo — does not modify live sources.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${HART_MIRROR_SRC:-$ROOT}"
DEST="$ROOT/consolidation/external/hart-runtime"

mkdir -p "$DEST"

copy() {
  local rel="$1"
  local src="$SRC/$rel"
  local dst="$DEST/$rel"
  if [[ ! -e "$src" ]]; then
    echo "SKIP missing: $rel"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  rsync -a "$src/" "$dst/" 2>/dev/null || rsync -a "$src" "$dst"
  echo "OK $rel"
}

# Single files
for f in \
  tables/new_tables.xml \
  jmri/layout_paths.py
do
  if [[ -f "$SRC/$f" ]]; then
    mkdir -p "$(dirname "$DEST/$f")"
    rsync -a "$SRC/$f" "$DEST/$f"
    echo "OK $f"
  else
    echo "SKIP missing: $f"
  fi
done

# Directory trees (layout ops)
for d in \
  jmri/layouts/hart \
  jmri/scripts \
  cats/data \
  cats/panels \
  cats/scripts \
  cats/resources/signals/hart-aar \
  cats/resources/signals/cats-masts \
  cats/resources/jmri-web \
  cats/resources/icons/USS/sensor \
  cats/resources/buttons \
  cats/docs \
  docs/wiring \
  tools/jmri/patches
do
  copy "$d"
done

MANIFEST="$DEST/MIRROR_MANIFEST.txt"
{
  echo "mirrored_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source=$SRC"
  echo "dest=$DEST"
  du -sh "$DEST" 2>/dev/null || true
} > "$MANIFEST"

echo "HART runtime mirror complete → $DEST"
cat "$MANIFEST"
