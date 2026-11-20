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

# The base discovery runs on: the generated tables with no logic and no mast properties.
python3 "$ROOT/tools/schematic/build_tables.py" --discovery-base

pp_begin "$SCRIPT"
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
python3 "$ROOT/tools/schematic/build_tables.py" --discovered-from "$STORED"
echo "DONE"
