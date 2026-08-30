#!/usr/bin/env bash
# Download CATS 3.2 (JMRI 4.24–5.16) into tools/cats/release3.2
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$ROOT/tools/cats/release3.2"
URL="http://cats4ctc.wdfiles.com/local--files/main%3Adownloads/release3.2.zip"
mkdir -p "$ROOT/tools/cats"
TMP="$(mktemp -t cats32.XXXXXX.zip)"
echo "Fetching $URL"
curl -fsSL "$URL" -o "$TMP"
rm -rf "$DEST"
mkdir -p "$DEST"
unzip -qo "$TMP" -d "$DEST"
rm -f "$TMP"
chmod +x "$DEST/cats.csh" "$DEST/designer.csh" 2>/dev/null || true
echo "Installed → $DEST"
echo "Next: ./tools/cats/install_into_jmri.sh"
echo "See cats/README.md for HART integration steps."
