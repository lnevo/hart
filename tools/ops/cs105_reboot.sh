#!/usr/bin/env bash
# Restart the TCS CS-105 over LCC through the Pi's running JMRI and list the
# nodes that come back. Same channel as cs105_roster_sync.sh (jmri_cmd_watcher).
# Track power drops for a few seconds; do not run it while trains are moving.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/jmri/layouts/hart/scripts/cs105_reboot.py"
source "$ROOT/tools/env/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
TIMEOUT="${CS105_TIMEOUT:-180}"

ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

ssh_pi 'test -f /tmp/jmri_watcher.ready' || { echo "jmri_cmd_watcher is not running on $PI_HOST (JMRI up?)" >&2; exit 1; }
if ssh_pi 'test -f /tmp/jmri_cmd.py'; then
  echo "another command is already waiting in /tmp/jmri_cmd.py on $PI_HOST" >&2; exit 1
fi

ssh_pi 'rm -f /tmp/jmri_cmd.out'
scp -q "${SSH_OPTS[@]}" "$SCRIPT" "$PI_HOST:/tmp/jmri_cmd.py.tmp"
ssh_pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'

echo "restarting the CS-105 (up to ${TIMEOUT}s)..."
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
