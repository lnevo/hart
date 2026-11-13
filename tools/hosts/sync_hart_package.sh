#!/usr/bin/env bash
# Deploy HART Digicon/JMRI package from this working tree over SSH.
#
# One staged tree per host, then:
#   Pi:      rsync (delta)  + apply_hart_package_local.sh
#   Windows: one tarball     + apply_hart_package_local.ps1
#
# Hosts are not git clones. Panels are path-rewritten per user-files, and the
# payload is a subset (no wiki, screenshots, linear layouts, or CATS src).
# The repo keeps the host scripts in tools/hosts/pi and tools/hosts/windows; the package
# still carries them at cats/scripts/pi and cats/scripts/windows, as the hosts expect.
# cats/scripts/sync_hart_package.sh is a wrapper that runs this file.
#
# Usage: ./tools/hosts/sync_hart_package.sh [--pi] [--win] [--all] [--dry-run] [--stage-only DIR]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Hosts: environment first, then tools/env/hart.env, then the defaults in load_env.sh
# (the same order the Python tools use through tools/hartlib/src/hartlib/hosts.py).
source "$ROOT/tools/env/load_env.sh"
WIN_HOST="$HART_WIN_SSH"
WIN_PORT="$HART_WIN_SSH_PORT"
PI_HOST="$HART_PI_SSH"
PI_USERFILES="$HART_PI_USERFILES"
WIN_USERFILES="$HART_WIN_USERFILES"
REWRITE="$ROOT/cats/scripts/rewrite_button_icon_paths.py"
DRY_RUN=0
# The repo is the master of the Operations Pro files (ADR-015). 0 restores the guards.
HART_OVERWRITE_OPS="${HART_OVERWRITE_OPS:-1}"
export HART_OVERWRITE_OPS

DO_PI=0
DO_WIN=0
DO_MAC_WEB=1
STAGE_ONLY=""
if [[ $# -gt 0 ]]; then
  DO_MAC_WEB=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pi) DO_PI=1; DO_MAC_WEB=1 ;;
      --win) DO_WIN=1; DO_MAC_WEB=1 ;;
      --all) DO_PI=1; DO_WIN=1; DO_MAC_WEB=1 ;;
      --mac-web-only) DO_MAC_WEB=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --stage-only)
        [[ $# -ge 2 && -n "$2" ]] || { echo "--stage-only needs a folder" >&2; exit 1; }
        STAGE_ONLY="$2"; shift ;;
      --stage-only=*)
        STAGE_ONLY="${1#*=}"
        [[ -n "$STAGE_ONLY" ]] || { echo "--stage-only needs a folder" >&2; exit 1; } ;;
      -h|--help)
        echo "Usage: $0 [--pi] [--win] [--all] [--dry-run] [--stage-only DIR]"
        echo "  Windows SSH: ${WIN_HOST} -p ${WIN_PORT} → %TEMP% drop + JMRI_UserFiles"
        echo "  Pi SSH:      ${PI_HOST} → /tmp drop + JMRI_UserFiles"
        echo "  Transfer:    rsync (Pi) / tar+scp (Windows). Not git pull."
        echo "  --stage-only DIR: build the host packages into DIR/pi and DIR/win and stop."
        echo "                    No ssh, no Mac install, and the repo's tables.xml is only checked."
        echo "  What a host last got: tools/hosts/deploy_status.sh [--pi] [--win] [--mac]"
        exit 0
        ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
  done
