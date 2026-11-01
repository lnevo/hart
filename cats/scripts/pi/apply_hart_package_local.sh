#!/usr/bin/env bash
# Install the deploy drop into JMRI_UserFiles and ~/.jmri profiles, then remove the drop.
# Called by sync_hart_package.sh --pi with HART set to a /tmp folder.
set -euo pipefail
HART="${HART:?HART must name the deploy drop}"
UF="${JMRI_USERFILES:-/home/pi/JMRI_UserFiles}"

case "$HART" in
  /tmp/hart-deploy.*) ;;
  *) echo "Refusing drop outside /tmp: $HART" >&2; exit 1 ;;
esac
trap 'rm -rf "$HART"' EXIT

chmod +x "$HART/cats/scripts/pi/"*.sh "$HART/cats/scripts/pi/JMRI_CATS" \
  "$HART/cats/scripts/install_jmri_web_override.sh" 2>/dev/null || true

mkdir -p "$UF"

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
  echo "Pi tables.xml updated"
fi

if [[ -d "$HART/cats/resources/buttons" ]]; then
  fanout "$HART/cats/resources/buttons" "resources/buttons"
  echo "Pi button icons updated"
fi

if [[ -d "$HART/cats/resources/misc" ]]; then
  fanout "$HART/cats/resources/misc" "resources/misc"
  rm -f "$HART/cats/resources/misc/linear5_panel_bg.jpg" "$UF/resources/misc/linear5_panel_bg.jpg" \
    /home/pi/.jmri/*.jmri/resources/misc/linear5_panel_bg.jpg
  echo "Pi panel background updated"
fi

if [[ -d "$HART/cats/resources/icons/USS/sensor" ]]; then
  fanout "$HART/cats/resources/icons/USS/sensor" "resources/icons/USS/sensor"
  echo "Pi USS sensor icons updated"
fi

if [[ -d "$HART/ctc/icons" ]]; then
  fanout "$HART/ctc/icons" "ctc/icons"
  if [[ -f "$HART/ctc/GUIObjects.xml" ]]; then
    mkdir -p "$UF/ctc"
    cp -f "$HART/ctc/GUIObjects.xml" "$UF/ctc/GUIObjects.xml"
  fi
  echo "Pi CTC icons + GUIObjects updated"
fi

# Masts are stock Basic (ADR-011). Retired custom signal sets have to be removed here. The JMRI install's own
# xml/signals/C&O-1980 is stock and stays.
for sys in cats-masts hart-aar "C&O-1980"; do
  rm -rf "$HART/cats/resources/signals/$sys" "$UF/resources/signals/$sys"
  for d in /home/pi/.jmri/*.jmri; do
    rm -rf "$d/resources/signals/$sys"
  done
done
rm -rf "${JMRI_HOME:-/home/pi/JMRI}/xml/signals/cats-masts"
rm -f "$HART/cats/scripts/windows/install_cats_masts.ps1"
rm -rf "$HART/tools/jmri/patches"
echo "Pi retired signal sets removed"

# Panels and launchers replaced by HART_CTC.xml / HART_ABS.xml (ADR-012).
rm -f "$HART"/cats/panels/HART_Master*.xml "$HART"/launch_hart_master*.sh

JYTHON=(
  "$HART/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$HART/jmri/layouts/hart/scripts/panel_status.py"
  "$HART/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$HART/jmri/scripts/signal_coordinator.py"
)
mkdir -p "$UF/jython"
for f in "${JYTHON[@]}"; do
  [[ -f "$f" ]] && cp -f "$f" "$UF/jython/"
done
rm -f "$UF/jython/hart_dispatcher_startup.py" "$UF/jython/patch_dispatcher_facing.py"
for d in "$UF/jython" /home/pi/.jmri/*.jmri/jython; do
  [[ -d "$d" ]] || continue
  (cd "$d" && rm -f sync_turnout_buttons.py sync_yard_ladder_buttons.py apply_dispatcher_roster_profiles.py SetBlockPreviewValues.py sync_layout_button.py mqtt_signalhead_publisher.py)
done
echo "preference:jython scripts -> $UF/jython"

TRAININFO="$HART/jmri/layouts/hart/dispatcher/traininfo"
if [[ -d "$TRAININFO" ]]; then
  mkdir -p "$UF/dispatcher/traininfo"
  rsync -a "$TRAININFO/" "$UF/dispatcher/traininfo/"
  echo "Pi dispatcher/traininfo updated"
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
    --profile /home/pi/.jmri/TCS_MQTT.jmri/profile/profile.xml \
    --script panel_status.py \
    --script signal_coordinator.py \
    --script jmri_cmd_watcher.py
  python3 "$PATCH" remove \
    --profile /home/pi/.jmri/TCS_MQTT.jmri/profile/profile.xml \
    --script prepare_nx_sml_paths.py 2>/dev/null || true
  rm -f "$UF/jython/prepare_nx_sml_paths.py"
  echo "Pi Dispatcher compatibility scripts + preference:jython Start Up updated"
  for s in apply_sml_cats_pairs.py unhold_signal_masts.py \
           apply_maintain_mqtt.py apply_mqtt_retain_at_startup.py; do
    python3 "$PATCH" remove \
      --profile /home/pi/.jmri/TCS_MQTT.jmri/profile/profile.xml \
      --script "$HART/jmri/layouts/hart/scripts/$s" \
      2>/dev/null || true
    rm -f "$HART/jmri/layouts/hart/scripts/$s"
  done
fi

if [[ -x "$HART/cats/scripts/install_jmri_web_override.sh" ]]; then
  bash "$HART/cats/scripts/install_jmri_web_override.sh"
fi
if [[ -x "$HART/cats/scripts/pi/install_desktop_icons.sh" ]]; then
  bash "$HART/cats/scripts/pi/install_desktop_icons.sh"
fi

echo "Pi apply_hart_package_local done"
