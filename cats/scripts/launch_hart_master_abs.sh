#!/usr/bin/env bash
# Launch CATS ABS: HOLD_ONLY, SECSIGNAL bound to JMRI masts — paint SML.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PANEL="$ROOT/cats/panels/HART_Master_ABS_hold.xml"
exec "$ROOT/cats/scripts/launch_cats.sh" "$PANEL"
