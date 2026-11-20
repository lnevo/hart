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
source "$ROOT/tools/hosts/profile_tables_guard.sh"
refuse_hart_tables "deploy"
refuse_unrestored_profile "deploy"
# Hosts: environment first, then tools/env/hart.env, then tools/env/defaults.env (via load_env.sh)
# (the same order the Python tools use through tools/hartlib/src/hartlib/hosts.py).
source "$ROOT/tools/env/load_env.sh"
WIN_HOST="$HART_WIN_SSH"
WIN_PORT="$HART_WIN_SSH_PORT"
PI_HOST="$HART_PI_SSH"
PI_USERFILES="$HART_PI_USERFILES"
WIN_USERFILES="$HART_WIN_USERFILES"
REWRITE="$ROOT/cats/scripts/rewrite_button_icon_paths.py"
# Features parked out of the active tables (hartlib.parked.PARKED: Entry/Exit, the Dispatcher System, the USS CTC
# machine). Their files outside tables.xml stay in the repo but are not shipped: the Dispatcher traininfo and options
# (jmri/layouts/hart/dispatcher) and the USS CTC icons and GUIObjects.xml (jmri/layouts/hart/ctc), and the jython that
# only serves them. Nothing here or in the host apply scripts removes copies already installed on a host: they stay
# until removed by hand (owner, 2026-11-17). Unparking a feature ships them again.
PARKED_DIRS="$(PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.parked dirs)" \
  || { echo "cannot read the parked features (tools/hartlib/src/hartlib/parked.py)" >&2; exit 1; }
PARKED_JYTHON="$(PYTHONPATH="$ROOT/tools/hartlib/src" python3 -m hartlib.parked jython)" \
  || { echo "cannot read the parked features (tools/hartlib/src/hartlib/parked.py)" >&2; exit 1; }
# parked_dir REL: whether the repo folder REL (jmri/layouts/hart/dispatcher, jmri/layouts/hart/ctc) is parked
parked_dir() { grep -qxF "$1" <<<"$PARKED_DIRS"; }
DRY_RUN=0
# The repo is the master of the Operations Pro files (ADR-015). 0 restores the guards.
HART_OVERWRITE_OPS="${HART_OVERWRITE_OPS:-1}"
export HART_OVERWRITE_OPS

DO_PI=0
DO_WIN=0
DO_MAC_WEB=1
STAGE_ONLY=""
CHECK_ONLY=0
if [[ $# -gt 0 ]]; then
  DO_MAC_WEB=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pi) DO_PI=1; DO_MAC_WEB=1 ;;
      --win) DO_WIN=1; DO_MAC_WEB=1 ;;
      --all) DO_PI=1; DO_WIN=1; DO_MAC_WEB=1 ;;
      --mac-web-only) DO_MAC_WEB=1 ;;
      # The checks alone, for the hosts named (redeploy_commit.sh runs them before an older commit's deploy).
      --check-only) CHECK_ONLY=1 ;;
      --check-pi-only) CHECK_ONLY=1; DO_PI=1 ;;  # --check-only --pi
      --dry-run) DRY_RUN=1 ;;
      --stage-only)
        [[ $# -ge 2 && -n "$2" ]] || { echo "--stage-only needs a folder" >&2; exit 1; }
        STAGE_ONLY="$2"; shift ;;
      --stage-only=*)
        STAGE_ONLY="${1#*=}"
        [[ -n "$STAGE_ONLY" ]] || { echo "--stage-only needs a folder" >&2; exit 1; } ;;
      -h|--help)
        echo "Usage: $0 [--pi] [--win] [--all] [--dry-run] [--stage-only DIR] [--check-only]"
        echo "  A real Pi deploy stops first if the Pi's Operations Pro files or tables.xml changed since the"
        echo "  last deploy or pull (make ops-pull, make tables-pull-pi); HART_DISCARD_PI_CHANGES=1 replaces them."
        echo "  Windows SSH: ${WIN_HOST} -p ${WIN_PORT} → %TEMP% drop + JMRI_UserFiles"
        echo "  Pi SSH:      ${PI_HOST} → /tmp drop + JMRI_UserFiles"
        echo "  Transfer:    rsync (Pi) / tar+scp (Windows). Not git pull."
        echo "  --stage-only DIR: build the host packages into DIR/pi and DIR/win and stop."
        echo "                    No ssh, no Mac install, and the repo's tables.xml is only checked."
        echo "  What a host last got: tools/hosts/deploy_status.sh [--pi] [--win] [--mac]"
        echo "  Redeploy an older commit (rollback): tools/hosts/redeploy_commit.sh <commit> --pi"
        echo "  A real deploy first asks each host named for an ssh answer and stops, before any file is sent"
        echo "  or installed, if one does not reply (with --pi --win an unreachable Windows stops it before the"
        echo "  Pi step). --check-only with the host flags runs this and the Pi check and stops there."
        echo "  Pi PanelPro: quit it first with tools/hosts/pi_quit_panelpro.sh --for-deploy;"
        echo "               the Pi deploy starts it again (also if the deploy fails). A plain"
        echo "               quit or one closed by hand stays closed. HART_PI_RESTART=0 skips."
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
    # sed reads all its input, so a long list cannot SIGPIPE printf under pipefail.
    printf '%s\n' "$DEPLOY_CHANGES" | sed -n '1,10s/^/    /p'
    [[ "$DEPLOY_DIRTY_PATHS" -le 10 ]] || echo "    ..."
  } >&2
