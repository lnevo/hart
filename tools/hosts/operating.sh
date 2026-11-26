#!/usr/bin/env bash
# The "operating" flag: set while the owner runs trains, or while a speed-matching run is on the
# layout. While it is set, the main guard hook (.claude/hooks/main_guard.py) blocks agents from what
# reaches the Pi and Windows: deploys, quitting or starting PanelPro there, STS updates, and (under
# the owner's flag) new speed-matching jobs. Mac-only work stays open. One flag file on the Mac,
# where the agents run: ~/.hart_operating (HART_OPERATING_FLAG overrides the path, for tests).
#
#   operating.sh on [--by owner|speedmatch] [REASON...]   set it (default --by owner)
#   operating.sh off [--owner]                            clear it; an owner flag needs --owner
#   operating.sh status                                   print it; exit 0 when set, 1 when clear
#   operating.sh guard WHAT                               for a layout deploy: exit 0 when clear, else say so
#                                                         and exit 3; HART_DEPLOY_WHILE_OPERATING=1 is the owner's
#                                                         override. An unreadable flag counts as set (fail closed).
#
# The owner asks an agent to set it ("I'm operating") and to clear it. An agent clears only a
# flag it set (--by speedmatch, after the run's log ends); clearing the owner's takes --owner,
# which an agent passes only when the owner says the session is over. An owner `on` takes over a
# speedmatch flag, so the session is not cleared with the run; any other second `on` keeps the first.
set -euo pipefail
FLAG="${HART_OPERATING_FLAG:-$HOME/.hart_operating}"
usage() { sed -n '2,18p' "$0"; }

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
    tmp="$(mktemp "${FLAG}.XXXXXX")"
    printf 'by=%s\nsince=%s\nreason=%s\n' "$by" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$reason" > "$tmp"
    if [[ -f "$FLAG" && "$by" == owner && "$(field by)" == speedmatch ]]; then
      mv "$tmp" "$FLAG"            # the owner's session outlasts the run: only --owner clears it now
      echo "operating flag taken over by the owner${reason:+: $reason} (was speedmatch)"
      exit 0
    fi
    # ln without -f fails when the flag exists: two calls at once cannot both set it
    if ln "$tmp" "$FLAG" 2>/dev/null; then
      rm -f "$tmp"
      echo "operating flag set: by=$by${reason:+ reason=$reason}"
    else
      rm -f "$tmp"
      echo "already set: by=$(field by) since=$(field since) reason=$(field reason)"
    fi
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
  guard)
    # sync_hart_package.sh (to the Pi or Windows) and redeploy_commit.sh call this, so a deploy run from a terminal
    # stops too, not only one an agent types (owner, 2026-11-23, ADR-025 amendment).
    what="${2:-a deploy to the Pi or Windows}"
    [[ -e "$FLAG" ]] || exit 0
    if [[ "${HART_DEPLOY_WHILE_OPERATING:-0}" == 1 ]]; then
      echo "operating flag is set, but HART_DEPLOY_WHILE_OPERATING=1: going ahead with $what" >&2
      exit 0
    fi
    if [[ -r "$FLAG" ]]; then
      echo "REFUSED: the operating flag is set (by=$(field by) since=$(field since) reason=$(field reason)), so $what waits." >&2
    else
      echo "REFUSED: the operating flag file $FLAG cannot be read; it counts as set, so $what waits." >&2
    fi
    echo "  Clear it when the session is over (tools/hosts/operating.sh off --owner), or override with HART_DEPLOY_WHILE_OPERATING=1." >&2
    exit 3
    ;;
  ""|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
