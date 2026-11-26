#!/usr/bin/env bash
# Install the deploy drop into JMRI_UserFiles and ~/.jmri profiles, then remove the drop.
# Called by sync_hart_package.sh --pi with HART set to a /tmp folder.
set -euo pipefail
HART="${HART:?HART must name the deploy drop}"
UF="${JMRI_USERFILES:-$HOME/JMRI_UserFiles}"

case "$HART" in
  /tmp/hart-deploy.*) ;;
  *) echo "Refusing drop outside /tmp: $HART" >&2; exit 1 ;;
esac
trap 'rm -rf "$HART"' EXIT

chmod +x "$HART/cats/scripts/pi/"*.sh "$HART/cats/scripts/pi/JMRI_CATS" \
  "$HART/cats/scripts/install_jmri_web_override.sh" 2>/dev/null || true

mkdir -p "$UF"

# First, so unpulled session state stops the deploy before anything changes.
bash "$HART/cats/scripts/install_ops_files.sh" "$HART/operations" "$UF/operations" --guard
# The DecoderPro roster (ADR-039 amendment 2026-11-26): the repo's, with what it replaces backed up. The gate
# stopped on an unpulled roster before anything was sent (G2), so what it replaces is what the last deploy installed.
bash "$HART/cats/scripts/pi/install_roster.sh" "$HART/roster" "$UF"

# CATS has no JMRI home: it opens real paths, so its files live here.
CATS_HOME="$UF/cats"
mkdir -p "$CATS_HOME/panels" "$CATS_HOME/launch" "$CATS_HOME/logs"
cp -f "$HART/cats/panels/"HART_CTC.xml "$HART/cats/panels/"HART_ABS.xml "$CATS_HOME/panels/"
shopt -s nullglob
for f in "$HART/cats/scripts/pi/"launch_*.sh "$HART/cats/scripts/pi/JMRI_CATS"; do
  cp -f "$f" "$CATS_HOME/launch/"
done
shopt -u nullglob
chmod +x "$CATS_HOME/launch/"*
cp -f "$HART/cats/scripts/pi/README_CATS.txt" "$CATS_HOME/"

copy_into() {
  local src="$1" dest="$2"
  [[ -e "$src" ]] || return 0
  mkdir -p "$dest"
  if [[ -d "$src" ]]; then
    rsync -a "$src/" "$dest/"
  else
    cp -f "$src" "$dest/"
  fi
}

# Install a file or directory into JMRI_UserFiles.
fanout() {
  local src="$1"
  local rel="$2" # path under the profile root
  copy_into "$src" "$UF/$rel"
  echo "$rel -> $UF/$rel"
}

if [[ -f "$HART/tables.xml" ]]; then
  # JMRI_UserFiles holds the only copy.
  mv -f "$HART/tables.xml" "$UF/tables.xml"
  # The deploy stamp now names these tables; an older pull stamp no longer counts (unpulled_changes.sh).
  rm -f "$UF/.tables_deployed.sha256"
  echo "Pi tables.xml updated"
fi

if [[ -d "$HART/cats/resources/buttons" ]]; then
  fanout "$HART/cats/resources/buttons" "resources/buttons"
  echo "Pi button icons updated"
fi

if [[ -d "$HART/cats/resources/misc" ]]; then
  fanout "$HART/cats/resources/misc" "resources/misc"
  echo "Pi panel background updated"
fi

if [[ -d "$HART/cats/resources/icons/USS/sensor" ]]; then
  fanout "$HART/cats/resources/icons/USS/sensor" "resources/icons/USS/sensor"
  echo "Pi USS sensor icons updated"
fi

if [[ -d "$HART/cats/resources/roster" ]]; then
  fanout "$HART/cats/resources/roster" "resources/roster"
  echo "Pi roster photos updated"
fi

if [[ -d "$HART/ctc/icons" ]]; then
  fanout "$HART/ctc/icons" "ctc/icons"
  if [[ -f "$HART/ctc/GUIObjects.xml" ]]; then
    mkdir -p "$UF/ctc"
    cp -f "$HART/ctc/GUIObjects.xml" "$UF/ctc/GUIObjects.xml"
  fi
  echo "Pi CTC icons + GUIObjects updated"
else
  # A parked USS CTC machine (hartlib.parked) ships no icons: the installed copies stay as they are.
  echo "Pi CTC icons not in the package (parked): $UF/ctc left as it is"
fi

# JMRI's MQTT startup race overlay, loaded by every JMRI app through ~/.jmri/jmri.conf (ADR-034).
# It installs only over the JMRI build it was made from; on any other it takes itself out.
if [[ -f "$HART/jmri/mqtt_overlay/install_overlay.py" ]]; then
  python3 "$HART/jmri/mqtt_overlay/install_overlay.py" \
    --jar "$HART/jmri/mqtt_overlay/hart-mqtt-race-fix.jar" \
    --settings-dir "$HOME/.jmri" --jmri-home "${JMRI_HOME:-$HOME/JMRI}"
fi

