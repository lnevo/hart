#!/usr/bin/env bash
# Load HART tables in PanelPro, run stock Stage 1 (auto-Yes shared-sensor), store.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
# PanelPro loads the tables of the checkout this script lives in (main or a worktree).
case "$ROOT" in
  "$HOME"/*) TABLES_URI="home:${ROOT#"$HOME"/}/jmri/layouts/hart/output/tables.xml" ;;
  *) TABLES_URI="$ROOT/jmri/layouts/hart/output/tables.xml" ;;
esac
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
PROFILE_ID="${JMRI_PROFILE:-My_JMRI_Railroad.3ef75bfd}"
PROFILE_XML="${JMRI_PROFILE_XML:-$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml}"
STARTJMRI="$JMRI_HOME/PanelPro.app/Contents/MacOS/StartJMRI"
PATCH="$ROOT/cats/scripts/patch_jmri_startup.py"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/run_dispatcher_stage1.py"
MARKER="${HART_STAGE1_MARKER:-/tmp/hart_stage1.done}"
LOG="${HART_STAGE1_LOG:-/tmp/hart_stage1.log}"
REPO_OUTPUT="$ROOT/jmri/layouts/hart/output/tables.xml"
REPO_TABLES="$REPO_OUTPUT"
REPO_TRAININFO="$ROOT/jmri/layouts/hart/dispatcher/traininfo"

if [[ ! -f "$PROFILE_XML" || ! -x "$STARTJMRI" ]]; then
  echo "PanelPro profile or launcher missing" >&2
  exit 1
fi
if pgrep -u "$(id -u)" -f 'java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.gui3\.dp3\.DecoderPro3|apps\.DecoderPro|apps\.DispatcherPro)' >/dev/null 2>&1; then
  echo "Quit local CATS/PanelPro before Stage 1" >&2
  exit 1
fi

BACKUP="$(mktemp)"
cp "$PROFILE_XML" "$BACKUP"
# Stage 1 drops the manual Princess SML pairs; keep a copy to restore them from.
BEFORE_TABLES="$(mktemp)"
cp "$REPO_TABLES" "$BEFORE_TABLES"
restore() {
  cp "$BACKUP" "$PROFILE_XML"
  rm -f "$BACKUP" "$BEFORE_TABLES"
}
trap restore EXIT
python3 "$ROOT/cats/scripts/patch_jmri_startup.py" load-tables --profile "$PROFILE_XML" \
  --tables "$TABLES_URI"   # automation works on this checkout's repo file (worktrees too)

python3 - "$PROFILE_XML" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for name in (
    "panel_status.py",
    "signal_coordinator.py",
    "sts_car_sync.py",
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
  --after signal_coordinator.py
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

# The manual steps after every Stage 1 (wiki/DISPATCHER_LAYOUT_HOOPS.md).
SCRIPTS="$ROOT/jmri/layouts/hart/scripts"
python3 "$SCRIPTS/restore_manual_sml_pairs.py" --panel "$REPO_OUTPUT" \
  --reference "$BEFORE_TABLES"
# Stage 1 writes Entire Train detection; HART cars detect head and tail only.
python3 "$SCRIPTS/fix_traininfo_detection.py" "$REPO_TRAININFO" | tail -1
python3 "$SCRIPTS/reconcile_dispatcher_stations.py" --panel "$REPO_OUTPUT" --no-sync
python3 "$SCRIPTS/disable_digicon_sml_in_tables.py" --panel "$REPO_OUTPUT"
# Stage 1 Store writes BlockContentsIcons at level 0 (behind the track) and
# puts its occupancy lamps back on the turnouts.
python3 "$SCRIPTS/polish_hart_layout_editor.py" --block-labels-only --sync-output
python3 "$SCRIPTS/polish_hart_layout_editor.py" --overlap-cleanup --panel "$REPO_OUTPUT"

echo "Stage 1 store is $REPO_OUTPUT"
echo "log: $LOG"