fi
if [[ -n "$STAGE_ONLY" ]]; then
  if [[ -e "$STAGE_ONLY" && -n "$(ls -A "$STAGE_ONLY" 2>/dev/null)" ]]; then
    echo "--stage-only: $STAGE_ONLY is not empty" >&2
    exit 1
  fi
  # Nothing leaves this machine and nothing outside DIR is written.
  [[ "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ]] || { DO_PI=1; DO_WIN=1; }
  DO_MAC_WEB=0
  DRY_RUN=1
fi

# What is being shipped: recorded in cats/deploy_stamp.txt on every host this run installs
# (tools/hosts/deploy_status.sh reads it back). Taken before the gates below touch tables.xml.
DEPLOY_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
DEPLOY_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
DEPLOY_CHANGES="$(git -C "$ROOT" status --porcelain 2>/dev/null || true)"
DEPLOY_DIRTY=no
DEPLOY_DIRTY_PATHS=0
if [[ -n "$DEPLOY_CHANGES" ]]; then
  DEPLOY_DIRTY=yes
  DEPLOY_DIRTY_PATHS="$(printf '%s\n' "$DEPLOY_CHANGES" | wc -l | tr -d ' ')"
  {
    echo "WARNING: this checkout has $DEPLOY_DIRTY_PATHS uncommitted or untracked path(s)."
    echo "  The hosts get files that are not in commit ${DEPLOY_COMMIT:0:12} ($DEPLOY_BRANCH); the stamp says dirty=yes."
    printf '%s\n' "$DEPLOY_CHANGES" | head -10 | sed 's/^/    /'
    [[ "$DEPLOY_DIRTY_PATHS" -le 10 ]] || echo "    ..."
  } >&2
fi
DEPLOY_DATE="$(date +%Y-%m-%dT%H:%M:%S%z)"
DEPLOY_FROM="$(hostname -s 2>/dev/null || hostname)"

# write_deploy_stamp FILE TARGET: key=value lines, one per fact.
write_deploy_stamp() {
  mkdir -p "$(dirname "$1")"
  cat >"$1" <<STAMP
# Layout deploy stamp, written by tools/hosts/sync_hart_package.sh. Read it with tools/hosts/deploy_status.sh.
commit=$DEPLOY_COMMIT
branch=$DEPLOY_BRANCH
dirty=$DEPLOY_DIRTY
dirty_paths=$DEPLOY_DIRTY_PATHS
tables_sha256=$DEPLOY_TABLES_SHA
tables_modified_by_deploy=$DEPLOY_TABLES_MODIFIED
date=$DEPLOY_DATE
deployed_from=$DEPLOY_FROM
target=$2
STAMP
}

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }
ssh_win() { ssh "${SSH_OPTS[@]}" -p "$WIN_PORT" "$WIN_HOST" "$@"; }
# SFTP needs "Subsystem sftp" in the Windows sshd_config (OpenSSH 10.4); fall back to
# the legacy scp protocol if a reinstall or reset has removed it.
scp_win() {
  scp "${SSH_OPTS[@]}" -P "$WIN_PORT" "$@" 2>/dev/null && return 0
  echo "scp over SFTP to Windows failed; retrying with the legacy protocol (-O). Check Subsystem sftp in sshd_config." >&2
  scp -O "${SSH_OPTS[@]}" -P "$WIN_PORT" "$@"
}

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

# The gates above may rewrite tables.xml, so the stamp also names the tables actually
# shipped and whether they differ from the committed file.
DEPLOY_TABLES_SHA=none
DEPLOY_TABLES_MODIFIED=no
if [[ -n "$TABLES" ]]; then
  DEPLOY_TABLES_SHA="$(shasum -a 256 "$TABLES" | cut -d' ' -f1)"
  committed_sha="$(git -C "$ROOT" show "HEAD:jmri/layouts/hart/output/tables.xml" 2>/dev/null | shasum -a 256 | cut -d' ' -f1)"
  if [[ "$DEPLOY_TABLES_SHA" != "$committed_sha" ]]; then
    DEPLOY_TABLES_MODIFIED=yes
    echo "WARNING: the tables.xml being shipped differs from commit ${DEPLOY_COMMIT:0:12} (uncommitted, or rewritten by the gates above). Commit it after the deploy; the stamp says tables_modified_by_deploy=yes." >&2
  fi
fi

JYTHON_STARTUP_SCRIPTS=(
  "$ROOT/jmri/layouts/hart/scripts/hide_cats_desk_windows.py"
  "$ROOT/jmri/layouts/hart/scripts/panel_status.py"
  "$ROOT/jmri/layouts/hart/scripts/jmri_cmd_watcher.py"
  "$ROOT/jmri/layouts/hart/scripts/sts_car_sync.py"
  "$ROOT/jmri/scripts/signal_coordinator.py"
)

HART_JYTHON_SCRIPTS=(
  jmri/layouts/hart/scripts/panel_status.py
  jmri/layouts/hart/scripts/add_yard_ladder_le_icons.py
  jmri/layouts/hart/scripts/discover_sml.py
  jmri/layouts/hart/scripts/hide_cats_desk_windows.py
  jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py
  jmri/layouts/hart/scripts/jmri_cmd_watcher.py
  jmri/layouts/hart/scripts/sts_car_sync.py
  jmri/layouts/hart/scripts/mimic_relay.py
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
      # STS sends car positions here (sts-plugins jmri_ops).
      python3 "$patch_startup" insert \
        --profile "$profxml" \
        --script preference:jython/sts_car_sync.py \
        --after panel_status.py
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

install_ops_local() {
  bash "$ROOT/cats/scripts/install_ops_files.sh" \
    "$ROOT/jmri/layouts/hart/operations" "${HOME}/JMRI_UserFiles/operations"
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
  _install_ctc_into "${HOME}/JMRI_UserFiles"
  _install_buttons_into "${HOME}/JMRI_UserFiles"
  _install_misc_into "${HOME}/JMRI_UserFiles"
  _install_uss_sensor_icons_into "${HOME}/JMRI_UserFiles"
  _install_roster_images_into "${HOME}/JMRI_UserFiles"
}

# Build the package that lands in a temporary folder on the host. The apply scripts install it from there.
stage_package() {
  local stage="$1"
  local user_files="$2"
  local target="$3"
  rm -rf "$stage"
  mkdir -p \
    "$stage/cats/panels" \
    "$stage/cats/resources/buttons" \
    "$stage/cats/resources/icons/USS/sensor" \
    "$stage/cats/resources/misc" \
    "$stage/cats/resources/roster" \
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
  if [[ -d "$ROOT/jmri/resources/roster" ]]; then
    cp -f "$ROOT/jmri/resources/roster/"*.jpg "$stage/cats/resources/roster/" 2>/dev/null || true
  fi

  cp -f "$ROOT/jmri/resources/misc/"* "$stage/cats/resources/misc/"

  rsync -a "$ROOT/jmri/resources/jmri-web/" "$stage/cats/resources/jmri-web/"
  python3 "$ROOT/tools/mqtt-mimic/build_mimic_web.py" --out "$stage/cats/resources/jmri-web/mimic"
  # Host scripts live in tools/hosts/ but land where the hosts and their shortcuts expect them (ADR-007).
  rsync -a "$ROOT/tools/hosts/pi/" "$stage/cats/scripts/pi/"
  rsync -a "$ROOT/tools/hosts/windows/" "$stage/cats/scripts/windows/"
  cp -f "$ROOT/cats/scripts/install_jmri_web_override.sh" \
    "$ROOT/cats/scripts/rewrite_button_icon_paths.py" \
    "$ROOT/cats/scripts/patch_jmri_startup.py" \
    "$ROOT/cats/scripts/install_ops_files.sh" \
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
  mkdir -p "$stage/operations"
  cp -f "$ROOT/jmri/layouts/hart/operations/"*.xml "$stage/operations/"
  chmod +x "$stage/cats/scripts/pi/"*.sh "$stage/cats/scripts/"*.sh 2>/dev/null || true
  # The host apply scripts install this last, so it only changes once a deploy has finished.
  write_deploy_stamp "$stage/cats/deploy_stamp.txt" "$target"
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

if [[ -n "$STAGE_ONLY" ]]; then
  mkdir -p "$STAGE_ONLY"
  if [[ "$DO_PI" -eq 1 ]]; then
    stage_package "$STAGE_ONLY/pi" "$PI_USERFILES" pi
    echo "Pi package -> $STAGE_ONLY/pi"
  fi
  if [[ "$DO_WIN" -eq 1 ]]; then
    stage_package "$STAGE_ONLY/win" "$WIN_USERFILES" win
    echo "Windows package -> $STAGE_ONLY/win"
  fi
  echo "DONE (stage only)"
  exit 0
fi

if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  # Mac JMRI is for development: the links follow the page's host to the Mac's own STS and
  # mimic server (PORT as in tools/mqtt-mimic/install_mimic_launchagent.sh).
  HART_MIMIC_PORT="${MIMIC_PORT:-8765}" bash "$ROOT/cats/scripts/install_jmri_web_override.sh"
  install_tables_local
  install_ops_local
  install_cats_panels_local
  install_ctc_icons_local
  install_jython_scripts
  write_deploy_stamp "${HOME}/JMRI_UserFiles/cats/deploy_stamp.txt" mac
  echo "deploy stamp -> ${HOME}/JMRI_UserFiles/cats/deploy_stamp.txt"
fi

if [[ "$DO_PI" -eq 1 ]]; then
  echo "Deploy → Pi ($PI_HOST) via rsync..."
  STAGE=$(mktemp -d)
  trap 'rm -rf "$STAGE"' EXIT
  stage_package "$STAGE" "$PI_USERFILES" pi
  PI_DROP="/tmp/hart-deploy.dry-run"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    PI_DROP="$(ssh_pi "mktemp -d /tmp/hart-deploy.XXXXXX")"
  fi
  push_rsync "$STAGE" "${PI_HOST}:${PI_DROP}/"
  rm -rf "$STAGE"
  trap - EXIT
  if [[ "$DRY_RUN" -eq 0 ]]; then
    # JMRI_USERFILES: the apply installs where the panel paths and the stamp say (HART_PI_USERFILES).
    ssh_pi "HART=${PI_DROP} JMRI_USERFILES='${PI_USERFILES}' HART_OVERWRITE_OPS=${HART_OVERWRITE_OPS} bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh"
  fi
  echo "Pi deploy done."
fi

if [[ "$DO_WIN" -eq 1 ]]; then
  echo "Deploy → Windows ($WIN_HOST:$WIN_PORT) via tar..."
  STAGE=$(mktemp -d)
  trap 'rm -rf "$STAGE"' EXIT
  stage_package "$STAGE" "$WIN_USERFILES" win
  push_tar_scp "$STAGE"
  rm -rf "$STAGE"
  trap - EXIT
  if [[ "$DRY_RUN" -eq 0 ]]; then
    rc=0
    ssh_win "powershell -NoProfile -ExecutionPolicy Bypass -File \"${WIN_DROP}\\cats\\scripts\\windows\\apply_hart_package_local.ps1\" -Hart \"${WIN_DROP}\" -OverwriteOps ${HART_OVERWRITE_OPS} -UserFiles \"${WIN_USERFILES}\"" || rc=$?
    ssh_win "powershell -NoProfile -Command \"Remove-Item -LiteralPath '${WIN_DROP}' -Recurse -Force\""
    [[ "$rc" -eq 0 ]] || exit "$rc"
  fi
  echo "Windows deploy done."
fi

echo "DONE"
