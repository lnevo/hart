#!/usr/bin/env bash
# One-shot PanelPro SML Discover → store tables.xml, then quit.
# Refuses if CATS/PanelPro is already running (MQTT client-id).
# The run lifecycle (profile backup and restore, Start Up items that run code off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/discover_sml.py"
MARKER="${HART_SML_DISCOVER_MARKER:-/tmp/hart_sml_discover.done}"
LOG="${HART_SML_DISCOVER_LOG:-/tmp/hart_sml_discover_panelpro.log}"

pp_refuse_running "Quit CATS/PanelPro first — SML Discover needs this profile alone."

python3 - <<PY
from pathlib import Path
p = Path("$TABLES")
t = p.read_text(encoding="utf-8")
old = '<layoutblocks class="jmri.jmrit.display.layoutEditor.configurexml.LayoutBlockManagerXml">'
new = '<layoutblocks class="jmri.jmrit.display.layoutEditor.configurexml.LayoutBlockManagerXml" blockrouting="yes">'
if 'blockrouting="yes"' not in t.split("<layoutblocks", 1)[-1][:200]:
    if old not in t:
        raise SystemExit("layoutblocks tag not found in $TABLES")
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    print("enabled blockrouting=yes in tables.xml")
else:
    print("blockrouting already yes")
PY

pp_begin "$SCRIPT"
rm -f "$MARKER"

export HART_SML_DISCOVER_STORE=1
export HART_SML_DISCOVER_EXIT=1
export HART_SML_DISCOVER_MARKER="$MARKER"
export HART_SML_DISCOVER_FILE="$TABLES"
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

# Discover stores Digicon dests Enabled; Digicon boot needs them Disabled until
# signal_coordinator.py takes control.
python3 "$ROOT/jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py"
echo "DONE"
