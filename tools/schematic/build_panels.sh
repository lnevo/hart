#!/usr/bin/env bash
# Rebuild every output drawn from the schematic, in the order they depend on each other, or check them all with
# --check (exit 1 if any is stale). `make panels` and `make panels CHECK=1` run this.
#
# usage: build_panels.sh [--check] [--full]
#
# The steps, in the order they run (the name is the one each step prints):
#
#   hands                 the plan rows' hands in switches.csv, from the plan graph
#   staging-sets          staging's control points, stations and detail sheets in the staging sections of
#                         plan_overrides.json and preferences.json, from stations.csv (the desk areas by its
#                         desk_code column) and sheets.csv (the layer files hold a section per sheet: hartlib.layer_files)
#   main-route            main_route in plan_overrides.json's main_upper section, from main_lines.csv (main_upper
#                         rows) and the plan graph; staging's main flags and milepost_route, from its staging rows
#   plan-lengths          block_lengths.csv's plan_in (the AnyRail plan 5.3c lengths) is written by plan_lengths.py,
#                         run by hand (it reads the private plan file): this only checks it (--check), in both modes
#   device-map            from the solved sheet; writes plan_overrides.json's main_upper section, which the schematic
#                         reads, so it runs before publishing
#   masts                 masts.csv, every level's masts (build_masts.py): staging's by the mast rule over its device
#                         map, with their device-master rows, and main and upper's from the device map's rows; after
#                         device-map, whose rows it reads
#   signals               signals.json (a section per sheet), from the plan graph and masts.csv; the schematic reads it.
#                         After masts, so one run draws the masts it writes. Nothing before it reads signals.json:
#                         device-map and masts give the same outputs with every signal dropped from it (the solve's
#                         signals layer places mast icons only), so there is no cycle
#   head-plan             signal_head_plan.csv (build_hart_signal_heads.py --wiring-only), from wiring.csv's wired heads;
#                         the CATS desks read its templates, so it runs before cats
#   schematic             the schematic draft and stations (publish_draft.py)
#   sml-current           the discovered Signal Mast Logic was discovered from the beans the sources give now:
#                         data/schematic/discovered_sml.stamp holds the sha256 of the discovery base it came from
#                         (run_sml_discover.sh writes it); a mismatch says to rerun discovery on the Mac. Always runs
#   tables                tables.xml (build_tables.py): the template, the staging beans of the device master, the Layout
#                         Editor build (build_layout_le.build, in memory), the discovered Signal Mast Logic (ADR-029:
#                         tables.xml is an output)
#   signals-sync          every level's heads and masts in tables.xml follow masts.csv (sync_signals.py
#                         --check), in both modes; after tables, which generates them from the device master
#   device-master         the device master is checked against tables.xml and the schematic (check_device_master.py
#                         --check), in both modes; after tables, which it checks
#   cats                  the CATS desks (build_cats_panel.py); after tables, whose turnouts, sensors, layout blocks
#                         and masts they read, so one make panels leaves the desks current with the tables
#   approved-desks        check_approved.py on the desks, straight after they are written
#   approved-live         check_approved.py on the live panel
#
# The approved-* steps stop a write that drifts from the owner-approved fingerprints, before anything else reads it.
#
# Each step reads the plugin's cache (<main checkout>/.cache/hart/schematic): the solve is shared, and Layout Editor panels whose
# inputs and plugin code are unchanged are read back, so a run after a small change redoes only what that change
# reaches. A write stops at the first failure, since what follows reads that step's output (step) or the files it
# checks (guard); --check runs every step and names each stale one.
#
# Each step also has a traced stamp (tools/schematic/panel_stamps.py, tools/audit/traced.py): a step runs under a hook
# that logs the repo files its Python processes read, probe and list; while all of those, its outputs, its code and the
# plugin's commit are what its last successful run left, it prints "<name>: current, skipped" and does not run, so an
# edit re-runs only the steps that read the file. A step that ran a program the hook cannot see records nothing and
# runs every time. The stamps are kept per checkout in .cache/panel-stamps/; --full (make panels FULL=1) ignores them
# and records. Guards always run.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1
# A step that cannot load the schematic-maps plugin fails rather than printing SKIPPED and passing, as in CI (owner,
# 2026-11-23): a worktree without the submodule must not look current. SCHEMATIC_REQUIRED=0 lets those steps skip.
export SCHEMATIC_REQUIRED="${SCHEMATIC_REQUIRED:-1}"