fi
# tools/hosts/redeploy_commit.sh runs an older commit's deploy from a detached worktree, with
# a clean environment that sets HART_REDEPLOY_FROM to the commit it was run from.
DEPLOY_SOURCE=deploy
DEPLOY_REDEPLOY_FROM=none
if [[ -n "${HART_REDEPLOY_FROM:-}" ]]; then
  DEPLOY_SOURCE=redeploy
  DEPLOY_REDEPLOY_FROM="$HART_REDEPLOY_FROM"
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
source=$DEPLOY_SOURCE
redeploy_from=$DEPLOY_REDEPLOY_FROM
STAMP
}

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
# The Pi calls (preflight, unpulled check, drop folder, rsync, apply, restart check) share one ssh
# connection: the first opens a master on a socket in a folder made for this run, the rest reuse it,
# and on_exit closes it and removes the folder. ControlPersist bounds a master left by a killed run.
# Windows keeps one connection per call: its OpenSSH server has not been tried with multiplexed
# sessions, and a failure there would come after the Pi was deployed. HART_SSH_MUX=0 turns reuse off.
PI_SSH_OPTS=("${SSH_OPTS[@]}")
SSH_MUX_DIR=""
ssh_mux_open() {
  [[ "${HART_SSH_MUX:-1}" != "0" ]] || return 0
  # A unix socket path is limited to about 104 bytes, and ssh adds a suffix while it binds.
  local parent="${TMPDIR:-/tmp}"
  [[ "${#parent}" -le 60 ]] || parent=/tmp
  if ! SSH_MUX_DIR="$(mktemp -d "${parent%/}/hart-ssh.XXXXXX")"; then
    echo "Note: could not make an ssh socket folder; each Pi call opens its own connection." >&2
    SSH_MUX_DIR=""
    return 0
  fi
  PI_SSH_OPTS+=(-o ControlMaster=auto -o "ControlPath=$SSH_MUX_DIR/pi" -o ControlPersist=120)
}
ssh_mux_close() {
  [[ -n "$SSH_MUX_DIR" ]] || return 0
  # Only a master that was opened is asked to exit (an unreachable Pi leaves no socket).
  if [[ -S "$SSH_MUX_DIR/pi" ]]; then
    ssh -o "ControlPath=$SSH_MUX_DIR/pi" -O exit "$PI_HOST" >/dev/null 2>&1 || true
  fi
  rm -rf "$SSH_MUX_DIR"
  SSH_MUX_DIR=""
}
ssh_pi() { ssh "${PI_SSH_OPTS[@]}" "$PI_HOST" "$@"; }
ssh_win() { ssh "${SSH_OPTS[@]}" -p "$WIN_PORT" "$WIN_HOST" "$@"; }
# SFTP needs "Subsystem sftp" in the Windows sshd_config (OpenSSH 10.4); fall back to
# the legacy scp protocol if a reinstall or reset has removed it.
scp_win() {
  scp "${SSH_OPTS[@]}" -P "$WIN_PORT" "$@" 2>/dev/null && return 0
  echo "scp over SFTP to Windows failed; retrying with the legacy protocol (-O). Check Subsystem sftp in sshd_config." >&2
  scp -O "${SSH_OPTS[@]}" -P "$WIN_PORT" "$@"
}

