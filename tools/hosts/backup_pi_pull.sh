#!/usr/bin/env bash
# Copy what lives only on the Pi's SD card onto the Mac, once a day (ADR-035).
# It only reads on the Pi.
#
#   - ~/.jmri (the PanelPro profile: MQTT connection, preferences), the JMRI user
#     files (roster, the Operations files the Pi writes live, backupPanels) and
#     ~/speedmatch, plus ~/Desktop, ~/.java, ~/.local/share/applications and
#     ~/jmrihelp (the rest of the 2026-11-23 swap's restore list), as one dated snapshot in $HART_BACKUP_DIR/pi/<time>/; files
#     unchanged since the newest snapshot are hard links to it, so a day costs
#     only what changed. The newest BACKUP_PI_KEEP (default 30) are kept.
#   - the live STS: tools/hosts/pi_sts_pull_backups.sh (its backups and a dump).
#
# A snapshot that did not finish keeps its .part name and is never counted or
# linked to. $HART_BACKUP_DIR/pi/last-ok holds the time of the last full run;
# backup_launchagents.sh status reads it. Exit 0 only when every part copied.
#
#   BACKUP_PI_HOST   ssh target (default $HART_PI_SSH); empty copies local paths (tests)
#   BACKUP_PI_SKIP_STS=1  skip the STS step (tests)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../env/load_env.sh"  # hosts: environment, hart.env, default
HOST="${BACKUP_PI_HOST-$HART_PI_SSH}"
USERFILES="${HART_PI_USERFILES:?HART_PI_USERFILES is not set}"
ROOT="${HART_BACKUP_DIR:-$HOME/Backups/hart}"
KEEP="${BACKUP_PI_KEEP:-30}"
[[ "$KEEP" =~ ^[1-9][0-9]*$ ]] || { echo "backup_pi_pull: BACKUP_PI_KEEP must be a whole number above 0, got $KEEP" >&2; exit 2; }

DEST="$ROOT/pi"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
# Two runs in one second would share a name, and mv would put the second inside the first.
n=1; SNAP="$DEST/$STAMP"
while [[ -e "$SNAP" || -e "$SNAP.part" ]]; do n=$((n + 1)); SNAP="$DEST/$STAMP-$n"; done
echo "backup_pi_pull: start $STAMP from ${HOST:-local paths}"

# The newest finished snapshot (names sort by time; .part ones are skipped).
prev="$(find "$DEST" -mindepth 1 -maxdepth 1 -type d -name '20*' ! -name '*.part' | sort | tail -n 1)"

copy() {  # <remote folder> <name in the snapshot>
  # Jython's compiled caches ($py.class) are rewritten while PanelPro runs and rebuilt from the .py files.
  local opts=(-a --exclude='*$py.class') from="$1/" rc=0
  if [[ -n "$HOST" ]]; then
    opts+=(-e "ssh -o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR")
    from="$HOST:$from"
  fi
  # --link-dest is read relative to the target, so give it an absolute path.
  [[ -n "$prev" && -d "$prev/$2" ]] && opts+=(--link-dest="$prev/$2")
  rsync "${opts[@]}" "$from" "$SNAP.part/$2/" || rc=$?
  # 24: a file vanished while it was read (JMRI rewrote it); what is there is a good copy of the rest.
  if [[ "$rc" == 24 ]]; then
    echo "backup_pi_pull: $2: some files changed while copying (rsync 24); kept the rest" >&2
  elif [[ "$rc" != 0 ]]; then
    echo "backup_pi_pull: $2: rsync failed (exit $rc); no snapshot made" >&2
    exit "$rc"
  fi
}

# A run that stopped part way left a .part folder; it is never used, so remove it.
find "$DEST" -mindepth 1 -maxdepth 1 -type d -name '20*.part' -exec rm -rf {} +
mkdir -p "$SNAP.part"
pi_home="${USERFILES%/*}"  # ~/.jmri and ~/speedmatch sit beside the user files
copy "$pi_home/.jmri" jmri
copy "$USERFILES" JMRI_UserFiles
copy "$pi_home/speedmatch" speedmatch
# Small, and restored by hand at the 2026-11-23 swap (docs/hosts/PI_OS_REBUILD.md, Phase 4).
copy "$pi_home/Desktop" Desktop
copy "$pi_home/.java" java
copy "$pi_home/.local/share/applications" applications
copy "$pi_home/jmrihelp" jmrihelp
mv "$SNAP.part" "$SNAP"
echo "backup_pi_pull: snapshot $SNAP ($(du -sh "$SNAP" | cut -f1), linked to ${prev:-nothing})"

# Keep the newest snapshots only.
find "$DEST" -mindepth 1 -maxdepth 1 -type d -name '20*' ! -name '*.part' | sort -r | tail -n +"$((KEEP + 1))" |
  while read -r old; do rm -rf "$old"; done

if [[ "${BACKUP_PI_SKIP_STS:-0}" != 1 ]]; then
  "$HERE/pi_sts_pull_backups.sh"
fi

date '+%Y-%m-%d %H:%M:%S' > "$DEST/last-ok"
echo "backup_pi_pull: done"
