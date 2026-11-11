#!/usr/bin/env bash
# Pull the DecoderPro roster FROM the Pi (command-station host) TO Mac and Windows
# JMRI_UserFiles for visibility/backup. Operations Pro files go the other way: the
# repo is their master and sync_hart_package.sh installs them (ADR-015).
#
# Does not commit roster (decoder CVs) to git.
# Usage: ./tools/hosts/sync_roster_from_pi.sh [--mac] [--win] [--all]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PI_HOST="${HART_PI_SSH:-pi}"
WIN_HOST="${HART_WIN_SSH:-lnevo@10.0.0.6}"
WIN_PORT="${HART_WIN_SSH_PORT:-2222}"
WIN_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
# Same as scp_win in cats/scripts/sync_hart_package.sh: SFTP first, legacy -O if it is off.
scp_win() {
  scp "${WIN_SSH_OPTS[@]}" -P "$WIN_PORT" "$@" 2>/dev/null && return 0
  echo "scp over SFTP to Windows failed; retrying with the legacy protocol (-O). Check Subsystem sftp in sshd_config." >&2
  scp -O "${WIN_SSH_OPTS[@]}" -P "$WIN_PORT" "$@"
}
# ADR-014: every host reads user files from JMRI_UserFiles, not the profile folder.
MAC_USERFILES="${HART_MAC_USERFILES:-$HOME/JMRI_UserFiles}"
WIN_USERFILES_REMOTE='C:/Users/lnevo/JMRI_UserFiles'
STAGE="${HART_ROSTER_STAGE:-$ROOT/jmri/host-copies/pi-roster-ops}"

DO_MAC=0
DO_WIN=0
if [[ $# -eq 0 ]]; then
  DO_MAC=1
  DO_WIN=1
else
  for a in "$@"; do
    case "$a" in
      --mac) DO_MAC=1 ;;
      --win) DO_WIN=1 ;;
      --all) DO_MAC=1; DO_WIN=1 ;;
      -h|--help)
        echo "Usage: $0 [--mac] [--win] [--all]"
        echo "  Source: $PI_HOST:/home/pi/JMRI_UserFiles/{roster.xml,roster/}"
        exit 0
        ;;
      *) echo "Unknown option: $a" >&2; exit 1 ;;
    esac
  done
fi

mkdir -p "$STAGE/roster"
echo "Pull ← Pi ($PI_HOST)…"
scp -o BatchMode=yes -o ConnectTimeout=15 \
  "$PI_HOST:/home/pi/JMRI_UserFiles/roster.xml" "$STAGE/roster.xml"
scp -o BatchMode=yes -o ConnectTimeout=15 -r \
  "$PI_HOST:/home/pi/JMRI_UserFiles/roster/." "$STAGE/roster/"

stamp=$(date +%Y%m%d_%H%M%S)
backup_if_exists() {
  local f="$1"
  if [[ -f "$f" ]]; then
    mkdir -p "$(dirname "$f")/backups"
    cp "$f" "$(dirname "$f")/backups/$(basename "$f").pre_pi_${stamp}"
    echo "  backup $f"
  fi
}

if [[ "$DO_MAC" -eq 1 ]]; then
  echo "Push → Mac $MAC_USERFILES"
  mkdir -p "$MAC_USERFILES/roster"
  backup_if_exists "$MAC_USERFILES/roster.xml"
  cp "$STAGE/roster.xml" "$MAC_USERFILES/roster.xml"
  rsync -a "$STAGE/roster/" "$MAC_USERFILES/roster/"
  echo "  Mac roster locos: $(grep -c '<locomotive ' "$MAC_USERFILES/roster.xml" || true)"
fi

if [[ "$DO_WIN" -eq 1 ]]; then
  echo "Push → Windows $WIN_HOST $WIN_USERFILES_REMOTE"
  ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" \
    "mkdir AppData\\Local\\Temp\\hart-roster-stage\\roster 2>nul & mkdir \"C:\\Users\\lnevo\\JMRI_UserFiles\\roster\" 2>nul & echo ok"
  scp_win \
    "$STAGE/roster.xml" "${WIN_HOST}:AppData/Local/Temp/hart-roster-stage/roster.xml"
  # Stream a tar so the copy skips macOS AppleDouble (._*) files; pack_roster_stage.sh
  # writes relative names.
  "$ROOT/tools/hosts/pack_roster_stage.sh" "$STAGE/roster" | \
    ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" \
      "tar -xf - -C AppData/Local/Temp/hart-roster-stage/roster"
  scp_win \
    "$ROOT/tools/hosts/win_install_roster.ps1" "${WIN_HOST}:AppData/Local/Temp/hart-roster-stage/win_install_roster.ps1"
  ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" \
    "powershell -NoProfile -ExecutionPolicy Bypass -File AppData/Local/Temp/hart-roster-stage/win_install_roster.ps1"
fi

echo "DONE (reopen DecoderPro on Mac/Win to see the copies)"
