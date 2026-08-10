#!/usr/bin/env bash
# Pi: Launch CATS with HART Master Digicon sheet (CTC).
# Installed to /home/pi/hart/launch_cats.sh (default panel = HART_Master.xml).
set -euo pipefail
JMRI_HOME="${JMRI_HOME:-/home/pi/JMRI}"
PANEL="${1:-/home/pi/hart/cats/panels/sheets/HART_Master.xml}"
JMRI_PROFILE="${JMRI_PROFILE:-TCS_MQTT.3f32a166}"
LOG="${CATS_LAUNCH_LOG:-/home/pi/hart/logs/cats_launch.log}"

if [[ ! -f "$JMRI_HOME/cats.jar" || ! -f "$JMRI_HOME/cats.csh" ]]; then
  echo "CATS not installed in $JMRI_HOME" >&2
  exit 1
fi
if [[ ! -f "$PANEL" ]]; then
  echo "Panel not found: $PANEL" >&2
  exit 1
fi
PANEL="$(cd "$(dirname "$PANEL")" && pwd)/$(basename "$PANEL")"

if [[ "${CATS_FORCE_LAUNCH:-}" != "1" ]] && pgrep -f "apps\.PanelPro|cats\.apps\.Crandic|jmri\.PanelPro" >/dev/null 2>&1; then
  echo "Refusing to launch: PanelPro/CATS already running." >&2
  echo "Quit PanelPro (or set CATS_FORCE_LAUNCH=1), then retry." >&2
  pgrep -lf "apps\.PanelPro|cats\.apps\.Crandic|jmri\.PanelPro" | head -5 >&2 || true
  exit 1
fi

mkdir -p "$(dirname "$LOG")"
: >"$LOG"
echo "JAVA: $(java -version 2>&1 | head -1)"
echo "JMRI_HOME=$JMRI_HOME"
echo "Profile=$JMRI_PROFILE"
echo "Panel=$PANEL"
echo "Log=$LOG"
cd "$JMRI_HOME"
export ARCH=aarch64
./cats.csh --profile="$JMRI_PROFILE" "$PANEL" 2>&1 | tee -a "$LOG"
