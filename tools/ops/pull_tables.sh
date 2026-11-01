#!/usr/bin/env bash
# Bring a PanelPro Store from ~/JMRI_UserFiles/tables.xml back into the repo (ADR-014).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${HOME}/JMRI_UserFiles/tables.xml"
DEST="$ROOT/jmri/layouts/hart/output/tables.xml"

if pgrep -f 'java .*(apps\.PanelPro\.PanelPro|cats\.apps\.Crandic)' >/dev/null 2>&1; then
  echo "Quit PanelPro and CATS first." >&2
  exit 1
fi
if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi
if cmp -s "$SRC" "$DEST"; then
  echo "Repo tables.xml already matches $SRC"
  exit 0
fi
cp -f "$SRC" "$DEST"
shasum -a 256 "$SRC" | cut -d' ' -f1 >"$(dirname "$SRC")/.tables_deployed.sha256"
echo "tables.xml -> $DEST. Run ./tools/check.sh, then commit."
