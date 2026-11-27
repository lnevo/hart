#!/usr/bin/env bash
# Publish the public portal build to www.hartrailroad.com. Server details are in the owner's private notes
# (private/web-server/ in the main checkout, gitignored), not in the repo.
# Builds with prepare_github_pages.py, smoke-tests links (check_portal_build.py), and stops
# if a count (files, pages, share cards, archive, logos, gallery, fleet) fell more than 10%
# since the last deploy (--force overrides). ADR-040: one deploy at a time (a lock in the
# shared git dir), never from a checkout behind origin/main (--allow-behind overrides), and
# the last deploy's commit, branch, dirty flag, worktree and time are kept in the manifest
# (make orient shows them; --status prints them). It stops before the build when main's push run of check.yml for
# HEAD ended red (tools/hosts/deploy/ci_pass.py --main-red).
# robots.txt, llms.txt and sitemap.xml come from the build (they replace the panel's robots.txt).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(git -C "$ROOT" rev-parse --show-toplevel)"
# Default: the rsync-only deploy alias (~/.ssh/config "Host hart-deploy"), whose forced rrsync command
# roots paths at the docroot. HART_WEB_HOST=<admin host> with HART_WEB_DOCROOT=<docroot path> uses a
# normal login and the absolute path; both values are in the private notes.
if [[ -n "${HART_WEB_HOST:-}" ]]; then
  if [[ -z "${HART_WEB_DOCROOT:-}" ]]; then
    echo "HART_WEB_HOST needs HART_WEB_DOCROOT (the site's docroot, in the private notes)" >&2
    exit 2
  fi
  DEST="$HART_WEB_HOST:${HART_WEB_DOCROOT%/}/"
else
  DEST="hart-deploy:"
fi
# macOS /usr/bin/rsync is openrsync, which the server's rrsync rejects; prefer Homebrew rsync.
RSYNC="$(command -v /opt/homebrew/bin/rsync || command -v rsync)"
if [[ "$DEST" == hart-deploy:* ]] && "$RSYNC" --version 2>&1 | grep -i openrsync >/dev/null; then
  echo "Refusing to deploy: $RSYNC is openrsync, which the deploy key's rrsync rejects. Run: brew install rsync" >&2
  echo "(or set HART_WEB_HOST and HART_WEB_DOCROOT to deploy with a normal login)" >&2
  exit 1
fi
# Last deploy's counts; gitignored, outside the docroot. Kept at the main checkout's root
# (via the shared git dir) so a deploy from any worktree compares with the same record.
COMMON="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
MANIFEST="$(cd "$COMMON/.." && pwd)/.deploy-manifest.json"
FORCE=""
ALLOW_BEHIND=""
for arg in "$@"; do
  case "$arg" in
    --force) FORCE="--allow-drop" ;;
    --allow-behind) ALLOW_BEHIND=1 ;;
    --status)
      if [[ -f "$MANIFEST" ]]; then cat "$MANIFEST"; else echo "No deploy record at $MANIFEST"; fi
      exit 0 ;;
    *) echo "usage: $0 [--force] [--allow-behind] [--status]" >&2; exit 2 ;;
  esac
done

# One deploy at a time across every worktree: rsync --delete from two builds would interleave.
# The lock is a directory that holds the owner's PID from the moment it exists: it is built
# under a private name and renamed into place (rename onto a non-empty directory fails, so
# only one deploy wins). A lock whose PID is gone is renamed aside, and checked, before it is taken.
LOCK="$COMMON/hart-site-deploy.lock"
rename() { python3 -c 'import os, sys; os.rename(sys.argv[1], sys.argv[2])' "$1" "$2" 2>/dev/null; }
take_lock() {
  local mine="$LOCK.new.$$"
  rm -rf "$mine"; mkdir "$mine"; echo $$ >"$mine/pid"; echo "$ROOT" >"$mine/where"
  rename "$mine" "$LOCK" || { rm -rf "$mine"; return 1; }
}
if ! take_lock; then
  holder="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [[ -z "$holder" ]] || kill -0 "$holder" 2>/dev/null; then
    echo "Refusing to deploy: another site deploy is running (PID ${holder:-?}, $(cat "$LOCK/where" 2>/dev/null || echo '?'))." >&2
    exit 1
  fi
  aside="$LOCK.stale.$$"
  if ! rename "$LOCK" "$aside" || [[ "$(cat "$aside/pid" 2>/dev/null)" != "$holder" ]]; then
    [[ -d "$aside" ]] && rename "$aside" "$LOCK"  # it was not the stale lock: put it back
    echo "Refusing to deploy: another deploy took the lock at the same moment." >&2
    exit 1
  fi
  rm -rf "$aside"
  echo "Took over a stale deploy lock (PID $holder is gone)." >&2
  take_lock || { echo "Refusing to deploy: another deploy took the lock at the same moment." >&2; exit 1; }
