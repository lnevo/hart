#!/usr/bin/env bash
# Publish the public portal build to www.hartrailroad.com (VestaCP/nginx on www.easte.net).
# Builds with prepare_github_pages.py, smoke-tests links (check_portal_build.py), and stops
# if archive/logo/gallery counts fell more than 10% since the last deploy (--force overrides).
# Vesta's robots.txt is left in place.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(git -C "$ROOT" rev-parse --show-toplevel)"
# Default: the rsync-only deploy key (~/.ssh/config "Host hart-deploy"), whose forced rrsync command
# roots paths at the docroot. HART_WEB_HOST=www.easte.net uses a normal login and the absolute path.
if [[ -n "${HART_WEB_HOST:-}" ]]; then
  DEST="$HART_WEB_HOST:/home/lnevo/web/hartrailroad.com/public_html/"
else
  DEST="hart-deploy:"
fi
# macOS /usr/bin/rsync is openrsync, which the server's rrsync rejects; prefer Homebrew rsync.
RSYNC="$(command -v /opt/homebrew/bin/rsync || command -v rsync)"
if [[ "$DEST" == hart-deploy:* ]] && "$RSYNC" --version 2>&1 | grep -qi openrsync; then
  echo "Refusing to deploy: $RSYNC is openrsync, which the deploy key's rrsync rejects. Run: brew install rsync" >&2
  echo "(or HART_WEB_HOST=www.easte.net $0 to deploy with a normal login)" >&2
  exit 1
fi
# Last deploy's counts; gitignored, outside the docroot.
MANIFEST="$ROOT/../.deploy-manifest.json"
FORCE=""
for arg in "$@"; do
  case "$arg" in
    --force) FORCE="--allow-drop" ;;
    *) echo "usage: $0 [--force]" >&2; exit 2 ;;
  esac
done

# Industry logos come from ops/hart-ops; without them rsync --delete removes them live.
if [[ ! -d "$REPO/ops/hart-ops/operator_logos" ]]; then
  echo "Refusing to deploy: ops/hart-ops/operator_logos is missing." >&2
  exit 1
fi
# Work-in-progress deploys are deliberate, so this only warns.
if [[ -n "$(git -C "$ROOT" status --porcelain -- .)" ]]; then
  echo "Warning: the portal has uncommitted changes; untracked files are not published." >&2
fi

DIST="$(mktemp -d)/hart-dist"
trap 'rm -rf "$(dirname "$DIST")"' EXIT
python3 "$ROOT/scripts/prepare_github_pages.py" "$DIST"
python3 "$ROOT/scripts/check_portal_build.py" --dist "$DIST" \
  --manifest "$(dirname "$DIST")/manifest.json" --previous "$MANIFEST" $FORCE
chmod -R u+rwX,go+rX,go-w "$DIST"
"$RSYNC" -az --delete --exclude robots.txt "$DIST/" "$DEST"
cp "$(dirname "$DIST")/manifest.json" "$MANIFEST"
echo "Deployed → https://www.hartrailroad.com/"
