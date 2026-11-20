#!/usr/bin/env bash
# Rebuild every output drawn from the schematic, in the order they depend on each other, or check them all with
# --check (exit 1 if any is stale). `make panels` and `make panels CHECK=1` run this.
#
# The steps, in the order they run (the name is the one each step prints):
#
#   hands                 hands.csv, from the plan graph
#   main-route            main_route in main_upper.plan_overrides.json, from main_lines_main_upper.csv and the plan graph
#   plan-lengths          block_lengths.csv's plan_in (the AnyRail plan 5.3c lengths) is written by plan_lengths.py,
#                         run by hand (it reads the private plan file): this only checks it (--check), in both modes
#   staging-masts         staging_masts.csv, staging_signals.csv and the device map's mast and head rows are written by
#                         build_staging_masts.py, run by hand: this only checks them (--check), in both modes
#   staging-sync          tables.xml follows staging_masts.csv through sync_staging_signals.py, run by hand with JMRI
#                         closed (it edits tables.xml): this only checks it (--check), in both modes
#   staging-map           device_map_staging.csv (its mast and head rows aside) and control_points_staging.csv are
#                         kept by hand: the four staging files are checked against tables.xml and the schematic
#                         (staging_device_map.py --check), in both modes
#   signals               <name>.signals.json, from the plan graph and the staging masts; the schematic reads it
#   device-map            from the solved sheet; writes main_upper.plan_overrides.json, a layer file the schematic
#                         reads, so it runs before publishing
#   main-upper-masts      main_upper_masts.csv, from the device map; the Layout Editor builds place these masts
#   schematic             the schematic draft and stations (publish_draft.py)
#   cats                  the CATS desks (build_cats_panel.py)
#   approved-desks        check_approved.py on the desks, straight after they are written
#   le-cutover            build_layout_le.py --as-live: the three-level candidate and the staging candidate it holds
#                         (the viewing trials are retired, owner 2026-11-17: the candidates show every level)
#   approved-candidate    check_approved.py on the cut-over candidate, straight after it is written (it is what
#                         replaces the live panel; the build never writes tables.xml)
#   approved-live         check_approved.py on the live panel
#
# The approved-* steps stop a write that drifts from the owner-approved fingerprints, before anything else reads it.
#
# Each step reads the plugin's cache (~/.cache/hart/schematic): the solve is shared, and Layout Editor panels whose
# inputs and plugin code are unchanged are read back, so a run after a small change redoes only what that change
# reaches. A write stops at the first failure, since what follows reads that step's output (step) or the files it
# checks (guard); --check runs every step and names each stale one.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

check=()
case "${1:-}" in
  "") ;;
  --check) check=(--check) ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

failed=()
run_step() {
  local stop=$1 name=$2 start=$SECONDS
  shift 2
  echo "== $name"
  if "$@" ${check[@]+"${check[@]}"}; then
    echo "   $name: ok, $((SECONDS - start)) s"
  else
    echo "   $name: FAILED, $((SECONDS - start)) s"
    failed+=("$name")
    [ ${#check[@]} -eq 0 ] && { echo "stopped: $stop"; exit 1; }
  fi
}
# A step that writes its outputs (or checks them, with --check).
step() { run_step "later steps read what $1 writes" "$@"; }
# A step that only checks, in both modes: it writes nothing, and its message names what to run by hand.
guard() { run_step "$1 only checks and it failed; later steps read the files it checks" "$@"; }

step hands python3 tools/schematic/build_hands.py
step main-route python3 tools/schematic/build_main_route.py
guard plan-lengths python3 tools/schematic/plan_lengths.py --check
guard staging-masts python3 tools/schematic/build_staging_masts.py --check
guard staging-sync python3 tools/schematic/sync_staging_signals.py --check
guard staging-map python3 tools/schematic/staging_device_map.py --check
step signals python3 tools/schematic/build_signals.py
step device-map python3 tools/schematic/build_device_map.py
step main-upper-masts python3 tools/schematic/build_main_upper_masts.py
step schematic python3 tools/schematic/publish_draft.py
step cats python3 tools/schematic/build_cats_panel.py
guard approved-desks python3 tools/schematic/check_approved.py cats-ctc cats-abs
step le-cutover python3 tools/schematic/build_layout_le.py --as-live
guard approved-candidate python3 tools/schematic/check_approved.py le-candidate
guard approved-live python3 tools/schematic/check_approved.py le-panel

if [ ${#failed[@]} -gt 0 ]; then
  echo "stale or failed: ${failed[*]}"
  exit 1
fi
echo "all current"
