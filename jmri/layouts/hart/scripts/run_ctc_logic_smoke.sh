#!/usr/bin/env bash
# Load the deployment bundle, start CTC Logic, verify columns/masts, exit.
# The run lifecycle (profile backup and restore, Start Up items that run code off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
SCRIPT="$ROOT/jmri/layouts/hart/scripts/ctc_logic_smoke.py"
MARKER="${HART_CTC_LOGIC_SMOKE_MARKER:-/tmp/hart_ctc_logic_smoke.done}"
LOG="${HART_CTC_LOGIC_SMOKE_LOG:-/tmp/hart_ctc_logic_smoke.log}"

pp_refuse_running "Quit CATS/PanelPro before the CTC Logic smoke test"

pp_begin "$SCRIPT"
rm -f "$MARKER"
export HART_CTC_LOGIC_SMOKE_MARKER="$MARKER"

pp_launch "$LOG"
rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-150}" 2 || rc=$?
if (( rc != 0 )); then
  echo "CTC Logic smoke did not produce a marker; log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi
pp_wait_exit "${HART_PANELPRO_EXIT_WAIT:-120}" || { echo "PanelPro did not quit after the CTC Logic smoke; stopping it" >&2; pp_stop_jmri; }

status="$(awk 'NR==1 {print; exit}' "$MARKER")"
detail="$(awk 'NR>1 {print}' "$MARKER")"
echo "CTC Logic smoke: $status"
echo "$detail"
[[ "$status" == "ok" ]]
