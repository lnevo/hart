#!/usr/bin/env bash
# Take a PanelPro Store from ~/JMRI_UserFiles/tables.xml off the Mac (ADR-014, ADR-029, R9d).
#
# tables.xml is an output (tools/schematic/build_tables.py writes it from its sources), so a Store is never copied
# over it. The Store counts as changed when it differs from what was last deployed or pulled (the newer of
# ~/JMRI_UserFiles/.tables_deployed.sha256 and the deploy stamp's tables_sha256, as tools/hosts/pi/unpulled_changes.sh
# reads them; with neither, the generated tables.xml; a Store already split in, store_splits.csv, is not changed). A
# changed Store is kept as mac-<date>.xml in the pulled folder (~/JMRI_UserFiles-pulled, or HART_PULLED_DIR: outside
# every checkout, profile_tables_guard.sh hart_pulled_dir), once per hash, with STORE.base beside it
# (tools/hosts/pi/tables_base.sh). It is not recorded as taken: the deploy stays stopped until
# tools/schematic/split_store.py has split it into the sources in a task worktree and that is merged.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UF="${HOME}/JMRI_UserFiles"
SRC="$UF/tables.xml"
GENERATED="$ROOT/jmri/layouts/hart/output/tables.xml"
source "$ROOT/tools/hosts/profile_tables_guard.sh"

if [[ ! -f "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 1
fi
generated_sha="$(shasum -a 256 "$GENERATED" | cut -d' ' -f1)"
# shellcheck disable=SC2046
unpulled="$(bash "$ROOT/tools/hosts/pi/unpulled_changes.sh" "$UF" "$generated_sha" $(hart_split_shas "$ROOT"))" \
  || { echo "Could not check $SRC against what was last deployed; nothing pulled." >&2; exit 1; }
if ! grep -qx tables <<<"$unpulled"; then
  echo "Nothing to pull: $SRC is what was last deployed, or a Store already split in (store_splits.csv)."
  exit 0
fi
tmp="$(mktemp "${TMPDIR:-/tmp}/mac-tables.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
cp "$SRC" "$tmp"
[[ "$(shasum -a 256 "$SRC" | cut -d' ' -f1)" == "$(shasum -a 256 "$tmp" | cut -d' ' -f1)" ]] \
  || { echo "$SRC changed while it was copied (a Store?); nothing pulled; pull again." >&2; exit 1; }
python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$tmp" \
  || { echo "$SRC does not parse (a Store still writing?); nothing pulled." >&2; exit 1; }
base="$(bash "$ROOT/tools/hosts/pi/tables_base.sh" "$UF")"
PULLED="$(hart_pulled_dir)" || exit 1
saved="$(hart_keep_store "$tmp" "$PULLED" mac "$base")" || exit 1
base="$(<"$saved.base")"   # a Store kept before keeps the base it was kept with
cat <<EOF
Pulled: the Store is kept as $saved (outside every checkout), its base ($base) in $saved.base.
It is not recorded as taken: deploys to the Mac stay stopped until its split is merged.
Next, in a task worktree (make wt TOPIC=store-split): python3 tools/schematic/split_store.py $saved
That reports what goes into the template, what needs the owner's merge or drop, and what the repo keeps.
EOF
