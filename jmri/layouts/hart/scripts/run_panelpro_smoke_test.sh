#!/usr/bin/env bash
# Load the deployment bundle in PanelPro, verify core beans, and exit.
# The run lifecycle (profile backup and restore, Start Up items that run code off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
SCRIPT="$ROOT/jmri/layouts/hart/scripts/panelpro_smoke_test.py"
MARKER="${HART_PANELPRO_SMOKE_MARKER:-/tmp/hart_panelpro_smoke.done}"
LOG="${HART_PANELPRO_SMOKE_LOG:-/tmp/hart_panelpro_smoke.log}"

pp_refuse_running "SKIPPED: quit CATS and PanelPro, then run the smoke test again" 0

pp_begin "$SCRIPT"
rm -f "$MARKER"
export HART_PANELPRO_SMOKE_MARKER="$MARKER"
# The parked features (hartlib.parked.PARKED): the smoke test expects them absent.
HART_PARKED="$(PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.parked features | tr '\n' ' ')"
export HART_PARKED
# The masts, sections, transits and traininfo the loaded tables must hold: the counts file audit_panel_contracts.py
# reads (audit_panel_graph.PANEL_COUNTS).
export HART_PANEL_COUNTS="$ROOT/jmri/layouts/hart/scripts/panel_counts.json"
# The main and upper blocks on a field sensor (a detector swapped in by its device row, ADR-028), from the file
# PanelPro loads (PP_TABLES_FILE, the one pp_begin names in the profile; hartlib.level_devices.field_detected): the
# smoke test holds each to that sensor, every other main and upper block to its virtual one.
HART_FIELD_DETECTED="$(PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.level_devices field-detected \
  "$PP_TABLES_FILE" | tr '\n' ';')"
export HART_FIELD_DETECTED

pp_launch "$LOG"
rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-120}" 2 || rc=$?
if (( rc != 0 )); then
  echo "PanelPro smoke test did not produce a marker; log: $LOG" >&2
  exit 1
fi
pp_wait_exit "${HART_PANELPRO_EXIT_WAIT:-120}" || { echo "PanelPro did not quit after the smoke test; stopping it" >&2; pp_stop_jmri; }

status="$(awk 'NR==1 {print; exit}' "$MARKER")"
detail="$(awk 'NR>1 {print}' "$MARKER")"
echo "PanelPro smoke: $status"
echo "$detail"
[[ "$status" == "ok" ]]
