#!/usr/bin/env bash
# Redeploy an earlier commit to the layout hosts (a rollback), with that commit's own deploy.
#
# Usage: tools/hosts/redeploy_commit.sh <commit> [--pi] [--win] [--all] [--mac] [--dry-run] [--stage-only DIR]
#        make redeploy COMMIT=<commit> HOSTS="--pi"
#
# It makes a temporary git worktree at <commit> on the branch redeploy/<sha12>, links the
# gitignored mirrors as make wt does, runs that commit's tools/hosts/sync_hart_package.sh
# from it, then removes the worktree and the branch. The hosts get exactly what a deploy
# of that commit would have sent; the stamp says branch=redeploy/<sha12>, and from this
# version on also source=redeploy and redeploy_from=<the commit this checkout is on>.
#
# Guards:
#   - The commit must have tools/hosts/sync_hart_package.sh with the deploy stamp (ADR-007
#     amendment 2026-11-12). Older commits are refused.
#   - A PanelPro Store in ~/JMRI_UserFiles/tables.xml that is not pulled stops it: run
#     make tables-pull first. HART_OVERWRITE_PROFILE_TABLES=1 overrides, as for a deploy.
#   - Operations Pro files keep their guards (HART_OVERWRITE_OPS=0): a Pi session that is
#     not pulled stops the Pi step (run make ops-pull), and a running JMRI keeps its files.
#     HART_OVERWRITE_OPS=1 replaces them as a normal deploy does (a backup is kept).
#
# --mac installs on the Mac only (sync_hart_package.sh with no host flag). --dry-run and
# --stage-only DIR are passed through; --stage-only needs no network.
# The commit a host has now: make deploy-status. The stamp keeps no history, so the commit
# before it comes from git: git log --first-parent --oneline origin/main.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SYNC_REL="tools/hosts/sync_hart_package.sh"
TABLES_REL="jmri/layouts/hart/output/tables.xml"

usage() { sed -n '4,5p' "$0" | sed 's/^# \{0,1\}//'; }

