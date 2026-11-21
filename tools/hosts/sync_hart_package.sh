#!/usr/bin/env bash
# Deploy HART Digicon/JMRI package from this working tree over SSH.
#
# This file is the entry point: it reads the flags and runs the steps in tools/hosts/deploy/, in order, so every
# check is made before anything is sent or installed:
#   gate.sh      every check (hosts answer, the Pi has nothing unpulled, the local gates, this Mac's Store check,
#                a trial staging, Windows can take the package); changes nothing
#   stage.sh     builds one staged tree per host, once
#   ship_mac.sh  installs on this Mac
#   ship_pi.sh   rsync (delta) + apply_hart_package_local.sh
#   ship_win.sh  one tarball + apply_hart_package_local.ps1
# Hosts are not git clones. Panels are path-rewritten per user-files, and the
# payload is a subset (no wiki, screenshots, linear layouts, or CATS src).
# The repo keeps the host scripts in tools/hosts/pi and tools/hosts/windows; the package
# still carries them at cats/scripts/pi and cats/scripts/windows, as the hosts expect.
# cats/scripts/sync_hart_package.sh is a wrapper that runs this file.
#
# Usage: ./tools/hosts/sync_hart_package.sh [--pi] [--win] [--all] [--dry-run] [--stage-only DIR]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_STEPS="$ROOT/tools/hosts/deploy"
source "$DEPLOY_STEPS/common.sh"
DRY_RUN=0
# The profile refusals come first, before anything else is read or made; every step makes them too, for a run of its own.
refuse_before_changing

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
        echo "  Every check runs before anything is sent or installed (tools/hosts/deploy/gate.sh): each host"
        echo "  named is asked for an ssh answer, the Pi for its unpulled files, this Mac for its Store, the"
        echo "  package is trial-built and Windows is asked for a temp folder and tar. A failure stops the run"
        echo "  with no file sent and no Mac install. --check-only with the host flags runs the host checks only."
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

# What is being shipped: the facts every step writes into the stamp (cats/deploy_stamp.txt on each host this run
# installs; tools/hosts/deploy_status.sh reads it back), taken once here, before any check touches tables.xml,
# and passed to the steps in the environment.
deploy_facts 1

# One EXIT trap for the whole run: the staged packages, the PanelPro quit for this deploy, the ssh sockets.
STAGE_DIR=""   # the staged packages (pi/, win/), built once per run
PI_STEP=0      # 1 from the checks passing until ship_pi.sh takes over: PanelPro quit for this deploy comes back on any way out
on_exit() {
  [[ -z "$STAGE_DIR" ]] || rm -rf "$STAGE_DIR"
  if [[ "$PI_STEP" -eq 1 ]]; then
    PI_STEP=0
    pi_restart_if_due
  fi
  ssh_mux_close
}
trap on_exit EXIT
if [[ -z "$STAGE_ONLY" ]]; then
  ssh_mux_open
fi

# 1. every check, before anything ships. A real run to a host also builds its package here (the gate's last local
# check), into the folder the steps below ship, so the package is built once.
STAGED_BY_GATE=0
gate_flags=()
if [[ ( "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ) && "$DRY_RUN" -eq 0 && -z "$STAGE_ONLY" ]]; then
  STAGE_DIR="$(mktemp -d)"
  STAGED_BY_GATE=1
  gate_flags+=(--stage-dir "$STAGE_DIR")
fi
[[ "$DO_PI" -eq 0 ]] || gate_flags+=(--pi)
[[ "$DO_WIN" -eq 0 ]] || gate_flags+=(--win)
[[ "$DO_MAC_WEB" -eq 0 ]] || gate_flags+=(--mac)
[[ "$DRY_RUN" -eq 0 ]] || gate_flags+=(--dry-run)
[[ "$CHECK_ONLY" -eq 0 ]] || gate_flags+=(--check-only)
[[ -z "$STAGE_ONLY" ]] || gate_flags+=(--stage-only)
bash "$DEPLOY_STEPS/gate.sh" ${gate_flags[@]+"${gate_flags[@]}"}
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  exit 0
fi
export HART_GATED=1   # every check has passed: the steps below do not ask the hosts again
# The Pi's PanelPro may have been quit for this deploy: a later failure brings it back (ship_pi.sh does too, once it runs).
[[ "$DRY_RUN" -eq 1 ]] || PI_STEP="$DO_PI"

# 2. the packages, once
stage_flags=()
[[ "$DO_PI" -eq 0 ]] || stage_flags+=(--pi)
[[ "$DO_WIN" -eq 0 ]] || stage_flags+=(--win)
if [[ -n "$STAGE_ONLY" ]]; then
  mkdir -p "$STAGE_ONLY"
  bash "$DEPLOY_STEPS/stage.sh" ${stage_flags[@]+"${stage_flags[@]}"} "$STAGE_ONLY"
  [[ "$DO_PI" -eq 0 ]] || echo "Pi package -> $STAGE_ONLY/pi"
  [[ "$DO_WIN" -eq 0 ]] || echo "Windows package -> $STAGE_ONLY/win"
  echo "DONE (stage only)"
  exit 0
fi
if [[ ( "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ) && "$STAGED_BY_GATE" -eq 0 ]]; then
  STAGE_DIR="$(mktemp -d)"   # a dry run: nothing was checked on a host, and the package is built now
  bash "$DEPLOY_STEPS/stage.sh" "${stage_flags[@]}" "$STAGE_DIR"
fi

# 3. the Mac, then the Pi, then Windows (Windows is kept matching the Pi, so the Pi step runs first)
if [[ "$DO_MAC_WEB" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  bash "$DEPLOY_STEPS/ship_mac.sh"
fi
ship_flags=()
[[ "$DRY_RUN" -eq 0 ]] || ship_flags+=(--dry-run)
if [[ "$DO_PI" -eq 1 ]]; then
  PI_STEP=0   # ship_pi.sh brings PanelPro back itself, also when it fails
  bash "$DEPLOY_STEPS/ship_pi.sh" ${ship_flags[@]+"${ship_flags[@]}"} "$STAGE_DIR/pi"
  export HART_PI_DONE=1
fi
if [[ "$DO_WIN" -eq 1 ]]; then
  bash "$DEPLOY_STEPS/ship_win.sh" ${ship_flags[@]+"${ship_flags[@]}"} "$STAGE_DIR/win"
fi

echo "DONE"
