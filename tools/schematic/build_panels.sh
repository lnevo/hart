#!/usr/bin/env bash
# Rebuild every output drawn from the schematic, in the order they depend on each other, or check them all with
# --check (exit 1 if any is stale). `make panels` and `make panels CHECK=1` run this.
#
#   hands.csv, <name>.signals.json   from the plan graph and the frozen mast facts; the schematic reads the signals
#   device map                       from the solved sheet; writes main_upper.plan_overrides.json, a layer file the
#                                    schematic reads, so it runs before publishing
#   schematic draft and stations     publish_draft.py
#   CATS desks                       build_cats_panel.py
#   Layout Editor trials, cut-over   build_layout_le.py (all levels, then staging alone), then --as-live
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
step signals python3 tools/schematic/build_signals.py
step device-map python3 tools/schematic/build_device_map.py
step schematic python3 tools/schematic/publish_draft.py
step cats python3 tools/schematic/build_cats_panel.py
step le-trial python3 tools/schematic/build_layout_le.py
step le-trial-staging python3 tools/schematic/build_layout_le.py --levels staging
step le-cutover python3 tools/schematic/build_layout_le.py --as-live

if [ ${#failed[@]} -gt 0 ]; then
  echo "stale or failed: ${failed[*]}"
  exit 1
fi
echo "all current"
