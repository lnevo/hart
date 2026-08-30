#!/usr/bin/env bash
# Launch CATS Designer (standalone jar — does not need JMRI running).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
# Prefer installed copy next to JMRI; fall back to tools package
if [[ -f "$JMRI_HOME/designer.jar" ]]; then
  cd "$JMRI_HOME"
  exec java -cp "./lib/*:designer.jar" designer.gui.Ctc
fi
CATS="$ROOT/tools/cats/release3.2"
if [[ ! -f "$CATS/designer.jar" ]]; then
  echo "designer.jar missing — run fetch + install_into_jmri.sh" >&2
  exit 1
fi
cd "$CATS"
exec java -cp "./lib/*:designer.jar" designer.gui.Ctc
