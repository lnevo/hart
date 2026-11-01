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
        echo "  Windows SSH: ${WIN_HOST} -p ${WIN_PORT} → %TEMP% drop + JMRI_UserFiles"
        echo "  Pi SSH:      ${PI_HOST} → /tmp drop + JMRI_UserFiles"
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
if [[ -f "$POLISH" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    python3 "$POLISH" --block-labels-only --sync-output --check
  else
    python3 "$POLISH" --block-labels-only --sync-output
  fi
fi
if [[ -f "$ROOT/jmri/layouts/hart/output/tables.xml" ]]; then
  TABLES="$ROOT/jmri/layouts/hart/output/tables.xml"
fi

PANEL_AUDIT="$ROOT/jmri/layouts/hart/scripts/audit_panel_contracts.py"
if [[ -n "$TABLES" && -f "$PANEL_AUDIT" ]]; then
  python3 "$PANEL_AUDIT" --strict
fi

SML_GATE="$ROOT/jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py"
if [[ -n "$TABLES" && -f "$SML_GATE" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    python3 "$SML_GATE" --dry-run --panel "$TABLES"
  else
    # Flip Digicon MQTT dests to Enabled=no in the file we ship.
    python3 "$SML_GATE" --panel "$TABLES"
  fi
fi

JYTHON_STARTUP_SCRIPTS=(
  "$ROOT/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$ROOT/jmri/layouts/hart/scripts/panel_status.py"
  "$ROOT/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$ROOT/jmri/scripts/signal_coordinator.py"
)

HART_JYTHON_SCRIPTS=(
  jmri/layouts/hart/scripts/panel_status.py
  jmri/layouts/hart/scripts/add_yard_ladder_le_icons.py
  jmri/layouts/hart/scripts/discover_sml.py
  jmri/layouts/hart/scripts/hide_cats_desk_windows.py
  jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py
  jmri/layouts/hart/scripts/jmri_cmd_watcher.py
)

LIVE_PANELS=(
  HART_CTC.xml
  HART_ABS.xml
)

install_jython_scripts() {
  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  local patch_startup="$ROOT/cats/scripts/patch_jmri_startup.py"
  _install_jython_into() {
    local profile="$1"
    local dest="$profile/jython"
    mkdir -p "$dest"
    local f
    for f in "${JYTHON_STARTUP_SCRIPTS[@]}"; do
      [[ -f "$f" ]] && cp -f "$f" "$dest/"
    done
    rm -f "$dest/hart_dispatcher_startup.py" "$dest/patch_dispatcher_facing.py"
    (cd "$dest" && rm -f sync_turnout_buttons.py sync_yard_ladder_buttons.py apply_dispatcher_roster_profiles.py SetBlockPreviewValues.py sync_layout_button.py mqtt_signalhead_publisher.py)
    echo "preference:jython scripts -> $dest"
    if [[ -d "$traininfo" ]] && compgen -G "$traininfo/*.xml" >/dev/null; then
      mkdir -p "$profile/dispatcher/traininfo"
      rsync -a --delete "$traininfo/" "$profile/dispatcher/traininfo/"
      echo "Dispatcher traininfo -> $profile/dispatcher/traininfo"
    fi
    local profxml="${HOME}/Library/Preferences/JMRI/My_JMRI_Railroad.jmri/profile/profile.xml"
    if [[ -f "$profxml" && -f "$patch_startup" ]]; then
      python3 "$patch_startup" retarget-jython \
        --profile "$profxml" \
        --script panel_status.py \
        --script signal_coordinator.py \
        --script jmri_cmd_watcher.py
      python3 "$patch_startup" remove \
        --profile "$profxml" \
        --script prepare_nx_sml_paths.py || true
      rm -f "$dest/prepare_nx_sml_paths.py"
      echo "Start Up retargeted -> preference:jython ($profxml)"
    fi
  }
  mkdir -p "${HOME}/JMRI_UserFiles"
  _install_jython_into "${HOME}/JMRI_UserFiles"
}

install_tables_local() {
  local src=""
  if [[ -f "$ROOT/jmri/layouts/hart/output/tables.xml" ]]; then
    src="$ROOT/jmri/layouts/hart/output/tables.xml"
  fi
  [[ -n "$src" ]] || return 0
  _copy_tables() {
    local dest="$1/tables.xml" stamp="$1/.tables_deployed.sha256"
    # A Store into this copy since the last deploy would be lost: stop instead.
    if [[ -f "$dest" && -f "$stamp" && "$(shasum -a 256 "$dest" | cut -d' ' -f1)" != "$(cat "$stamp")" ]] \
      && ! cmp -s "$src" "$dest" && [[ "${HART_OVERWRITE_PROFILE_TABLES:-0}" != "1" ]]; then
      echo "STOP: $dest changed since the last deploy. Run make tables-pull to bring the changes into the repo, or set HART_OVERWRITE_PROFILE_TABLES=1." >&2
      exit 1
    fi
    cp -f "$src" "$dest"
    shasum -a 256 "$dest" | cut -d' ' -f1 >"$stamp"
    echo "tables.xml -> $dest"
  }
  mkdir -p "${HOME}/JMRI_UserFiles"
  _copy_tables "${HOME}/JMRI_UserFiles"
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
    rm -f "$dest/linear5_panel_bg.jpg"
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
  mkdir -p "${HOME}/JMRI_UserFiles"
  _install_ctc_into "${HOME}/JMRI_UserFiles"
  _install_buttons_into "${HOME}/JMRI_UserFiles"
  _install_misc_into "${HOME}/JMRI_UserFiles"
  _install_uss_sensor_icons_into "${HOME}/JMRI_UserFiles"
}

# Build the package that lands in a temporary folder on the host. The apply scripts install it from there.
stage_package() {
  local stage="$1"
  local user_files="$2"
  rm -rf "$stage"
  mkdir -p \
    "$stage/cats/panels" \
    "$stage/cats/resources/buttons" \
    "$stage/cats/resources/icons/USS/sensor" \
    "$stage/cats/resources/misc" \
    "$stage/cats/scripts" \
    "$stage/ctc/icons" \
    "$stage/jmri/layouts/hart/scripts" \
    "$stage/jmri/layouts/hart/dispatcher" \
    "$stage/jmri/scripts"

  local p
  for p in "${LIVE_PANELS[@]}"; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" \
      --user-files "$user_files" --out "$stage/cats/panels/$p"
  done

  local f
  for f in "$ROOT/jmri/resources/buttons/"lamp_*.png \
           "$ROOT/jmri/resources/buttons/"triangle_*.png; do
    [[ -f "$f" ]] && cp -f "$f" "$stage/cats/resources/buttons/"
  done
  if [[ -d "$ROOT/jmri/resources/icons/USS/sensor" ]]; then
    cp -f "$ROOT/jmri/resources/icons/USS/sensor/"yellow-*.gif \
      "$stage/cats/resources/icons/USS/sensor/" 2>/dev/null || true
  fi

  cp -f "$ROOT/jmri/resources/misc/"* "$stage/cats/resources/misc/"

  rsync -a "$ROOT/jmri/resources/jmri-web/" "$stage/cats/resources/jmri-web/"
  rsync -a "$ROOT/cats/scripts/pi/" "$stage/cats/scripts/pi/"
  rsync -a "$ROOT/cats/scripts/windows/" "$stage/cats/scripts/windows/"
  cp -f "$ROOT/cats/scripts/install_jmri_web_override.sh" \
    "$ROOT/cats/scripts/rewrite_button_icon_paths.py" \
    "$ROOT/cats/scripts/patch_jmri_startup.py" \
    "$stage/cats/scripts/"

  for f in "${HART_JYTHON_SCRIPTS[@]}"; do
    [[ -f "$ROOT/$f" ]] && cp -f "$ROOT/$f" "$stage/$(dirname "$f")/"
  done
  cp -f "$ROOT/jmri/scripts/signal_coordinator.py" "$stage/jmri/scripts/"

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
    echo "dry-run: would scp $(du -h "$tgz" | awk '{print $1}') package → ${WIN_HOST}:%TEMP%"
    rm -f "$tgz"
    return 0
  fi
  # Windows OpenSSH is cmd.exe; extract with PowerShell so it is not shell-specific.
  WIN_DROP="$(ssh_win "powershell -NoProfile -Command \"\$d = Join-Path \$env:TEMP ('hart-deploy-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory \$d | Out-Null; \$d\"" | tr -d '\r' | tail -1)"
  [[ -n "$WIN_DROP" ]] || { echo "Could not create a Windows temp folder" >&2; rm -f "$tgz"; exit 1; }
  scp_win "$tgz" "${WIN_HOST}:${WIN_DROP//\\//}/_pkg.tgz"
  ssh_win "powershell -NoProfile -Command \"Set-Location '${WIN_DROP}'; tar -xzf _pkg.tgz; Remove-Item _pkg.tgz -Force\""
  rm -f "$tgz"
}

if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  bash "$ROOT/cats/scripts/install_jmri_web_override.sh"
  install_tables_local
  install_cats_panels_local
  install_ctc_icons_local
  install_jython_scripts
fi

if [[ "$DO_PI" -eq 1 ]]; then
  echo "Deploy → Pi ($PI_HOST) via rsync..."
  STAGE=$(mktemp -d)
  trap 'rm -rf "$STAGE"' EXIT
  stage_package "$STAGE" "$PI_USERFILES"
  PI_DROP="/tmp/hart-deploy.dry-run"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    PI_DROP="$(ssh_pi "mktemp -d /tmp/hart-deploy.XXXXXX")"
  fi
  push_rsync "$STAGE" "${PI_HOST}:${PI_DROP}/"
  rm -rf "$STAGE"
  trap - EXIT
  if [[ "$DRY_RUN" -eq 0 ]]; then
    ssh_pi "HART=${PI_DROP} bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh"
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
    rc=0
    ssh_win "powershell -NoProfile -ExecutionPolicy Bypass -File \"${WIN_DROP}\\cats\\scripts\\windows\\apply_hart_package_local.ps1\" -Hart \"${WIN_DROP}\"" || rc=$?
    ssh_win "powershell -NoProfile -Command \"Remove-Item -LiteralPath '${WIN_DROP}' -Recurse -Force\""
    [[ "$rc" -eq 0 ]] || exit "$rc"
  fi
  echo "Windows deploy done."
fi

echo "DONE"
