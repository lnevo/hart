#!/usr/bin/env bash
# Deploy step 3: install on this Mac, from the repo (the web override, tables.xml, Operations Pro files, the
# DecoderPro roster, CATS panels, CTC icons, jython and the stamp). The gate has already run the Mac's Store check;
# it runs again here because this step changes the Mac and can be run alone.
#
# Usage: ship_mac.sh      (takes no staged folder: the Mac's panels name its own user files)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
[[ $# -eq 0 ]] || { echo "Usage: ship_mac.sh" >&2; exit 1; }
refuse_before_changing
load_parked
deploy_facts
tables_facts

install_jython_scripts() {
  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  local patch_startup="$ROOT/cats/scripts/patch_jmri_startup.py"
  _install_jython_into() {
    local profile="$1"
    local dest="$profile/jython"
    mkdir -p "$dest"
    local f
    for f in "${JYTHON_STARTUP_SCRIPTS[@]}" "${JYTHON_SIBLING_MODULES[@]}" "${JYTHON_PANEL_STATUS_PARTS[@]}"; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
      # Jython's compiled copy of a module it imported: one not older than the new .py would be reused.
      rm -f "$dest/$(basename "$f" .py)\$py.class"
    done
    echo "preference:jython scripts -> $dest"
    if parked_dir jmri/layouts/hart/dispatcher; then
      echo "Dispatcher traininfo parked: not installed; $profile/dispatcher left as it is"
    elif [[ -d "$traininfo" ]] && compgen -G "$traininfo/*.xml" >/dev/null; then
      mkdir -p "$profile/dispatcher/traininfo"
      rsync -a --delete --exclude '.DS_Store' --exclude '._*' "$traininfo/" "$profile/dispatcher/traininfo/"  # Finder litter never copied
      echo "Dispatcher traininfo -> $profile/dispatcher/traininfo"
    fi
    local profxml="${HOME}/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml"
    if [[ -f "$profxml" && -f "$patch_startup" ]]; then
      python3 "$patch_startup" retarget-jython \
        --profile "$profxml" \
        --script panel_status.py \
        --script signal_coordinator.py \
        --script jmri_cmd_watcher.py
      # STS sends car positions here (sts-plugins jmri_ops).
      python3 "$patch_startup" insert \
        --profile "$profxml" \
        --script preference:jython/sts_car_sync.py \
        --after panel_status.py
      # A Start Up entry for a retired script stays in an old profile.xml until it is stripped.
      python3 "$patch_startup" remove \
        --profile "$profxml" \
        --script prepare_nx_sml_paths.py || true
      echo "Start Up retargeted -> preference:jython ($profxml)"
    fi
  }
  mkdir -p "${HOME}/JMRI_UserFiles"
  _install_jython_into "${HOME}/JMRI_UserFiles"
}

install_tables_local() {
  [[ -n "$TABLES" ]] || return 0
  local dest="${HOME}/JMRI_UserFiles/tables.xml" stamp="${HOME}/JMRI_UserFiles/.tables_deployed.sha256"
  mkdir -p "${HOME}/JMRI_UserFiles"
  cp -f "$TABLES" "$dest"
  shasum -a 256 "$dest" | cut -d' ' -f1 >"$stamp"
  echo "tables.xml -> $dest"
}

install_ops_local() {
  bash "$ROOT/cats/scripts/install_ops_files.sh" \
    "$ROOT/jmri/layouts/hart/operations" "${HOME}/JMRI_UserFiles/operations"
}

# The DecoderPro roster (ADR-039 amendment 2026-11-26), from the repo master, with what it replaces backed up. No
# unpulled check here: the Mac's roster is a copy (the Pi's is the one DecoderPro programs), so a Mac edit survives only
# in JMRI_UserFiles/backups/roster/.
install_roster_local() {
  bash "$ROOT/tools/hosts/pi/install_roster.sh" "$ROSTER_MASTER" "${HOME}/JMRI_UserFiles"
}

install_cats_panels_local() {
  local dest="${HOME}/JMRI_UserFiles/cats/panels"
  mkdir -p "$dest"
  local p
  for p in "${LIVE_PANELS[@]}"; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" \
      --user-files "${HOME}/JMRI_UserFiles" --out "$dest/$p"
  done
  echo "CATS panels -> $dest"
}

install_ctc_icons_local() {
  local src="$ROOT/jmri/layouts/hart/ctc"
  [[ -d "$src/icons" ]] || return 0
  _install_ctc_into() {
    local dest="$1/ctc"
    mkdir -p "$dest/icons"
    cp -f "$src/icons/"*.gif "$dest/icons/"
    if [[ -f "$src/GUIObjects.xml" ]]; then
      cp -f "$src/GUIObjects.xml" "$dest/GUIObjects.xml"
    fi
    echo "CTC icons -> $dest"
  }
  _install_buttons_into() {
    local dest="$1/resources/buttons"
    mkdir -p "$dest"
    local f
    for f in "$ROOT/jmri/resources/buttons/"triangle_*.png; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
    done
    echo "button icons -> $dest"
  }
  _install_misc_into() {
    local dest="$1/resources/misc"
    mkdir -p "$dest"
    cp -f "$ROOT/jmri/resources/misc/"* "$dest/"
    echo "panel background -> $dest"
  }
  _install_uss_sensor_icons_into() {
    local dest="$1/resources/icons/USS/sensor"
    local src="$ROOT/jmri/resources/icons/USS/sensor"
    [[ -d "$src" ]] || return 0
    mkdir -p "$dest"
    local f
    for f in "$src/"yellow-*.gif; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
    done
    echo "USS sensor icons -> $dest"
  }
  _install_roster_images_into() {
    # Locomotive photos the DecoderPro roster entries point at (preference:resources/roster/<id>.jpg).
    local src="$ROOT/jmri/resources/roster"
    [[ -d "$src" ]] || return 0
    local dest="$1/resources/roster"
    mkdir -p "$dest"
    cp -f "$src/"*.jpg "$dest/" 2>/dev/null || true
    echo "roster photos -> $dest"
  }
  mkdir -p "${HOME}/JMRI_UserFiles"
  if parked_dir jmri/layouts/hart/ctc; then
    echo "USS CTC icons parked: not installed; ${HOME}/JMRI_UserFiles/ctc left as it is"
  else
    _install_ctc_into "${HOME}/JMRI_UserFiles"
  fi
  _install_buttons_into "${HOME}/JMRI_UserFiles"
  _install_misc_into "${HOME}/JMRI_UserFiles"
  _install_uss_sensor_icons_into "${HOME}/JMRI_UserFiles"
  _install_roster_images_into "${HOME}/JMRI_UserFiles"
}

# A Store into this Mac's tables.xml since the last deploy would be lost: stop before anything is installed.
check_mac_store || exit 1
# Mac JMRI is for development: the STS and mimic links follow the page's host to the Mac's own
# STS and mimic server (PORT as in tools/mqtt-mimic/install_mimic_launchagent.sh). The
# speed-match link names the Pi, the only host that serves that page (HART_PI_WEB_HOST, load_env.sh).
HART_PI_HOST="$HART_PI_WEB_HOST" HART_MIMIC_PORT="${MIMIC_PORT:-8765}" bash "$ROOT/cats/scripts/install_jmri_web_override.sh"
install_tables_local
install_ops_local
install_roster_local
install_cats_panels_local
install_ctc_icons_local
install_jython_scripts
# JMRI's MQTT startup race overlay for PanelPro.app and every other JMRI app on this Mac (ADR-034).
python3 "$ROOT/tools/jmri/mqtt_overlay/install_overlay.py" \
  --jar "$ROOT/tools/jmri/mqtt_overlay/hart-mqtt-race-fix.jar" \
  --settings-dir "${HOME}/Library/Preferences/JMRI" --jmri-home "${JMRI_HOME:-/Applications/JMRI}"
write_deploy_stamp "${HOME}/JMRI_UserFiles/cats/deploy_stamp.txt" mac
echo "deploy stamp -> ${HOME}/JMRI_UserFiles/cats/deploy_stamp.txt"
