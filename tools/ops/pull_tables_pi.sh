#!/usr/bin/env bash
# Bring a PanelPro Store made on the Pi back to the repo (ADR-014, ADR-029). A running PanelPro does not
# stop the pull: JMRI writes the file only on a Store, so let any Store finish first.
#
# tables.xml is an output (tools/schematic/build_tables.py writes it from its sources), so a Store is never
# copied over it. Until R9d splits a Store into the sources, this keeps the Pi's Store in the gitignored
# jmri/layouts/hart/output/pulled/pi-<date>.xml and stops: the owner's PanelPro edits are kept in that file.
# The Pi's .tables_deployed.sha256 is left alone, so the deploy guard keeps blocking until the edits are in
# the sources and deployed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
UF="$HART_PI_USERFILES"
DEST="$ROOT/jmri/layouts/hart/output/tables.xml"
PULLED="$ROOT/jmri/layouts/hart/output/pulled"

tmp="$(mktemp "${TMPDIR:-/tmp}/pi-tables.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
scp -q "$PI_HOST:$UF/tables.xml" "$tmp"
[[ -s "$tmp" ]] || { echo "The Pi's $UF/tables.xml is empty or missing; nothing pulled." >&2; exit 1; }
python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$tmp" \
  || { echo "The Pi's tables.xml does not parse (a Store still writing?); nothing pulled." >&2; exit 1; }
if cmp -s "$tmp" "$DEST"; then
  echo "Repo tables.xml already matches the Pi's"
  exit 0
fi
mkdir -p "$PULLED"
saved="$PULLED/pi-$(date +%Y%m%d-%H%M%S).xml"
cp "$tmp" "$saved"
cat >&2 <<EOF
STOP: the Pi's Store differs from the generated tables.xml, which is never replaced by a Store (ADR-029).
The Store is saved as ${saved#"$ROOT"/} (gitignored); the owner's PanelPro edits are kept in that file.
R9d's pull will split such a Store into devices.csv, the template and the discovered Signal Mast Logic;
until then, carry the edits into those sources by hand and run python3 tools/schematic/build_tables.py.
The Pi's deployed hash is unchanged, so a deploy still stops until the edits reach the sources.
EOF
exit 1
