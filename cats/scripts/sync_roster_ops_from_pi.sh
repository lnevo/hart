#!/usr/bin/env bash
# Pull DecoderPro roster + Operations Pro inventories FROM the Pi (command-station
# host / SoR) TO Mac and Windows JMRI profiles for visibility/backup.
#
# Does not commit roster (decoder CVs) to git.
# Usage: ./cats/scripts/sync_roster_ops_from_pi.sh [--mac] [--win] [--all]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PI_HOST="${HART_PI_SSH:-pi}"
WIN_HOST="${HART_WIN_SSH:-lnevo@10.0.0.6}"
WIN_PORT="${HART_WIN_SSH_PORT:-2222}"
MAC_PROFILE="${HART_MAC_JMRI_PROFILE:-$HOME/Library/Preferences/JMRI/My_JMRI_Railroad.jmri}"
WIN_PROFILE_REMOTE='C:/Users/lnevo/JMRI/My_JMRI_Railroad.jmri'
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
        echo "  Source: $PI_HOST:/home/pi/JMRI_UserFiles/{roster.xml,roster/,operations/}"
        exit 0
        ;;
      *) echo "Unknown option: $a" >&2; exit 1 ;;
    esac
  done
fi

mkdir -p "$STAGE/roster" "$STAGE/operations"
echo "Pull ← Pi ($PI_HOST)…"
scp -o BatchMode=yes -o ConnectTimeout=15 \
  "$PI_HOST:/home/pi/JMRI_UserFiles/roster.xml" "$STAGE/roster.xml"
scp -o BatchMode=yes -o ConnectTimeout=15 -r \
  "$PI_HOST:/home/pi/JMRI_UserFiles/roster/." "$STAGE/roster/"
scp -o BatchMode=yes -o ConnectTimeout=15 \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/"Operations*.xml \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/Operations.xml" \
  "$STAGE/operations/" 2>/dev/null || \
scp -o BatchMode=yes -o ConnectTimeout=15 \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/OperationsCarRoster.xml" \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/OperationsEngineRoster.xml" \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/OperationsLocationRoster.xml" \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/OperationsRouteRoster.xml" \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/OperationsTrainRoster.xml" \
  "$PI_HOST:/home/pi/JMRI_UserFiles/operations/Operations.xml" \
  "$STAGE/operations/"

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
  echo "Push → Mac $MAC_PROFILE"
  mkdir -p "$MAC_PROFILE/roster" "$MAC_PROFILE/operations"
  backup_if_exists "$MAC_PROFILE/roster.xml"
  backup_if_exists "$MAC_PROFILE/operations/OperationsCarRoster.xml"
  cp "$STAGE/roster.xml" "$MAC_PROFILE/roster.xml"
  rsync -a "$STAGE/roster/" "$MAC_PROFILE/roster/"
  cp "$STAGE/operations/"Operations*.xml "$MAC_PROFILE/operations/" 2>/dev/null || true
  cp "$STAGE/operations/Operations.xml" "$MAC_PROFILE/operations/" 2>/dev/null || true
  echo "  Mac roster locos: $(grep -c '<locomotive ' "$MAC_PROFILE/roster.xml" || true)"
fi

if [[ "$DO_WIN" -eq 1 ]]; then
  echo "Push → Windows $WIN_HOST $WIN_PROFILE_REMOTE"
  ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" \
    "mkdir hart\\_roster_stage\\roster hart\\_roster_stage\\operations 2>nul & mkdir \"C:\\Users\\lnevo\\JMRI\\My_JMRI_Railroad.jmri\\roster\" \"C:\\Users\\lnevo\\JMRI\\My_JMRI_Railroad.jmri\\operations\" 2>nul & echo ok"
  scp -O -o BatchMode=yes -o ConnectTimeout=15 -P "$WIN_PORT" \
    "$STAGE/roster.xml" "${WIN_HOST}:hart/_roster_stage/roster.xml"
  # scp -r of a dir ending in /. can send "." which OpenSSH rejects.
  # Skip macOS AppleDouble (._*) so Windows copy does not choke.
  find "$STAGE/roster" -maxdepth 1 -type f ! -name '._*' -print0 | \
    tar -C "$STAGE/roster" --null -T - -cf - | \
    ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" \
      "tar -xf - -C hart/_roster_stage/roster"
  scp -O -o BatchMode=yes -o ConnectTimeout=15 -P "$WIN_PORT" \
    "$STAGE/operations/"*.xml "${WIN_HOST}:hart/_roster_stage/operations/"
  scp -O -o BatchMode=yes -o ConnectTimeout=15 -P "$WIN_PORT" \
    "$ROOT/cats/scripts/win_install_roster_ops.ps1" "${WIN_HOST}:hart/_roster_stage/win_install_roster_ops.ps1"
  ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$WIN_PORT" "$WIN_HOST" \
    "powershell -NoProfile -ExecutionPolicy Bypass -File hart/_roster_stage/win_install_roster_ops.ps1"
fi

echo "DONE (Pi remains SoR; reopen DecoderPro/Operations on Mac/Win to see copies)"
