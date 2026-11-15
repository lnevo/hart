#!/usr/bin/env bash
# One-shot PanelPro NX Discover (SML mode by default) → store tables.xml, then quit.
# Full interlock: HART_NX_LOCK=1. Refuses if CATS/PanelPro is already running (MQTT client-id).
# The run lifecycle (profile backup and restore, Start Up items that run code off, stopping
# PanelPro on timeout or a signal) is tools/hosts/panelpro_session.sh.
# Sensor states are only painted in this PanelPro (setOwnState): no MQTT publish from the script.
# Painting still fires JMRI's own listeners (Logix, LogixNG, SML, Dispatcher, block occupancy),
# which can act on what they see. Before Discover the script paints every occupancy sensor
# INACTIVE so routing can stabilise; that clear always runs. Run it with the layout idle, and a
# rehearsal with the broker unreachable.
#   HART_NX_SMOKE=1   opt in to the Brick occupancy smoke (paints BS Switch 1 ACTIVE and back)
#   HART_NX_THROW=1   with the smoke, sets a real NX route: that commands MQTT turnouts
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
refuse_hart_tables "run PanelPro on tables.xml"
pp_profile
TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/discover_nx.py"
MARKER="${HART_NX_DISCOVER_MARKER:-/tmp/hart_nx_discover.done}"
LOG="${HART_NX_DISCOVER_LOG:-/tmp/hart_nx_discover_panelpro.log}"

pp_refuse_running "Quit CATS/PanelPro first — NX Discover needs this profile alone."

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

export HART_NX_DISCOVER_STORE=1
export HART_NX_DISCOVER_EXIT=1
export HART_NX_DISCOVER_MARKER="$MARKER"
export HART_NX_DISCOVER_FILE="$TABLES"
export HART_NX_DISCOVER_WAIT="${HART_NX_DISCOVER_WAIT:-180}"
export HART_NX_SMOKE="${HART_NX_SMOKE:-0}"
export HART_NX_THROW="${HART_NX_THROW:-}"
if [[ "$HART_NX_THROW" == "1" ]]; then
  echo "HART_NX_THROW=1: the smoke sets a real NX route, which commands MQTT turnouts." >&2
fi

echo "Launching PanelPro for NX Discover (MQTT to the Pi broker)..."
pp_launch "$LOG"

rc=0
pp_wait_marker "$MARKER" "${HART_PANELPRO_TIMEOUT:-$((HART_NX_DISCOVER_WAIT + 60))}" 2 || rc=$?
if (( rc == 1 )); then
  echo "PanelPro exited before NX Discover finished. Log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi
if (( rc != 0 )); then
  echo "NX Discover timed out. Log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi

status=$(head -1 "$MARKER")
detail=$(sed -n '2p' "$MARKER")
echo "NX Discover $status $detail"
if [[ "$status" != "ok" ]]; then
  tail -80 "$LOG" >&2 || true
  exit 1
fi

# EXIT=1 should have quit Java; otherwise stop the PanelPro this run started (never another).
pp_wait_exit "${HART_PANELPRO_EXIT_WAIT:-60}" || { echo "PanelPro did not quit after NX Discover; stopping it" >&2; pp_stop_jmri; }
echo "DONE"
