#!/usr/bin/env bash
# Deploy HART Digicon/JMRI package from repo SoR via SSH (no Dropbox).
# Usage: ./cats/scripts/sync_hart_package.sh [--pi] [--win] [--all]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WIN_HOST="${HART_WIN_SSH:-lnevo@10.0.0.6}"
WIN_PORT="${HART_WIN_SSH_PORT:-2222}"
PI_HOST="${HART_PI_SSH:-pi}"

DO_PI=0
DO_WIN=0
DO_MAC_WEB=1
if [[ $# -gt 0 ]]; then
  DO_MAC_WEB=0
  for a in "$@"; do
    case "$a" in
      --pi) DO_PI=1; DO_MAC_WEB=1 ;;
      --win) DO_WIN=1; DO_MAC_WEB=1 ;;
      --all) DO_PI=1; DO_WIN=1; DO_MAC_WEB=1 ;;
      --mac-web-only) DO_MAC_WEB=1 ;;
      -h|--help)
        echo "Usage: $0 [--pi] [--win] [--all]"
        echo "  Windows SSH: ${WIN_HOST} -p ${WIN_PORT} → %USERPROFILE%/hart"
        echo "  Pi SSH:      ${PI_HOST} → /home/pi/hart + JMRI_UserFiles"
        exit 0
        ;;
      *) echo "Unknown option: $a" >&2; exit 1 ;;
    esac
  done
fi

