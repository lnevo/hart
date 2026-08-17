#!/usr/bin/env bash
# Pi: Launch CATS with a HART Digicon panel.
# Installed to /home/pi/hart/launch_cats.sh (default panel = HART_Master.xml).
#
# CATS is its own JMRI app. It loads the same profile Start Up as PanelPro
# (preference:tables.xml, then retain/publisher scripts), then the Digicon XML.
# Do not run it at the same time as PanelPro on this profile (MQTT client-id
# collide; Rodney Black: never Store JMRI tables while a CATS layout is open).
#
# PanelPro is the place to edit/store JMRI tables and connections. Quit it,
# then launch CATS. CATS_FORCE_LAUNCH=1 is an emergency override only.
set -euo pipefail
# labwc/Xwayland: without this, Swing frames (tables, console, clock) paint blank;
# Layout Editor still works because it repaints on a timer.
export _JAVA_AWT_WM_NONREPARENTING="${_JAVA_AWT_WM_NONREPARENTING:-1}"
JMRI_HOME="${JMRI_HOME:-/home/pi/JMRI}"
PANEL="${1:-/home/pi/hart/cats/panels/HART_Master.xml}"
JMRI_PROFILE="${JMRI_PROFILE:-TCS_MQTT.3f32a166}"
LOG="${CATS_LAUNCH_LOG:-/home/pi/hart/logs/cats_launch.log}"

alert() {
  echo "$1" >&2
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}" ]]; then
    zenity --error --width=420 --title="CATS" --text="$1" 2>/dev/null || true
  fi
}

if [[ ! -f "$JMRI_HOME/cats.jar" || ! -f "$JMRI_HOME/cats.csh" ]]; then
  alert "CATS not installed in $JMRI_HOME"
  exit 1
fi
if [[ ! -f "$PANEL" ]]; then
  alert "Panel not found: $PANEL"
  exit 1
fi
PANEL="$(cd "$(dirname "$PANEL")" && pwd)/$(basename "$PANEL")"

jmri_already_running() {
  # Match the JVM only — not this script, ssh, or grep command lines.
  pgrep -u "$(id -u)" -f 'java .*(apps\.PanelPro\.PanelPro|cats\.apps\.Crandic)' >/dev/null 2>&1
}

if [[ "${CATS_FORCE_LAUNCH:-}" != "1" ]] && jmri_already_running; then
  alert "PanelPro or CATS is already running on this Pi.

Quit PanelPro first (use it only to edit/store JMRI tables), then click CATS again.

Do not run both at once — they share profile TCS_MQTT and the MQTT client id."
  pgrep -lf 'java .*(apps\.PanelPro\.PanelPro|cats\.apps\.Crandic)' | head -5 >&2 || true
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
