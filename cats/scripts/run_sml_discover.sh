#!/usr/bin/env bash
# One-shot PanelPro SML Discover → store tables.xml, then quit.
# Refuses if CATS/PanelPro is already running (MQTT client-id).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
PROFILE_ID="${JMRI_PROFILE:-My_JMRI_Railroad.3ef75bfd}"
PROFILE_XML="${JMRI_PROFILE_XML:-$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml}"
TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/discover_sml.py"
PATCH="$ROOT/cats/scripts/patch_jmri_startup.py"
MARKER="${HART_SML_DISCOVER_MARKER:-/tmp/hart_sml_discover.done}"
STARTJMRI="$JMRI_HOME/PanelPro.app/Contents/MacOS/StartJMRI"

if [[ ! -f "$PROFILE_XML" ]]; then
  echo "profile.xml not found: $PROFILE_XML" >&2
  exit 1
fi
if [[ ! -x "$STARTJMRI" ]]; then
  echo "PanelPro StartJMRI not found: $STARTJMRI" >&2
  exit 1
fi
if pgrep -u "$(id -u)" -f 'java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.DecoderPro|apps\.DispatcherPro)' >/dev/null 2>&1; then
  echo "Quit CATS/PanelPro first — SML Discover needs this profile alone." >&2
  exit 1
fi

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

BAK="$(mktemp)"
cp "$PROFILE_XML" "$BAK"
restore() {
  cp "$BAK" "$PROFILE_XML"
  rm -f "$BAK"
}
trap restore EXIT

python3 "$PATCH" insert --profile "$PROFILE_XML" --script "$SCRIPT" --after mqtt_signalhead_publisher.py
rm -f "$MARKER"

export HART_SML_DISCOVER_STORE=1
export HART_SML_DISCOVER_EXIT=1
export HART_SML_DISCOVER_MARKER="$MARKER"
export HART_SML_DISCOVER_FILE="$TABLES"
export HART_SML_DISCOVER_WAIT="${HART_SML_DISCOVER_WAIT:-180}"

if [[ -z "${JAVA_HOME:-}" ]]; then
  for ver in 21 17 11; do
    if JH=$(/usr/libexec/java_home -v "$ver" 2>/dev/null); then
      export JAVA_HOME="$JH"
      break
    fi
  done
fi

echo "Launching PanelPro for SML Discover (MQTT to minipc)..."
"$STARTJMRI" -p "$PROFILE_ID" >/tmp/hart_sml_discover_panelpro.log 2>&1 &
JPID=$!

deadline=$((SECONDS + ${HART_SML_DISCOVER_WAIT:-180} + 60))
while (( SECONDS < deadline )); do
  if [[ -f "$MARKER" ]]; then
    break
  fi
  if ! kill -0 "$JPID" 2>/dev/null; then
    echo "PanelPro exited before Discover finished. Log: /tmp/hart_sml_discover_panelpro.log" >&2
    tail -40 /tmp/hart_sml_discover_panelpro.log >&2 || true
    exit 1
  fi
  sleep 2
done

if [[ ! -f "$MARKER" ]]; then
  echo "Discover timed out. Log: /tmp/hart_sml_discover_panelpro.log" >&2
  tail -40 /tmp/hart_sml_discover_panelpro.log >&2 || true
  kill "$JPID" 2>/dev/null || true
  exit 1
fi

status=$(head -1 "$MARKER")
detail=$(sed -n '2p' "$MARKER")
echo "Discover $status $detail"
if [[ "$status" != "ok" ]]; then
  tail -60 /tmp/hart_sml_discover_panelpro.log >&2 || true
  kill "$JPID" 2>/dev/null || true
  exit 1
fi

# EXIT=1 should have quit Java; don't leave a stray PanelPro.
sleep 2
if kill -0 "$JPID" 2>/dev/null; then
  kill "$JPID" 2>/dev/null || true
  sleep 2
  pkill -u "$(id -u)" -f 'java .*(apps\.PanelPro\.PanelPro)' >/dev/null 2>&1 || true
fi

cp "$TABLES" "$ROOT/tables/new_tables.xml"
echo "copied tables.xml -> tables/new_tables.xml"
# Discover stores Digicon dests Enabled; Digicon boot needs them Disabled until
# mqtt_signalhead_publisher.py takes control.
python3 "$ROOT/cats/scripts/disable_digicon_sml_in_tables.py"
echo "DONE"
