#!/usr/bin/env bash
# Publish the public portal build to www.hartrailroad.com (VestaCP/nginx on www.easte.net).
# Same tree as GitHub Pages (prepare_github_pages.py); Vesta's robots.txt is left in place.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${HART_WEB_HOST:-www.easte.net}"
DOCROOT="/home/lnevo/web/hartrailroad.com/public_html/"
DIST="$(mktemp -d)/hart-dist"
trap 'rm -rf "$(dirname "$DIST")"' EXIT
python3 "$ROOT/scripts/prepare_github_pages.py" "$DIST"
rm -f "$DIST/.nojekyll"
chmod -R u+rwX,go+rX,go-w "$DIST"
rsync -az --delete --exclude robots.txt "$DIST/" "$HOST:$DOCROOT"
echo "Deployed → http://www.hartrailroad.com/"
