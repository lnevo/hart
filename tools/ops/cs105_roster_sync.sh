#!/usr/bin/env bash
# Sync the JMRI roster into the TCS CS-105 through the Pi's running JMRI.
#
# Drops the generic script (submodule external/jmri-cs105-roster-sync, public repo
# lnevo/jmri-cs105-roster-sync) into the Pi's jmri_cmd_watcher channel (/tmp/jmri_cmd.py) and prints the result.
# Without --apply it only prints the plan.
#
#   tools/ops/cs105_roster_sync.sh                 plan
#   tools/ops/cs105_roster_sync.sh --apply         create missing trains, update labels
#   tools/ops/cs105_roster_sync.sh --apply --only 1993,572
#   tools/ops/cs105_roster_sync.sh --apply --rename   also rename existing CS-105 entries
#   tools/ops/cs105_roster_sync.sh --apply --rename --names road   names as "<road> <number>"
set -euo pipefail

source "$(cd "$(dirname "$0")/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default; first, so hart.env cannot move ROOT, SCRIPT or LIST
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/external/jmri-cs105-roster-sync/cs105_roster_sync.py"
[[ -f "$SCRIPT" ]] || { echo "missing $SCRIPT: git submodule update --init external/jmri-cs105-roster-sync" >&2; exit 1; }
PI_HOST="$HART_PI_SSH"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
TIMEOUT="${CS105_TIMEOUT:-900}"

APPLY=False RENAME=False ONLY="" NAMES=id
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=True ;;
    --rename) RENAME=True ;;
    --only) ONLY="$2"; shift ;;
    --names) NAMES="$2"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

ssh_pi 'test -f /tmp/jmri_watcher.ready' || { echo "jmri_cmd_watcher is not running on $PI_HOST (JMRI up?)" >&2; exit 1; }
if ssh_pi 'test -f /tmp/jmri_cmd.py'; then
  echo "another command is already waiting in /tmp/jmri_cmd.py on $PI_HOST" >&2; exit 1
fi

DROP="$(mktemp)"
trap 'rm -f "$DROP"' EXIT
{
  printf 'CS105_APPLY=%s\nCS105_RENAME=%s\nCS105_ONLY="%s"\nCS105_NAMES="%s"\n' "$APPLY" "$RENAME" "$ONLY" "$NAMES"
  cat "$SCRIPT"
} > "$DROP"

ssh_pi 'rm -f /tmp/jmri_cmd.out'
# copy to a temp name, then rename, so the watcher never runs a half-copied file
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
