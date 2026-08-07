#!/usr/bin/env bash
# Copy CATS 3.2 into a JMRI install (required — cats.jar must sit next to jmri.jar).
# Default: /Applications/JMRI
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/tools/cats/release3.2"
JMRI_HOME="${1:-/Applications/JMRI}"

if [[ ! -f "$JMRI_HOME/jmri.jar" ]]; then
  echo "JMRI not found at $JMRI_HOME (no jmri.jar)" >&2
  exit 1
fi
if [[ ! -f "$SRC/cats.jar" ]]; then
  echo "CATS package missing — run: $ROOT/tools/cats/fetch_cats_3.2.sh" >&2
  exit 1
fi

echo "Installing CATS 3.2 → $JMRI_HOME"
cp -f "$SRC/cats.jar" "$SRC/designer.jar" "$SRC/cats.csh" "$SRC/designer.csh" "$JMRI_HOME/"
# optional assets
[[ -f "$SRC/crandic.gif" ]] && cp -f "$SRC/crandic.gif" "$JMRI_HOME/"
mkdir -p "$JMRI_HOME/lib" "$JMRI_HOME/resources" "$JMRI_HOME/examples"
# CATS ships log4j + jdom2; copy if not already present (do not overwrite JMRI jars blindly)
for j in "$SRC"/lib/*.jar; do
  base=$(basename "$j")
  if [[ ! -f "$JMRI_HOME/lib/$base" ]]; then
    cp -f "$j" "$JMRI_HOME/lib/"
    echo "  + lib/$base"
  fi
done
# manuals / examples stay optional under examples
cp -f "$SRC"/examples/*.xml "$JMRI_HOME/examples/" 2>/dev/null || true

chmod +x "$JMRI_HOME/cats.csh" "$JMRI_HOME/designer.csh"
echo "Done. Launch with: $ROOT/cats/scripts/launch_cats.sh"
echo "Do NOT use sudo. Do NOT start a second PanelPro on the same profile first — CATS starts JMRI itself."