ssh_win() { ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" "$@"; }
scp_win() { scp -O -o BatchMode=yes -o ConnectTimeout=15 -P "$WIN_PORT" "$@"; }

TABLES=""
if [[ -f "$ROOT/jmri/layouts/hart/output/tables.xml" ]]; then
  TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
elif [[ -f "$ROOT/tables/new_tables.xml" ]]; then
  TABLES="$ROOT/tables/new_tables.xml"
fi

PANEL_AUDIT="$ROOT/jmri/layouts/hart/scripts/audit_panel_contracts.py"
if [[ -n "$TABLES" && -f "$PANEL_AUDIT" ]]; then
  python3 "$PANEL_AUDIT" --strict
fi

REWRITE="$ROOT/cats/scripts/rewrite_button_icon_paths.py"

install_dispatcher_facing_patch() {
  local patch="$ROOT/jmri/layouts/hart/scripts/patch_dispatcher_facing.py"
  local startup="$ROOT/jmri/layouts/hart/scripts/hart_dispatcher_startup.py"
  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  [[ -f "$patch" && -f "$startup" ]] || return 0
  _install_facing_into() {
    local profile="$1"
    local dest="$profile/jython"
    mkdir -p "$dest"
    cp -f "$patch" "$startup" "$dest/"
    echo "Dispatcher compatibility scripts -> $dest"
    if [[ -d "$traininfo" ]] && compgen -G "$traininfo/*.xml" >/dev/null; then
      mkdir -p "$profile/dispatcher/traininfo"
      cp -f "$traininfo/"*.xml "$profile/dispatcher/traininfo/"
      echo "Dispatcher traininfo -> $profile/dispatcher/traininfo"
    fi
  }
  if [[ -d "${HOME}/Library/Preferences/JMRI" ]]; then
    for d in "${HOME}/Library/Preferences/JMRI"/*.jmri; do
      [[ -d "$d" ]] && _install_facing_into "$d"
    done
  fi
  if [[ -d "${HOME}/.jmri" ]]; then
    for d in "${HOME}/.jmri"/*.jmri; do
      [[ -d "$d" ]] && _install_facing_into "$d"
    done
  fi
  if [[ -d "${HOME}/JMRI_UserFiles" ]]; then
    _install_facing_into "${HOME}/JMRI_UserFiles"
  fi
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
  _install_hart_aar_into() {
    local dest="$1/resources/signals/hart-aar"
    mkdir -p "$dest"
    cp -f "$ROOT/cats/resources/signals/hart-aar/"aspects.xml \
      "$ROOT/cats/resources/signals/hart-aar/"appearance-SL-2-digicon.xml \
      "$dest/"
    echo "hart-aar -> $dest"
  }
  if [[ -d "${HOME}/Library/Preferences/JMRI" ]]; then
    for d in "${HOME}/Library/Preferences/JMRI"/*.jmri; do
      [[ -d "$d" ]] && _install_ctc_into "$d" && _install_hart_aar_into "$d"
    done
  fi
  if [[ -d "${HOME}/.jmri" ]]; then
    for d in "${HOME}/.jmri"/*.jmri; do
      [[ -d "$d" ]] && _install_ctc_into "$d" && _install_hart_aar_into "$d"
    done
  fi
  if [[ -d "${HOME}/JMRI_UserFiles" ]]; then
    _install_ctc_into "${HOME}/JMRI_UserFiles"
    _install_hart_aar_into "${HOME}/JMRI_UserFiles"
  fi
}

if [[ "$DO_MAC_WEB" -eq 1 ]]; then
  bash "$ROOT/cats/scripts/install_jmri_web_override.sh"
  install_ctc_icons_local
  install_dispatcher_facing_patch
fi

if [[ "$DO_PI" -eq 1 ]]; then
  echo "Deploy → Pi ($PI_HOST)..."
  ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p \
    /home/pi/hart/cats/panels \
    /home/pi/hart/cats/resources/buttons \
    /home/pi/hart/cats/resources/jmri-web \
    /home/pi/hart/cats/scripts \
    /home/pi/hart/jmri/layouts/hart/scripts \
    /home/pi/hart/jmri/scripts \
    /home/pi/JMRI_UserFiles/web/servlet/home'

  # Rewrite button paths before upload
  STAGE=$(mktemp -d)
  for p in HART_Master.xml HART_Master_ABS.xml HART_Master_ABS_hold.xml HART_Master_CTC_hold.xml; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" --hart-root /home/pi/hart --out "$STAGE/$p"
  done
  scp -o BatchMode=yes "$STAGE"/*.xml "$PI_HOST:/home/pi/hart/cats/panels/"
  rm -rf "$STAGE"

  if compgen -G "$ROOT/cats/resources/buttons/lamp_*.png" > /dev/null; then
    scp -o BatchMode=yes "$ROOT/cats/resources/buttons/"lamp_*.png \
      "$PI_HOST:/home/pi/hart/cats/resources/buttons/"
  fi
  scp -o BatchMode=yes -r "$ROOT/cats/resources/jmri-web/." \
    "$PI_HOST:/home/pi/hart/cats/resources/jmri-web/"
  scp -o BatchMode=yes \
    "$ROOT/cats/scripts/install_jmri_web_override.sh" \
    "$REWRITE" \
    "$PI_HOST:/home/pi/hart/cats/scripts/"
  # Launchers: CATS and PanelPro are sequential (no CATS_FORCE_LAUNCH).
  scp -o BatchMode=yes \
    "$ROOT/cats/scripts/pi/launch_cats.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_abs.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_abs_hold.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_ctc_hold.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_desktop.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_abs_desktop.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_abs_hold_desktop.sh" \
    "$ROOT/cats/scripts/pi/launch_hart_master_ctc_hold_desktop.sh" \
    "$ROOT/cats/scripts/pi/launch_cats_desktop.sh" \
    "$ROOT/cats/scripts/pi/JMRI_CATS" \
    "$ROOT/cats/scripts/pi/README_CATS.txt" \
    "$PI_HOST:/home/pi/hart/"
  ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/hart/cats/scripts/pi'
  scp -o BatchMode=yes \
    "$ROOT/cats/scripts/pi/CATS_CTC.desktop" \
    "$ROOT/cats/scripts/pi/CATS_ABS.desktop" \
    "$ROOT/cats/scripts/pi/install_desktop_icons.sh" \
    "$PI_HOST:/home/pi/hart/cats/scripts/pi/"
  ssh -o BatchMode=yes "$PI_HOST" 'chmod +x \
    /home/pi/hart/launch_cats.sh \
    /home/pi/hart/launch_cats_desktop.sh \
    /home/pi/hart/JMRI_CATS \
    /home/pi/hart/launch_hart_master.sh \
    /home/pi/hart/launch_hart_master_abs.sh \
    /home/pi/hart/launch_hart_master_abs_hold.sh \
    /home/pi/hart/launch_hart_master_ctc_hold.sh \
    /home/pi/hart/launch_hart_master_desktop.sh \
    /home/pi/hart/launch_hart_master_abs_desktop.sh \
    /home/pi/hart/launch_hart_master_abs_hold_desktop.sh \
    /home/pi/hart/launch_hart_master_ctc_hold_desktop.sh \
    /home/pi/hart/cats/scripts/pi/install_desktop_icons.sh'
  ssh -o BatchMode=yes "$PI_HOST" '/home/pi/hart/cats/scripts/pi/install_desktop_icons.sh'
  scp -o BatchMode=yes \
    "$ROOT/jmri/layouts/hart/scripts/apply_maintain_mqtt.py" \
    "$ROOT/jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py" \
    "$ROOT/jmri/layouts/hart/scripts/add_yard_ladder_le_icons.py" \
    "$ROOT/jmri/layouts/hart/scripts/apply_mqtt_retain_at_startup.py" \
    "$ROOT/jmri/layouts/hart/scripts/discover_sml.py" \
    "$ROOT/jmri/layouts/hart/scripts/hart_dispatcher_startup.py" \
    "$ROOT/jmri/layouts/hart/scripts/patch_dispatcher_facing.py" \
    "$ROOT/jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py" \
    "$PI_HOST:/home/pi/hart/jmri/layouts/hart/scripts/"
  # Native SML cutover: retired startup workarounds must stay out of the Pi
  # profile. apply_sml_cats_pairs: SML lives in tables.xml via Discover.
  # unhold_signal_masts: Held is CATS CTC's channel (hold at load, unhold on
  # route lining); a blanket unhold watchdog fights it. ABS mimic is unbound.
  scp -o BatchMode=yes "$ROOT/cats/scripts/patch_jmri_startup.py" \
    "$PI_HOST:/home/pi/hart/cats/scripts/"
  ssh -o BatchMode=yes "$PI_HOST" \
    'for s in apply_sml_cats_pairs.py unhold_signal_masts.py; do \
       python3 /home/pi/hart/cats/scripts/patch_jmri_startup.py remove \
         --profile /home/pi/.jmri/TCS_MQTT.jmri/profile/profile.xml \
         --script /home/pi/hart/jmri/layouts/hart/scripts/$s \
         2>/dev/null || true; \
       rm -f /home/pi/hart/jmri/layouts/hart/scripts/$s; \
     done'
  scp -o BatchMode=yes \
    "$ROOT/jmri/scripts/mqtt_signalhead_publisher.py" \
    "$PI_HOST:/home/pi/hart/jmri/scripts/"
  ssh -o BatchMode=yes "$PI_HOST" \
    'chmod +x /home/pi/hart/cats/scripts/install_jmri_web_override.sh; /home/pi/hart/cats/scripts/install_jmri_web_override.sh'
  if [[ -n "$TABLES" ]]; then
    scp -o BatchMode=yes "$TABLES" "$PI_HOST:/home/pi/JMRI_UserFiles/tables.xml"
    echo "Pi tables.xml updated"
  fi
  TRAININFO="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  if [[ -d "$TRAININFO" ]] && compgen -G "$TRAININFO/*.xml" > /dev/null; then
    ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/JMRI_UserFiles/dispatcher/traininfo'
    scp -o BatchMode=yes "$TRAININFO"/*.xml \
      "$PI_HOST:/home/pi/JMRI_UserFiles/dispatcher/traininfo/"
    echo "Pi dispatcher/traininfo updated"
  fi
  if [[ -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" ]]; then
    ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/JMRI_UserFiles/dispatcher'
    scp -o BatchMode=yes "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" \
      "$PI_HOST:/home/pi/JMRI_UserFiles/dispatcher/dispatcheroptions.xml"
    echo "Pi dispatcheroptions.xml updated"
  fi
  ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/JMRI_UserFiles/jython'
  scp -o BatchMode=yes \
    "$ROOT/jmri/layouts/hart/scripts/hart_dispatcher_startup.py" \
    "$ROOT/jmri/layouts/hart/scripts/patch_dispatcher_facing.py" \
    "$PI_HOST:/home/pi/JMRI_UserFiles/jython/"
  echo "Pi Dispatcher compatibility scripts updated"
  # Digicon SHSM appearances (incl. dwarf) for LE + mast load
  ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/JMRI_UserFiles/resources/signals/cats-masts /home/pi/hart/cats/resources/signals/cats-masts'
  scp -o BatchMode=yes \
    "$ROOT/cats/resources/signals/cats-masts/"appearance-cats-virtual*.xml \
    "$ROOT/cats/resources/signals/cats-masts/aspects.xml" \
    "$ROOT/cats/resources/signals/cats-masts/index.shtml" \
    "$PI_HOST:/home/pi/JMRI_UserFiles/resources/signals/cats-masts/"
  scp -o BatchMode=yes \
    "$ROOT/cats/resources/signals/cats-masts/"appearance-cats-virtual*.xml \
    "$ROOT/cats/resources/signals/cats-masts/aspects.xml" \
    "$ROOT/cats/resources/signals/cats-masts/index.shtml" \
    "$PI_HOST:/home/pi/hart/cats/resources/signals/cats-masts/"
  echo "Pi cats-masts updated"
  # hart-aar signal system (2-head Digicon SHSM masts in tables.xml need it to load)
  ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/JMRI_UserFiles/resources/signals/hart-aar /home/pi/hart/cats/resources/signals/hart-aar'
  scp -o BatchMode=yes \
    "$ROOT/cats/resources/signals/hart-aar/aspects.xml" \
    "$ROOT/cats/resources/signals/hart-aar/appearance-SL-2-digicon.xml" \
    "$PI_HOST:/home/pi/JMRI_UserFiles/resources/signals/hart-aar/"
  scp -o BatchMode=yes \
    "$ROOT/cats/resources/signals/hart-aar/aspects.xml" \
    "$ROOT/cats/resources/signals/hart-aar/appearance-SL-2-digicon.xml" \
    "$PI_HOST:/home/pi/hart/cats/resources/signals/hart-aar/"
  ssh -o BatchMode=yes "$PI_HOST" 'for d in /home/pi/.jmri/*.jmri; do
    [ -d "$d" ] || continue
    mkdir -p "$d/resources/signals/hart-aar"
    cp -f /home/pi/JMRI_UserFiles/resources/signals/hart-aar/* "$d/resources/signals/hart-aar/"
  done'
  echo "Pi hart-aar updated"
  # Custom CTC track/turnout gifs + GUIObjects (preference:ctc/)
  if [[ -d "$ROOT/jmri/layouts/hart/ctc/icons" ]]; then
    ssh -o BatchMode=yes "$PI_HOST" 'mkdir -p /home/pi/JMRI_UserFiles/ctc/icons /home/pi/hart/ctc/icons'
    scp -o BatchMode=yes "$ROOT/jmri/layouts/hart/ctc/icons/"*.gif \
      "$PI_HOST:/home/pi/JMRI_UserFiles/ctc/icons/"
    scp -o BatchMode=yes "$ROOT/jmri/layouts/hart/ctc/icons/"*.gif \
      "$PI_HOST:/home/pi/hart/ctc/icons/"
    if [[ -f "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" ]]; then
      scp -o BatchMode=yes "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" \
        "$PI_HOST:/home/pi/JMRI_UserFiles/ctc/GUIObjects.xml"
      scp -o BatchMode=yes "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" \
        "$PI_HOST:/home/pi/hart/ctc/GUIObjects.xml"
    fi
    echo "Pi CTC icons + GUIObjects updated"
  fi
  echo "Pi deploy done."
fi

if [[ "$DO_WIN" -eq 1 ]]; then
  echo "Deploy → Windows ($WIN_HOST:$WIN_PORT)..."
  ssh_win 'mkdir hart\cats\panels hart\cats\resources\buttons hart\cats\resources\jmri-web\servlet\home hart\cats\scripts\windows hart\jmri\layouts\hart\scripts hart\jmri\layouts\hart\dispatcher\traininfo hart\jmri\scripts hart\ctc\icons 2>nul & mkdir %USERPROFILE%\JMRI_UserFiles\web\servlet\home 2>nul & echo dirs_ok'

  STAGE=$(mktemp -d)
  for p in HART_Master.xml HART_Master_ABS.xml HART_Master_ABS_hold.xml HART_Master_CTC_hold.xml; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" \
      --hart-root "C:/Users/lnevo/hart" --out "$STAGE/$p"
  done
  scp_win "$STAGE"/*.xml "${WIN_HOST}:hart/cats/panels/"
  rm -rf "$STAGE"

  if compgen -G "$ROOT/cats/resources/buttons/lamp_*.png" > /dev/null; then
    scp_win "$ROOT/cats/resources/buttons/"lamp_*.png \
      "${WIN_HOST}:hart/cats/resources/buttons/"
  fi
  scp_win "$ROOT/cats/resources/jmri-web/servlet/home/Home.html" \
    "${WIN_HOST}:hart/cats/resources/jmri-web/servlet/home/Home.html"
  scp_win "$ROOT/cats/resources/jmri-web/sts.html" \
    "${WIN_HOST}:hart/cats/resources/jmri-web/sts.html"

  scp_win \
    "$ROOT/jmri/layouts/hart/scripts/apply_maintain_mqtt.py" \
    "$ROOT/jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py" \
    "$ROOT/jmri/layouts/hart/scripts/add_yard_ladder_le_icons.py" \
    "$ROOT/jmri/layouts/hart/scripts/apply_mqtt_retain_at_startup.py" \
    "$ROOT/jmri/layouts/hart/scripts/discover_sml.py" \
    "$ROOT/jmri/layouts/hart/scripts/hart_dispatcher_startup.py" \
    "$ROOT/jmri/layouts/hart/scripts/patch_dispatcher_facing.py" \
    "$ROOT/jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py" \
    "${WIN_HOST}:hart/jmri/layouts/hart/scripts/"
  scp_win "$ROOT/jmri/layouts/hart/dispatcher/traininfo/"*.xml \
    "${WIN_HOST}:hart/jmri/layouts/hart/dispatcher/traininfo/"
  if [[ -f "$ROOT/jmri/layouts/hart/scripts/install_yl_windows.py" ]]; then
    scp_win "$ROOT/jmri/layouts/hart/scripts/install_yl_windows.py" \
      "${WIN_HOST}:hart/jmri/layouts/hart/scripts/"
  fi
  scp_win "$ROOT/jmri/scripts/mqtt_signalhead_publisher.py" \
    "${WIN_HOST}:hart/jmri/scripts/"

  for f in install_hart_tables.ps1 create_hart_master_desktop.ps1 \
           apply_hart_package_local.ps1 install_cats_masts.ps1 \
           launch_hart_master.bat launch_hart_master_abs.bat \
           launch_hart_master_abs_hold.bat launch_hart_master_ctc_hold.bat \
           launch_cats_desktop.bat; do
    [[ -f "$ROOT/cats/scripts/windows/$f" ]] && \
      scp_win "$ROOT/cats/scripts/windows/$f" "${WIN_HOST}:hart/cats/scripts/windows/$f"
  done

  if [[ -n "$TABLES" ]]; then
    # Full LE panel including Digicon signalmasticons (cats-virtual imagelinks required).
    scp_win "$TABLES" "${WIN_HOST}:hart/tables.xml"
  fi
  if [[ -d "$ROOT/jmri/layouts/hart/ctc/icons" ]]; then
    scp_win "$ROOT/jmri/layouts/hart/ctc/icons/"*.gif \
      "${WIN_HOST}:hart/ctc/icons/"
    if [[ -f "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" ]]; then
      scp_win "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" \
        "${WIN_HOST}:hart/ctc/GUIObjects.xml"
    fi
    echo "Windows hart/ctc icons staged"
  fi

  # Digicon SHSM appearances for Windows profiles
  ssh_win 'mkdir hart\cats\resources\signals\cats-masts hart\cats\resources\signals\hart-aar 2>nul & echo ok'
  scp_win \
    "$ROOT/cats/resources/signals/cats-masts/"appearance-cats-virtual*.xml \
    "$ROOT/cats/resources/signals/cats-masts/aspects.xml" \
    "$ROOT/cats/resources/signals/cats-masts/index.shtml" \
    "${WIN_HOST}:hart/cats/resources/signals/cats-masts/"
  scp_win \
    "$ROOT/cats/resources/signals/hart-aar/aspects.xml" \
    "$ROOT/cats/resources/signals/hart-aar/appearance-SL-2-digicon.xml" \
    "${WIN_HOST}:hart/cats/resources/signals/hart-aar/"

  scp_win "$ROOT/cats/scripts/windows/apply_hart_package_local.ps1" \
    "${WIN_HOST}:hart/cats/scripts/windows/apply_hart_package_local.ps1"
  ssh_win 'powershell -NoProfile -ExecutionPolicy Bypass -File hart\cats\scripts\windows\apply_hart_package_local.ps1'
  # Install cats-masts into Windows JMRI profiles (incl. dwarf)
  scp_win "$ROOT/cats/scripts/windows/install_cats_masts.ps1" \
    "${WIN_HOST}:hart/cats/scripts/windows/install_cats_masts.ps1"
  ssh_win 'powershell -NoProfile -ExecutionPolicy Bypass -File hart\cats\scripts\windows\install_cats_masts.ps1'
  # Keep JMRI-root tables.xml in sync if present (some launches use it)
  ssh_win 'if exist %USERPROFILE%\JMRI\tables.xml copy /Y %USERPROFILE%\hart\tables.xml %USERPROFILE%\JMRI\tables.xml'
  echo "Windows deploy done."
fi

echo "DONE"
