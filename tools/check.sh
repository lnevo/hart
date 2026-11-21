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
# The schematic plugin's cache, the folder the builds use (publish_draft.CACHE: <main checkout>/.cache/hart/schematic, private to this user), for every job
# here: the Layout Editor job calls the build directly and would otherwise solve the whole sheet in its one process
# (about 3 minutes; seconds with the cache warm). An empty SCHEMATIC_CACHE (set by the caller) keeps it off. CI keeps
# the folder between runs (.github/workflows/check.yml).
# A folder that cannot be made leaves the cache off, as before.
if [[ -z "${SCHEMATIC_CACHE+set}" ]]; then
  source "$ROOT/tools/hosts/profile_tables_guard.sh"
  cache="$(hart_cache_dir "$ROOT" schematic)"
  if mkdir -p "$cache" 2>/dev/null && chmod 700 "$cache"; then
    export SCHEMATIC_CACHE="$cache"
  else
    echo "schematic cache off: cannot make $cache"
  fi
fi
# A worktree not made by make wt (a subagent's isolation worktree, an older one) may lack the submodules the checks
# import (CHECK_SUBMODULES in tools/agent/worktrees.py); check them out the way make wt does. Only in a worktree
# (.git is a file there): the main checkout is not changed, and CI checks them out itself (.github/workflows/check.yml).
if [[ -z "${CI:-}" && -f .git ]]; then
  python3 tools/agent/worktrees.py submodules "$ROOT" || echo "checks that need a missing submodule will skip or fail"
