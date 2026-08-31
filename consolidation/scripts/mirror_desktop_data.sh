#!/usr/bin/env bash
# Mirror Desktop/HART operational data into consolidation/external/desktop-data/
# Read-only rsync — does not modify ~/Desktop/HART/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$ROOT/consolidation/external/desktop-data"
DESKTOP="${DESKTOP_HART:-$HOME/Desktop/HART}"

mkdir -p "$DEST"

rsync_dir() {
  local name="$1"
  local src="$2"
  local dst="$DEST/$name"
  if [[ ! -d "$src" ]]; then
    echo "SKIP missing: $src"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  rsync -a --delete "$src/" "$dst/"
  echo "OK $name ← $src"
  du -sh "$dst" 2>/dev/null || true
}

# Required for card pipeline + STS seed (CarImagesFinal)
rsync_dir "car-images/CarImagesFinal" "$DESKTOP/Car Cards/CarImagesFinal"

# Bench wiring mirror (pipeline 8)
rsync_dir "wiring-bench" "$DESKTOP/Wiring Documentation"

# Car Cards docs not fully duplicated in hart-ops git
rsync_dir "car-cards/docs" "$DESKTOP/Car Cards/docs"

# DJ Trains prototype photos/data
rsync_dir "dj-trains" "$DESKTOP/DJ Trains"

# Raw incoming drop folder (empty — pipeline target; do not mirror old Images/)
mkdir -p "$DEST/car-cards/incoming" "$DEST/car-cards/print"
touch "$DEST/car-cards/incoming/.gitkeep" 2>/dev/null || true
echo "OK car-cards/incoming (empty drop folder for new raw photos)"

# Full car-card print deck (~345 MB) — mirror only, not git
if [[ -f "$DESKTOP/Car Cards/card_pipeline/output/HART_All_Car_Cards.docx" ]]; then
  rsync -a "$DESKTOP/Car Cards/card_pipeline/output/HART_All_Car_Cards.docx" "$DEST/car-cards/print/"
  echo "OK car-cards/print/HART_All_Car_Cards.docx"
  du -sh "$DEST/car-cards/print/HART_All_Car_Cards.docx" 2>/dev/null || true
fi

# hart-ops tracked print outputs (also in submodule git)
if [[ -d "$ROOT/consolidation/external/hart-ops/card_pipeline/output" ]]; then
  rsync -a "$ROOT/consolidation/external/hart-ops/card_pipeline/output/" "$DEST/car-cards/print/hart-ops-output/" 2>/dev/null || true
  echo "OK car-cards/print/hart-ops-output/"
fi
if [[ "${DESKTOP_MIRROR_RAW:-0}" == "1" ]]; then
  rsync_dir "car-images/Images" "$DESKTOP/Car Cards/Images"
fi

# F-root archive files (class F) — copy loose files at Desktop/HART root only
FROOT="$DEST/f-root"
mkdir -p "$FROOT"
count=0
while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  rsync -a "$f" "$FROOT/$base"
  count=$((count + 1))
done < <(find "$DESKTOP" -maxdepth 1 -type f -print0 2>/dev/null)
echo "OK f-root ($count files)"

MANIFEST="$DEST/MIRROR_MANIFEST.txt"
{
  echo "mirrored_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source_desktop=$DESKTOP"
  echo "dest=$DEST"
  echo "raw_images=${DESKTOP_MIRROR_RAW:-0}"
  du -sh "$DEST"/* 2>/dev/null || true
} > "$MANIFEST"

echo "Desktop data mirror complete → $DEST"
cat "$MANIFEST"
