#!/usr/bin/env bash
# The TCS CS-105 through the Pi's running JMRI. Each subcommand drops a Jython script into the Pi's
# jmri_cmd_watcher channel (/tmp/jmri_cmd.py) and prints what comes back (docs/jmri/CS105_ROSTER_SYNC.md).
#
#   cs105.sh reboot                                   restart the CS-105 over LCC and list the nodes that come back;
#                                                     track power drops for a few seconds, so not while trains move
#   cs105.sh roster-sync                              plan the JMRI roster to CS-105 sync, write nothing
#   cs105.sh roster-sync --apply                      create missing trains, update labels
#   cs105.sh roster-sync --apply --only 1993,572
#   cs105.sh roster-sync --apply --rename             also rename existing CS-105 entries
#   cs105.sh roster-sync --apply --rename --names road   names as "<road> <number>"
#   cs105.sh consist query NODE...                    list the listeners each train node holds
#   cs105.sh consist attach LEAD FOLLOW [--flags N]   LEAD lists FOLLOW (default flags 6: reverse, F0 linked);
#                                                     a consist takes one attach per side
#   cs105.sh consist detach LEAD FOLLOW               drop the listener on both nodes, then query both
#
# consist sends LCC Train Control messages (jmri/layouts/hart/scripts/cs105_consist.py), so it is refused while
# the operating flag is set (tools/hosts/operating.sh), with no override. A train node is six hex bytes,
# 06.01.00.00.C8.49 for long address 2121. CS105_TIMEOUT sets the wait in seconds.
set -euo pipefail

source "$(cd "$(dirname "$0")/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default; first, so hart.env cannot move ROOT
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PI_HOST="$HART_PI_SSH"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
CONSIST_LOG="/tmp/cs105_consist.$(date +%Y%m%d%H%M%S).$$.log"   # one per run: an earlier run's thread cannot end this one
DROP=""   # the script with its settings, built on the Mac
trap '[[ -z "$DROP" ]] || rm -f "$DROP"' EXIT

usage() { sed -n '2,19p' "$0"; }
die() { echo "cs105.sh: $*" >&2; exit 2; }
ssh_pi() { ssh "${SSH_OPTS[@]}" "$PI_HOST" "$@"; }

# Drop FILE into the watcher channel and wait up to TIMEOUT s for /tmp/jmri_cmd.out; print it; fail unless it says ok.
drop_and_wait() {
  local file="$1" timeout="$2" banner="$3" out i
  ssh_pi 'test -f /tmp/jmri_watcher.ready' || { echo "jmri_cmd_watcher is not running on $PI_HOST (JMRI up?)" >&2; exit 1; }
  if ssh_pi 'test -f /tmp/jmri_cmd.py'; then
    echo "another command is already waiting in /tmp/jmri_cmd.py on $PI_HOST" >&2; exit 1
  fi
  ssh_pi 'rm -f /tmp/jmri_cmd.out'
  # copy to a temp name, then rename, so the watcher never runs a half-copied file
  scp -q "${SSH_OPTS[@]}" "$file" "$PI_HOST:/tmp/jmri_cmd.py.tmp"
  ssh_pi 'mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py'
  echo "$banner (up to ${timeout}s)..."
  for ((i = 0; i < timeout; i++)); do
    if ssh_pi 'test -f /tmp/jmri_cmd.out'; then
      out="$(ssh_pi 'cat /tmp/jmri_cmd.out')"
      printf '%s\n' "$out"
      [[ "${out%%$'\n'*}" == "ok" ]] || exit 1
      return 0
    fi
    sleep 1
  done
  echo "timed out waiting for /tmp/jmri_cmd.out" >&2
  exit 1
}

