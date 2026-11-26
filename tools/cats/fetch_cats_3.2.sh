#!/usr/bin/env bash
# Download CATS 3.2 (JMRI 4.24–5.16) into tools/cats/release3.2, checked against its pinned sha256.
#   CATS_ZIP=/path/release3.2.zip   use a zip already on disk instead of downloading (checked the same way)
#   CATS_DEST=/path                  install somewhere else (default tools/cats/release3.2)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${CATS_DEST:-$ROOT/tools/cats/release3.2}"
URL="https://cats4ctc.wdfiles.com/local--files/main%3Adownloads/release3.2.zip"
# release3.2.zip as published: 9898265 bytes, 37 files
SHA256="e38e7dba78df751daf2cd0bf4f710e3b9108a147a87440cab2afba4e2eef0aa1"

TMP=""
cleanup() { if [[ -n "$TMP" ]]; then rm -f "$TMP"; fi; }
trap cleanup EXIT

if [[ -n "${CATS_ZIP:-}" ]]; then
  ZIP="$CATS_ZIP"
  [[ -f "$ZIP" ]] || { echo "fetch_cats_3.2.sh: CATS_ZIP=$ZIP is not a file" >&2; exit 1; }
else
  TMP="$(mktemp -t cats32.XXXXXX)"
  echo "Fetching $URL"
  curl -fsSL "$URL" -o "$TMP"
  ZIP="$TMP"
fi

actual="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
if [[ "$actual" != "$SHA256" ]]; then
  echo "fetch_cats_3.2.sh: $ZIP does not match the pinned CATS 3.2 zip" >&2
  echo "  expected sha256 $SHA256" >&2
  echo "  actual   sha256 $actual" >&2
  echo "  nothing installed; if CATS published a new 3.2 zip, check it and update SHA256 here" >&2
  exit 1
fi

rm -rf "$DEST"
mkdir -p "$DEST"
unzip -qo "$ZIP" -d "$DEST"
chmod +x "$DEST/cats.csh" "$DEST/designer.csh" 2>/dev/null || true
echo "Installed → $DEST"
echo "Next: ./tools/cats/install_into_jmri.sh"
echo "See cats/README.md for HART integration steps."
