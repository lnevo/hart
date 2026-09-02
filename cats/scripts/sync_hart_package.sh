#!/usr/bin/env bash
# Deploy HART Digicon/JMRI package from this working tree over SSH.
#
# One staged tree per host, then:
#   Pi:      rsync (delta)  + apply_hart_package_local.sh
#   Windows: one tarball     + apply_hart_package_local.ps1
#
# Hosts are not git clones. Panels are path-rewritten per user-files, and the
# payload is a subset (no wiki, screenshots, linear layouts, or CATS src).
#
# Usage: ./cats/scripts/sync_hart_package.sh [--pi] [--win] [--all] [--dry-run]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WIN_HOST="${HART_WIN_SSH:-lnevo@10.0.0.6}"
WIN_PORT="${HART_WIN_SSH_PORT:-2222}"
PI_HOST="${HART_PI_SSH:-pi}"
PI_HART="${HART_PI_HART:-/home/pi/hart}"
WIN_HART_REL="${HART_WIN_HART:-hart}"
PI_USERFILES="${HART_PI_USERFILES:-/home/pi/JMRI_UserFiles}"
WIN_USERFILES="${HART_WIN_USERFILES:-C:/Users/lnevo/JMRI_UserFiles}"
REWRITE="$ROOT/cats/scripts/rewrite_button_icon_paths.py"
DRY_RUN=0

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
      --dry-run) DRY_RUN=1 ;;
      -h|--help)
        echo "Usage: $0 [--pi] [--win] [--all] [--dry-run]"
        echo "  Windows SSH: ${WIN_HOST} -p ${WIN_PORT} → %USERPROFILE%/${WIN_HART_REL}"
        echo "  Pi SSH:      ${PI_HOST} → ${PI_HART} + JMRI_UserFiles"
        echo "  Transfer:    rsync (Pi) / tar+scp (Windows). Not git pull."
        exit 0
        ;;
      *) echo "Unknown option: $a" >&2; exit 1 ;;
    esac
  done
fi

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }
ssh_win() { ssh "${SSH_OPTS[@]}" -p "$WIN_PORT" "$WIN_HOST" "$@"; }
scp_win() { scp -O "${SSH_OPTS[@]}" -P "$WIN_PORT" "$@"; }

