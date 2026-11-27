#!/usr/bin/env bash
# Show what the last layout deploy shipped to each host: the stamp that
# sync_hart_package.sh leaves in JMRI_UserFiles/cats/deploy_stamp.txt, and how that
# commit compares with this checkout. It only reads, on the hosts and here.
#
# Usage: tools/hosts/deploy_status.sh [--pi] [--win] [--mac] [--all]   (default --pi)
# Hosts come from load_env.sh (HART_PI_SSH, HART_PI_USERFILES, HART_WIN_SSH,
# HART_WIN_SSH_PORT, HART_WIN_USERFILES): environment, then hart.env, then the default.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
STAMP_REL="cats/deploy_stamp.txt"

TARGETS=()
for a in "$@"; do
  case "$a" in
    --pi) TARGETS+=(pi) ;;
    --win) TARGETS+=(win) ;;
    --mac) TARGETS+=(mac) ;;
    --all) TARGETS+=(pi win mac) ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $a" >&2; exit 2 ;;
  esac
done
[[ ${#TARGETS[@]} -gt 0 ]] || TARGETS=(pi)

read_stamp() {
  case "$1" in
    pi) ssh "${SSH_OPTS[@]}" "$HART_PI_SSH" "cat '$HART_PI_USERFILES/$STAMP_REL'" ;;
    win)
      local path="${HART_WIN_USERFILES//\//\\}\\${STAMP_REL//\//\\}"
      ssh "${SSH_OPTS[@]}" -p "$HART_WIN_SSH_PORT" "$HART_WIN_SSH" \
        "powershell -NoProfile -Command \"Get-Content -Raw -LiteralPath '$path'\"" | tr -d '\r' ;;
    mac) cat "$HOME/JMRI_UserFiles/$STAMP_REL" ;;
  esac
}

# live_changes COMMIT: how many commits since COMMIT touch a path the deploy ships (tools/hosts/live_paths.txt),
# and which paths; and the live changes the host has that this checkout lacks. Ahead alone says nothing:
# most commits change docs or tools.
live_changes() {
  local out line section count=0 behind=0 ahead_paths=() behind_paths=()
  if ! out="$(python3 "$ROOT/tools/hosts/live_paths.py" changed "$1" HEAD)"; then
    echo "  Cannot tell which commits touch live paths (see the message above)."
    rc=1
    return
  fi
  while IFS= read -r line; do
    case "$line" in
      "ahead "*) section=ahead; count="${line#ahead }" ;;
      "behind "*) section=behind; behind="${line#behind }" ;;
      "  "*) if [[ "$section" == ahead ]]; then ahead_paths+=("${line#  }"); else behind_paths+=("${line#  }"); fi ;;
    esac
  done <<<"$out"
  if [[ "$count" == 0 ]]; then
    echo "  None of the commits ahead changes a live artifact: nothing to deploy."
  elif [[ ${#ahead_paths[@]} -eq 0 ]]; then
    echo "  Of them, $count touch live artifacts, but the changes cancel out: a deploy would ship nothing new."
  else
    echo "  Of them, $count touch live artifacts; a deploy would ship:"
    printf '    %s\n' "${ahead_paths[@]}"
  fi
  if [[ "$behind" != 0 ]]; then
    if [[ ${#behind_paths[@]} -eq 0 ]]; then
      echo "  WARNING: $behind live-touching commit(s) on the host are not in this checkout (their changes cancel out)."
    else
      echo "  WARNING: the host has $behind live-touching commit(s) this checkout lacks; a deploy from here would roll back:"
      printf '    %s\n' "${behind_paths[@]}"
    fi
  fi
}

compare() {
  local commit="$1" head
  head="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  if [[ -z "$commit" || "$commit" == unknown ]]; then
    echo "  The stamp names no commit."
  elif [[ "$commit" == "$head" ]]; then
    echo "  Same commit as this checkout."
  elif git -C "$ROOT" cat-file -e "${commit}^{commit}" 2>/dev/null; then
    echo "  This checkout is $(git -C "$ROOT" rev-list --count "$commit..HEAD") commit(s) ahead and" \
      "$(git -C "$ROOT" rev-list --count "HEAD..$commit") behind the deployed one."
    live_changes "$commit"
  else
    echo "  The deployed commit is not in this checkout (fetch, or it was never pushed)."
  fi
}

rc=0
for t in "${TARGETS[@]}"; do
  echo "== $t"
  if ! out="$(read_stamp "$t" 2>/dev/null)" || [[ -z "$out" ]]; then
    echo "  No deploy stamp (host unreachable, or no deploy since stamps began)."
    rc=1
    continue
  fi
  printf '%s\n' "$out" | grep -v '^#' | sed 's/^/  /'
  grep -q '^dirty=yes' <<<"$out" && echo "  WARNING: shipped from a checkout with uncommitted changes."
  grep -q '^tables_modified_by_deploy=yes' <<<"$out" &&
    echo "  WARNING: the tables.xml shipped is not the committed one (uncommitted, or rewritten by the deploy gates)."
  if grep -q '^source=redeploy' <<<"$out"; then
    echo "  NOTE: a redeploy of an older commit (tools/hosts/redeploy_commit.sh); deploy from main to go forward."
  elif grep -q '^branch=HEAD$' <<<"$out"; then
    echo "  NOTE: shipped from a detached checkout (a redeploy of a commit older than source=, or by hand)."
  fi
  compare "$(sed -n '/^commit=/{s///;p;q;}' <<<"$out")"
done
exit "$rc"
