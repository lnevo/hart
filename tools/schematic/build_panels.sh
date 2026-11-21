#!/usr/bin/env bash
# Rebuild every output drawn from the schematic, in the order they depend on each other, or check them all with
# --check (exit 1 if any is stale). `make panels` and `make panels CHECK=1` run this.
#
# The steps, in the order they run (the name is the one each step prints):
#
#   hands                 hands.csv, from the plan graph
#   staging-sets          staging's control points, stations and detail sheets in the staging sections of
#                         plan_overrides.json and preferences.json, from control_points_staging.csv, stations.csv and
#                         sheets.csv (the layer files hold a section per sheet: hartlib.layer_files)
#   main-route            main_route in plan_overrides.json's main_upper section, from main_lines.csv (main_upper
#                         rows) and the plan graph; staging's main flags and milepost_route, from its staging rows
#   plan-lengths          block_lengths.csv's plan_in (the AnyRail plan 5.3c lengths) is written by plan_lengths.py,
#                         run by hand (it reads the private plan file): this only checks it (--check), in both modes
#   staging-masts         staging_masts.csv, staging_signals.csv and the devices.csv rows of the staging masts and
#                         heads are written by build_staging_masts.py,
#                         run by hand: this only checks them (--check), in both modes
#   signals               signals.json (a section per sheet), from the plan graph and the masts; the schematic reads it
#   device-map            from the solved sheet; writes plan_overrides.json's main_upper section, which the schematic
#                         reads, so it runs before publishing
#   main-upper-masts      main_upper_masts.csv, from the device map; the Layout Editor builds place these masts
#   schematic             the schematic draft and stations (publish_draft.py)
#   le-cutover            build_layout_le.py --as-live: the three-level candidate and the staging candidate it holds
#                         (the viewing trials are retired, owner 2026-11-17: the candidates show every level)
#   approved-candidate    check_approved.py on the cut-over candidate, straight after it is written
#   tables                tables.xml (build_tables.py): the template, the staging beans of devices.csv, the Layout
#                         Editor build, the discovered Signal Mast Logic (ADR-029: tables.xml is an output)
#   staging-sync          the staging heads and masts in tables.xml follow staging_masts.csv (sync_staging_signals.py
#                         --check), in both modes; after tables, which generates them from devices.csv
#   device-master         devices.csv is checked against tables.xml and the schematic (check_device_master.py
#                         --check), in both modes; after tables, which it checks
#   cats                  the CATS desks (build_cats_panel.py); after tables, whose turnouts, sensors, layout blocks
#                         and masts they read, so one make panels leaves the desks current with the tables
#   approved-desks        check_approved.py on the desks, straight after they are written
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
step staging-sets python3 tools/schematic/build_staging_sets.py
step main-route python3 tools/schematic/build_main_route.py
guard plan-lengths python3 tools/schematic/plan_lengths.py --check
guard staging-masts python3 tools/schematic/build_staging_masts.py --check
step signals python3 tools/schematic/build_signals.py
step device-map python3 tools/schematic/build_device_map.py
step main-upper-masts python3 tools/schematic/build_main_upper_masts.py
step schematic python3 tools/schematic/publish_draft.py
step le-cutover python3 tools/schematic/build_layout_le.py --as-live
guard approved-candidate python3 tools/schematic/check_approved.py le-candidate
step tables python3 tools/schematic/build_tables.py
guard staging-sync python3 tools/schematic/sync_staging_signals.py --check
guard device-master python3 tools/schematic/check_device_master.py --check
step cats python3 tools/schematic/build_cats_panel.py
guard approved-desks python3 tools/schematic/check_approved.py cats-ctc cats-abs
guard approved-live python3 tools/schematic/check_approved.py le-panel

if [ ${#failed[@]} -gt 0 ]; then
  echo "stale or failed: ${failed[*]}"
  exit 1
fi
echo "all current"
