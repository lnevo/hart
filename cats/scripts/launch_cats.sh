#!/usr/bin/env bash
# Launch CATS from the JMRI install (cats.jar next to jmri.jar):
#   - select your JMRI profile (MQTT / tables)
#   - auto-open a Digicon panel XML
#
# Usage:
#   ./cats/scripts/launch_cats.sh
#   ./cats/scripts/launch_cats.sh cats/panels/HART_splice_magnet.xml
#   JMRI_PROFILE=My_JMRI_Railroad.3ef75bfd ./cats/scripts/launch_cats.sh
#
# macOS Local Network / MQTT:
#   Agent-launched java inherits Cursor's TCC. Grant Cursor Local Network once
#   (System Settings → Privacy & Security → Local Network), then restart Cursor
#   / relaunch CATS. PanelPro often never appears in that list — that is fine.
#   If Cursor is still blocked: CATS_LAUNCH_VIA=app|terminal hand off.
#   Override: CATS_LAUNCH_VIA=direct|app|terminal|auto
#
# Logs (stdout+stderr via 2>&1 | tee):
#   Default: cats/logs/cats_launch.log
#   CATS_LAUNCH_LOG=/tmp/cats.log ./cats/scripts/launch_cats.sh
#   CATS_LAUNCH_LOG= ./cats/scripts/launch_cats.sh   # disable
#
# Do not use sudo. CATS starts its own JMRI — do not launch while PanelPro /
# another CATS/JMRI is already running (MQTT client-id + profile collide).
# Override only if you know what you are doing: CATS_FORCE_LAUNCH=1
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
JMRI_HOME="${JMRI_HOME:-/Applications/JMRI}"
# Default: HART Master Digicon sheet (full layout; CTC).
# ABS open-house copy: HART_Master_ABS.xml via launch_hart_master_abs.sh
# Scratch/designer: HART_sheet_West_Yard2.xml — not the default launch target.
# Gate 1: ./cats/scripts/launch_cats.sh cats/panels/HART.xml
# Always use direct cats.csh unless you explicitly set CATS_LAUNCH_VIA=app|terminal.
# (PanelPro.app handoff changed JMRI behavior — do not use as default.)
PANEL="${1:-$ROOT/cats/panels/sheets/HART_Master.xml}"
JMRI_PROFILE="${JMRI_PROFILE:-My_JMRI_Railroad.3ef75bfd}"
CATS_LAUNCH_VIA="${CATS_LAUNCH_VIA:-direct}"
# Capture Java/JMRI stdout+stderr (ClassCast, MQTT, "not in a Block", …).
# Override: CATS_LAUNCH_LOG=/path/to.log   or CATS_LAUNCH_LOG=  to disable.
CATS_LAUNCH_LOG="${CATS_LAUNCH_LOG:-$ROOT/cats/logs/cats_launch.log}"

if [[ ! -f "$JMRI_HOME/cats.jar" || ! -f "$JMRI_HOME/cats.csh" ]]; then
  echo "CATS not installed in $JMRI_HOME" >&2
  echo "Run: $ROOT/tools/cats/install_into_jmri.sh" >&2
  exit 1
fi
if [[ ! -f "$PANEL" ]]; then
  echo "Panel not found: $PANEL" >&2
  exit 1
fi
PANEL="$(cd "$(dirname "$PANEL")" && pwd)/$(basename "$PANEL")"

jmri_already_running() {
  # Local JMRI/CATS only (java main classes). Does not probe remote layout JMRI.
  pgrep -f 'cats\.apps\.Crandic|apps\.PanelPro|jmri\.PanelPro|apps\.DecoderPro|apps\.DispatcherPro' >/dev/null 2>&1
}
if [[ "${CATS_FORCE_LAUNCH:-}" != "1" ]] && jmri_already_running; then
  echo "Refusing to launch CATS: JMRI/PanelPro/CATS is already running locally." >&2
  echo "Quit that instance first, then relaunch — or set CATS_FORCE_LAUNCH=1." >&2
  pgrep -lf 'cats\.apps\.Crandic|apps\.PanelPro|jmri\.PanelPro|apps\.DecoderPro|apps\.DispatcherPro' 2>/dev/null | head -5 >&2 || true
  exit 1
fi

if [[ -z "${JAVA_HOME:-}" ]]; then
  for ver in 21 17 11; do
    if JH=$(/usr/libexec/java_home -v "$ver" 2>/dev/null); then
      export JAVA_HOME="$JH"
      break
    fi
  done
fi
if [[ -z "${JAVA_HOME:-}" || ! -x "${JAVA_HOME}/bin/java" ]]; then
  echo "Need Java 11+ (JMRI 5.15). Install a JDK and retry." >&2
  /usr/libexec/java_home -V 2>&1 || true
  exit 1
