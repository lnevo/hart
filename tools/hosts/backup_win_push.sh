#!/usr/bin/env bash
# Copy the Mac's data that git does not hold to the Windows box, once a week (ADR-035).
# The Windows box is a second machine, not off-site: this covers a dead Mac disk or a
# dead Time Machine disk, not the house.
#
# Each folder in FOLDERS is mirrored into WSL at $BACKUP_WIN_DIR/<name>/. A file that
# was changed or deleted on the Mac is moved, not lost, into
# $BACKUP_WIN_DIR/replaced/<time>/<name>/ (kept BACKUP_WIN_KEEP_DAYS, default 90).
# A folder missing on the Mac is reported and skipped, never mirrored as empty. An entry may
# also be one file, copied into $BACKUP_WIN_DIR/<name>/. Entries named secrets-* (owner,
# 2026-11-25) are copied with owner-only permissions (folders 700, files 600) and their
# replaced copies are tightened the same way; their contents are never printed.
# $HART_BACKUP_DIR/win-last-ok holds the time of the last run in which every folder copied.
#
#   BACKUP_WIN_HOST  ssh target (default $HART_WIN_SSH); empty copies to a local folder (tests)
#   BACKUP_WIN_DIR   target folder (default ~/backups/mac inside WSL)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../env/load_env.sh"
HOST="${BACKUP_WIN_HOST-$HART_WIN_SSH}"
PORT="${HART_WIN_SSH_PORT:-2222}"
DISTRO="${HART_WIN_WSL_DISTRO:-Ubuntu-24.04}"
ROOT="${HART_BACKUP_DIR:-$HOME/Backups/hart}"
TARGET="${BACKUP_WIN_DIR:-}"  # default: ~/backups/mac in WSL, made absolute below
KEEP_DAYS="${BACKUP_WIN_KEEP_DAYS:-90}"
[[ "$KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "backup_win_push: BACKUP_WIN_KEEP_DAYS must be a whole number above 0, got $KEEP_DAYS" >&2; exit 2; }
MAIN="$(dirname "$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)")"
STAMP="$(date +%Y%m%d-%H%M%S)"

# name|folder on the Mac. Names are the folders on the Windows side, with no spaces: the
# remote command line goes through Windows' sshd and wsl.exe, which split it on spaces.
FOLDERS=(
  "media|$MAIN/media"
  "car-cards|$MAIN/ops/car-cards"
  "wiring-bench|$MAIN/docs/wiring/bench"
  "sts-pi|$MAIN/external/sts-docker-data/pi"
  "pi-snapshots|$ROOT/pi"
  "Layout|$HOME/Documents/Layout"
  "NMRA-AP|$HOME/Documents/NMRA AP"
  # secrets (owner, 2026-11-25): the Pi image's keys and passwords, the router notes, the
  # Sheets credentials. ~/.ssh is not here: agents cannot read it; the owner adds it by hand.
  "secrets-pi-os|$HOME/.config/hart/pi-os"
  "secrets-net|$HOME/dev/net"
  "secrets-env|$MAIN/.env.local"
)
if [[ -n "${BACKUP_WIN_FOLDERS:-}" ]]; then  # tests: newline-separated name|folder lines
  FOLDERS=()
  while IFS= read -r line; do [[ -n "$line" ]] && FOLDERS+=("$line"); done <<< "$BACKUP_WIN_FOLDERS"
fi

remote() {  # run a bash script (stdin) in WSL, or locally for tests
  if [[ -n "$HOST" ]]; then
    ssh -o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR -p "$PORT" "$HOST" "wsl.exe -d $DISTRO -- bash -s"
  else
    bash -s
  fi
}

# -H keeps the Pi snapshots' hard links, so 30 snapshots cost one copy plus changes, as on the Mac.
opts=(-a -H --delete --backup --timeout=300)
if [[ -n "$HOST" ]]; then
  opts+=(-e "ssh -o BatchMode=yes -o ConnectTimeout=10 -o LogLevel=ERROR -p $PORT"
         --rsync-path="wsl.exe -d $DISTRO -- rsync")
fi

# rsync's remote side starts in the Windows user folder (/mnt/c/...), so the target must be absolute.
if [[ -z "$TARGET" ]]; then
  # shellcheck disable=SC2016  # expanded in WSL
  wsl_home="$(echo 'echo "$HOME"' | remote)"
  [[ "$wsl_home" == /* ]] || { echo "backup_win_push: could not read the WSL home (got '$wsl_home')" >&2; exit 2; }
  TARGET="$wsl_home/backups/mac"
fi
[[ "$TARGET" == /* ]] || { echo "backup_win_push: BACKUP_WIN_DIR must be absolute, got $TARGET" >&2; exit 2; }
remote <<< "mkdir -p '$TARGET'"

echo "backup_win_push: start $STAMP to ${HOST:-local}:$TARGET"
failed=0
for entry in "${FOLDERS[@]}"; do
  name="${entry%%|*}" from="${entry#*|}"
  if [[ "$name" == *[[:space:]]* ]]; then
    echo "backup_win_push: the Windows name '$name' has a space; use one without" >&2
    exit 2
  fi
  if [[ -d "$from" ]]; then
    src="$from/"  # the trailing slash copies the folder's contents, and follows the folder itself if it is a link
  elif [[ -f "$from" ]]; then
    src="$from"   # one file, into its own folder on the Windows side
  else
    echo "backup_win_push: MISSING $from; $name skipped" >&2
    failed=1
    continue
  fi
  to="$TARGET/$name/"
  dest="${HOST:+$HOST:}$to"
  extra=()
  [[ "$name" == secrets-* ]] && extra=("--chmod=D700,F600")  # one argument: rsync takes a comma list
  # --backup-dir is read on the receiving side, relative to the target folder.
  rc=0
  rsync "${opts[@]}" ${extra[@]+"${extra[@]}"} --backup-dir="../replaced/$STAMP/$name" "$src" "$dest" < /dev/null || rc=$?
  if [[ "$rc" == 0 ]]; then
    echo "backup_win_push: $name ok"
  elif [[ "$rc" == 24 ]]; then  # a file vanished while it was read; the rest copied
    echo "backup_win_push: $name ok, but some files changed while copying (rsync 24)" >&2
  else
    echo "backup_win_push: $name FAILED (rsync exit $rc)" >&2
    failed=1
  fi
done

# Old replaced files go after KEEP_DAYS. The target is made by rsync above. Secrets, and their
# replaced copies (rsync's backup keeps the old mode), are owner-only.
remote <<EOF
set -e
[ -d "$TARGET/replaced" ] && find "$TARGET/replaced" -mindepth 1 -maxdepth 1 -type d -mtime +$KEEP_DAYS -exec rm -rf {} + || true
find "$TARGET" -maxdepth 3 -name 'secrets-*' -exec chmod -R go-rwx {} + 2>/dev/null || true
EOF

if [[ "$failed" == 0 ]]; then
  mkdir -p "$ROOT"
  date '+%Y-%m-%d %H:%M:%S' > "$ROOT/win-last-ok"
  echo "backup_win_push: done"
else
  echo "backup_win_push: finished with failures; win-last-ok not updated" >&2
  exit 1
fi
