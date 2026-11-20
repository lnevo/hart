#!/usr/bin/env bash
# Bring a PanelPro Store from ~/JMRI_UserFiles/tables.xml back to the repo (ADR-014, ADR-029).
#
# tables.xml is an output (tools/schematic/build_tables.py writes it from its sources), so a Store is never
# copied over it. Until R9d splits a Store into the sources, this keeps the Store in the gitignored
# jmri/layouts/hart/output/pulled/mac-<date>.xml and stops: the owner's PanelPro edits are kept in that file.
# Nothing in the repo or the profile is changed (the profile's deployed hash stays, so the change still counts
# as unpulled).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${HOME}/JMRI_UserFiles/tables.xml"
DEST="$ROOT/jmri/layouts/hart/output/tables.xml"
PULLED="$ROOT/jmri/layouts/hart/output/pulled"

if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi
if cmp -s "$SRC" "$DEST"; then
  echo "Repo tables.xml already matches $SRC"
  exit 0
fi
mkdir -p "$PULLED"
saved="$PULLED/mac-$(date +%Y%m%d-%H%M%S).xml"
cp "$SRC" "$saved"
cat >&2 <<EOF
STOP: the Store differs from the generated tables.xml, which is never replaced by a Store (ADR-029).
The Store is saved as ${saved#"$ROOT"/} (gitignored); the owner's PanelPro edits are kept in that file.
R9d's pull will split such a Store into devices.csv, the template and the discovered Signal Mast Logic;
until then, carry the edits into those sources by hand and run python3 tools/schematic/build_tables.py.
Nothing in the repo or in ~/JMRI_UserFiles was changed.
EOF
exit 1
