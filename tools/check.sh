#!/usr/bin/env bash
# Run before any commit that changes tables or signals. Deploy gates run separately.
# HART_TABLES=<tables file> runs the table checks against that file instead of the checkout's
# own (the Layout Editor cut-over candidate, a sandbox copy; hartlib.paths). The unit tests
# always run against the checkout's own file.
set -uo pipefail
# A relative HART_TABLES is the caller's (read before the cd below), and ~ is expanded as hartlib does.
if [[ -n "${HART_TABLES:-}" ]]; then
  case "$HART_TABLES" in "~"/*) HART_TABLES="$HOME/${HART_TABLES#"~/"}" ;; esac
  [[ -f "$HART_TABLES" ]] || { echo "HART_TABLES=$HART_TABLES: no such file"; exit 1; }
  HART_TABLES="$(cd "$(dirname "$HART_TABLES")" && pwd)/$(basename "$HART_TABLES")"
  export HART_TABLES
  echo "Table checks read $HART_TABLES (HART_TABLES), not the checkout's tables file"
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export JMRI_LAYOUT=hart
# The schematic plugin's cache, the folder the builds use (publish_draft.CACHE, private to this user), for every job
# here: the Layout Editor tests call the build directly and would otherwise solve the whole sheet about five times
# (about 7 minutes; seconds with the cache warm). An empty SCHEMATIC_CACHE (set by the caller) keeps it off. CI keeps
# the folder between runs (.github/workflows/check.yml).
# A folder that cannot be made leaves the cache off, as before.
if [[ -z "${SCHEMATIC_CACHE+set}" ]]; then
  if mkdir -p "$HOME/.cache/hart/schematic" 2>/dev/null && chmod 700 "$HOME/.cache/hart/schematic"; then
    export SCHEMATIC_CACHE="$HOME/.cache/hart/schematic"
  else
    echo "schematic cache off: cannot make $HOME/.cache/hart/schematic"
  fi
fi
# A worktree not made by make wt (a subagent's isolation worktree, an older one) may lack the submodules the checks
# import (CHECK_SUBMODULES in tools/agent/worktrees.py); check them out the way make wt does. Only in a worktree
# (.git is a file there): the main checkout is not changed, and CI checks them out itself (.github/workflows/check.yml).
if [[ -z "${CI:-}" && -f .git ]]; then
  python3 tools/agent/worktrees.py submodules "$ROOT" || echo "checks that need a missing submodule will skip or fail"
fi
fail=0
run() {
  echo "--- $1"
  shift
  local start=$SECONDS
  "$@" || fail=1
  (( SECONDS - start < 5 )) || echo "    ($((SECONDS - start))s)"
}
# The slow part (unit tests, public text, the portal build) runs at the same time once the read-only
# checks above it are done, at most one job per core. Every one works in its own temp folders. `later`
# starts a job with its output in a file; `collect` waits for each in the order started and prints its
# output under its heading. Job control (set -m) gives each job its own process group with the signals a
# terminal has (a plain background job ignores SIGINT), and Ctrl-C or TERM stops every group still running.
set -m
JOBS="$(mktemp -d)"
MAX_JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
(( MAX_JOBS >= 2 )) || MAX_JOBS=2
names=()
pids=()
stop_jobs() {
  local pid
  for pid in ${pids[@]+"${pids[@]}"}; do kill -TERM -- "-$pid" 2>/dev/null; done
}
trap 'rm -rf "$JOBS"' EXIT
trap 'stop_jobs; exit 130' INT
trap 'stop_jobs; exit 143' TERM
later() {
  local name="$1"
  shift
  while (( $(jobs -rp | wc -l) >= MAX_JOBS )); do sleep 0.2; done
  local n="${#names[@]}"
  (start=$SECONDS; "$@" >"$JOBS/$n.log" 2>&1; rc=$?; echo "$((SECONDS - start))" >"$JOBS/$n.time"; exit "$rc") &
  pids+=("$!")
  names+=("$name")
}
collect() {
  local i took
  for i in "${!names[@]}"; do
    if wait "${pids[$i]}"; then
      echo "--- ${names[$i]} ($(cat "$JOBS/$i.time")s)"
    else
      fail=1
      took="$(cat "$JOBS/$i.time" 2>/dev/null)" || took="killed before it finished, no "
      echo "--- ${names[$i]} FAILED (${took}s)"
    fi
    cat "$JOBS/$i.log"
  done
}
# Unit tests compare fixtures with the checkout's tables file, so HART_TABLES never reaches them.
unit() {
  local name="$1"
  shift
  later "$name" env -u HART_TABLES "$@"
}
run phase02 python3 jmri/scripts/check_hart_phase02.py
run tables-browser python3 www/scripts/build_tables_browser.py --check
run layout-index python3 www/scripts/build_layout_index.py --check
run layout-index-cats python3 www/scripts/build_cats_layout_index.py --check
run wiring-json python3 www/scripts/build_wiring_json.py --check
run track-lengths python3 jmri/layouts/hart/scripts/export_track_lengths.py --check
run speedmatch-routes python3 jmri/layouts/hart/scripts/speedmatch/build_routes.py --check
run panel-contracts python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
run baselines python3 jmri/layouts/hart/scripts/capture_public_name_baseline.py --check
run os-lamps-display-only python3 jmri/layouts/hart/scripts/occupancy_lamps_display_only.py --check
run digicon-disabled python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py --check
run status-counts python3 tools/ops/status_counts.py --check
# Prints SKIPPED and passes when the schematic-maps plugin submodule is not checked out (fails in CI, SCHEMATIC_REQUIRED=1).
run schematic-signals python3 tools/schematic/build_signals.py --check
run schematic-cats python3 tools/schematic/build_cats_panel.py --check
run schematic-hands python3 tools/schematic/build_hands.py --check
run schematic-approved python3 tools/schematic/check_approved.py
run schematic-device-map python3 tools/schematic/build_device_map.py --check
run schematic-main-upper-masts python3 tools/schematic/build_main_upper_masts.py --check
run schematic-staging-device-map python3 tools/schematic/staging_device_map.py --check
run schematic-staging-masts python3 tools/schematic/build_staging_masts.py --check
run schematic-staging-sync python3 tools/schematic/sync_staging_signals.py --check
run wiring-v86 python3 docs/wiring/scripts/add_main_upper_levels.py --check
run sml-invariants python3 tools/audit/check_sml_invariants.py
# The parked features (Entry/Exit, Dispatcher System, USS CTC): none of their elements or names in the tables
# file, all of them in jmri/layouts/hart/parked/tables_parked.xml (the live snapshot, with its source commit).
run parked env PYTHONPATH=tools/hartlib/src python3 -m hartlib.parked check
run mqtt-static python3 tools/audit/check_mqtt_no_static_lists.py
run wiring-crosswalk python3 tools/audit/check_wiring_crosswalk.py
run layout-facts python3 tools/audit/check_layout_facts.py
# The fact files against each other (hartlib.railroad: switches, name map, main and upper control points, device map,
# masts, the tables file); KNOWN in the module lists what is reported and left.
run railroad-facts env PYTHONPATH=tools/hartlib/src python3 -m hartlib.railroad check
run name-copies python3 tools/audit/check_name_copies.py
run ai-speak python3 tools/audit/check_ai_speak.py
run tracked-policy python3 tools/audit/check_tracked_policy.py
run agent-docs python3 tools/audit/check_agent_docs.py
run desks python3 cats/scripts/validate_cats_panel.py
# The longest jobs start first, so none of them waits behind the quick ones: unit-jmri, then the per-file guard and
# host jobs with the files in SLOW of both folders (each 10-20 s; the Layout Editor ones longer with an empty
# schematic cache) ahead of the rest.
SLOW=" test_worktrees.py test_panelpro_wrappers.py test_deploy_stage.py test_redeploy_commit.py test_build_layout_le.py \
test_le_cutover.py test_le_mast_parity.py "
slow_first() {
  local f
  for f in "$@"; do [[ "$SLOW" == *" ${f##*/} "* ]] && echo "$f"; done
  for f in "$@"; do [[ "$SLOW" == *" ${f##*/} "* ]] || echo "$f"; done
  return 0
}
unit unit-jmri python3 -m unittest discover -q -s jmri/layouts/hart/scripts/tests
# The host tests start real processes and wait out their timers, and the guard tests are many separate modules:
# both run one job per file, found as discover finds them, the files in SLOW of both folders first. A file in
# BY_CLASS runs one job per test class instead (test_worktrees: about 40 tests of git calls, 20 s in one job).
for d in tools/hosts/tests tools/audit/tests; do
  if [[ -n "$(find "$d" -mindepth 2 -name 'test*.py' -print -quit)" ]]; then
    echo "--- $d: tests in a subfolder; give them their own job in check.sh"
    fail=1
  fi
