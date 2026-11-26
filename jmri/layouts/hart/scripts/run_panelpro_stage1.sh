#!/usr/bin/env bash
# Load HART tables in PanelPro, run stock Stage 1 (auto-Yes shared-sensor), store.
# Parked with the Dispatcher System. tables.xml is generated since R9c (ADR-029), so the Stage 1 Store and
# its repairs go to stage1-<date>.xml in the pulled folder (hart_pulled_dir: the main checkout's gitignored media/, shared by every worktree), never over
# tables.xml; split_store.py (R9d) takes such a Store back into the sources. On unpark, decide how Stage 1's output
# becomes source data before relying on this wrapper.
# The run lifecycle (profile backup and restore, Start Up items that run code off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
SCRIPT="$ROOT/jmri/layouts/hart/scripts/run_dispatcher_stage1.py"
MARKER="${HART_STAGE1_MARKER:-/tmp/hart_stage1.done}"
LOG="${HART_STAGE1_LOG:-/tmp/hart_stage1.log}"
REPO_TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
PULLED="$(hart_pulled_dir)" || exit 1
REPO_OUTPUT="$PULLED/stage1-$(date +%Y%m%d-%H%M%S).xml"   # the Store, in the pulled folder
REPO_TRAININFO="$ROOT/jmri/layouts/hart/dispatcher/traininfo"

pp_refuse_running "Quit local CATS/PanelPro before Stage 1"

pp_begin "$SCRIPT"
# Keep the tables as they were before Stage 1: reconcile_dispatcher_stations.py and the polish pass
# take it as --reference (the generated panel gets its icon spots back from it).
BEFORE_TABLES="$(mktemp)"
PP_TMP_FILES+=("$BEFORE_TABLES")
cp "$REPO_TABLES" "$BEFORE_TABLES"
rm -f "$MARKER"

export HART_STAGE1_MARKER="$MARKER"
export HART_STAGE1_TABLES="$REPO_TABLES"
export HART_STAGE1_TRAININFO="$REPO_TRAININFO"
export HART_STAGE1_STORE="$REPO_OUTPUT"

pp_launch "$LOG"
# Stage 1 on HART can take a long time (graph + hundreds of transits).
rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-2700}" 5 || rc=$?
if (( rc != 0 )); then
  echo "Stage 1 did not produce a marker; log: $LOG" >&2
  exit 1
fi

# JMRI writes the marker just before it exits. The repairs below save tables.xml,
# so wait for PanelPro to be gone and unable to Store over them.
if ! pp_wait_exit "${HART_STAGE1_EXIT_WAIT:-180}"; then
  echo "PanelPro is still running ${HART_STAGE1_EXIT_WAIT:-180}s after the Stage 1 marker; stopping it and not running the repairs. Run the repairs listed in jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md by hand. log: $LOG" >&2
  exit 1
fi
if pp_jmri_running; then
  echo "Another CATS/PanelPro is running; not running the repairs. Quit it, then run the repairs listed in jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md by hand. log: $LOG" >&2
  exit 1
fi

status="$(awk 'NR==1 {print; exit}' "$MARKER")"
detail="$(awk 'NR>1 {print}' "$MARKER")"
echo "Stage 1: $status"
echo "$detail"
if [[ "$status" != "ok" ]]; then
  exit 1
fi

# The manual steps after every Stage 1 (jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md).
# Each runs even if an earlier one failed; the wrapper fails at the end.
SCRIPTS="$ROOT/jmri/layouts/hart/scripts"
repair_failed=0
repair() {
  "$@" || { echo "REPAIR FAILED: $*" >&2; repair_failed=1; }
}
# Safety first: Digicon SML stays stored disabled until the coordinator enables it.
repair python3 "$SCRIPTS/disable_digicon_sml_in_tables.py" --panel "$REPO_OUTPUT"
# Stage 1 writes Entire Train detection; HART cars detect head and tail only.
repair python3 "$SCRIPTS/fix_traininfo_detection.py" "$REPO_TRAININFO"
# --reference: Stage 1's deleted and re-added cluster icons, lamps and train-name labels go back
# where they stood on the generated panel before it.
repair python3 "$SCRIPTS/reconcile_dispatcher_stations.py" --panel "$REPO_OUTPUT" --no-sync \
  --reference "$BEFORE_TABLES"
# Stage 1 drops generated bean comments (SML section notes, Dispatcher sensors).
repair python3 "$SCRIPTS/check_bean_comments.py"
# Stage 1 Store writes BlockContentsIcons at level 0 (behind the track), moves
# train-name labels and puts its occupancy lamps back on the turnouts.
repair python3 "$ROOT/jmri/layouts/hart/parked/polish_hart_layout_editor.py" --panel "$REPO_OUTPUT" --reference "$BEFORE_TABLES"
if (( repair_failed )); then
  echo "Stage 1 stored, but a repair failed (see above); fix it before committing." >&2
  exit 1
fi

echo "Stage 1 store is $REPO_OUTPUT (tables.xml is unchanged and generated, ADR-029)"
echo "log: $LOG"