fi
fail=0
# Local stamps (tools/audit/check_stamps.py): a job whose declared inputs match its last pass is skipped, and prints
# "<job>: current, skipped". CI (CI is set), FULL=1 and an audit run never skip. CHECK_ONLY=<regex> runs only the
# jobs whose name matches (a quick look at one job). CHECK_AUDIT=<folder> logs the repo files each job's Python
# opens, for `check_stamps.py audit-report` and tools/audit/tests/test_check_stamps.py.
STAMPS=1
if [[ -n "${CI:-}" || "${FULL:-}" == 1 || -n "${CHECK_AUDIT:-}" ]]; then STAMPS=0; fi
if [[ -n "${CHECK_AUDIT:-}" ]]; then
  mkdir -p "$CHECK_AUDIT"
  CHECK_AUDIT="$(cd "$CHECK_AUDIT" && pwd)"
  rm -f "$CHECK_AUDIT"/*.log "$CHECK_AUDIT"/*.name
fi
# The jobs (the read-only checks as one "static" job, unit tests, public text, the portal build) run at the same time,
# at most one job per core. Every one works in its own temp folders. `later`
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
  if [[ -n "${CHECK_ONLY:-}" && ! "$name" =~ $CHECK_ONLY ]]; then return 0; fi
  while (( $(jobs -rp | wc -l) >= MAX_JOBS )); do sleep 0.2; done
  local n="${#names[@]}"
  (
    start=$SECONDS
    src=2
    if (( STAMPS )); then
      python3 tools/audit/check_stamps.py current "$name" --save "$JOBS/$n.stamp" >"$JOBS/$n.stamplog" 2>&1
      src=$?
      # anything but 0 (current) or 1 (not current) is run, don't record; so is a current verdict without a stamp file
      (( src == 0 || src == 1 )) || src=2
      if (( src == 0 )) && [[ ! -s "$JOBS/$n.stamp" ]]; then src=2; fi
    fi
    if (( src == 0 )); then
      echo "$name: current, skipped" >"$JOBS/$n.log"
      : >"$JOBS/$n.skip"
      rc=0
    else
      if [[ -n "${CHECK_AUDIT:-}" ]]; then
        echo "$name" >"$CHECK_AUDIT/$n.name"
        export CHECK_AUDIT_LOG="$CHECK_AUDIT/$n.log" CHECK_AUDIT_ROOT="$ROOT" PYTHONPATH="$ROOT/tools/audit/stamp_audit${PYTHONPATH:+:$PYTHONPATH}"
      fi
      "$@" >"$JOBS/$n.log" 2>&1
      rc=$?
      # a check that printed SKIPPED did not really run: no stamp (a unit job's output may quote the word)
      # and a unit job whose output shows skipped tests (their conditions are not in the stamp)
      if (( rc == 0 && src == 1 )) && [[ -s "$JOBS/$n.stamp" ]] && ! grep -q "skipped=" "$JOBS/$n.log" \
         && { [[ "$name" == unit-* ]] || ! grep -q SKIPPED "$JOBS/$n.log"; }; then
        python3 tools/audit/check_stamps.py record "$name" "$JOBS/$n.stamp" >>"$JOBS/$n.stamplog" 2>&1
      fi
      if [[ -s "$JOBS/$n.stamplog" ]]; then { echo "--- stamps ($name):"; cat "$JOBS/$n.stamplog"; } >>"$JOBS/$n.log"; fi
    fi
    echo "$((SECONDS - start))" >"$JOBS/$n.time"
    exit "$rc"
  ) &
  pids+=("$!")
  names+=("$name")
}
collect() {
  local i took skipped=0
  for i in "${!names[@]}"; do
    if wait "${pids[$i]}"; then
      if [[ -e "$JOBS/$i.skip" ]]; then
        skipped=$((skipped + 1))
      else
        echo "--- ${names[$i]} ($(cat "$JOBS/$i.time")s)"
      fi
    else
      fail=1
      took="$(cat "$JOBS/$i.time" 2>/dev/null)" || took="killed before it finished, no "
      echo "--- ${names[$i]} FAILED (${took}s)"
    fi
    cat "$JOBS/$i.log"
  done
  if (( skipped > 0 )); then echo "$skipped of ${#names[@]} jobs current, skipped (FULL=1 runs them all)"; fi
}
# Unit tests compare fixtures with the checkout's tables file, so HART_TABLES never reaches them.
unit() {
  local name="$1"
  shift
  later "$name" env -u HART_TABLES "$@"
}
# The read-only checks run as one job ("static"), one after another, beside the unit jobs.
run() {
  echo "--- $1"
  shift
  local start=$SECONDS
  "$@" || static_rc=1
  (( SECONDS - start < 5 )) || echo "    ($((SECONDS - start))s)"
}
static_checks() {
  local static_rc=0
run phase02 python3 jmri/scripts/check_hart_phase02.py
run tables-browser python3 www/scripts/build_tables_browser.py --check
run repo-guide python3 www/scripts/repo_guide_page.py --check
run pipeline-map-site python3 tools/ops/build_pipeline_map.py --public --out www/library/pipeline-map.html --back repository-guide.html --check
run jmri-additions python3 www/scripts/jmri_additions_page.py --check
run layout-index python3 www/scripts/build_layout_index.py --check
run layout-index-cats python3 www/scripts/build_cats_layout_index.py --check
run wiring-json python3 www/scripts/build_wiring_json.py --check
run track-lengths python3 jmri/layouts/hart/scripts/export_track_lengths.py --check
run speedmatch-routes python3 jmri/layouts/hart/scripts/speedmatch/build_routes.py --check
run panel-contracts python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
run baselines python3 jmri/layouts/hart/scripts/capture_public_name_baseline.py --check
run digicon-disabled python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py --check
run status-counts python3 tools/ops/status_counts.py --check
# Prints SKIPPED and passes when the schematic-maps plugin submodule is not checked out (fails in CI, SCHEMATIC_REQUIRED=1).
run schematic-signals python3 tools/schematic/build_signals.py --check
run schematic-cats python3 tools/schematic/build_cats_panel.py --check
run schematic-hands python3 tools/schematic/build_hands.py --check
run schematic-main-route python3 tools/schematic/build_main_route.py --check
run schematic-staging-sets python3 tools/schematic/build_staging_sets.py --check
run schematic-approved python3 tools/schematic/check_approved.py
run schematic-device-map python3 tools/schematic/build_device_map.py --check
run schematic-masts python3 tools/schematic/build_masts.py --check
# tables.xml is an output (ADR-029): it must be what build_tables.py writes from the template, devices.csv, the
# Layout Editor build and the discovered Signal Mast Logic; a Store is never copied over it (make tables-pull keeps
# it in media/pulled-stores in the main checkout and tools/schematic/split_store.py splits it into the template and devices.csv)
run tables python3 tools/schematic/build_tables.py --check
run schematic-device-master python3 tools/schematic/check_device_master.py --check
run schematic-plan-lengths python3 tools/schematic/plan_lengths.py --check
run schematic-signals-sync python3 tools/schematic/sync_signals.py --check
# The track plan article: its drawings against the owner's plan (SKIPPED where the plan is not), and the article
# against its drawings and the block lengths.
run levels-svg python3 tools/anyrail/levels_svg.py --check
run levels-page python3 tools/anyrail/levels_page.py --check
run wiring-v86 python3 tools/wiring/write_inventory.py --check
run sml-invariants python3 tools/audit/check_sml_invariants.py
# The parked features (Entry/Exit, Dispatcher System, USS CTC): none of their elements or names in the tables
# file, all of them in jmri/layouts/hart/parked/tables_parked.xml (the live snapshot, with its source commit).
run parked env PYTHONPATH=tools/hartlib/src python3 -m hartlib.parked check
run mqtt-static python3 tools/audit/check_mqtt_no_static_lists.py
run wiring-crosswalk python3 tools/audit/check_wiring_crosswalk.py
run layout-facts python3 tools/audit/check_layout_facts.py
# The fact files against each other (hartlib.railroad: devices.csv, switches.csv, masts.csv, the tables file);
# KNOWN in the module lists what is reported and left.
run railroad-facts env PYTHONPATH=tools/hartlib/src python3 -m hartlib.railroad check
# devices.csv and its column dictionary (python3 -m hartlib.devices)
run devices env PYTHONPATH=tools/hartlib/src python3 -m hartlib.devices check
run panel-status python3 tools/schematic/panel_items.py --check
run name-copies python3 tools/audit/check_name_copies.py
run ai-speak python3 tools/audit/check_ai_speak.py
run tracked-policy python3 tools/audit/check_tracked_policy.py
run agent-docs python3 tools/audit/check_agent_docs.py
run docs-index python3 tools/ops/build_docs_index.py --check
run desks python3 cats/scripts/validate_cats_panel.py
  return "$static_rc"
}
later static static_checks
# The longest jobs start first, so none of them waits behind the quick ones: the Layout Editor job, unit-jmri, then
# the per-file guard and host jobs, with the files in SLOW of each folder (each 10-20 s) ahead of the rest.
SLOW=" test_worktrees.py test_panelpro_wrappers.py test_deploy_stage.py test_deploy_gates.py test_redeploy_commit.py "
SLOW+="test_main_panel_names_copies.py test_polish_hart_layout_editor.py "
# The Layout Editor test files run as one job in one process: each builds the three-level candidate through
# test_build_layout_le.built(), cached per process, so three jobs solved the sheet three times side by side with an
# empty schematic cache (about 5 minutes each).
LE_TESTS="test_build_layout_le test_le_cutover test_le_mast_parity"
SLOW+=" test_panel_stamps.py test_build_tables.py test_build_panels.py "
slow_first() {
  local f
  for f in "$@"; do [[ "$SLOW" == *" ${f##*/} "* ]] && echo "$f"; done
  for f in "$@"; do [[ "$SLOW" == *" ${f##*/} "* ]] || echo "$f"; done
  return 0
}
# shellcheck disable=SC2086  # LE_TESTS is a list of module names
unit "unit-guards layout-editor ($LE_TESTS)" env PYTHONPATH=tools/audit/tests python3 -m unittest -q $LE_TESTS
# unit-jmri runs one job per file on a local run, the slow files first: about 25 s in one job, 16 s spread over six
# cores. CI keeps one job: its four cores are taken by the Layout Editor job and the guard files for minutes, so a
# split would only add some 50 interpreter starts there.
JMRI_TESTS=jmri/layouts/hart/scripts/tests
if [[ -n "${CI:-}" ]]; then
  unit unit-jmri python3 -m unittest discover -q -s jmri/layouts/hart/scripts/tests
