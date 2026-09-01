#!/usr/bin/env bash
# Load HART tables in PanelPro, run stock Stage 1 (auto-Yes shared-sensor), store.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
PROFILE_ID="${JMRI_PROFILE:-My_JMRI_Railroad.3ef75bfd}"
PROFILE_XML="${JMRI_PROFILE_XML:-$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml}"
STARTJMRI="$JMRI_HOME/PanelPro.app/Contents/MacOS/StartJMRI"
PATCH="$ROOT/cats/scripts/patch_jmri_startup.py"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/run_dispatcher_stage1.py"
MARKER="${HART_STAGE1_MARKER:-/tmp/hart_stage1.done}"
LOG="${HART_STAGE1_LOG:-/tmp/hart_stage1.log}"
REPO_TABLES="$ROOT/tables/new_tables.xml"
REPO_OUTPUT="$ROOT/jmri/layouts/hart/output/tables.xml"
REPO_TRAININFO="$ROOT/jmri/layouts/hart/dispatcher/traininfo"

if [[ ! -f "$PROFILE_XML" || ! -x "$STARTJMRI" ]]; then
  echo "PanelPro profile or launcher missing" >&2
  exit 1
fi
if pgrep -u "$(id -u)" -f 'java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.DecoderPro|apps\.DispatcherPro)' >/dev/null 2>&1; then
  echo "Quit local CATS/PanelPro before Stage 1" >&2
  exit 1
fi

BACKUP="$(mktemp)"
cp "$PROFILE_XML" "$BACKUP"
restore() {
  cp "$BACKUP" "$PROFILE_XML"
  rm -f "$BACKUP"
}
trap restore EXIT

python3 - "$PROFILE_XML" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for name in (
    "apply_maintain_mqtt.py",
    "sync_turnout_buttons.py",
    "mqtt_signalhead_publisher.py",
):
    pattern = re.compile(
        r'<perform\b(?=[^>]*\bname="[^"]*'
        + re.escape(name)
        + r'")[^>]*/>'
    )
    text, count = pattern.subn(
        lambda match: match.group(0).replace('enabled="yes"', 'enabled="no"'),
        text,
        count=1,
    )
    if count != 1:
        print("startup action not present (ok): " + name)
path.write_text(text, encoding="utf-8")
PY

python3 "$PATCH" insert --profile "$PROFILE_XML" --script "$SCRIPT" \
  --after mqtt_signalhead_publisher.py
rm -f "$MARKER"

export HART_STAGE1_MARKER="$MARKER"
export HART_STAGE1_TABLES="$REPO_TABLES"
export HART_STAGE1_TRAININFO="$REPO_TRAININFO"
export HART_STAGE1_STORE="$REPO_OUTPUT"

if [[ -z "${JAVA_HOME:-}" ]]; then
  for ver in 21 17 11; do
    if JH=$(/usr/libexec/java_home -v "$ver" 2>/dev/null); then
      export JAVA_HOME="$JH"
      break
    fi
  done
fi

"$STARTJMRI" -p "$PROFILE_ID" >"$LOG" 2>&1 &
JPID=$!
# Stage 1 on HART can take a long time (graph + hundreds of transits).
deadline=$((SECONDS + 2700))
while (( SECONDS < deadline )); do
  [[ -f "$MARKER" ]] && break
  if ! kill -0 "$JPID" 2>/dev/null; then
    break
  fi
  sleep 5
done

if [[ ! -f "$MARKER" ]]; then
  kill "$JPID" 2>/dev/null || true
  echo "Stage 1 did not produce a marker; log: $LOG" >&2
  exit 1
fi

status="$(awk 'NR==1 {print; exit}' "$MARKER")"
detail="$(awk 'NR>1 {print}' "$MARKER")"
echo "Stage 1: $status"
echo "$detail"
if [[ "$status" != "ok" ]]; then
  exit 1
fi

# Stage 1 Store writes BlockContentsIcons at level 0 (behind the track).
python3 "$ROOT/jmri/layouts/hart/scripts/polish_hart_layout_editor.py" \
  --block-labels-only --sync-output

echo "Stage 1 store is $REPO_OUTPUT (also copied to new_tables.xml)"
echo "log: $LOG"