check=()
full=0
for arg in "$@"; do
  case "$arg" in
    --check) check=(--check) ;;
    --full) full=1 ;;
    *) echo "usage: $0 [--check] [--full]" >&2; exit 2 ;;
  esac
done
STAMPS=(python3 tools/schematic/panel_stamps.py)
# No stamps while HART_TABLES is set or the plugin is off its pin: nothing is skipped and nothing recorded (said once).
why=$("${STAMPS[@]}" unstampable) && unstamped=0 || unstamped=1
if [ "$unstamped" -eq 1 ]; then
  [ "$full" -eq 0 ] && echo "stamps off for this run: $why"
  full=1
  nostamp=1
else
  nostamp=0
fi

failed=()
# traced LOG CMD...: run CMD with the trace hook logging into LOG (tools/audit/traced.py), or plainly when LOG is empty.
traced() {
  local log=$1
  shift
  if [ -z "$log" ]; then "$@"; return; fi
  env -u HART_TRACE_SPAWN HART_TRACE_LOG="$log" HART_TRACE_ROOT="$PWD" \
    PYTHONPATH="$PWD/tools/audit/trace_hook${PYTHONPATH:+:$PYTHONPATH}" "$@"
}
# run_step STOP KIND NAME CMD...: KIND is "stamped" for a step (skipped while its stamp is the last successful run's,
# tools/schematic/panel_stamps.py; --full ignores the stamps) and "guard" for a check that always runs.
run_step() {
  local stop=$1 kind=$2 name=$3 start=$SECONDS
  shift 3
  echo "== $name"
  if [ "$kind" = stamped ] && [ "$full" -eq 0 ] && "${STAMPS[@]}" current "$name" "$@" 2>/dev/null; then
    echo "   $name: current, skipped"
    return
  fi
  local out; out=$(mktemp)
  local trace=""
  if [ "$kind" = stamped ] && [ "$nostamp" -eq 0 ]; then
    trace=$(mktemp)
    printf '0\tb\n' >"$trace"      # the runner starts one Python process: its start must be in the trace
    "${STAMPS[@]}" snapshot "$trace.before"     # git and plugin state now: a change while the step runs records nothing
  fi
  if traced "$trace" "$@" ${check[@]+"${check[@]}"} | tee "$out"; then
    echo "   $name: ok, $((SECONDS - start)) s"
    # a step that printed SKIPPED did not really run (plugin off its pin): it must not stamp
    if [ -n "$trace" ]; then
      if grep -q '^SKIPPED' "$out"; then
        echo "   $name: printed SKIPPED, no stamp"
        "${STAMPS[@]}" forget "$name"
      else
        "${STAMPS[@]}" record "$name" --trace "$trace" --snapshot "$trace.before" "$@"
      fi
    fi
    rm -f "$out" ${trace:+"$trace" "$trace.before"}
  else
    rm -f "$out" ${trace:+"$trace" "$trace.before"}
    echo "   $name: FAILED, $((SECONDS - start)) s"
    [ "$kind" = stamped ] && "${STAMPS[@]}" forget "$name"
    failed+=("$name")
    [ ${#check[@]} -eq 0 ] && { echo "stopped: $stop"; exit 1; }
  fi
}
# A step that writes its outputs (or checks them, with --check).
step() { run_step "later steps read what $1 writes" stamped "$@"; }
# A step that only checks, in both modes: it writes nothing, and its message names what to run by hand.
guard() { run_step "$1 only checks and it failed; later steps read the files it checks" guard "$@"; }

step hands python3 tools/schematic/build_hands.py
step staging-sets python3 tools/schematic/build_staging_sets.py
step main-route python3 tools/schematic/build_main_route.py
guard plan-lengths python3 tools/schematic/plan_lengths.py --check
step device-map python3 tools/schematic/build_device_map.py
step masts python3 tools/schematic/build_masts.py
step signals python3 tools/schematic/build_signals.py
step head-plan python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py --wiring-only
step schematic python3 tools/schematic/publish_draft.py
guard sml-current python3 tools/schematic/check_sml_current.py
step tables python3 tools/schematic/build_tables.py
guard signals-sync python3 tools/schematic/sync_signals.py --check
guard device-master python3 tools/schematic/check_device_master.py --check
step cats python3 tools/schematic/build_cats_panel.py
guard approved-desks python3 tools/schematic/check_approved.py cats-ctc cats-abs
guard approved-live python3 tools/schematic/check_approved.py le-panel

if [ ${#failed[@]} -gt 0 ]; then
  echo "stale or failed: ${failed[*]}"
  exit 1
fi
echo "all current"
