#!/usr/bin/env bash
# Read-only validator orchestrator. Writes reports under consolidation/audits/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIT_DIR="$ROOT/consolidation/audits"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="$AUDIT_DIR/run_all_${TS}.log"
mkdir -p "$AUDIT_DIR"

# shellcheck source=consolidation/validators/_hart_root.sh
source "$ROOT/consolidation/validators/_hart_root.sh"

cd "$ROOT"
exec > >(tee "$REPORT") 2>&1

echo "=== HART consolidation validators ==="
echo "Root: $ROOT"
echo "HART_LIVE_ROOT: $HART_LIVE_ROOT"
echo "Report: $REPORT"
echo

FAIL=0

run() {
  local name="$1"
  shift
  echo "--- $name ---"
  if "$@"; then
    echo "OK: $name"
  else
    echo "FAIL: $name"
    FAIL=1
  fi
  echo
}

run "audit_strict" bash consolidation/validators/check_audit_strict.sh
run "phase02" bash consolidation/validators/check_phase02.sh
run "phase02_map_draft" bash consolidation/validators/check_phase02_from_map.sh
run "names_diff" python3 consolidation/validators/check_names_diff.py
run "sml_invariants" python3 consolidation/validators/check_sml_invariants.py
run "mqtt_static" python3 consolidation/validators/check_mqtt_no_static_lists.py
run "wiring_crosswalk" python3 consolidation/validators/check_wiring_crosswalk.py

echo "=== Summary ==="
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL PASSED"
  ln -sf "$(basename "$REPORT")" "$AUDIT_DIR/latest.log"
  exit 0
else
  echo "SOME CHECKS FAILED — see $REPORT"
  ln -sf "$(basename "$REPORT")" "$AUDIT_DIR/latest.log"
  exit 1
fi
