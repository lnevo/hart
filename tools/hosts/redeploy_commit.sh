#!/usr/bin/env bash
# Redeploy an earlier commit to the layout hosts (a rollback), with that commit's own deploy.
#
# Usage: tools/hosts/redeploy_commit.sh <commit> [--pi] [--win] [--all] [--mac] [--dry-run] [--stage-only DIR] [--allow-unmerged]
#        make redeploy COMMIT=<commit> HOSTS="--pi"
#
# It makes a temporary detached git worktree at <commit>, runs that commit's own
# tools/hosts/sync_hart_package.sh from it with a clean environment and this checkout's
# host settings, then removes the worktree. The hosts get exactly what a deploy of that
# commit would have sent. From this version on the stamp says source=redeploy and
# redeploy_from=<the commit this checkout is on>; older commits' stamps say branch=HEAD.
#
# Guards:
#   - The commit must be on origin/main (git fetch first); --allow-unmerged permits others.
#   - It must have tools/hosts/sync_hart_package.sh with the deploy stamp (ADR-007
#     amendment 2026-11-12). Older commits are refused.
#   - A PanelPro Store in ~/JMRI_UserFiles/tables.xml that is not pulled stops it: run
#     make tables-pull first. HART_OVERWRITE_PROFILE_TABLES=1 overrides, as for a deploy.
#   - Operations Pro files keep their guards (HART_OVERWRITE_OPS=0): a Pi session that is
#     not pulled stops the Pi step (run make ops-pull), and a running JMRI keeps its files.
#     HART_OVERWRITE_OPS=1 replaces them as a normal deploy does (a backup is kept).
#   - With --pi or --all, Operations Pro files or a tables.xml Store changed on the Pi since the
#     last deploy or pull stop it (make ops-pull, make tables-pull-pi). HART_DISCARD_PI_CHANGES=1
#     replaces them.
#   - With --pi, --win or --all, every host named must answer over ssh before anything is built or
#     sent, as for a deploy (older commits' own deploys lack that check).
#
# --mac installs on the Mac only. --dry-run and --stage-only DIR are passed through;
# --stage-only needs no network. The commit a host has now: make deploy-status. The stamp
# keeps no history, so the commit before it comes from git log --first-parent origin/main.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
refuse_hart_tables "deploy"
refuse_unrestored_profile "deploy"
SYNC_REL="tools/hosts/sync_hart_package.sh"
TABLES_REL="jmri/layouts/hart/output/tables.xml"

usage() { sed -n '4,5p' "$0" | sed 's/^# \{0,1\}//'; }

COMMIT=""
PASS=()
HOST_FLAG=0
MAC=0
STAGE_ONLY=""
DRY_RUN=0
ALLOW_UNMERGED=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pi|--win|--all) PASS+=("$1"); HOST_FLAG=1 ;;
    --mac) MAC=1; HOST_FLAG=1 ;;
    --dry-run) PASS+=("$1"); DRY_RUN=1 ;;
    --allow-unmerged) ALLOW_UNMERGED=1 ;;
    --stage-only)
      [[ $# -ge 2 && -n "$2" ]] || { echo "--stage-only needs a folder" >&2; exit 2; }
      STAGE_ONLY="$2"; shift ;;
    --stage-only=*)
      STAGE_ONLY="${1#*=}"
      [[ -n "$STAGE_ONLY" ]] || { echo "--stage-only needs a folder" >&2; exit 2; } ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    *)
      [[ -z "$COMMIT" ]] || { echo "One commit only (got $COMMIT and $1)" >&2; exit 2; }
      COMMIT="$1" ;;
  esac
  shift
done
[[ -n "$COMMIT" ]] || { usage >&2; exit 2; }
if [[ -z "$STAGE_ONLY" && "$HOST_FLAG" -eq 0 ]]; then
  echo "Name the hosts: --pi, --win, --all, or --mac for the Mac only (or --stage-only DIR)." >&2
  exit 2
