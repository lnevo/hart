#!/usr/bin/env bash
# Launch CATS from the JMRI install (cats.jar next to jmri.jar).
# Usage: ./cats/scripts/launch_cats.sh
# Do not use sudo. Quit PanelPro first — CATS starts its own JMRI.
#
# Expectation: window chrome looks like JMRI (File/Edit/Tools…). That is normal.
# Digicon CTC board appears after File → Open on a CATS panel XML.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
# Default: Brick plant (magnet). Wired: HART_Brick.xml · Smoke: HART_smoke_Armstrong.xml
PANEL="${1:-$ROOT/cats/panels/HART_Brick_magnet.xml}"

if [[ ! -f "$JMRI_HOME/cats.jar" || ! -f "$JMRI_HOME/cats.csh" ]]; then
  echo "CATS not installed in $JMRI_HOME" >&2
  echo "Run: $ROOT/tools/cats/install_into_jmri.sh" >&2
  exit 1
fi

# cats.csh prefers the old Oracle Java 8 browser plug-in on macOS, but JMRI 5.15
# needs Java 11+ (class file 55). Force a modern JDK first.
if [[ -z "${JAVA_HOME:-}" ]]; then
  for ver in 21 17 11; do
    if JH=$(/usr/libexec/java_home -v "$ver" 2>/dev/null); then
      export JAVA_HOME="$JH"
      break
    fi
  done
fi
if [[ -z "${JAVA_HOME:-}" || ! -x "${JAVA_HOME}/bin/java" ]]; then
  echo "Need Java 11+ (JMRI 5.15). Install a JDK and retry." >&2
  /usr/libexec/java_home -V 2>&1 || true
  exit 1
fi

echo "JAVA_HOME=$JAVA_HOME"
"${JAVA_HOME}/bin/java" -version 2>&1 | head -1
echo "Starting CATS from $JMRI_HOME"
echo "When JMRI finishes loading:"
echo "  File → Open → $PANEL"
echo "Quit any existing PanelPro first if it uses the same profile."

cd "$JMRI_HOME"
# Avoid Apple Silicon 'readelf' noise in cats.csh ARM probe
export ARCH=aarch64
exec ./cats.csh
