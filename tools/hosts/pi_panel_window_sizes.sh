#!/usr/bin/env bash
# Set the Pi profile's saved panel window sizes to tables.xml's (tools/hosts/panel_window_sizes.py, its header).
# A host utility run by hand, not part of make panels or a deploy (owner, 2026-11-22).
#
# The sizes are those of the tables installed on the Pi ($HART_PI_USERFILES/tables.xml). It checks first: with
# nothing to change (or with --check) it stops there and touches nothing. Otherwise, JMRI rewriting user-interface.xml
# while it runs and when it quits, it quits a running PanelPro (PanelPro's own Quit, answering No to the Store
# prompt: pi_quit_panelpro.sh), sets the sizes, keeps the Pi's copy as user-interface.xml.hart-<stamp>.bak beside it,
# puts the new one in place and starts PanelPro again (pi_start_panelpro.sh), also when a step after the quit fails.
# A PanelPro that was not running is left closed.
#
# Usage: tools/hosts/pi_panel_window_sizes.sh [--check]     (host from HART_PI_SSH, default "pi")
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"   # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1
[[ $# -le 1 && ( $# -eq 0 || $CHECK -eq 1 ) ]] || { echo "usage: $0 [--check]" >&2; exit 2; }

# the profile PanelPro runs on the Pi (HART_PI_PROFILE, "<name>.<id>", load_env.sh), whose folder is
# ~/.jmri/<name>.jmri; the Pi keeps other profiles (MQTT, Offline, Test ...) this leaves alone
PROFILE="$HART_PI_PROFILE"
[[ "$PROFILE" == ?*.?* ]] || { echo "STOP: HART_PI_PROFILE is not <name>.<id>: '$PROFILE'" >&2; exit 1; }
REMOTE="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" \
  "ls -d ~/.jmri/${PROFILE%%.*}.jmri/profile/*/user-interface.xml 2>/dev/null")" || true
n="$(grep -c . <<<"$REMOTE" || true)"
[[ "$n" == 1 ]] || { echo "STOP: expected one user-interface.xml in ~/.jmri/${PROFILE%%.*}.jmri on $PI_HOST, found $n:" >&2; echo "$REMOTE" >&2; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/hart_pi_windows.XXXXXX")"
QUIT=0
cleanup() {
  # PanelPro was quit by this run and the run stopped before starting it: start it again, so the layout is not left
  # without it
  if (( QUIT )); then "$ROOT/tools/hosts/pi_start_panelpro.sh" || echo "PanelPro did not start on the Pi; start it: tools/hosts/pi_start_panelpro.sh" >&2; fi
  rm -rf "$TMP"
}
trap cleanup EXIT
# the sizes come from the tables installed on the Pi, which its panels are drawn from, not from this checkout's
scp -q -o BatchMode=yes "$PI_HOST:$HART_PI_USERFILES/tables.xml" "$TMP/tables.xml"
scp -q -o BatchMode=yes "$PI_HOST:$REMOTE" "$TMP/user-interface.xml"
SIZES=(python3 "$ROOT/tools/hosts/panel_window_sizes.py" "$TMP/user-interface.xml" --tables "$TMP/tables.xml")
rc=0
"${SIZES[@]}" --check || rc=$?
(( rc <= 1 )) || exit "$rc"
if (( CHECK )) || (( rc == 0 )); then
  exit "$rc"          # --check, or nothing to change: PanelPro is left as it is
fi

RUNNING=0
ssh -o BatchMode=yes "$PI_HOST" "pgrep -f 'org.jmri.profile=$PROFILE' >/dev/null" && RUNNING=1
if (( RUNNING )); then
  "$ROOT/tools/hosts/pi_quit_panelpro.sh"
  QUIT=1
  scp -q -o BatchMode=yes "$PI_HOST:$REMOTE" "$TMP/user-interface.xml"   # as PanelPro left it on quitting
fi
"${SIZES[@]}"
STAMP="$(date +%Y%m%d-%H%M%S)"
ssh -o BatchMode=yes "$PI_HOST" "cp -p '$REMOTE' '$REMOTE.hart-$STAMP.bak'"
scp -q -o BatchMode=yes "$TMP/user-interface.xml" "$PI_HOST:$REMOTE"
echo "Pi: $REMOTE updated; its previous copy is $REMOTE.hart-$STAMP.bak"
if (( RUNNING )); then
  QUIT=0
  "$ROOT/tools/hosts/pi_start_panelpro.sh"
else
  echo "PanelPro was not running on the Pi; left closed."
fi