fi
if [[ "$MAC" -eq 1 ]]; then
  # sync_hart_package.sh with no flag is the Mac install; with other flags it needs its own.
  if [[ "$DRY_RUN" -eq 1 && ${#PASS[@]} -eq 1 ]]; then
    echo "The deploy has no dry run for the Mac install, so --mac --dry-run would show nothing." >&2
    exit 2
  fi
  [[ ${#PASS[@]} -eq 0 ]] || PASS+=(--mac-web-only)
fi
if [[ -n "$STAGE_ONLY" ]]; then
  [[ "$STAGE_ONLY" == /* ]] || STAGE_ONLY="$PWD/$STAGE_ONLY"
  PASS+=(--stage-only "$STAGE_ONLY")
fi
REAL=0
[[ -n "$STAGE_ONLY" || "$DRY_RUN" -eq 1 ]] || REAL=1

SHA="$(git -C "$ROOT" rev-parse --verify --quiet "${COMMIT}^{commit}" || true)"
if [[ -z "$SHA" ]]; then
  echo "REFUSED: $COMMIT is not a commit in this checkout (git fetch origin, or check the hash)." >&2
  exit 1
fi
SHORT="${SHA:0:12}"
if [[ "$ALLOW_UNMERGED" -eq 0 ]]; then
  if ! git -C "$ROOT" rev-parse --verify --quiet origin/main >/dev/null; then
    echo "REFUSED: no origin/main here to check $SHORT against; git fetch first (or --allow-unmerged)." >&2
    exit 1
  fi
  if ! git -C "$ROOT" merge-base --is-ancestor "$SHA" origin/main; then
    echo "REFUSED: $SHORT is not on origin/main (git fetch first if it was merged). --allow-unmerged deploys it anyway." >&2
    exit 1
  fi
fi
if ! git -C "$ROOT" cat-file -e "$SHA:$SYNC_REL" 2>/dev/null; then
  echo "REFUSED: $SHORT has no $SYNC_REL. It predates the deploy's move to tools/hosts/" \
    "(ADR-007 amendment 2026-11-12), so it cannot be redeployed with this script." >&2
  exit 1
fi
# grep reads to the end: with -q it stops at the match, git can die of SIGPIPE, and pipefail refuses a good commit.
if ! git -C "$ROOT" show "$SHA:$SYNC_REL" | grep 'write_deploy_stamp' >/dev/null; then
  echo "REFUSED: $SHORT predates the deploy stamp (cats/deploy_stamp.txt), so make deploy-status" \
    "could not tell what the hosts run. Pick a later commit." >&2
  exit 1
fi

BASE="$(mktemp -d "${TMPDIR:-/tmp}/hart-redeploy.XXXXXX")"
WT="$BASE/hart"
cleanup() {
  [[ -d "$WT" ]] && git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1
  git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
  rm -rf "$BASE"
}
trap cleanup EXIT

# A real Mac install replaces ~/JMRI_UserFiles/tables.xml. Stop here, before anything is
# built, if it holds a Store that is not pulled (the test sync_hart_package.sh makes).
if [[ "$REAL" -eq 1 ]]; then
  git -C "$ROOT" show "$SHA:$TABLES_REL" >"$BASE/tables.xml" 2>/dev/null || : >"$BASE/tables.xml"
  if profile_tables_unpulled "$BASE/tables.xml" "$HOME/JMRI_UserFiles"; then
    echo "STOP: $HOME/JMRI_UserFiles/tables.xml changed since the last deploy (a PanelPro Store?). Run make" \
      "tables-pull and commit it first; a redeploy would replace it. HART_OVERWRITE_PROFILE_TABLES=1 discards it." >&2
    exit 1
  fi
fi

# The old commit runs with a clean environment: the basics a deploy needs, the deploy's own
# switches, and the host settings as this checkout resolves them (environment, hart.env,
# defaults), named by load_env.sh's own list. hart.env is gitignored, so the worktree has none,
# and nothing the caller's shell exported (repo roots, STS paths) can point it back here.
if ! hosts="$(bash -c 'set -eu; source "$1/tools/env/load_env.sh"
    for n in $HART_HOST_NAMES; do [[ -z "${!n:-}" ]] || printf "%s=%s\n" "$n" "${!n}"; done' _ "$ROOT")" \
    || [[ -z "$hosts" ]]; then
  echo "REFUSED: could not read the host settings from tools/env/load_env.sh (see above)." >&2
  exit 1
fi
CHILD_ENV=(PATH="$PATH" HOME="$HOME" HART_ENV_FILE="$BASE/no-hart.env"
           HART_OVERWRITE_OPS="${HART_OVERWRITE_OPS:-0}" HART_REDEPLOY_FROM="$(git -C "$ROOT" rev-parse HEAD)")
for n in USER LOGNAME TERM LANG LC_ALL TMPDIR SSH_AUTH_SOCK HART_OVERWRITE_PROFILE_TABLES HART_PI_RESTART HART_DISCARD_PI_CHANGES MIMIC_PORT; do
  [[ -z "${!n:-}" ]] || CHILD_ENV+=("$n=${!n}")
done
while IFS= read -r line; do
  [[ -n "$line" ]] && CHILD_ENV+=("$line")
done <<<"$hosts"

# This checkout's checks, run before the old commit's deploy (older commits lack them): stop if a
# host named does not answer over ssh, or if the owner changed Operations Pro files or stored
# tables.xml on the Pi since the last deploy or pull.
CHECK_HOSTS=()
for a in ${PASS[@]+"${PASS[@]}"}; do  # bash 3.2: an empty array is unbound under set -u
  if [[ "$a" == --pi || "$a" == --win || "$a" == --all ]]; then CHECK_HOSTS+=("$a"); fi
done
if [[ "$REAL" -eq 1 && ${#CHECK_HOSTS[@]} -gt 0 ]]; then
  bash "$ROOT/$SYNC_REL" --check-only "${CHECK_HOSTS[@]}" || exit 1
fi

echo "Redeploy $SHORT: temporary worktree $WT (detached)"
git -C "$ROOT" worktree add -q --detach "$WT" "$SHA"
# The deploy audit places masts by the schematic-maps plugin (a submodule). A new worktree has none checked out, so
# check out the commit's own pin from this repo's module store; stop if that fails rather than audit without it.
if git -C "$WT" config -f .gitmodules --get submodule.external/model-railroad-skills.path >/dev/null 2>&1; then
  git -C "$WT" submodule update --init -q external/model-railroad-skills \
    || { echo "Redeploy $SHORT: cannot check out external/model-railroad-skills in $WT" >&2; exit 1; }
fi

rc=0
env -i "${CHILD_ENV[@]}" bash "$WT/$SYNC_REL" ${PASS[@]+"${PASS[@]}"} || rc=$?
if [[ "$rc" -ne 0 ]]; then
  echo "Redeploy of $SHORT failed (exit $rc). See the output above; make deploy-status shows what each host has." >&2
elif [[ -n "$STAGE_ONLY" ]]; then
  echo "Staged $SHORT into $STAGE_ONLY (nothing deployed)."
else
  echo "Redeployed $SHORT. Go forward again with make deploy-layout (or deploy-all) from main."
fi
exit "$rc"
