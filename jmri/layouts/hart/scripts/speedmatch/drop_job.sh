#!/usr/bin/env bash
# Copy a job file made by make_job.py to the Pi's jmri_cmd_watcher. The job only STARTS in
# JMRI (the watcher answers "started"); its log on the Pi fills as it runs and ends with END.
#
#   drop_job.sh JOBFILE            send it, report that it started
#   drop_job.sh --fetch LOG [DIR]  copy a log from the Pi into DIR (default .)
#   drop_job.sh --kill             ask a running steps job to stop (it sets its own throttle to 0)
set -euo pipefail
PI_HOST="${HART_PI_SSH:-pi}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

case "${1:-}" in
  --kill) ssh_pi 'touch /tmp/speedrun.kill'; echo "kill flag set; the runner stops its loco at speed 0 and ends"; exit 0 ;;
  --fetch) scp -q "${SSH_OPTS[@]}" "$PI_HOST:$2" "${3:-.}/"; echo "copied $2"; exit 0 ;;
  ""|-h|--help) sed -n '2,8p' "$0"; exit 0 ;;
esac
JOB="$1"
[[ -f "$JOB" ]] || { echo "no such job file: $JOB" >&2; exit 1; }
ssh_pi 'test -f /tmp/jmri_watcher.ready' || { echo "jmri_cmd_watcher is not running on $PI_HOST (JMRI up?)" >&2; exit 1; }
if ssh_pi 'test -f /tmp/jmri_cmd.py'; then
  echo "another command is already waiting in /tmp/jmri_cmd.py on $PI_HOST" >&2; exit 1
fi
ssh_pi 'rm -f /tmp/speedrun.kill /tmp/jmri_cmd.out'
# copy to a temp name, then rename, so the watcher never runs a half-copied file
scp -q "${SSH_OPTS[@]}" "$JOB" "$PI_HOST:/tmp/jmri_cmd.py.tmp"
ssh_pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'
for ((i = 0; i < 60; i++)); do
  if ssh_pi 'test -f /tmp/jmri_cmd.out'; then ssh_pi 'cat /tmp/jmri_cmd.out'; exit 0; fi
  sleep 1
done
echo "no answer from the watcher within 60 s" >&2
exit 1