else
  for t in $(slow_first "$JMRI_TESTS"/test*.py); do
    f="$(basename "$t")"
    unit "unit-jmri ${f%.py}" python3 -m unittest discover -q -s "$JMRI_TESTS" -p "$f"
  done
fi
# The host tests start real processes and wait out their timers, and the guard tests are many separate modules:
# both run one job per file, found as discover finds them, the files in SLOW first. A file in
# BY_CLASS runs one job per test class instead (test_worktrees: about 40 tests of git calls, 20 s in one job).
for d in "$JMRI_TESTS" tools/hosts/tests tools/audit/tests tools/schematic/tests; do
  if [[ -n "$(find "$d" -mindepth 2 -name 'test*.py' -print -quit)" ]]; then
    echo "--- $d: tests in a subfolder; give them their own job in check.sh"
    fail=1
  fi
done
BY_CLASS=" test_worktrees.py "
BY_CLASS+=" test_panel_stamps.py "      # in tools/schematic/tests
# A class in BY_METHOD runs one job per test (test_panel_stamps.ShellTest: eight runs of build_panels.sh in scratch repos).
BY_METHOD=" test_panel_stamps.ShellTest "
for t in $(slow_first tools/hosts/tests/test*.py tools/audit/tests/test*.py tools/schematic/tests/test*.py); do
  d="$(dirname "$t")"
  f="$(basename "$t")"
  [[ "$d" == tools/audit/tests && " $LE_TESTS " == *" ${f%.py} "* ]] && continue    # in the Layout Editor job above
  kind=unit-guards
  [[ "$d" == tools/hosts/tests ]] && kind=unit-hosts
  [[ "$d" == tools/schematic/tests ]] && kind=unit-schematic
  if [[ "$BY_CLASS" == *" $f "* ]]; then
    classes="$(python3 tools/audit/test_classes.py "$t")" || { echo "--- $kind ${f%.py}: cannot list its test classes"; fail=1; continue; }
    for c in $classes; do
      if [[ "$BY_METHOD" == *" $c "* ]]; then
        for m in $(python3 tools/audit/test_classes.py "$t" --methods "$c"); do
          unit "$kind $m" python3 -m unittest discover -q -s "$d" -p "$f" -k "$m"
        done
      else
        unit "$kind $c" python3 -m unittest discover -q -s "$d" -p "$f" -k "$c."
      fi
    done
  else
    unit "$kind ${f%.py}" python3 -m unittest discover -q -s "$d" -p "$f"
  fi
done
unit unit-jmri-scripts python3 -m unittest discover -q -s jmri/scripts/tests
unit unit-cats python3 -m unittest discover -q -s cats/scripts/tests
unit unit-mimic python3 -m unittest discover -q -s tools/mqtt-mimic/tests
unit unit-hartlib python3 -m unittest discover -q -s tools/hartlib/tests
unit unit-anyrail python3 -m unittest discover -q -s tools/anyrail/tests
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