JYTHON=(
  "$HART/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$HART/jmri/layouts/hart/scripts/hide_band_panels.py"
  "$HART/jmri/layouts/hart/scripts/panel_status.py"
  # panel_status.py's PARTS: installed beside it, not Start Up items.
  "$HART/jmri/layouts/hart/scripts/panel_status_turnouts.py"
  "$HART/jmri/layouts/hart/scripts/panel_status_clicks.py"
  "$HART/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$HART/jmri/layouts/hart/scripts/sts_car_sync.py"
  "$HART/jmri/layouts/hart/scripts/mimic_relay.py"
  "$HART/jmri/scripts/signal_coordinator.py"
  # signal_coordinator.py's SIBLING_MODULES: installed beside it, not Start Up items.
  "$HART/jmri/scripts/sml_beans.py"
  "$HART/jmri/scripts/sml_claims.py"
  "$HART/jmri/scripts/sml_handoff.py"
  "$HART/jmri/scripts/sml_events.py"
  "$HART/jmri/scripts/sml_quit.py"
  "$HART/jmri/scripts/sml_ui.py"
)
mkdir -p "$UF/jython"
for f in "${JYTHON[@]}"; do
  [[ -f "$f" ]] && cp -f "$f" "$UF/jython/"
  # Jython's compiled copy of a module it imported: one not older than the new .py would be reused.
  rm -f "$UF/jython/$(basename "$f" .py)\$py.class"
done
echo "preference:jython scripts -> $UF/jython"

# A parked Dispatcher System (hartlib.parked) ships no traininfo or options: the installed copies stay as they are.
TRAININFO="$HART/jmri/layouts/hart/dispatcher/traininfo"
if [[ ! -d "$HART/jmri/layouts/hart/dispatcher" ]]; then
  echo "Pi dispatcher files not in the package (parked): $UF/dispatcher left as it is"
elif [[ -d "$TRAININFO" ]]; then
  mkdir -p "$UF/dispatcher/traininfo"
  # --delete: the profile mirrors the repo, so routes from old names do not linger in the Dispatcher picker.
  rsync -a --delete "$TRAININFO/" "$UF/dispatcher/traininfo/"
  echo "Pi dispatcher/traininfo mirrored"
fi
if [[ -f "$HART/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" ]]; then
  mkdir -p "$UF/dispatcher"
  cp -f "$HART/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" \
    "$UF/dispatcher/dispatcheroptions.xml"
  echo "Pi dispatcheroptions.xml updated"
fi

PATCH="$HART/cats/scripts/patch_jmri_startup.py"
if [[ -f "$PATCH" ]]; then
  python3 "$PATCH" retarget-jython \
    --profile "$HOME/.jmri/TCS_MQTT.jmri/profile/profile.xml" \
    --script panel_status.py \
    --script signal_coordinator.py \
    --script jmri_cmd_watcher.py
  # STS sends car positions here (sts-plugins jmri_ops).
  python3 "$PATCH" insert \
    --profile "$HOME/.jmri/TCS_MQTT.jmri/profile/profile.xml" \
    --script preference:jython/sts_car_sync.py \
    --after jmri_cmd_watcher.py
  # LCOS mimic page (/web/mimic/) publishes its feedback through this.
  python3 "$PATCH" insert \
    --profile "$HOME/.jmri/TCS_MQTT.jmri/profile/profile.xml" \
    --script preference:jython/mimic_relay.py \
    --after sts_car_sync.py
  # A Start Up entry for a retired script stays in an old profile.xml until it is stripped.
  python3 "$PATCH" remove \
    --profile "$HOME/.jmri/TCS_MQTT.jmri/profile/profile.xml" \
    --script prepare_nx_sml_paths.py 2>/dev/null || true
  echo "Pi Dispatcher compatibility scripts + preference:jython Start Up updated"
fi

if [[ -x "$HART/cats/scripts/install_jmri_web_override.sh" ]]; then
  bash "$HART/cats/scripts/install_jmri_web_override.sh"
fi
# Speed-match live view (/web/speedmatch/): the page, and its publisher as a user service.
if [[ -d "$HART/cats/resources/speedmatch-web" && -d "$HART/cats/speedmatch-live" ]]; then
  mkdir -p "$UF/web/speedmatch/live"
  cp -f "$HART/cats/resources/speedmatch-web/"* "$UF/web/speedmatch/"
  mkdir -p "$HOME/speedmatch/publisher" "$HOME/.config/systemd/user"
  rsync -a --delete "$HART/cats/speedmatch-live/" "$HOME/speedmatch/publisher/"
  cp -f "$HART/cats/scripts/pi/hart-speedmatch-live.service" "$HOME/.config/systemd/user/"
  loginctl enable-linger "$USER" 2>/dev/null || true
  # The deploy arrives over ssh, which may not carry the user manager's bus address.
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
  if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable hart-speedmatch-live.service >/dev/null 2>&1 || true
    systemctl --user restart hart-speedmatch-live.service \
      || echo "WARN: speed-match publisher (hart-speedmatch-live) did not start"
  else
    echo "WARN: no systemd user session; speed-match publisher not started"
  fi
  echo "Speed-match live view -> $UF/web/speedmatch/ (publisher: hart-speedmatch-live)"
fi
if [[ -x "$HART/cats/scripts/pi/install_desktop_icons.sh" ]]; then
  bash "$HART/cats/scripts/pi/install_desktop_icons.sh"
fi

# Last, so the stamp names a deploy only once everything above has been installed.
if [[ -f "$HART/cats/deploy_stamp.txt" ]]; then
  cp -f "$HART/cats/deploy_stamp.txt" "$CATS_HOME/deploy_stamp.txt"
  echo "deploy stamp -> $CATS_HOME/deploy_stamp.txt"
fi

echo "Pi apply_hart_package_local done"