COMMIT=""
PASS=()
HOST_FLAG=0
STAGE_ONLY=""
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pi|--win|--all) PASS+=("$1"); HOST_FLAG=1 ;;
    --mac) HOST_FLAG=1 ;;
    --dry-run) PASS+=("$1"); DRY_RUN=1 ;;
    --stage-only)
      [[ $# -ge 2 && -n "$2" ]] || { echo "--stage-only needs a folder" >&2; exit 2; }
      STAGE_ONLY="$2"; shift ;;
    --stage-only=*)
      STAGE_ONLY="${1#*=}"
      [[ -n "$STAGE_ONLY" ]] || { echo "--stage-only needs a folder" >&2; exit 2; } ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
if [[ -n "$STAGE_ONLY" ]]; then
  [[ "$STAGE_ONLY" == /* ]] || STAGE_ONLY="$PWD/$STAGE_ONLY"
  PASS+=(--stage-only "$STAGE_ONLY")
fi

SHA="$(git -C "$ROOT" rev-parse --verify --quiet "${COMMIT}^{commit}" || true)"
if [[ -z "$SHA" ]]; then
  echo "REFUSED: $COMMIT is not a commit in this checkout (git fetch origin, or check the hash)." >&2
  exit 1
fi
SHORT="${SHA:0:12}"
if ! git -C "$ROOT" cat-file -e "$SHA:$SYNC_REL" 2>/dev/null; then
  echo "REFUSED: $SHORT has no $SYNC_REL. It predates the deploy's move to tools/hosts/" \
    "(ADR-007 amendment 2026-11-12), so it cannot be redeployed with this script." >&2
  exit 1
fi
if ! git -C "$ROOT" show "$SHA:$SYNC_REL" | grep -q 'write_deploy_stamp'; then
  echo "REFUSED: $SHORT predates the deploy stamp (cats/deploy_stamp.txt), so make deploy-status" \
    "could not tell what the hosts run. Pick a later commit." >&2
  exit 1
fi
if git -C "$ROOT" rev-parse --verify --quiet origin/main >/dev/null \
    && ! git -C "$ROOT" merge-base --is-ancestor "$SHA" origin/main 2>/dev/null; then
  echo "WARNING: $SHORT is not on origin/main." >&2
fi

# A real Mac install replaces ~/JMRI_UserFiles/tables.xml. Stop here, before anything is
# built, if it holds a Store that is not pulled (the same test sync_hart_package.sh makes).
if [[ -z "$STAGE_ONLY" && "$DRY_RUN" -eq 0 ]]; then
  dest="$HOME/JMRI_UserFiles/tables.xml"
  stamp="$HOME/JMRI_UserFiles/.tables_deployed.sha256"
  if [[ -f "$dest" && -f "$stamp" && "${HART_OVERWRITE_PROFILE_TABLES:-0}" != "1" ]] \
      && [[ "$(shasum -a 256 "$dest" | cut -d' ' -f1)" != "$(cat "$stamp")" ]] \
      && ! git -C "$ROOT" show "$SHA:$TABLES_REL" 2>/dev/null | cmp -s - "$dest"; then
    echo "STOP: $dest changed since the last deploy (a PanelPro Store?). Run make tables-pull and" \
      "commit it first; a redeploy would replace it. HART_OVERWRITE_PROFILE_TABLES=1 discards it." >&2
    exit 1
  fi
fi

# Host settings as this checkout resolves them (environment, hart.env, defaults). hart.env
# is gitignored, so the old commit's worktree has none: it gets the values instead.
HOST_NAMES=(HART_MQTT_BROKER HART_MQTT_PORT HART_JMRI_JSON HART_PI_SSH HART_PI_USERFILES
            HART_WIN_SSH HART_WIN_SSH_PORT HART_WIN_USERFILES HART_PI_WEB_HOST)
HOST_ENV=()
while IFS= read -r line; do
  [[ -n "$line" ]] && HOST_ENV+=("$line")
done < <(bash -c 'source "$1/tools/env/load_env.sh"; shift; for n in "$@"; do printf "%s=%s\n" "$n" "${!n-}"; done' \
  _ "$ROOT" "${HOST_NAMES[@]}")
# Paths load_env.sh derives from a repo root: unset, so the old worktree derives its own.
PATH_NAMES=(HART_REPO_ROOT HART_RUNTIME_ROOT HART_LIVE_ROOT HART_OPS_ROOT LCOS_BRIDGE_ROOT
            STS_DOCKER_ROOT STS_HELPERS_ROOT STS_DATA_ROOT STS_BACKUPS_DIR STS_DATABASE_DIR
            STS_IMAGES_DIR HART_CAR_CARDS_ROOT HART_CAR_IMAGES_FINAL HART_STS_HELPERS STS_DOCKER
            _hart_env_loaded MQTT_HOST HART_MQTT_HOST JMRI_JSON)
UNSET=()
for n in "${PATH_NAMES[@]}"; do UNSET+=(-u "$n"); done

BASE="$(mktemp -d "${TMPDIR:-/tmp}/hart-redeploy.XXXXXX")"
WT="$BASE/hart"
BRANCH="redeploy/$SHORT"
FROM="$(git -C "$ROOT" rev-parse HEAD)"
MAIN="$(git -C "$ROOT" worktree list --porcelain | sed -n '1s/^worktree //p')"

cleanup() {
  git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
  git -C "$ROOT" branch -D "$BRANCH" >/dev/null 2>&1 || true
  git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
  rm -rf "$BASE"
}
trap cleanup EXIT

git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
echo "Redeploy $SHORT: temporary worktree $WT on $BRANCH"
git -C "$ROOT" worktree add -q -B "$BRANCH" "$WT" "$SHA"
# The mirrors make wt links, and their info/exclude lines, so the stamp says dirty=no.
python3 - "$ROOT/tools/agent/worktrees.py" "$MAIN" "$WT" <<'PY' || echo "WARNING: mirror links not made" >&2
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("hart_worktrees", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
main, wt = Path(sys.argv[2]), Path(sys.argv[3])
w.exclude_mirrors(main)
for rel in w.MIRRORS:
    src, dst = main / rel, wt / rel
    if src.exists() and not dst.exists() and dst.parent.is_dir():
        dst.symlink_to(src)
PY

rc=0
env "${UNSET[@]}" "${HOST_ENV[@]}" \
  HART_ENV_FILE="$BASE/no-hart.env" \
  HART_OVERWRITE_OPS="${HART_OVERWRITE_OPS:-0}" \
  HART_REDEPLOY_FROM="$FROM" \
  bash "$WT/$SYNC_REL" ${PASS[@]+"${PASS[@]}"} || rc=$?
if [[ "$rc" -ne 0 ]]; then
  echo "Redeploy of $SHORT failed (exit $rc). See the output above; make deploy-status shows what each host has." >&2
elif [[ -n "$STAGE_ONLY" ]]; then
  echo "Staged $SHORT into $STAGE_ONLY (nothing deployed)."
else
  echo "Redeployed $SHORT. Go forward again with make deploy-layout (or deploy-all) from main."
fi
exit "$rc"
