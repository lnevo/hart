#!/usr/bin/env bash
# The "operating" flag: set while the owner runs trains, or while a speed-matching run is on the
# layout. While it is set, the main guard hook (.claude/hooks/main_guard.py) blocks agents from
# deploying, writing the JMRI tables, and quitting, starting or test-loading PanelPro on the Mac
# or the Pi. One flag file on the Mac, where the agents run: ~/.hart_operating (HART_OPERATING_FLAG
# overrides the path, for tests).
#
#   operating.sh on [--by owner|speedmatch] [REASON...]   set it (default --by owner)
#   operating.sh off [--owner]                            clear it; an owner flag needs --owner
#   operating.sh status                                   print it; exit 0 when set, 1 when clear
#
# The owner asks an agent to set it ("I'm operating") and to clear it. An agent clears only a
# flag it set (--by speedmatch, after the run's log ends); clearing the owner's takes --owner,
# which an agent passes only when the owner says the session is over.
set -euo pipefail
FLAG="${HART_OPERATING_FLAG:-$HOME/.hart_operating}"
usage() { sed -n '2,15p' "$0"; }

field() { sed -n "s/^$1=//p" "$FLAG" 2>/dev/null | head -1; }

case "${1:-}" in
  on)
    shift
    by=owner
    if [[ "${1:-}" == "--by" ]]; then
      by="${2:-}"; shift 2 || true
    fi
    if [[ "$by" != owner && "$by" != speedmatch ]]; then
      echo "operating.sh: --by must be owner or speedmatch, not '${by}'" >&2; exit 2
    fi
    reason="${*:-}"
    if [[ -f "$FLAG" ]]; then
      echo "already set: by=$(field by) since=$(field since) reason=$(field reason)"
      exit 0
    fi
    tmp="$(mktemp "${FLAG}.XXXXXX")"
    printf 'by=%s\nsince=%s\nreason=%s\n' "$by" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$reason" > "$tmp"
    mv "$tmp" "$FLAG"
    echo "operating flag set: by=$by${reason:+ reason=$reason}"
    ;;
  off)
    shift
    if [[ ! -f "$FLAG" ]]; then
      echo "operating flag already clear"; exit 0
    fi
    if [[ "$(field by)" == owner && "${1:-}" != "--owner" ]]; then
      echo "operating.sh: the owner set this flag (since $(field since)); clear it only when the owner says, with --owner" >&2
      exit 1
    fi
    rm -f "$FLAG"
    echo "operating flag cleared"
    ;;
  status)
    if [[ -f "$FLAG" ]]; then
      echo "operating: by=$(field by) since=$(field since) reason=$(field reason)"; exit 0
    fi
    echo "not operating"; exit 1
    ;;
  ""|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
