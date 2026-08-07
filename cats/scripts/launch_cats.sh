#!/usr/bin/env bash
# Launch CATS from the JMRI install (cats.jar must be next to jmri.jar).
# Usage: ./cats/scripts/launch_cats.sh [path-to-panel.xml]
# Do not use sudo. Do not start PanelPro on the same profile first — CATS launches JMRI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
PANEL="${1:-$ROOT/cats/panels/HART_Brick.xml}"

if [[ ! -f "$JMRI_HOME/cats.jar" || ! -f "$JMRI_HOME/cats.csh" ]]; then
  echo "CATS not installed in $JMRI_HOME" >&2
  echo "Run: $ROOT/tools/cats/install_into_jmri.sh" >&2
  exit 1
fi
if [[ ! -f "$PANEL" ]]; then
  echo "Panel not found: $PANEL" >&2
  exit 1
fi

echo "JMRI home: $JMRI_HOME"
echo "After CATS opens: File → Open → $PANEL"
echo "Quit PanelPro on this profile first — CATS starts its own JMRI."
cd "$JMRI_HOME"
# StartJMRI needs cats.jar on the classpath (--cp:a). cats.csh also works
# but prints harmless readelf noise on Apple Silicon.
START="$JMRI_HOME/PanelPro.app/Contents/MacOS/StartJMRI"
if [[ -x "$START" ]]; then
  exec "$START" --cp:a=cats.jar -m cats.apps.Crandic
fi
exec ./cats.csh