fi
WORK=""
cleanup() { [[ -n "$WORK" ]] && rm -rf "$WORK"; rm -rf "$LOCK"; }
trap cleanup EXIT

# Industry logos come from ops/hart-ops; without them rsync --delete removes them live.
if [[ ! -d "$REPO/ops/hart-ops/operator_logos" ]]; then
  echo "Refusing to deploy: ops/hart-ops/operator_logos is missing." >&2
  exit 1
fi
# rsync --delete replaces the whole site, so a checkout that lacks a commit on origin/main
# would take that commit's pages off the site.
if ! git -C "$ROOT" fetch --quiet origin main; then
  if [[ -z "$ALLOW_BEHIND" ]]; then
    echo "Refusing to deploy: cannot fetch origin/main to check this checkout is current (--allow-behind skips)." >&2
    exit 1
  fi
  echo "Warning: origin/main not fetched; deploying without the up-to-date check." >&2
elif ! git -C "$ROOT" merge-base --is-ancestor origin/main HEAD; then
  missing="$(git -C "$ROOT" rev-list --count HEAD..origin/main)"
  in_www="$(git -C "$ROOT" rev-list --count HEAD..origin/main -- .)"
  if [[ -z "$ALLOW_BEHIND" ]]; then
    echo "Refusing to deploy: HEAD lacks $missing commit(s) on origin/main, $in_www of them under www/; a deploy would take those off the site." >&2
    echo "Merge or pull origin/main first, or pass --allow-behind." >&2
    exit 1
  fi
  echo "Warning: HEAD lacks $missing commit(s) on origin/main, $in_www of them under www/; deploying anyway (--allow-behind)." >&2
fi
BRANCH="$(git -C "$ROOT" symbolic-ref --quiet --short HEAD || echo detached)"
COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
# Main is not red (the owner's rule), as the layout deploy's G0c (tools/hosts/deploy/gate.sh): a finished push run of
# check.yml on main for HEAD that ended failure, cancelled or timed_out stops here, before the build and the upload.
# A run still going, a pass, any other ending, no run yet (a branch) or GitHub not answering do not block.
main_red_rc=0
main_red_line="$(python3 "$REPO/tools/hosts/deploy/ci_pass.py" --main-red --commit "$COMMIT")" || main_red_rc=$?
case "$main_red_rc" in
  0) echo "$main_red_line" ;;
  4) echo "$main_red_line" >&2; exit 1 ;;
  *) echo "main red check: could not check ${COMMIT:0:12} (exit $main_red_rc)${main_red_line:+: $main_red_line}; not blocking (owner ruling 2026-11-27)" >&2 ;;
esac
DIRTY=no
# Work-in-progress deploys are deliberate, so these only warn.
if [[ -n "$(git -C "$ROOT" status --porcelain -- .)" ]]; then
  DIRTY=yes
  echo "Warning: the portal has uncommitted changes; untracked files are not published." >&2
fi
if [[ "$BRANCH" != main ]]; then
  echo "Warning: deploying from $BRANCH, not main; the next deploy from main replaces it." >&2
fi
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

WORK="$(mktemp -d)"
DIST="$WORK/hart-dist"
python3 "$ROOT/scripts/prepare_github_pages.py" "$DIST" --require-mirrors
python3 "$ROOT/scripts/check_portal_build.py" --dist "$DIST" \
  --manifest "$WORK/manifest.json" --previous "$MANIFEST" $FORCE
chmod -R u+rwX,go+rX,go-w "$DIST"
"$RSYNC" -az --delete "$DIST/" "$DEST"
# The counts plus what was deployed (ADR-040); make orient reads this record.
COMMIT="$COMMIT" BRANCH="$BRANCH" DIRTY="$DIRTY" WORKTREE="$REPO" STARTED="$STARTED" \
  python3 - "$WORK/manifest.json" "$MANIFEST.new" <<'PY' && mv "$MANIFEST.new" "$MANIFEST" || {
import json, os, sys
from datetime import datetime, timezone
data = json.load(open(sys.argv[1], encoding="utf-8"))
data["deploy"] = {
    "commit": os.environ["COMMIT"], "branch": os.environ["BRANCH"], "dirty": os.environ["DIRTY"] == "yes",
    "worktree": os.environ["WORKTREE"], "started": os.environ["STARTED"],
    "finished": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
with open(sys.argv[2], "w", encoding="utf-8") as out:
    json.dump(data, out, indent=2)
    out.write("\n")
PY
  echo "The site IS deployed, but the deploy record was NOT updated: $MANIFEST still names the previous deploy." >&2
  exit 1
}
echo "Deployed → https://www.hartrailroad.com/"
