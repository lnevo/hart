#!/usr/bin/env bash
# Launch CATS 3.2 runtime (JMRI must already be running with HART profile / hart_prod.xml).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CATS="$ROOT/tools/cats/release3.2"
PANEL="${1:-$ROOT/cats/panels/HART_Brick.xml}"
if [[ ! -f "$CATS/cats.jar" ]]; then
  echo "CATS not installed — run: $ROOT/tools/cats/fetch_cats_3.2.sh" >&2
  exit 1
fi
if [[ ! -f "$PANEL" ]]; then
  echo "Panel not found: $PANEL" >&2
  exit 1
fi
echo "Open in CATS after launch: $PANEL"
echo "JMRI should already be up with jmri/layouts/hart/output/hart_prod.xml"
cd "$CATS"
exec ./cats.csh
