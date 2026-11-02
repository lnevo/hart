#!/usr/bin/env bash
# Move the six Operations Pro files between the Pi and the repo (ADR-015).
#   pull     copy the Pi's files into jmri/layouts/hart/operations/
#   install  copy the repo's files to the Pi. JMRI must be closed there.
# The Pi holds live session state, so pull and commit before changing the files.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PI_HOST="${HART_PI_SSH:-pi}"
REPO_DIR="$ROOT/jmri/layouts/hart/operations"
PI_DIR="/home/pi/JMRI_UserFiles/operations"
FILES=(Operations.xml OperationsCarRoster.xml OperationsEngineRoster.xml
       OperationsLocationRoster.xml OperationsRouteRoster.xml OperationsTrainRoster.xml)

case "${1:-}" in
  pull)
    for f in "${FILES[@]}"; do scp -q "$PI_HOST:$PI_DIR/$f" "$REPO_DIR/$f"; done
    git -C "$ROOT" status --short -- "$REPO_DIR"
    ;;
  install)
    # Quoted for the remote shell; the brackets stop the pattern matching itself.
    if ssh "$PI_HOST" "pgrep -f '[j]mri|[a]pps.PanelPro|[c]ats'" >/dev/null; then
      echo "JMRI is running on the Pi. Close it first; it would overwrite these files." >&2
      exit 1
    fi
    stamp="$(date +%Y%m%d_%H%M%S)"
    ssh "$PI_HOST" "mkdir -p '$PI_DIR/backups/pre_repo_$stamp' && cd '$PI_DIR' && cp ${FILES[*]} 'backups/pre_repo_$stamp/'"
    for f in "${FILES[@]}"; do scp -q "$REPO_DIR/$f" "$PI_HOST:$PI_DIR/$f"; done
    echo "Installed on the Pi; backup is $PI_DIR/backups/pre_repo_$stamp"
    ;;
  *)
    echo "Usage: $0 pull|install" >&2
    exit 2
    ;;
esac
