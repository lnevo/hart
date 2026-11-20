#!/usr/bin/env bash
# Take a PanelPro Store from ~/JMRI_UserFiles/tables.xml off the Mac (ADR-014, ADR-029).
#
# tables.xml is an output (tools/schematic/build_tables.py writes it from its sources), so a Store is never copied
# over it. The Store counts as changed when it differs from what was last deployed or pulled (the newer of
# ~/JMRI_UserFiles/.tables_deployed.sha256 and the deploy stamp's tables_sha256, as tools/hosts/pi/unpulled_changes.sh
# reads them). A changed Store is kept in the gitignored jmri/layouts/hart/output/pulled/mac-<date>.xml and, once
# that copy is safely saved, recorded as taken (.tables_deployed.sha256), so the next deploy goes ahead and replaces
# the profile's file with the generated one. The owner's PanelPro edits are then only in the kept file: carry them
# into devices.csv or the template before that deploy (R9d's pull will split a Store automatically).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UF="${HOME}/JMRI_UserFiles"
SRC="$UF/tables.xml"
PULLED="$ROOT/jmri/layouts/hart/output/pulled"

if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi
if [[ -z "$(bash "$ROOT/tools/hosts/pi/unpulled_changes.sh" "$UF" | grep -x tables || true)" ]]; then
  echo "Nothing to pull: $SRC is what was last deployed or pulled."
  exit 0
fi
python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$SRC" \
  || { echo "$SRC does not parse (a Store still writing?); nothing pulled." >&2; exit 1; }
mkdir -p "$PULLED"
saved="$PULLED/mac-$(date +%Y%m%d-%H%M%S).xml"
cp "$SRC" "$saved"
sha="$(shasum -a 256 "$saved" | cut -d' ' -f1)"
# Record it as taken only once the kept copy is the file read (a Store after the copy still counts as unpulled).
[[ "$(shasum -a 256 "$SRC" | cut -d' ' -f1)" == "$sha" ]] \
  || { echo "$SRC changed while it was copied (a Store?); kept ${saved#"$ROOT"/} but not recorded as taken; pull again." >&2; exit 1; }
echo "$sha" >"$UF/.tables_deployed.sha256"
cat <<EOF
Pulled: the Store is kept as ${saved#"$ROOT"/} (gitignored) and recorded as taken.
The owner's PanelPro edits are in that file only: carry them into devices.csv or the template
(jmri/layouts/hart/data/) and run python3 tools/schematic/build_tables.py before the next deploy.
R9d's pull will do this split automatically. The next deploy replaces ~/JMRI_UserFiles/tables.xml with the
generated tables.xml.
EOF
