#!/usr/bin/env bash
# Launch CATS ABS (HOLD_ONLY): turnout control on; JMRI SML owns aspects.
# Rebuild from Master ABS if missing:
#   python3 cats/scripts/build_hart_master_abs_hold.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOLD="$ROOT/cats/panels/HART_Master_ABS_hold.xml"
if [[ ! -f "$HOLD" ]]; then
  python3 "$ROOT/cats/scripts/build_hart_master_abs_hold.py"
fi
exec "$ROOT/cats/scripts/launch_cats.sh" "$HOLD"