# PanelPro quit for this deploy (pi_quit_panelpro.sh --for-deploy leaves a marker) comes
# back up, also when the Pi step fails. panelpro_restart_due.sh drops a stale marker and
# never starts PanelPro next to CATS. One closed by hand stays closed. HART_PI_RESTART=0
# skips it.
pi_restart_if_due() {
  [[ "$DRY_RUN" -eq 0 && "${HART_PI_RESTART:-1}" != "0" ]] || return 0
  local due
  due="$(ssh_pi "bash -s" < "$ROOT/tools/hosts/pi/panelpro_restart_due.sh")" || due="unknown"
  case "$due" in
    yes)
      echo "Starting PanelPro on the Pi again (it was quit for this deploy)..."
      bash "$ROOT/tools/hosts/pi_start_panelpro.sh" \
        || echo "PanelPro did not start on the Pi; run tools/hosts/pi_start_panelpro.sh" >&2 ;;
    running) echo "Note: JMRI was running on the Pi during the deploy; restart it to load the new files." >&2 ;;
    stale) echo "The PanelPro quit-for-deploy marker on the Pi was over 2 h old; leaving PanelPro closed." ;;
    no) ;;
    *) echo "Could not check whether to start PanelPro on the Pi; run tools/hosts/pi_start_panelpro.sh if it should be up." >&2 ;;
  esac
}

