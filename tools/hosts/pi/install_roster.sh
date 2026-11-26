#!/usr/bin/env bash
# Install the DecoderPro roster on this host (ADR-039 amendment 2026-11-26): roster.xml and the roster/ files it
# names, from SRC (the repo master jmri/layouts/hart/roster, or the package's roster/ folder) into USERFILES, where
# JMRI reads it.
#   install_roster.sh SRC USERFILES
# The repo wins: the files it replaces are kept in USERFILES/backups/roster/pre_deploy_<time>/. Files roster.xml does
# not name (JMRI's *.bak, old entry files) are left as they are: JMRI does not read them. Afterwards the host's roster
# must hash as SRC's (roster_sha.sh); then USERFILES/.roster_deployed.sha256 names it, which the Pi deploy's check
# (unpulled_changes.sh) compares a later DecoderPro save with. The Pi deploy has already stopped on an unpulled
# roster before this runs (tools/hosts/deploy/gate.sh G2); HART_DISCARD_PI_CHANGES=1 is the only way past that, and
# then this backup is the one copy of what the Pi had.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/roster_sha.sh"
[[ $# -eq 2 ]] || { echo "usage: install_roster.sh SRC USERFILES" >&2; exit 2; }
SRC="$1"
UF="$2"
STAMP="$UF/.roster_deployed.sha256"

# Inputs first: a source without roster.xml, with a bad name in it, or naming a file it lacks installs nothing.
[[ -f "$SRC/roster.xml" ]] || { echo "STOP: no roster.xml in $SRC; the roster was not installed." >&2; exit 1; }
names="$(roster_files "$SRC")" || { echo "STOP: the roster was not installed." >&2; exit 1; }
[[ -n "$names" ]] || { echo "STOP: $SRC/roster.xml names no locomotive file; the roster was not installed." >&2; exit 1; }
count=0
while IFS= read -r name; do
  [[ -f "$SRC/roster/$name" ]] || { echo "STOP: $SRC/roster.xml names roster/$name, which is not in $SRC; the roster was not installed." >&2; exit 1; }
  count=$((count + 1))
done <<<"$names"

want="$(roster_sha "$SRC")"
have="$(roster_sha "$UF")" || have=unreadable   # a bad name in the host's own roster.xml: replaced, after a backup
if [[ "$want" == "$have" ]]; then
  echo "$want" >"$STAMP"
  echo "DecoderPro roster already current -> $UF"
  exit 0
fi

mkdir -p "$UF/roster"
backup="$UF/backups/roster/pre_deploy_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup/roster"
[[ ! -f "$UF/roster.xml" ]] || cp -p "$UF/roster.xml" "$backup/"
while IFS= read -r name; do
  [[ ! -f "$UF/roster/$name" ]] || cp -p "$UF/roster/$name" "$backup/roster/"
  cp -f "$SRC/roster/$name" "$UF/roster/$name"
done <<<"$names"
# roster.xml last: JMRI reads the index first, so it only names files already in place.
cp -f "$SRC/roster.xml" "$UF/roster.xml"

got="$(roster_sha "$UF")"
if [[ "$got" != "$want" ]]; then
  echo "STOP: after the install the roster in $UF does not hash as the repo's ($got, want $want); what it replaced is in $backup." >&2
  exit 1
fi
echo "$want" >"$STAMP"
echo "DecoderPro roster -> $UF ($count locos; backup $backup)"
