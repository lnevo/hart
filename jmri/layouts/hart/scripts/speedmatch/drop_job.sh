#!/usr/bin/env bash
# Copy a job file made by make_job.py to the Pi's jmri_cmd_watcher. The job only STARTS in
# JMRI (the watcher answers "started"); its log on the Pi fills as it runs and ends with END.
#
#   drop_job.sh JOBFILE [--force]  send it; refuses while a runner is still active
#   drop_job.sh --fetch LOG [DIR]  copy a log from the Pi into DIR (default .)
#   drop_job.sh --kill             ask a running job to stop (it sets its own throttle to 0)
#
# A runner (steps or move) creates /tmp/speedrun.active when it starts and removes it when
# it ends. --force overrides that check: use it only after the log shows END (a JMRI crash
# can leave the file behind). A kill flag (/tmp/speedrun.kill) is never removed here: the
# operator removes it (ssh pi rm /tmp/speedrun.kill) once the runner has ended.
set -euo pipefail
# Hosts: environment, hart.env, default. Sourced first, so hart.env cannot move ROOT. If the repo or
# load_env.sh is not found, warn and use "pi": --kill and usage must still work.
ROOT="$(cd "$(dirname "$0")" && git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$ROOT" && -f "$ROOT/tools/env/load_env.sh" ]]; then
  source "$ROOT/tools/env/load_env.sh"
else
  echo "drop_job.sh: tools/env/load_env.sh not found; using host ${HART_PI_SSH:-pi}" >&2
fi
PI_HOST="${HART_PI_SSH:-pi}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }
usage() { sed -n '2,13p' "$0"; }

case "${1:-}" in
  --kill) ssh_pi 'touch /tmp/speedrun.kill'; echo "kill flag set; the runner stops its loco at speed 0 and ends. Remove the flag afterwards: ssh $PI_HOST rm /tmp/speedrun.kill"; exit 0 ;;
  --fetch) [[ -n "${2:-}" ]] || { usage; exit 2; }
    scp -q "${SSH_OPTS[@]}" "$PI_HOST:$2" "${3:-.}/"; echo "copied $2"; exit 0 ;;
  ""|-h|--help) usage; exit 0 ;;
esac
JOB="$1"
FORCE="${2:-}"
[[ -f "$JOB" ]] || { echo "no such job file: $JOB" >&2; exit 1; }
ssh_pi 'test -f /tmp/jmri_watcher.ready' || { echo "jmri_cmd_watcher is not running on $PI_HOST (JMRI up?)" >&2; exit 1; }
if ssh_pi 'test -f /tmp/jmri_cmd.py'; then
  echo "another command is already waiting in /tmp/jmri_cmd.py on $PI_HOST" >&2; exit 1
fi
if grep -q speedrun.active "$JOB"; then
  if ssh_pi 'test -f /tmp/speedrun.kill'; then
    echo "/tmp/speedrun.kill exists on $PI_HOST: the new runner would stop at once. Once the old runner has ended, remove it: ssh $PI_HOST rm /tmp/speedrun.kill" >&2; exit 1
  fi
  if ssh_pi 'test -f /tmp/speedrun.active' && [[ "$FORCE" != "--force" ]]; then
    echo "a runner is still active on $PI_HOST ($(ssh_pi 'cat /tmp/speedrun.active')). Wait for END in its log, or --force after it shows END." >&2; exit 1
  fi
  [[ "$FORCE" == "--force" ]] && ssh_pi 'rm -f /tmp/speedrun.active'
fi
ssh_pi 'rm -f /tmp/jmri_cmd.out'
# copy to a temp name, then rename, so the watcher never runs a half-copied file
scp -q "${SSH_OPTS[@]}" "$JOB" "$PI_HOST:/tmp/jmri_cmd.py.tmp"
ssh_pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'
for ((i = 0; i < 60; i++)); do
  if ssh_pi 'test -f /tmp/jmri_cmd.out'; then ssh_pi 'cat /tmp/jmri_cmd.out'; exit 0; fi
  sleep 1
done
echo "no answer from the watcher within 60 s" >&2
exit 1
