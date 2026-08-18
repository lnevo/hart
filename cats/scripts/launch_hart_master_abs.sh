#!/usr/bin/env bash
# Launch CATS ABS: Digicon reference panel. SECSIGNAL names unbound from JMRI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PANEL="$ROOT/cats/panels/HART_Master_ABS.xml"
exec "$ROOT/cats/scripts/launch_cats.sh" "$PANEL"
