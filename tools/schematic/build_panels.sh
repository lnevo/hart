#!/usr/bin/env bash
# Rebuild every output drawn from the schematic, in the order they depend on each other, or check them all with
# --check (exit 1 if any is stale). `make panels` and `make panels CHECK=1` run this.
#
#   staging device map               device_map_staging.csv and its files are kept by hand: checked against tables.xml
#                                    and the schematic (staging_device_map.py --check), in both modes
#   staging masts                    staging_masts.csv, staging_signals.csv and the device map's mast and head rows are
#                                    written by build_staging_masts.py, and tables.xml follows them through
#                                    sync_staging_signals.py; both are run by hand (the second edits tables.xml), so
#                                    this only checks them (--check), in both modes, before anything reads the files
#   hands.csv, <name>.signals.json   from the plan graph and the staging masts; the schematic reads the signals
#   device map                       from the solved sheet; writes main_upper.plan_overrides.json, a layer file the
#                                    schematic reads, so it runs before publishing
#   main_upper_masts.csv             from the device map; the Layout Editor builds place these masts
#   schematic draft and stations     publish_draft.py
#   CATS desks                       build_cats_panel.py
#   Layout Editor cut-over           build_layout_le.py --as-live: the three-level candidate and the staging
#                                    candidate it holds (the viewing trials are retired, owner 2026-11-17: the
#                                    candidates show every level)
#   approved-*                       check_approved.py, straight after what it guards: the desks after they are written,
#                                    the cut-over candidate after it is written (it is what replaces the live panel; the
#                                    build never writes tables.xml), and the live panel. A write that drifts from the
#                                    owner-approved fingerprints stops there, before anything else reads it.
#
# Each step reads the plugin's cache (~/.cache/hart/schematic): the solve is shared, and Layout Editor panels whose
# inputs and plugin code are unchanged are read back, so a run after a small change redoes only what that change
# reaches. A write stops at the first failure, since what follows reads its output; --check runs every step and
# names each stale one.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

check=()
case "${1:-}" in
  "") ;;
  --check) check=(--check) ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

failed=()
step() {
  local name=$1 start=$SECONDS
  shift
  echo "== $name"
  if "$@" ${check[@]+"${check[@]}"}; then
    echo "   $name: ok, $((SECONDS - start)) s"
  else
    echo "   $name: FAILED, $((SECONDS - start)) s"
    failed+=("$name")
    [ ${#check[@]} -eq 0 ] && { echo "stopped: later steps read what $name writes"; exit 1; }
  fi
}

step hands python3 tools/schematic/build_hands.py
step staging-masts python3 tools/schematic/build_staging_masts.py --check
step staging-sync python3 tools/schematic/sync_staging_signals.py --check
step staging-map python3 tools/schematic/staging_device_map.py --check
step signals python3 tools/schematic/build_signals.py
step device-map python3 tools/schematic/build_device_map.py
step main-upper-masts python3 tools/schematic/build_main_upper_masts.py
step schematic python3 tools/schematic/publish_draft.py
step cats python3 tools/schematic/build_cats_panel.py
step approved-desks python3 tools/schematic/check_approved.py cats-ctc cats-abs
step le-cutover python3 tools/schematic/build_layout_le.py --as-live
step approved-candidate python3 tools/schematic/check_approved.py le-candidate
step approved-live python3 tools/schematic/check_approved.py le-panel

if [ ${#failed[@]} -gt 0 ]; then
  echo "stale or failed: ${failed[*]}"
  exit 1
fi
echo "all current"