fi

echo "JAVA_HOME=$JAVA_HOME"
"${JAVA_HOME}/bin/java" -version 2>&1 | head -1
echo "Starting CATS from $JMRI_HOME"
echo "JMRI profile: $JMRI_PROFILE"
echo "Auto-open Digicon: $PANEL"
echo "Quit any existing PanelPro first if it uses the same profile."

resolve_via() {
  # Default / auto → direct cats.csh only. Never auto-pick PanelPro.app.
  case "${1:-direct}" in
    app|terminal|direct) echo "$1" ;;
    auto|"") echo "direct" ;;
    *) echo "direct" ;;
  esac
}

VIA="$(resolve_via "$CATS_LAUNCH_VIA")"
echo "Launch via: $VIA (CATS_LAUNCH_VIA=$CATS_LAUNCH_VIA)"
if [[ -n "$CATS_LAUNCH_LOG" ]]; then
  mkdir -p "$(dirname "$CATS_LAUNCH_LOG")"
  : >"$CATS_LAUNCH_LOG"
  echo "Logging stdout+stderr → $CATS_LAUNCH_LOG"
fi

# Do NOT touch MQTT from launch (no retain clear/sync/seed, no broker probes).
# Field + broker are SoR. Occasional junk cleanup is manual only:
#   python3 cats/scripts/clear_mqtt_cmd_sensor_retain.py
# Digicon load safety: cats-pts-nullguard overlay (tools/cats/install_into_jmri.sh).

# Run cats.csh with optional tee of combined stdout/stderr.
run_cats() {
  local profile="$1" panel="$2"
  if [[ -n "$CATS_LAUNCH_LOG" ]]; then
    # Keep Terminal/console live; also append everything to the log.
    ./cats.csh --profile="$profile" "$panel" 2>&1 | tee -a "$CATS_LAUNCH_LOG"
  else
    exec ./cats.csh --profile="$profile" "$panel"
  fi
}

launch_direct() {
  cd "$JMRI_HOME"
  export ARCH=aarch64
  # Profile via JMRI -D; panel path is the sole Crandic layout argv (avoid "--"
  # leaking a second bare token → "Multiple layouts are being requested").
  run_cats "$JMRI_PROFILE" "$PANEL"
}

launch_app() {
  # PanelPro.app StartJMRI does not put cats.jar on CP by default — append it.
  # LaunchServices attributes Local Network to jmri.PanelPro, not Cursor.
  # Note: app handoff does not inherit our tee; use terminal|direct for logs.
  local app="$JMRI_HOME/PanelPro.app"
  if [[ ! -d "$app" ]]; then
    echo "PanelPro.app not found at $app — falling back to direct" >&2
    launch_direct
  fi
  if [[ -n "$CATS_LAUNCH_LOG" ]]; then
    echo "WARN: CATS_LAUNCH_VIA=app cannot tee into $CATS_LAUNCH_LOG — use terminal or direct." >&2
  fi
  echo "Handing off to $app (approve Local Network for PanelPro once if prompted)."
  open -n -a "$app" --args \
    --cp:a=cats.jar \
    -m cats.apps.Crandic \
    --profile="$JMRI_PROFILE" \
    "$PANEL"
}

launch_terminal() {
  # Runs cats.csh inside Terminal.app (usually already has Local Network).
  # stdout+stderr tee'd into CATS_LAUNCH_LOG when set.
  local cmd
  if [[ -n "$CATS_LAUNCH_LOG" ]]; then
    cmd=$(printf 'export JAVA_HOME=%q; export ARCH=aarch64; mkdir -p %q; : > %q; cd %q && ./cats.csh --profile=%q %q 2>&1 | tee -a %q; echo EXIT:$? | tee -a %q' \
      "$JAVA_HOME" "$(dirname "$CATS_LAUNCH_LOG")" "$CATS_LAUNCH_LOG" \
      "$JMRI_HOME" "$JMRI_PROFILE" "$PANEL" "$CATS_LAUNCH_LOG" "$CATS_LAUNCH_LOG")
  else
    cmd=$(printf 'export JAVA_HOME=%q; export ARCH=aarch64; cd %q && exec ./cats.csh --profile=%q %q' \
      "$JAVA_HOME" "$JMRI_HOME" "$JMRI_PROFILE" "$PANEL")
  fi
  echo "Handing off to Terminal.app…"
  osascript -e "tell application \"Terminal\" to do script \"$cmd\"" >/dev/null
}

case "$VIA" in
  direct) launch_direct ;;
  app) launch_app ;;
  terminal) launch_terminal ;;
  *)
    echo "Unknown CATS_LAUNCH_VIA=$VIA (use auto|app|direct|terminal)" >&2
    exit 1
    ;;
esac