# One EXIT trap for the whole run. The host steps set these flags instead of their own traps.
STAGE_DIR=""   # the staged packages (pi/, win/), built once per run
WIN_TGZ=""     # the Windows tarball
PI_STEP=0      # 1 while the Pi step runs: PanelPro quit for this deploy comes back on any way out
PI_DONE=0      # the Pi got this package
WIN_STEP=0     # 1 while the Windows step runs
on_exit() {
  [[ -z "$STAGE_DIR" ]] || rm -rf "$STAGE_DIR"
  [[ -z "$WIN_TGZ" ]] || rm -f "$WIN_TGZ"
  if [[ "$PI_STEP" -eq 1 ]]; then
    PI_STEP=0
    pi_restart_if_due
  fi
  if [[ "$WIN_STEP" -eq 1 && "$PI_DONE" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
    echo "The Pi has this deploy but Windows does not: run ./tools/hosts/sync_hart_package.sh --win once Windows answers, so the two match again." >&2
  fi
  ssh_mux_close
}
trap on_exit EXIT
if [[ -z "$STAGE_ONLY" && "$DO_PI" -eq 1 ]]; then
  ssh_mux_open
fi

# Windows is kept matching the Pi, and the Pi step runs first. A host that does not answer would
# stop the run after the other host, the Mac or the repo's tables.xml had already changed, so ask
# every host named on the command line for one ssh no-op before the gates below rewrite anything
# or a byte is sent. It runs before the Pi's unpulled check, which needs ssh too and would name
# the wrong cause for a Pi that is down. A dry run and --stage-only change nothing on a host and skip it.
preflight_hosts() {
  local down=() pi_up=0 h
  if [[ "$DO_PI" -eq 1 ]]; then
    if ssh_pi true </dev/null >/dev/null; then pi_up=1; else down+=("the Pi ($PI_HOST)"); fi
  fi
  # "exit 0" also runs under cmd.exe, the Windows OpenSSH shell.
  if [[ "$DO_WIN" -eq 1 ]] && ! ssh_win "exit 0" </dev/null >/dev/null; then
    down+=("Windows ($WIN_HOST port $WIN_PORT)")
  fi
  [[ "${#down[@]}" -gt 0 ]] || return 0
  for h in "${down[@]}"; do
    echo "STOP: cannot reach $h over ssh." >&2
  done
  echo "No file was sent to or installed on any host, and the Mac install did not run. Deploy again once every host answers." >&2
  # A PanelPro quit for this deploy comes back, as after any stopped Pi deploy: the one thing done on a host.
  if [[ "$pi_up" -eq 1 ]]; then
    echo "The Pi answered: PanelPro there is started again if it was quit for this deploy (a line below says so)." >&2
    pi_restart_if_due
  fi
  exit 1
}
if [[ "$DRY_RUN" -eq 0 ]]; then
  preflight_hosts
fi

# What the owner changed on the Pi since the last deploy or pull would be replaced: Operations
# Pro saves its files as the session runs, and a PanelPro Store rewrites tables.xml. Stop before
# the gates rewrite anything or a byte is sent, and bring back a PanelPro quit for this deploy.
# HART_DISCARD_PI_CHANGES=1 replaces them anyway (the owner's call).
pi_stop() {
  echo "$1" >&2
  pi_restart_if_due
  exit 1
}
if [[ "$DO_PI" -eq 1 && "$DRY_RUN" -eq 0 && "${HART_DISCARD_PI_CHANGES:-0}" != "1" ]]; then
  if ! unpulled="$(ssh_pi "bash -s -- '$PI_USERFILES'" < "$ROOT/tools/hosts/pi/unpulled_changes.sh")"; then
    pi_stop "STOP: could not check the Pi for unpulled changes. HART_DISCARD_PI_CHANGES=1 deploys without the check."
  fi
  if [[ -n "$unpulled" ]]; then
    msg=""
    grep -qx ops <<<"$unpulled" && msg+="STOP: the Pi's Operations Pro files changed since the last deploy or pull. Run make ops-pull and commit first."$'\n'
    grep -qx tables <<<"$unpulled" && msg+="STOP: the Pi's tables.xml changed since the last deploy (a PanelPro Store). Run make tables-pull-pi and commit first."$'\n'
    pi_stop "${msg}HART_DISCARD_PI_CHANGES=1 replaces them anyway."
  fi
fi
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  [[ "$DO_PI" -eq 0 ]] || echo "Pi check: nothing unpulled."
  echo "Host check: every host named answered over ssh."
  exit 0
fi

TABLES=""
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

HART_JYTHON_SCRIPTS=()
for f in \
  jmri/layouts/hart/scripts/panel_status.py \
  jmri/layouts/hart/scripts/discover_sml.py \
  jmri/layouts/hart/scripts/hide_cats_desk_windows.py \
  jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py \
  jmri/layouts/hart/scripts/jmri_cmd_watcher.py \
  jmri/layouts/hart/scripts/sts_car_sync.py \
  jmri/layouts/hart/scripts/mimic_relay.py; do
  # a script that only serves a parked feature is not shipped (repair_dispatcher_traininfo.py)
  grep -qxF "$(basename "$f")" <<<"$PARKED_JYTHON" || HART_JYTHON_SCRIPTS+=("$f")
done

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
    if parked_dir jmri/layouts/hart/dispatcher; then
      echo "Dispatcher traininfo parked: not installed; $profile/dispatcher left as it is"
    elif [[ -d "$traininfo" ]] && compgen -G "$traininfo/*.xml" >/dev/null; then
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
    if profile_tables_unpulled "$src" "$1"; then
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

# Build the package that lands in a temporary folder on the host. The apply scripts install it from there.
# The Pi and Windows packages differ only in the panels (their icon paths name the host's user files) and
# the stamp's target, so stage_package builds the rest once and stage_host_finish adds those two per host.
stage_package() {
  local stage="$1"
  rm -rf "$stage"
  mkdir -p \
    "$stage/cats/panels" \
    "$stage/cats/resources/buttons" \
    "$stage/cats/resources/icons/USS/sensor" \
    "$stage/cats/resources/misc" \
    "$stage/cats/resources/roster" \
    "$stage/cats/scripts" \
    "$stage/jmri/layouts/hart/scripts" \
    "$stage/jmri/scripts"

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
  # Speed-match live view for the Pi (/web/speedmatch/): the page, and the publisher with the
  # files it reads, laid out as in the repo (scripts/speedmatch, data/block_lengths.csv).
  local sm="$ROOT/jmri/layouts/hart/scripts/speedmatch"
  python3 "$sm/dashboard/publish_live.py" --build-page "$stage/cats/resources/speedmatch-web" >/dev/null
  mkdir -p "$stage/cats/speedmatch-live/scripts/speedmatch/dashboard" "$stage/cats/speedmatch-live/data"
  cp -f "$sm/analyze.py" "$sm/liverule.py" "$sm/routes.json" "$stage/cats/speedmatch-live/scripts/speedmatch/"
  cp -f "$sm/dashboard/dashstate.py" "$sm/dashboard/dashsources.py" "$sm/dashboard/export_site_runs.py" \
    "$sm/dashboard/publish_live.py" "$stage/cats/speedmatch-live/scripts/speedmatch/dashboard/"
  cp -f "$ROOT/jmri/layouts/hart/data/block_lengths.csv" "$stage/cats/speedmatch-live/data/"
  cp -f "$ROOT/docs/jmri/speedmatching/profile-2026-11-08/speed_by_step.csv" \
    "$stage/cats/speedmatch-live/data/speed_by_step_2026-11-08.csv"
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

  # A parked feature's folder is left out of the package; the host apply scripts install only what the package
  # holds, so the copies already on a host stay as they are.
  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  if ! parked_dir jmri/layouts/hart/dispatcher; then
    mkdir -p "$stage/jmri/layouts/hart/dispatcher"
    if [[ -d "$traininfo" ]]; then
      rsync -a "$traininfo/" "$stage/jmri/layouts/hart/dispatcher/traininfo/"
    fi
    if [[ -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" ]]; then
      cp -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" \
        "$stage/jmri/layouts/hart/dispatcher/"
    fi
  fi

  if ! parked_dir jmri/layouts/hart/ctc && [[ -d "$ROOT/jmri/layouts/hart/ctc/icons" ]]; then
    mkdir -p "$stage/ctc/icons"
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
  # Finder litter (.DS_Store, AppleDouble) from a gitignored corner of the checkout must not reach the package,
  # whichever copy step brought it.
  find "$stage" \( -name '.DS_Store' -o -name '._*' \) -type f -delete
}

# stage_host_finish STAGE USER_FILES TARGET: the panels rewritten for the host, then its stamp.
stage_host_finish() {
  local stage="$1" user_files="$2" target="$3" p
  for p in "${LIVE_PANELS[@]}"; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" \
      --user-files "$user_files" --out "$stage/cats/panels/$p"
  done
  # The host apply scripts install this last, so it only changes once a deploy has finished.
  write_deploy_stamp "$stage/cats/deploy_stamp.txt" "$target"
}

# stage_hosts DIR: DIR/pi and DIR/win for the hosts named, from one staged build.
stage_hosts() {
  local dir="$1" first=pi
  [[ "$DO_PI" -eq 1 ]] || first=win
  stage_package "$dir/$first"
  if [[ "$DO_PI" -eq 1 && "$DO_WIN" -eq 1 ]]; then
    rsync -a "$dir/pi/" "$dir/win/"
  fi
  [[ "$DO_PI" -eq 0 ]] || stage_host_finish "$dir/pi" "$PI_USERFILES" pi
  [[ "$DO_WIN" -eq 0 ]] || stage_host_finish "$dir/win" "$WIN_USERFILES" win
}

push_rsync() {
  local stage="$1"
  local dest="$2" # user@host:/path/
  local flags=(-az --exclude '.DS_Store' --exclude '._*')
  if [[ "$DRY_RUN" -eq 1 ]]; then
    flags+=(-n --stats)
  fi
  rsync "${flags[@]}" -e "ssh ${PI_SSH_OPTS[*]}" "$stage/" "$dest"
}

# The Windows tarball. The name ends in the X's: BSD mktemp (macOS) only fills trailing ones, so a
# template ending in .tgz made the literal name and failed on the next run. on_exit
# removes it on every way out.
push_tar_scp() {
  local stage="$1"
  local tgz
  tgz="$(mktemp "${TMPDIR:-/tmp}/hart-pkg.XXXXXX")"
  WIN_TGZ="$tgz"
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
  stage_hosts "$STAGE_ONLY"
  [[ "$DO_PI" -eq 0 ]] || echo "Pi package -> $STAGE_ONLY/pi"
  [[ "$DO_WIN" -eq 0 ]] || echo "Windows package -> $STAGE_ONLY/win"
  echo "DONE (stage only)"
  exit 0
fi

if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  # Mac JMRI is for development: the STS and mimic links follow the page's host to the Mac's own
  # STS and mimic server (PORT as in tools/mqtt-mimic/install_mimic_launchagent.sh). The
  # speed-match link names the Pi, the only host that serves that page (HART_PI_WEB_HOST, load_env.sh).
  HART_PI_HOST="$HART_PI_WEB_HOST" HART_MIMIC_PORT="${MIMIC_PORT:-8765}" bash "$ROOT/cats/scripts/install_jmri_web_override.sh"
  install_tables_local
  install_ops_local
  install_cats_panels_local
  install_ctc_icons_local
  install_jython_scripts
  write_deploy_stamp "${HOME}/JMRI_UserFiles/cats/deploy_stamp.txt" mac
  echo "deploy stamp -> ${HOME}/JMRI_UserFiles/cats/deploy_stamp.txt"
fi

if [[ "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ]]; then
  # The Pi step starts here: a staging failure also brings back PanelPro quit for this deploy.
  PI_STEP="$DO_PI"
  STAGE_DIR="$(mktemp -d)"
  stage_hosts "$STAGE_DIR"
fi

if [[ "$DO_PI" -eq 1 ]]; then
  echo "Deploy → Pi ($PI_HOST) via rsync..."
  PI_STEP=1
  PI_DROP="/tmp/hart-deploy.dry-run"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    PI_DROP="$(ssh_pi "mktemp -d /tmp/hart-deploy.XXXXXX")"
  fi
  push_rsync "$STAGE_DIR/pi" "${PI_HOST}:${PI_DROP}/"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    # JMRI_USERFILES: the apply installs where the panel paths and the stamp say (HART_PI_USERFILES).
    ssh_pi "HART=${PI_DROP} JMRI_USERFILES='${PI_USERFILES}' HART_OVERWRITE_OPS=${HART_OVERWRITE_OPS} bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh"
  fi
  echo "Pi deploy done."
  PI_DONE=1
  PI_STEP=0
  pi_restart_if_due
fi

if [[ "$DO_WIN" -eq 1 ]]; then
  echo "Deploy → Windows ($WIN_HOST:$WIN_PORT) via tar..."
  WIN_STEP=1
  push_tar_scp "$STAGE_DIR/win"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    rc=0
    ssh_win "powershell -NoProfile -ExecutionPolicy Bypass -File \"${WIN_DROP}\\cats\\scripts\\windows\\apply_hart_package_local.ps1\" -Hart \"${WIN_DROP}\" -OverwriteOps ${HART_OVERWRITE_OPS} -UserFiles \"${WIN_USERFILES}\"" || rc=$?
    ssh_win "powershell -NoProfile -Command \"Remove-Item -LiteralPath '${WIN_DROP}' -Recurse -Force\""
    [[ "$rc" -eq 0 ]] || exit "$rc"
  fi
  WIN_STEP=0
  echo "Windows deploy done."
fi

echo "DONE"
