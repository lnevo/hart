#!/usr/bin/env bash
# Run before any commit that changes tables or signals. Deploy gates run separately.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export JMRI_LAYOUT=hart
fail=0
run() {
  echo "--- $1"
  shift
  "$@" || fail=1
}
run phase02 python3 jmri/scripts/check_hart_phase02.py
run tables-browser python3 www/scripts/build_tables_browser.py --check
run panel-contracts python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
run sml-invariants python3 tools/audit/check_sml_invariants.py
run mqtt-static python3 tools/audit/check_mqtt_no_static_lists.py
run wiring-crosswalk python3 tools/audit/check_wiring_crosswalk.py
run tracked-policy python3 tools/audit/check_tracked_policy.py
run agent-docs python3 tools/audit/check_agent_docs.py
run unit-jmri python3 -m unittest discover -q -s jmri/layouts/hart/scripts/tests
run unit-cats python3 -m unittest discover -q -s cats/scripts/tests
run unit-mimic python3 -m unittest discover -q -s tools/mqtt-mimic/tests
run unit-guards python3 -m unittest discover -q -s tools/audit/tests
run desks python3 cats/scripts/validate_cats_panel.py
# The portal build reads the private hart-ops submodule, which CI does not have.
if [[ -z "${CI:-}" ]]; then
  run portal python3 www/scripts/check_portal_build.py
else
  echo "--- portal skipped in CI"
fi
if [[ "$fail" -eq 0 ]]; then echo "ALL PASSED"; else echo "FAILED"; fi
exit "$fail"
