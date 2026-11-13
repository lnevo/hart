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
  printf '%s\n' "$out" | grep -q '^dirty=yes' && echo "  WARNING: shipped from a checkout with uncommitted changes."
  printf '%s\n' "$out" | grep -q '^tables_modified_by_deploy=yes' &&
    echo "  WARNING: the tables.xml shipped is not the committed one (uncommitted, or rewritten by the deploy gates)."
  compare "$(printf '%s\n' "$out" | sed -n 's/^commit=//p' | head -1)"
done
exit "$rc"
