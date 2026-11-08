#!/usr/bin/env bash
# Create DecoderPro roster entries for new locomotives through the Pi's running JMRI.
#
# Embeds jmri/layouts/hart/data/new_locos.json (from `cars.py locos publish`) in
# jmri/layouts/hart/scripts/loco_roster_import.py and drops it into the jmri_cmd_watcher
# channel. Without --apply it only prints the plan.
#
#   tools/ops/loco_roster_import.sh            plan
#   tools/ops/loco_roster_import.sh --apply    create the missing roster entries
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/loco_roster_import.py"
LIST="$ROOT/jmri/layouts/hart/data/new_locos.json"
PI_HOST="${HART_PI_SSH:-pi}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
TIMEOUT="${LOCO_IMPORT_TIMEOUT:-120}"

APPLY=False
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=True ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
[[ -f "$LIST" ]] || { echo "no $LIST: run cars.py locos publish first" >&2; exit 1; }

ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

ssh_pi 'test -f /tmp/jmri_watcher.ready' || { echo "jmri_cmd_watcher is not running on $PI_HOST (JMRI up?)" >&2; exit 1; }
if ssh_pi 'test -f /tmp/jmri_cmd.py'; then
  echo "another command is already waiting in /tmp/jmri_cmd.py on $PI_HOST" >&2; exit 1
fi

DROP="$(mktemp)"
trap 'rm -f "$DROP"' EXIT
{
  printf 'LOCO_IMPORT_APPLY=%s\n' "$APPLY"
  printf 'LOCO_IMPORT_JSON=%s\n' "$(python3 -c 'import json,sys; print(repr(json.dumps(json.load(open(sys.argv[1])))))' "$LIST")"
  cat "$SCRIPT"
} > "$DROP"

ssh_pi 'rm -f /tmp/jmri_cmd.out'
scp -q "${SSH_OPTS[@]}" "$DROP" "$PI_HOST:/tmp/jmri_cmd.py.tmp"
ssh_pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'

echo "[$([[ $APPLY == True ]] && echo APPLY || echo PLAN)] waiting for the Pi's JMRI (up to ${TIMEOUT}s)..."
for ((i = 0; i < TIMEOUT; i++)); do
  if ssh_pi 'test -f /tmp/jmri_cmd.out'; then
    OUT="$(ssh_pi 'cat /tmp/jmri_cmd.out')"
    printf '%s\n' "$OUT"
    [[ "${OUT%%$'\n'*}" == "ok" ]] || exit 1
    exit 0
  fi
  sleep 1
done
echo "timed out waiting for /tmp/jmri_cmd.out" >&2
exit 1