cmd_reboot() {
  [[ "${1:-}" != -h && "${1:-}" != --help ]] || { usage; exit 0; }
  [[ $# -eq 0 ]] || die "reboot takes no arguments"
  drop_and_wait "$ROOT/jmri/layouts/hart/scripts/cs105_reboot.py" "${CS105_TIMEOUT:-180}" "restarting the CS-105"
}

cmd_roster_sync() {
  local script="$ROOT/external/jmri-cs105-roster-sync/cs105_roster_sync.py"
  local apply=False rename=False only="" names=id
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --apply) apply=True ;;
      --rename) rename=True ;;
      --only)   # goes into the dropped script's source, so plain ids only
        [[ $# -ge 2 && "$2" =~ ^[0-9A-Za-z,.\ ]+$ ]] || die "--only needs a list of roster ids or numbers (1993,572)"
        only="$2"; shift ;;
      --names)
        [[ $# -ge 2 && ( "$2" == id || "$2" == road ) ]] || die "--names needs id or road"
        names="$2"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
  done
  [[ -f "$script" ]] || { echo "missing $script: git submodule update --init external/jmri-cs105-roster-sync" >&2; exit 1; }
  DROP="$(mktemp)"
  {
    printf 'CS105_APPLY=%s\nCS105_RENAME=%s\nCS105_ONLY="%s"\nCS105_NAMES="%s"\n' "$apply" "$rename" "$only" "$names"
    cat "$script"
  } > "$DROP"
  drop_and_wait "$DROP" "${CS105_TIMEOUT:-900}" \
    "[$([[ $apply == True ]] && echo APPLY || echo PLAN)] waiting for the Pi's JMRI"
}

node_ok() { [[ "$1" =~ ^([0-9A-Fa-f]{2}\.){5}[0-9A-Fa-f]{2}$ ]]; }

refuse_while_operating() {
  local flag="${HART_OPERATING_FLAG:-$HOME/.hart_operating}"
  [[ -e "$flag" || -L "$flag" ]] || return 0
  echo "REFUSED: the operating flag is set, so cs105.sh consist sends nothing to the CS-105." >&2
  "$ROOT/tools/hosts/operating.sh" status >&2 || true
  echo "  It runs once the owner clears the flag (tools/hosts/operating.sh off --owner) or the speed-matching run ends." >&2
  exit 3
}

cmd_consist() {
  local action="${1:-}" lead="" follow="" flags=6 nodes=() n timeout i log
  [[ -n "$action" ]] || die "consist needs query, attach or detach"
  [[ "$action" != -h && "$action" != --help ]] || { usage; exit 0; }
  shift
  case "$action" in
    query)
      [[ $# -ge 1 ]] || die "consist query needs at least one train node"
      nodes=("$@") ;;
    attach|detach)
      [[ $# -ge 2 ]] || die "consist $action needs LEAD and FOLLOW"
      lead="$1" follow="$2"; shift 2
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --flags)
            [[ "$action" == attach ]] || die "--flags is for attach"
            if [[ $# -lt 2 || ! "$2" =~ ^[0-9]{1,3}$ ]] || (( 10#$2 > 255 )); then die "--flags needs a number 0 to 255"; fi
            flags="$((10#$2))"; shift ;;
          *) die "unknown option: $1" ;;
        esac
        shift
      done
      [[ "$lead" != "$follow" ]] || die "LEAD and FOLLOW are the same node"
      nodes=("$lead" "$follow") ;;
    *) die "consist takes query, attach or detach, not '$action'" ;;
  esac
  for n in "${nodes[@]}"; do node_ok "$n" || die "train node '$n' is not six hex bytes (06.01.00.00.C8.49)"; done
  refuse_while_operating

  DROP="$(mktemp)"
  {
    printf 'ACTION = "%s"\n' "$action"
    if [[ "$action" == query ]]; then
      printf 'NODES = ['; printf '"%s", ' "${nodes[@]}"; printf ']\n'
    else
      printf 'NODES = []\n'
    fi
    printf 'LEAD = "%s"\nFOLLOW = "%s"\nFLAGS = %s\nLOGF = "%s"\n' "$lead" "$follow" "$flags" "$CONSIST_LOG"
    cat "$ROOT/jmri/layouts/hart/scripts/cs105_consist.py"
  } > "$DROP"

  timeout="${CS105_TIMEOUT:-120}"
  ssh_pi "rm -f $CONSIST_LOG"
  drop_and_wait "$DROP" "$timeout" "[consist $action] waiting for the Pi's JMRI"
  # the script answers "started" and works in a thread; its log ends with END
  for ((i = 0; i < timeout; i++)); do
    log="$(ssh_pi "cat $CONSIST_LOG 2>/dev/null" || true)"
    if [[ "${log##*$'\n'}" == END || "$log" == END ]]; then
      printf '%s\n' "$log"
      [[ "$log" != *ERROR* ]] || exit 1
      return 0
    fi
    sleep 1
  done
  printf '%s\n' "$log"
  echo "timed out waiting for END in $CONSIST_LOG" >&2
  exit 1
}

sub="${1:-}"
[[ $# -eq 0 ]] || shift
case "$sub" in
  reboot) cmd_reboot "$@" ;;
  roster-sync) cmd_roster_sync "$@" ;;
  consist) cmd_consist "$@" ;;
  -h|--help) usage ;;
  "") usage >&2; exit 2 ;;
  *) echo "cs105.sh: unknown subcommand '$sub'" >&2; usage >&2; exit 2 ;;
esac
