#!/usr/bin/env bash
# Bring a PanelPro Store made on the Pi into the repo (ADR-014). The Pi's JMRI_UserFiles/tables.xml
# is copied over the repo file, and the Pi's .tables_deployed.sha256 is rewritten so the next
# deploy no longer stops on it. A running PanelPro does not stop the pull: JMRI writes the file
# only on a Store, so let any Store finish first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
UF="$HART_PI_USERFILES"
DEST="$ROOT/jmri/layouts/hart/output/tables.xml"

tmp="$(mktemp "${TMPDIR:-/tmp}/pi-tables.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
scp -q "$PI_HOST:$UF/tables.xml" "$tmp"
[[ -s "$tmp" ]] || { echo "The Pi's $UF/tables.xml is empty or missing; nothing pulled." >&2; exit 1; }
python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$tmp" \
  || { echo "The Pi's tables.xml does not parse (a Store still writing?); nothing pulled." >&2; exit 1; }
if cmp -s "$tmp" "$DEST"; then
  echo "Repo tables.xml already matches the Pi's"
else
  cp -f "$tmp" "$DEST"
  echo "Pi tables.xml -> $DEST. Run ./tools/check.sh, then commit."
fi
ssh "$PI_HOST" "cd '$UF' && sha256sum tables.xml | cut -d' ' -f1 >.tables_deployed.sha256"
