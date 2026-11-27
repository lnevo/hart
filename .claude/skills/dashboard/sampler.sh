#!/bin/bash
# Live-dashboard sampler: one JSON line every 2 minutes with host load and Claude counts.
#   sampler.sh OUT.jsonl     run under a Monitor; prints "SYNC HH:MM" every 10 minutes
# Counts come from this Mac, not from ListAgents, so a steward without ListAgents can run it:
# sessions are claude processes, subagents are task outputs written in the last 3 minutes.
OUT=${1:?usage: sampler.sh OUT.jsonl}
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO" || exit 1
W=$(bash -c 'source tools/env/load_env.sh && echo "$HART_WIN_SSH"')
P=$(bash -c 'source tools/env/load_env.sh && echo "${HART_WIN_SSH_PORT:-2222}"')
MCPU=$(sysctl -n hw.ncpu)
TASKS=${CLAUDE_TASKS_ROOT:-/private/tmp/claude-$(id -u)}
n=0
while true; do
  t=$(date +%H:%M)
  mload=$(sysctl -n vm.loadavg | awk '{print $2}')
  w=$(printf '%s\n' 'cat /proc/loadavg | cut -d" " -f1; nproc; ls -d ~/wt/*/ 2>/dev/null | wc -l' \
    | ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR -p "$P" "$W" "wsl.exe -d Ubuntu-24.04 -- bash -s" 2>/dev/null \
    | tr '\r' ' ' | tr '\n' ' ')
  set -- $w
  sess=$(ps -axo comm | grep -c -x claude)
  ag=$(find -L "$TASKS" -path '*/tasks/a*.output' -mmin -3 2>/dev/null | wc -l | tr -d ' ')
  printf '{"at":"%s","mac_load1":%s,"mac_cpus":%s,"win_load1":%s,"win_cpus":%s,"win_remote_runs":%s,"sessions":%s,"subagents":%s,"claude_total":%s}\n' \
    "$t" "${mload:-null}" "$MCPU" "${1:-null}" "${2:-null}" "${3:-null}" "$sess" "$ag" "$((sess + ag))" >> "$OUT"
  n=$((n + 1)); if [ $((n % 5)) -eq 1 ]; then echo "SYNC $t"; fi
  sleep 120
done
