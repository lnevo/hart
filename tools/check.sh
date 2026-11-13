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
run track-lengths python3 jmri/layouts/hart/scripts/export_track_lengths.py --check
run panel-contracts python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
run baselines python3 jmri/layouts/hart/scripts/capture_public_name_baseline.py --check
run le-polish python3 jmri/layouts/hart/scripts/polish_hart_layout_editor.py --check
run le-overlap python3 jmri/layouts/hart/scripts/polish_hart_layout_editor.py --overlap-cleanup --check
run digicon-disabled python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py --check
run dispatcher-stations python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py --check --no-sync
run sml-invariants python3 tools/audit/check_sml_invariants.py
run mqtt-static python3 tools/audit/check_mqtt_no_static_lists.py
run wiring-crosswalk python3 tools/audit/check_wiring_crosswalk.py
run tracked-policy python3 tools/audit/check_tracked_policy.py
run agent-docs python3 tools/audit/check_agent_docs.py
run unit-jmri python3 -m unittest discover -q -s jmri/layouts/hart/scripts/tests
run unit-cats python3 -m unittest discover -q -s cats/scripts/tests
run unit-mimic python3 -m unittest discover -q -s tools/mqtt-mimic/tests
run unit-guards python3 -m unittest discover -q -s tools/audit/tests
run unit-hosts python3 -m unittest discover -q -s tools/hosts/tests
run unit-portal python3 -m unittest discover -q -s www/scripts/tests
run desks python3 cats/scripts/validate_cats_panel.py
# Car cards, intake and publications. Uses ops/hart-ops/.venv when it exists; a checkout
# without it (a worktree) skips, CI installs ops/hart-ops/requirements-test.txt.
HOPS_PY=python3
[[ -x ops/hart-ops/.venv/bin/python ]] && HOPS_PY=ops/hart-ops/.venv/bin/python
# The venv carries pypdf for the PDF part; plain python3 checks everything else.
run public-text "$HOPS_PY" tools/audit/check_public_text.py
if [[ -n "${CI:-}" ]] || "$HOPS_PY" -c "import numpy, scipy, docx, pytesseract" 2>/dev/null; then
  run unit-hart-ops "$HOPS_PY" -m unittest discover -q -s ops/hart-ops/tests
else
  echo "--- unit-hart-ops skipped (no ops/hart-ops/.venv)"
fi
# The portal build needs the gitignored photo mirrors (media/), which CI does not have.
if [[ -z "${CI:-}" ]]; then
  run portal python3 www/scripts/check_portal_build.py
else
  echo "--- portal skipped in CI"
fi
if [[ "$fail" -eq 0 ]]; then echo "ALL PASSED"; else echo "FAILED"; fi
exit "$fail"