done
BY_CLASS=" test_worktrees.py "
for t in $(slow_first tools/hosts/tests/test*.py tools/audit/tests/test*.py); do
  d="$(dirname "$t")"
  f="$(basename "$t")"
  kind=unit-guards
  [[ "$d" == tools/hosts/tests ]] && kind=unit-hosts
  if [[ "$BY_CLASS" == *" $f "* ]]; then
    classes="$(python3 tools/audit/test_classes.py "$t")" || { echo "--- $kind ${f%.py}: cannot list its test classes"; fail=1; continue; }
    for c in $classes; do
      unit "$kind $c" python3 -m unittest discover -q -s "$d" -p "$f" -k "$c."
    done
  else
    unit "$kind ${f%.py}" python3 -m unittest discover -q -s "$d" -p "$f"
  fi
done
unit unit-jmri-scripts python3 -m unittest discover -q -s jmri/scripts/tests
unit unit-cats python3 -m unittest discover -q -s cats/scripts/tests
unit unit-mimic python3 -m unittest discover -q -s tools/mqtt-mimic/tests
unit unit-hartlib python3 -m unittest discover -q -s tools/hartlib/tests
unit unit-schematic python3 -m unittest discover -q -s tools/schematic/tests
unit unit-portal python3 -m unittest discover -q -s www/scripts/tests
# Car cards, intake and publications. Uses ops/hart-ops/.venv when it exists; a checkout
# without it (a worktree) skips, CI installs ops/hart-ops/requirements-test.txt.
HOPS_PY=python3
[[ -x ops/hart-ops/.venv/bin/python ]] && HOPS_PY=ops/hart-ops/.venv/bin/python
# The venv carries pypdf for the PDF part; plain python3 checks everything else.
later public-text "$HOPS_PY" tools/audit/check_public_text.py
if [[ -n "${CI:-}" ]] || "$HOPS_PY" -c "import numpy, scipy, docx, pytesseract" 2>/dev/null; then
  unit unit-hart-ops "$HOPS_PY" -m unittest discover -q -s ops/hart-ops/tests
else
  later "unit-hart-ops skipped (no ops/hart-ops/.venv)" true
fi
# The portal build needs the gitignored photo mirrors (media/), which CI does not have. It is skipped only when
# tools/audit/portal_inputs.py exits 3 (this checkout changes no site input); a crash there runs it, and
# PORTAL_CHECK=1 runs it anyway. The website deploy always runs it, with its count comparison.
portal_why=""
if [[ -z "${CI:-}" && "${PORTAL_CHECK:-}" != 1 ]]; then
  portal_why="$(python3 tools/audit/portal_inputs.py)"
  portal_rc=$?
fi
if [[ -n "${CI:-}" ]]; then
  later "portal skipped in CI" true
elif [[ "${PORTAL_CHECK:-}" != 1 && "$portal_rc" -eq 3 ]]; then
  later "portal skipped: $portal_why (PORTAL_CHECK=1 runs it)" true
else
  later portal python3 www/scripts/check_portal_build.py
fi
collect
if [[ "$fail" -eq 0 ]]; then echo "ALL PASSED"; else echo "FAILED"; fi
exit "$fail"
