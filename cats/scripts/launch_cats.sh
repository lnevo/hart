#!/usr/bin/env bash
# Launch CATS from the JMRI install (cats.jar next to jmri.jar).
# Usage: ./cats/scripts/launch_cats.sh
# Do not use sudo. Quit PanelPro first — CATS starts its own JMRI.
#
# Expectation: window chrome looks like JMRI (File/Edit/Tools…). That is normal.
# The Digicon CTC board appears after File → Open on a CATS panel XML
# (e.g. cats/panels/HART_Brick.xml). There is no separate top-level "CATS" menu.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
PANEL="${1:-$ROOT/cats/panels/HART_Brick.xml}"

if [[ ! -f "$JMRI_HOME/cats.jar" || ! -f "$JMRI_HOME/cats.csh" ]]; then
  echo "CATS not installed in $JMRI_HOME" >&2
  echo "Run: $ROOT/tools/cats/install_into_jmri.sh" >&2
  exit 1
fi

echo "Starting CATS (main class cats.apps.Crandic) from $JMRI_HOME"
echo "When JMRI finishes loading:"
echo "  File → Open → $PANEL"
echo "You should then see the Digicon-style CTC grid (Brick stub)."
echo "Quit any existing PanelPro first if it uses the same profile."

cd "$JMRI_HOME"
# Avoid Apple Silicon 'readelf' noise in cats.csh ARM probe
export ARCH=aarch64
exec ./cats.csh
