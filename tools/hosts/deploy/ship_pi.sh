#!/usr/bin/env bash
# Deploy step 4: send the Pi's package (rsync, delta) and apply it there (apply_hart_package_local.sh), then start
# PanelPro again if it was quit for this deploy. Every check was made by gate.sh.
#
# Usage: ship_pi.sh [--dry-run] STAGED_PI_DIR     (the pi/ folder stage.sh built)
#   --dry-run  rsync -n --stats only: no drop folder, no apply
# PanelPro quit for this deploy (pi_quit_panelpro.sh --for-deploy) comes back also when this step fails.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
DO_PI=1
STAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -*) echo "ship_pi.sh: unknown option: $1" >&2; exit 1 ;;
    *) [[ -z "$STAGE" ]] || { echo "ship_pi.sh: one folder only" >&2; exit 1; }; STAGE="$1" ;;
  esac
  shift
done
[[ -d "$STAGE" ]] || { echo "Usage: ship_pi.sh [--dry-run] STAGED_PI_DIR" >&2; exit 1; }
deploy_facts

PI_STEP=1   # 1 until the Pi step is done: PanelPro quit for this deploy comes back on any way out
on_exit() {
  if [[ "$PI_STEP" -eq 1 ]]; then
    PI_STEP=0
    pi_restart_if_due
  fi
  ssh_mux_close
}
trap on_exit EXIT
ssh_mux_open

push_rsync() {
  local stage="$1"
  local dest="$2" # user@host:/path/
  local flags=(-az --exclude '.DS_Store' --exclude '._*')
  if [[ "$DRY_RUN" -eq 1 ]]; then
    flags+=(-n --stats)
  fi
  rsync "${flags[@]}" -e "ssh ${PI_SSH_OPTS[*]}" "$stage/" "$dest"
}

echo "Deploy → Pi ($PI_HOST) via rsync..."
PI_DROP="/tmp/hart-deploy.dry-run"
if [[ "$DRY_RUN" -eq 0 ]]; then
  PI_DROP="$(ssh_pi "mktemp -d /tmp/hart-deploy.XXXXXX")"
fi
push_rsync "$STAGE" "${PI_HOST}:${PI_DROP}/"
if [[ "$DRY_RUN" -eq 0 ]]; then
  # JMRI_USERFILES: the apply installs where the panel paths and the stamp say (HART_PI_USERFILES).
  ssh_pi "HART=${PI_DROP} JMRI_USERFILES='${PI_USERFILES}' HART_OVERWRITE_OPS=${HART_OVERWRITE_OPS} bash ${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh"
fi
echo "Pi deploy done."
PI_STEP=0
pi_restart_if_due
