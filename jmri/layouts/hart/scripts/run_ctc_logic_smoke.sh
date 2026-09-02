#!/usr/bin/env bash
# Load the deployment bundle, start CTC Logic, verify columns/masts, exit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
PROFILE_ID="${JMRI_PROFILE:-My_JMRI_Railroad.3ef75bfd}"
PROFILE_XML="${JMRI_PROFILE_XML:-$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml}"
STARTJMRI="$JMRI_HOME/PanelPro.app/Contents/MacOS/StartJMRI"
PATCH="$ROOT/cats/scripts/patch_jmri_startup.py"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/ctc_logic_smoke.py"
MARKER="${HART_CTC_LOGIC_SMOKE_MARKER:-/tmp/hart_ctc_logic_smoke.done}"
LOG="${HART_CTC_LOGIC_SMOKE_LOG:-/tmp/hart_ctc_logic_smoke.log}"

if [[ ! -f "$PROFILE_XML" || ! -x "$STARTJMRI" ]]; then
  echo "PanelPro profile or launcher missing" >&2
  exit 1
fi
if pgrep -u "$(id -u)" -f 'java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.DecoderPro|apps\.DispatcherPro)' >/dev/null 2>&1; then
  echo "Quit CATS/PanelPro before the CTC Logic smoke test" >&2
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
    "sync_layout_button.py",
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
export HART_CTC_LOGIC_SMOKE_MARKER="$MARKER"

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
deadline=$((SECONDS + 150))
while (( SECONDS < deadline )); do
  [[ -f "$MARKER" ]] && break
  if ! kill -0 "$JPID" 2>/dev/null; then
    break
  fi
  sleep 2
done

if [[ ! -f "$MARKER" ]]; then
  kill "$JPID" 2>/dev/null || true
  echo "CTC Logic smoke did not produce a marker; log: $LOG" >&2
  tail -40 "$LOG" >&2 || true
  exit 1
fi

status="$(awk 'NR==1 {print; exit}' "$MARKER")"
detail="$(awk 'NR>1 {print}' "$MARKER")"
echo "CTC Logic smoke: $status"
echo "$detail"
[[ "$status" == "ok" ]]
