#!/usr/bin/env bash
# Take a PanelPro Store made on the Pi off the Pi (ADR-014, ADR-029, R9d). A running PanelPro does not stop the pull:
# JMRI writes the file only on a Store, so let any Store finish first.
#
# tables.xml is an output (tools/schematic/build_tables.py writes it from its sources), so a Store is never copied
# over it. The Store counts as changed when the deploy's own check says so (tools/hosts/pi/unpulled_changes.sh: the
# Pi's file against the newer of its .tables_deployed.sha256 and the deploy stamp's tables_sha256, with neither the
# generated tables.xml; a Store already split in, store_splits.csv, is not changed). A changed Store is kept as
# pi-<date>.xml in the pulled folder (~/JMRI_UserFiles-pulled, or HART_PULLED_DIR: outside every checkout,
# profile_tables_guard.sh hart_pulled_dir), once per hash, with STORE.base beside it naming what the Pi had before
# the session (tools/hosts/pi/tables_base.sh). It is not recorded as taken: the deploy stays stopped until
# tools/schematic/split_store.py has split it into the sources in a task worktree and that is merged
# (store_splits.csv then names its hash).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
UF="$HART_PI_USERFILES"
GENERATED="$ROOT/jmri/layouts/hart/output/tables.xml"
source "$ROOT/tools/hosts/profile_tables_guard.sh"

generated_sha="$(shasum -a 256 "$GENERATED" | cut -d' ' -f1)"
split_shas="$(hart_split_shas "$ROOT" | tr '\n' ' ' | sed 's/ *$//')"
unpulled="$(ssh "$PI_HOST" "bash -s -- '$UF' '$generated_sha'${split_shas:+ $split_shas}" <"$ROOT/tools/hosts/pi/unpulled_changes.sh")" \
  || { echo "Could not check the Pi for an unpulled Store; nothing pulled." >&2; exit 1; }
if ! grep -qx tables <<<"$unpulled"; then
  echo "Nothing to pull: the Pi's tables.xml is what was last deployed, or a Store already split in (store_splits.csv)."
  exit 0
fi
tmp="$(mktemp "${TMPDIR:-/tmp}/pi-tables.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
scp -q "$PI_HOST:$UF/tables.xml" "$tmp"
[[ -s "$tmp" ]] || { echo "The Pi's $UF/tables.xml is empty or missing; nothing pulled." >&2; exit 1; }
python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$tmp" \
  || { echo "The Pi's tables.xml does not parse (a Store still writing?); nothing pulled." >&2; exit 1; }
base="$(ssh "$PI_HOST" "bash -s -- '$UF'" <"$ROOT/tools/hosts/pi/tables_base.sh")" \
  || { echo "Could not read the Pi's deploy stamp for the Store's base; nothing pulled." >&2; exit 1; }
PULLED="$(hart_pulled_dir)" || exit 1
saved="$(hart_keep_store "$tmp" "$PULLED" pi "$base")" || exit 1
base="$(<"$saved.base")"   # a Store kept before keeps the base it was kept with
cat <<EOF
Pulled: the Pi's Store is kept as $saved (outside every checkout), its base ($base) in $saved.base.
It is not recorded as taken: deploys to the Pi stay stopped until its split is merged.
Next, in a task worktree (make wt TOPIC=store-split): python3 tools/schematic/split_store.py $saved
That reports what goes into the template, what needs the owner's merge or drop, and what the repo keeps.
EOF
