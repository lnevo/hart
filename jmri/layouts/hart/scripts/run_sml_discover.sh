#!/usr/bin/env bash
# One-shot PanelPro SML Discover on this checkout's tables.xml, Store to a temporary file, then quit.
# The Store's Signal Mast Logic and mast properties go to jmri/layouts/hart/data/schematic/discovered_sml.xml
# (the one writer of that file) and tools/schematic/build_tables.py writes tables.xml from it (ADR-029:
# tables.xml is an output; the Store itself is never kept). Discovery runs from an empty list: the
# wrapper first writes tables.xml without any Signal Mast Logic (build_tables.py --discovery-base), so a
# discovered file that names a renamed or removed mast never blocks its own repair. If the run stops before
# the end, tables.xml stays that base (build_tables.py --check says so): run the wrapper again.
# Refuses if CATS/PanelPro is already running (MQTT client-id).
# The run lifecycle (profile backup and restore, Start Up items that run code off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
SCRIPT="$ROOT/jmri/layouts/hart/scripts/discover_sml.py"
MARKER="${HART_SML_DISCOVER_MARKER:-/tmp/hart_sml_discover.done}"
LOG="${HART_SML_DISCOVER_LOG:-/tmp/hart_sml_discover_panelpro.log}"

pp_refuse_running "Quit CATS/PanelPro first — SML Discover needs this profile alone."

pp_begin "$SCRIPT"
# The base discovery runs on: the generated tables with no logic and no mast properties. From here on a failed
# run leaves tables.xml as that base, and the exit says so (panelpro_session.sh PP_FAIL_NOTE).
# HART_TABLES_REVIEW=1: discover on a candidate the owner has not approved yet (build_tables.py --review)
REVIEW=(); [[ "${HART_TABLES_REVIEW:-}" == 1 ]] && REVIEW=(--review)
PP_FAIL_NOTE="tables.xml is now the discovery base (no Signal Mast Logic). Restore it: python3 tools/schematic/build_tables.py${REVIEW[*]:+ ${REVIEW[*]}} (or run this wrapper again)"
python3 "$ROOT/tools/schematic/build_tables.py" --discovery-base ${REVIEW[@]+"${REVIEW[@]}"}
# The stamp of this discovery: the sha256 of that base, so make panels' sml-current guard can tell when a later
# change to the generated beans makes the discovered logic stale.
BASE_SHA="$(python3 "$ROOT/tools/schematic/build_tables.py" --base-hash ${REVIEW[@]+"${REVIEW[@]}"} | tail -1)"
[[ "$BASE_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "could not hash the discovery base: $BASE_SHA" >&2; exit 1; }
rm -f "$MARKER"
STORED="$(mktemp "${TMPDIR:-/tmp}/hart_sml_discover.XXXXXX")"
PP_TMP_FILES+=("$STORED")

export HART_SML_DISCOVER_STORE=1
export HART_SML_DISCOVER_EXIT=1
export HART_SML_DISCOVER_MARKER="$MARKER"
export HART_SML_DISCOVER_FILE="$STORED"
export HART_SML_DISCOVER_WAIT="${HART_SML_DISCOVER_WAIT:-180}"

echo "Launching PanelPro for SML Discover (MQTT to the Pi broker)..."
pp_launch "$LOG"

rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-$((HART_SML_DISCOVER_WAIT + 60))}" 2 || rc=$?
if (( rc == 1 )); then
  echo "PanelPro exited before SML Discover finished. Log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi
if (( rc != 0 )); then
  echo "SML Discover timed out. Log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi

status=$(head -1 "$MARKER")
detail=$(sed -n '2p' "$MARKER")
echo "SML Discover $status $detail"
if [[ "$status" != "ok" ]]; then
  tail -60 "$LOG" >&2 || true
  exit 1
fi

# EXIT=1 should have quit Java; otherwise stop the PanelPro this run started (never another).
pp_wait_exit "${HART_PANELPRO_EXIT_WAIT:-60}" || { echo "PanelPro did not quit after SML Discover; stopping it" >&2; pp_stop_jmri; }

# The discovered logic into its own file, then tables.xml from its sources. Discover stores Digicon
# destinations Enabled; the generator stores them disabled until signal_coordinator.py takes control.
if ! python3 "$ROOT/tools/schematic/build_tables.py" --discovered-from "$STORED" ${REVIEW[@]+"${REVIEW[@]}"}; then
  # keep the discovery's Store, outside every checkout: the temporary file goes when this run ends
  pulled="$(hart_pulled_dir)" || exit 1
  kept="$pulled/discovery-$(date +%Y%m%d-%H%M%S).xml"
  cp "$STORED" "$kept"
  echo "The discovery's Store is kept as $kept." >&2
  echo "Fix what build_tables.py names above, then: python3 tools/schematic/build_tables.py --discovered-from $kept${REVIEW[*]:+ ${REVIEW[*]}}" >&2
  exit 1
fi
echo "$BASE_SHA" > "$ROOT/jmri/layouts/hart/data/schematic/discovered_sml.stamp"
PP_FAIL_NOTE=""
echo "DONE"
