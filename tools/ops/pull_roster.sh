#!/usr/bin/env bash
# Bring the Pi's DecoderPro roster into the repo master jmri/layouts/hart/roster (ADR-039 amendment 2026-11-26):
# roster.xml and the roster/ files it names, after a programming session or a new loco. `make roster-pull` runs it.
# It only reads on the Pi (JMRI may stay up: DecoderPro writes the roster only on a save) and never marks the Pi as
# pulled: the Pi counts as pulled once the repo holds its roster (the deploy gate compares the two hashes,
# tools/hosts/pi/roster_sha.sh), so commit, merge, then deploy from the updated main.
#
# Run from the main checkout (which stays clean for deploys) it writes into an ops-pull-* worktree, the one an earlier
# pull left unmerged or a new one, as the deploy gate's own pull does (autopull_target, tools/hosts/deploy/autopull.sh).
# It picks or makes that worktree only once the Pi's roster is copied and checked, so a run with nothing to pull, or
# one that stops, makes none.
# After the copy it fills locos.csv's dcc_address and long_address from the roster and runs the link check
# (tools/ops/check_roster.py --write); a check problem is printed and the exit is 3, with the roster files kept.
#
# Exit: 0 pulled, or nothing to pull; 1 nothing pulled (the reason is printed); 3 pulled, but check_roster.py
# found a problem to fix before the commit.
# Usage: tools/ops/pull_roster.sh
set -euo pipefail
[[ $# -eq 0 ]] || { sed -n '2,15p' "$0" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/hosts/deploy/common.sh"   # hosts (load_env.sh), ROSTER_MASTER, ssh_pi, autopull_target
SHA_SCRIPT="$ROOT/tools/hosts/pi/roster_sha.sh"
source "$SHA_SCRIPT"

# pi_roster SCRIPT: runs roster_sha.sh's functions and then SCRIPT on the Pi, in its JMRI_UserFiles ($1 there).
pi_roster() { { cat "$SHA_SCRIPT"; echo "$1"; } | ssh_pi "bash -s -- '$PI_USERFILES'"; }

pi_sha="$(pi_roster 'roster_sha "$1"')" || { echo "STOP: could not read the Pi's roster over ssh ($PI_HOST); nothing pulled." >&2; exit 1; }
if [[ "$pi_sha" == none ]]; then
  echo "STOP: the Pi has no $PI_USERFILES/roster.xml; nothing pulled." >&2
  exit 1
fi
repo_sha="$(roster_sha "$ROSTER_MASTER")" || { echo "STOP: cannot hash the repo master $ROSTER_MASTER; nothing pulled." >&2; exit 1; }
if [[ "$pi_sha" == "$repo_sha" ]]; then
  echo "Nothing to pull: the Pi's DecoderPro roster is the repo's (${pi_sha:0:12})."
  exit 0
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/pi-roster.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
# roster.xml and the files it names, in one tar stream (a named file the Pi lacks fails the tar)
if ! pi_roster 'cd "$1" && names="$(roster_files .)" && { echo roster.xml; sed "s|^|roster/|" <<<"$names"; } | tar -cf - -T -' \
    | tar -xf - -C "$tmp"; then
  echo "STOP: could not copy the Pi's roster (roster.xml names a file the Pi lacks, or ssh dropped); nothing pulled." >&2
  exit 1
fi
got="$(roster_sha "$tmp")" || { echo "STOP: the copy of the Pi's roster names a bad file; nothing pulled." >&2; exit 1; }
if [[ "$got" != "$pi_sha" ]]; then
  echo "STOP: the Pi's roster changed while it was copied (a DecoderPro save?); nothing pulled. Run it again." >&2
  exit 1
fi
python3 - "$tmp" <<'PY' || { echo "STOP: a file of the Pi's roster does not parse; nothing pulled." >&2; exit 1; }
import sys, xml.etree.ElementTree as ET
from pathlib import Path
for p in sorted(Path(sys.argv[1]).rglob("*.xml")):
    try:
        ET.parse(p)
    except ET.ParseError as exc:
        sys.exit(f"{p.relative_to(sys.argv[1])}: {exc}")
PY

# Where to write: this checkout, or from the main checkout an ops-pull-* worktree (autopull_target).
failed=""
kept=""
autopull_target roster || { printf 'STOP: %s' "$failed" >&2; exit 1; }
TARGET="$AUTOPULL_TARGET"
if [[ "$TARGET" != "$ROOT" ]]; then
  echo "This is the main checkout: pulling into $TARGET"
  [[ -f "$TARGET/tools/ops/check_roster.py" ]] \
    || { echo "STOP: $TARGET has no tools/ops/check_roster.py (a branch from before the roster master); nothing pulled. Merge main into it, or remove it, and run again." >&2; exit 1; }
  ROSTER_MASTER="$TARGET/jmri/layouts/hart/roster"
fi

# The master becomes the copy: the files it names, and no entry file the Pi's roster.xml no longer names.
names="$(roster_files "$tmp")"
mkdir -p "$ROSTER_MASTER/roster"
shopt -s nullglob
for f in "$ROSTER_MASTER"/roster/*; do
  grep -qxF "$(basename "$f")" <<<"$names" || { rm -f "$f"; echo "removed roster/$(basename "$f") (the Pi's roster.xml no longer names it)"; }
done
while IFS= read -r name; do
  cp -f "$tmp/roster/$name" "$ROSTER_MASTER/roster/$name"
done <<<"$names"
cp -f "$tmp/roster.xml" "$ROSTER_MASTER/roster.xml"
now="$(roster_sha "$ROSTER_MASTER")"
if [[ "$now" != "$pi_sha" ]]; then
  echo "STOP: after the copy $ROSTER_MASTER does not hash as the Pi's roster ($now, want $pi_sha); check git status there." >&2
  exit 1
fi
echo "Pulled: the Pi's DecoderPro roster (${pi_sha:0:12}) -> $ROSTER_MASTER"
rc=0
python3 "$TARGET/tools/ops/check_roster.py" --write || rc=3
git -C "$TARGET" status --short -- jmri/layouts/hart/roster ops/hart-ops/data/locos.csv || true
if [[ "$rc" -ne 0 ]]; then
  echo "The roster files are kept, but check_roster.py found the problems above: fix them (locos.csv) before the commit." >&2
  exit 3
fi
echo "Review the diff and commit jmri/layouts/hart/roster (and locos.csv if it changed), merge, then deploy."
