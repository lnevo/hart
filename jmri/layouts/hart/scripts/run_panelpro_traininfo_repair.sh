#!/usr/bin/env bash
# Load HART in PanelPro, repair stale generated TrainInfo bindings, then exit.
# The run lifecycle (profile backup and restore, publishing Start Up scripts off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
# The profile's own user files folder unless set (a rehearsal profile has its own).
PROFILE_TRAININFO="${HART_PROFILE_TRAININFO:-$PP_USER_FILES/dispatcher/traininfo}"
REPO_TRAININFO="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py"
MARKER="${HART_TRAININFO_MARKER:-/tmp/hart_traininfo_repair.done}"
LOG="${HART_TRAININFO_LOG:-/tmp/hart_traininfo_repair.log}"

pp_refuse_running "Quit local CATS/PanelPro before repairing TrainInfo"

mkdir -p "$PROFILE_TRAININFO"
cp "$REPO_TRAININFO"/*.xml "$PROFILE_TRAININFO/"

pp_begin
python3 "$PP_PATCH" insert --profile "$PROFILE_XML" --script "$SCRIPT" \
  --after signal_coordinator.py
rm -f "$MARKER"
export HART_TRAININFO_REPAIR=1
export HART_TRAININFO_MARKER="$MARKER"
export HART_TRAININFO_EXIT=1
# The repair works on the folder copied above, which is copied back into the repo below.
export HART_TRAININFO_DIR="$PROFILE_TRAININFO"

pp_launch "$LOG"
rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-120}" 2 || rc=$?
if (( rc != 0 )); then
  echo "TrainInfo repair did not produce a marker; log: $LOG" >&2
  exit 1
fi
pp_wait_exit "${HART_PANELPRO_EXIT_WAIT:-120}" || { echo "PanelPro did not quit after the repair; stopping it" >&2; pp_stop_jmri; }

status="$(awk 'NR==1 {print; exit}' "$MARKER")"
detail="$(awk 'NR>1 {print}' "$MARKER")"
echo "TrainInfo repair: $status"
echo "$detail"
if [[ "$status" != "ok" ]]; then
  exit 1
fi

cp "$PROFILE_TRAININFO"/*.xml "$REPO_TRAININFO/"
python3 "$ROOT/jmri/layouts/hart/scripts/audit_panel_contracts.py" --strict
