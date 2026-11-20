#!/usr/bin/env bash
# Take a PanelPro Store made on the Pi off the Pi (ADR-014, ADR-029). A running PanelPro does not stop the pull:
# JMRI writes the file only on a Store, so let any Store finish first.
#
# tables.xml is an output (tools/schematic/build_tables.py writes it from its sources), so a Store is never copied
# over it. The Store counts as changed when the deploy's own check says so (tools/hosts/pi/unpulled_changes.sh: the
# Pi's file against the newer of its .tables_deployed.sha256 and the deploy stamp's tables_sha256; with neither, the
# generated tables.xml). A changed Store is kept as pi-<date>.xml in the pulled folder (~/JMRI_UserFiles-pulled, or
# HART_PULLED_DIR: outside every checkout, profile_tables_guard.sh hart_pulled_dir) and, once it is safely saved,
# recorded as taken on the Pi (.tables_deployed.sha256 is set to the kept copy's hash), so the next deploy goes
# ahead and replaces the Pi's file with the generated one. The owner's PanelPro edits are then only in the kept
# file: carry them into devices.csv or the template before that deploy (R9d's pull will split a Store
# automatically).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
UF="$HART_PI_USERFILES"
GENERATED="$ROOT/jmri/layouts/hart/output/tables.xml"
source "$ROOT/tools/hosts/profile_tables_guard.sh"

generated_sha="$(shasum -a 256 "$GENERATED" | cut -d' ' -f1)"
unpulled="$(ssh "$PI_HOST" "bash -s -- '$UF' '$generated_sha'" <"$ROOT/tools/hosts/pi/unpulled_changes.sh")" \
  || { echo "Could not check the Pi for an unpulled Store; nothing pulled." >&2; exit 1; }
if ! grep -qx tables <<<"$unpulled"; then
  echo "Nothing to pull: the Pi's tables.xml is what was last deployed or pulled."
  exit 0
fi
tmp="$(mktemp "${TMPDIR:-/tmp}/pi-tables.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
scp -q "$PI_HOST:$UF/tables.xml" "$tmp"
[[ -s "$tmp" ]] || { echo "The Pi's $UF/tables.xml is empty or missing; nothing pulled." >&2; exit 1; }
python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$tmp" \
  || { echo "The Pi's tables.xml does not parse (a Store still writing?); nothing pulled." >&2; exit 1; }
PULLED="$(hart_pulled_dir)" || exit 1
saved="$PULLED/pi-$(date +%Y%m%d-%H%M%S).xml"
cp "$tmp" "$saved"
pulled_sha="$(shasum -a 256 "$saved" | cut -d' ' -f1)"
[[ "$(shasum -a 256 "$tmp" | cut -d' ' -f1)" == "$pulled_sha" ]] \
  || { echo "The kept copy $saved does not match what was read; not recorded as taken." >&2; exit 1; }
# The hash of the copy kept, not of the Pi's file now: a Store after the scp still counts as unpulled.
ssh "$PI_HOST" "echo $pulled_sha >'$UF/.tables_deployed.sha256'" \
  || { echo "Kept $saved, but could not record it as taken on the Pi; the next deploy still stops. Pull again." >&2; exit 1; }
cat <<EOF
Pulled: the Pi's Store is kept as $saved (outside every checkout) and recorded as taken on the Pi.
The owner's PanelPro edits are in that file only: carry them into devices.csv or the template
(jmri/layouts/hart/data/) and run python3 tools/schematic/build_tables.py before the next deploy.
R9d's pull will do this split automatically. The next deploy replaces the Pi's tables.xml with the
generated tables.xml.
EOF