TABLES=""
POLISH="$ROOT/jmri/layouts/hart/scripts/polish_hart_layout_editor.py"
if [[ -f "$POLISH" && -f "$ROOT/tables/new_tables.xml" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    python3 "$POLISH" --block-labels-only --sync-output --check
  else
    python3 "$POLISH" --block-labels-only --sync-output
  fi
fi
if [[ -f "$ROOT/jmri/layouts/hart/output/tables.xml" ]]; then
  TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
elif [[ -f "$ROOT/tables/new_tables.xml" ]]; then
  TABLES="$ROOT/tables/new_tables.xml"
fi

PANEL_AUDIT="$ROOT/jmri/layouts/hart/scripts/audit_panel_contracts.py"
if [[ -n "$TABLES" && -f "$PANEL_AUDIT" ]]; then
  python3 "$PANEL_AUDIT" --strict
fi

SML_GATE="$ROOT/cats/scripts/disable_digicon_sml_in_tables.py"
if [[ -n "$TABLES" && -f "$SML_GATE" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    python3 "$SML_GATE" --dry-run --panel "$TABLES"
  else
    # Flip Digicon MQTT dests to Enabled=no in the file we ship; do not copy over the other tables file.
    python3 "$SML_GATE" --panel "$TABLES" --no-sync
  fi
fi

JYTHON_STARTUP_SCRIPTS=(
  "$ROOT/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$ROOT/jmri/layouts/hart/scripts/sync_layout_button.py"
  "$ROOT/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$ROOT/jmri/scripts/mqtt_signalhead_publisher.py"
)

HART_JYTHON_SCRIPTS=(
  jmri/layouts/hart/scripts/sync_layout_button.py
  jmri/layouts/hart/scripts/add_yard_ladder_le_icons.py
  jmri/layouts/hart/scripts/discover_sml.py
  jmri/layouts/hart/scripts/hide_cats_desk_windows.py
  jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py
  jmri/layouts/hart/scripts/jmri_cmd_watcher.py
)

LIVE_PANELS=(
  HART_Master.xml
  HART_Master_ABS.xml
  HART_Master_ABS_hold.xml
  HART_Master_CTC_hold.xml
)

install_dispatcher_facing_patch() {
  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  local patch_startup="$ROOT/cats/scripts/patch_jmri_startup.py"
  _install_facing_into() {
    local profile="$1"
    local dest="$profile/jython"
    mkdir -p "$dest"
    local f
    for f in "${JYTHON_STARTUP_SCRIPTS[@]}"; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
    done
    rm -f "$dest/hart_dispatcher_startup.py" "$dest/patch_dispatcher_facing.py"
    echo "preference:jython scripts -> $dest"
    if [[ -d "$traininfo" ]] && compgen -G "$traininfo/*.xml" >/dev/null; then
      mkdir -p "$profile/dispatcher/traininfo"
      rsync -a --delete "$traininfo/" "$profile/dispatcher/traininfo/"
      echo "Dispatcher traininfo -> $profile/dispatcher/traininfo"
    fi
    local profxml="$profile/profile/profile.xml"
    if [[ -f "$profxml" && -f "$patch_startup" ]]; then
      python3 "$patch_startup" retarget-jython \
        --profile "$profxml" \
        --script sync_layout_button.py \
        --script mqtt_signalhead_publisher.py \
        --script jmri_cmd_watcher.py
      python3 "$patch_startup" remove \
        --profile "$profxml" \
        --script prepare_nx_sml_paths.py || true
      rm -f "$dest/prepare_nx_sml_paths.py"
      echo "Start Up retargeted -> preference:jython ($profxml)"
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

install_tables_local() {
  local src=""
  if [[ -f "$ROOT/jmri/layouts/hart/output/tables.xml" ]]; then
    src="$ROOT/jmri/layouts/hart/output/tables.xml"
  elif [[ -f "$ROOT/tables/new_tables.xml" ]]; then
    src="$ROOT/tables/new_tables.xml"
  fi
  [[ -n "$src" ]] || return 0
  _copy_tables() {
    cp -f "$src" "$1/tables.xml"
    echo "tables.xml -> $1/tables.xml"
  }
  if [[ -d "${HOME}/Library/Preferences/JMRI" ]]; then
    for d in "${HOME}/Library/Preferences/JMRI"/*.jmri; do
      [[ -d "$d" ]] && _copy_tables "$d"
    done
  fi
  if [[ -d "${HOME}/.jmri" ]]; then
    for d in "${HOME}/.jmri"/*.jmri; do
      [[ -d "$d" ]] && _copy_tables "$d"
    done
  fi
  if [[ -d "${HOME}/JMRI_UserFiles" ]]; then
    _copy_tables "${HOME}/JMRI_UserFiles"
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
  _install_buttons_into() {
    local dest="$1/resources/buttons"
    mkdir -p "$dest"
    local f
    for f in "$ROOT/cats/resources/buttons/"triangle_*.png; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
    done
    echo "button icons -> $dest"
  }
  _install_uss_sensor_icons_into() {
    local dest="$1/resources/icons/USS/sensor"
    local src="$ROOT/cats/resources/icons/USS/sensor"
    [[ -d "$src" ]] || return 0
    mkdir -p "$dest"
    local f
    for f in "$src/"yellow-*.gif; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
    done
    echo "USS sensor icons -> $dest"
  }
  if [[ -d "${HOME}/Library/Preferences/JMRI" ]]; then
    for d in "${HOME}/Library/Preferences/JMRI"/*.jmri; do
      [[ -d "$d" ]] && _install_ctc_into "$d" && _install_hart_aar_into "$d" && _install_buttons_into "$d" && _install_uss_sensor_icons_into "$d"
    done
  fi
  if [[ -d "${HOME}/.jmri" ]]; then
    for d in "${HOME}/.jmri"/*.jmri; do
      [[ -d "$d" ]] && _install_ctc_into "$d" && _install_hart_aar_into "$d" && _install_buttons_into "$d" && _install_uss_sensor_icons_into "$d"
    done
  fi
  if [[ -d "${HOME}/JMRI_UserFiles" ]]; then
    _install_ctc_into "${HOME}/JMRI_UserFiles"
    _install_hart_aar_into "${HOME}/JMRI_UserFiles"
    _install_buttons_into "${HOME}/JMRI_UserFiles"
    _install_uss_sensor_icons_into "${HOME}/JMRI_UserFiles"
  fi
}

# Build the on-disk package that lands in ~/hart on the host.
stage_package() {
  local stage="$1"
  local user_files="$2"
  rm -rf "$stage"
  mkdir -p \
    "$stage/cats/panels" \
    "$stage/cats/resources/buttons" \
    "$stage/cats/resources/icons/USS/sensor" \
    "$stage/cats/scripts" \
    "$stage/ctc/icons" \
    "$stage/jmri/layouts/hart/scripts" \
    "$stage/jmri/layouts/hart/dispatcher" \
    "$stage/jmri/scripts" \
    "$stage/tools/jmri/patches"

  local guard="$ROOT/tools/jmri/patches/hart-startup-guard.jar"
  if [[ -f "$guard" ]]; then
    cp -f "$guard" "$stage/tools/jmri/patches/"
  fi

  local p
  for p in "${LIVE_PANELS[@]}"; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" \
      --user-files "$user_files" --out "$stage/cats/panels/$p"
  done

  local f
  for f in "$ROOT/cats/resources/buttons/"lamp_*.png \
           "$ROOT/cats/resources/buttons/"triangle_*.png; do
    [[ -f "$f" ]] && cp -f "$f" "$stage/cats/resources/buttons/"
  done
  if [[ -d "$ROOT/cats/resources/icons/USS/sensor" ]]; then
    cp -f "$ROOT/cats/resources/icons/USS/sensor/"yellow-*.gif \
      "$stage/cats/resources/icons/USS/sensor/" 2>/dev/null || true
  fi

  rsync -a "$ROOT/cats/resources/jmri-web/" "$stage/cats/resources/jmri-web/"
  rsync -a "$ROOT/cats/resources/signals/cats-masts/" "$stage/cats/resources/signals/cats-masts/"
  rsync -a "$ROOT/cats/resources/signals/hart-aar/" "$stage/cats/resources/signals/hart-aar/"
  rsync -a "$ROOT/cats/scripts/pi/" "$stage/cats/scripts/pi/"
  rsync -a "$ROOT/cats/scripts/windows/" "$stage/cats/scripts/windows/"
  cp -f "$ROOT/cats/scripts/install_jmri_web_override.sh" \
    "$ROOT/cats/scripts/rewrite_button_icon_paths.py" \
    "$ROOT/cats/scripts/patch_jmri_startup.py" \
    "$stage/cats/scripts/"
  mkdir -p "$stage/cats/docs"
  cp -f "$ROOT/cats/docs/DISPATCHER_GUIDE_CTC.md" "$stage/cats/docs/"

  for f in "${HART_JYTHON_SCRIPTS[@]}"; do
    [[ -f "$ROOT/$f" ]] && cp -f "$ROOT/$f" "$stage/$(dirname "$f")/"
  done
  if [[ -f "$ROOT/jmri/layouts/hart/scripts/install_yl_windows.py" ]]; then
    cp -f "$ROOT/jmri/layouts/hart/scripts/install_yl_windows.py" \
      "$stage/jmri/layouts/hart/scripts/"
  fi
  cp -f "$ROOT/jmri/scripts/mqtt_signalhead_publisher.py" "$stage/jmri/scripts/"

  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  if [[ -d "$traininfo" ]]; then
    rsync -a "$traininfo/" "$stage/jmri/layouts/hart/dispatcher/traininfo/"
  fi
  if [[ -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" ]]; then
    cp -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" \
      "$stage/jmri/layouts/hart/dispatcher/"
  fi

  if [[ -d "$ROOT/jmri/layouts/hart/ctc/icons" ]]; then
    rsync -a "$ROOT/jmri/layouts/hart/ctc/icons/" "$stage/ctc/icons/"
    [[ -f "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" ]] && \
      cp -f "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" "$stage/ctc/"
  fi
  if [[ -n "$TABLES" ]]; then
    cp -f "$TABLES" "$stage/tables.xml"
  fi
  chmod +x "$stage/cats/scripts/pi/"*.sh "$stage/cats/scripts/"*.sh 2>/dev/null || true
}

push_rsync() {
  local stage="$1"
  local dest="$2" # user@host:/path/
  local flags=(-az --exclude '.DS_Store' --exclude '._*')
  if [[ "$DRY_RUN" -eq 1 ]]; then
    flags+=(-n --stats)
  fi
  rsync "${flags[@]}" -e "ssh ${SSH_OPTS[*]}" "$stage/" "$dest"
}

push_tar_scp() {
  local stage="$1"
  local tgz
  tgz="$(mktemp /tmp/hart-pkg.XXXXXX.tgz)"
  COPYFILE_DISABLE=1 tar -C "$stage" -czf "$tgz" .
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry-run: would scp $(du -h "$tgz" | awk '{print $1}') package → ${WIN_HOST}:${WIN_HART_REL}/"
    rm -f "$tgz"
    return 0
  fi
  # Windows OpenSSH is cmd.exe; extract with PowerShell so it is not shell-specific.
  ssh_win "if not exist ${WIN_HART_REL} mkdir ${WIN_HART_REL}"
  scp_win "$tgz" "${WIN_HOST}:${WIN_HART_REL}/_pkg.tgz"
  ssh_win "powershell -NoProfile -Command \"Set-Location '${WIN_HART_REL}'; tar -xzf _pkg.tgz; Remove-Item _pkg.tgz -Force\""
  rm -f "$tgz"
}

if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  bash "$ROOT/cats/scripts/install_jmri_web_override.sh"
  install_tables_local
  install_ctc_icons_local
  install_dispatcher_facing_patch
fi

if [[ "$DO_PI" -eq 1 ]]; then
  echo "Deploy → Pi ($PI_HOST) via rsync..."
  STAGE=$(mktemp -d)
  trap 'rm -rf "$STAGE"' EXIT
  stage_package "$STAGE" "$PI_USERFILES"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    ssh_pi "mkdir -p ${PI_HART}"
  fi
  push_rsync "$STAGE" "${PI_HOST}:${PI_HART}/"
  rm -rf "$STAGE"
  trap - EXIT
  if [[ "$DRY_RUN" -eq 0 ]]; then
    ssh_pi "bash ${PI_HART}/cats/scripts/pi/apply_hart_package_local.sh"
  fi
  echo "Pi deploy done."
fi

if [[ "$DO_WIN" -eq 1 ]]; then
  echo "Deploy → Windows ($WIN_HOST:$WIN_PORT) via tar..."
  STAGE=$(mktemp -d)
  trap 'rm -rf "$STAGE"' EXIT
  stage_package "$STAGE" "$WIN_USERFILES"
  push_tar_scp "$STAGE"
  rm -rf "$STAGE"
  trap - EXIT
  if [[ "$DRY_RUN" -eq 0 ]]; then
    ssh_win 'powershell -NoProfile -ExecutionPolicy Bypass -File hart\cats\scripts\windows\apply_hart_package_local.ps1'
    ssh_win 'if exist %USERPROFILE%\JMRI\tables.xml copy /Y %USERPROFILE%\hart\tables.xml %USERPROFILE%\JMRI\tables.xml'
  fi
  echo "Windows deploy done."
fi

echo "DONE"
