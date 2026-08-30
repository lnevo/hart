#!/usr/bin/env bash
# Install the HART tree at /home/pi/hart into JMRI_UserFiles and ~/.jmri profiles.
# Called by sync_hart_package.sh --pi after rsync.
set -euo pipefail
HART="${HART:-/home/pi/hart}"
UF="${JMRI_USERFILES:-/home/pi/JMRI_UserFiles}"

if [[ ! -d "$HART" ]]; then
  echo "Missing $HART" >&2
  exit 1
fi

# Desktop Exec= paths are /home/pi/hart/launch_*.sh (not cats/scripts/pi/).
shopt -s nullglob
for f in "$HART/cats/scripts/pi/"launch_*.sh \
         "$HART/cats/scripts/pi/JMRI_CATS" \
         "$HART/cats/scripts/pi/README_CATS.txt"; do
  [[ -e "$f" ]] || continue
  cp -f "$f" "$HART/"
done
chmod +x "$HART/"launch_*.sh "$HART/JMRI_CATS" \
  "$HART/cats/scripts/pi/install_desktop_icons.sh" \
  "$HART/cats/scripts/install_jmri_web_override.sh" 2>/dev/null || true

mkdir -p "$UF"

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

# Fan-out a file or directory into UserFiles + every ~/.jmri/*.jmri profile.
fanout() {
  local src="$1"
  local rel="$2" # path under the profile root
  copy_into "$src" "$UF/$rel"
  echo "$rel -> $UF/$rel"
  local d
  for d in /home/pi/.jmri/*.jmri; do
    [[ -d "$d" ]] || continue
    copy_into "$src" "$d/$rel"
  done
}

if [[ -f "$HART/tables.xml" ]]; then
  cp -f "$HART/tables.xml" "$UF/tables.xml"
  echo "Pi tables.xml updated"
fi

if [[ -d "$HART/cats/resources/buttons" ]]; then
  fanout "$HART/cats/resources/buttons" "resources/buttons"
  echo "Pi button icons updated"
fi

if [[ -d "$HART/ctc/icons" ]]; then
  fanout "$HART/ctc/icons" "ctc/icons"
  if [[ -f "$HART/ctc/GUIObjects.xml" ]]; then
    mkdir -p "$UF/ctc"
    cp -f "$HART/ctc/GUIObjects.xml" "$UF/ctc/GUIObjects.xml"
    for d in /home/pi/.jmri/*.jmri; do
      [[ -d "$d" ]] || continue
      mkdir -p "$d/ctc"
      cp -f "$HART/ctc/GUIObjects.xml" "$d/ctc/GUIObjects.xml"
    done
  fi
  echo "Pi CTC icons + GUIObjects updated"
fi

for sys in cats-masts hart-aar; do
  if [[ -d "$HART/cats/resources/signals/$sys" ]]; then
    fanout "$HART/cats/resources/signals/$sys" "resources/signals/$sys"
    echo "Pi $sys updated"
  fi
done

JYTHON=(
  "$HART/jmri/layouts/hart/scripts/hart_dispatcher_startup.py"
  "$HART/jmri/layouts/hart/scripts/patch_dispatcher_facing.py"
  "$HART/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$HART/jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py"
  "$HART/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$HART/jmri/scripts/mqtt_signalhead_publisher.py"
)
mkdir -p "$UF/jython"
for f in "${JYTHON[@]}"; do
  [[ -f "$f" ]] && cp -f "$f" "$UF/jython/"
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
    --script sync_yard_ladder_buttons.py \
    --script mqtt_signalhead_publisher.py \
    --script jmri_cmd_watcher.py
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
