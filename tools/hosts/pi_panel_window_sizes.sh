#!/usr/bin/env bash
# Set the Pi profile's saved panel window sizes to tables.xml's (tools/hosts/panel_window_sizes.py, its header).
# A host utility run by hand, not part of make panels or a deploy (owner, 2026-11-22).
#
# JMRI rewrites user-interface.xml while it runs and when it quits, so this quits PanelPro first (PanelPro's own
# Quit, answering No to the Store prompt: pi_quit_panelpro.sh), copies the file here, sets the sizes, keeps the
# Pi's copy as user-interface.xml.hart-<stamp>.bak beside it, puts the new one in place, and starts PanelPro again
# (pi_start_panelpro.sh). With --check it only reports, and touches nothing on the Pi.
#
# Usage: tools/hosts/pi_panel_window_sizes.sh [--check]     (host from HART_PI_SSH, default "pi")
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"   # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1
[[ $# -le 1 && ( $# -eq 0 || $CHECK -eq 1 ) ]] || { echo "usage: $0 [--check]" >&2; exit 2; }

# the profile PanelPro runs on the Pi: the one pi_start_panelpro.sh starts (its PROFILE, "<name>.<id>"), whose
# folder is ~/.jmri/<name>.jmri; the Pi keeps other profiles (MQTT, Offline, Test ...) this leaves alone
PROFILE="$(sed -n 's/^PROFILE="\(.*\)"$/\1/p' "$ROOT/tools/hosts/pi_start_panelpro.sh")"
[[ -n "$PROFILE" ]] || { echo "STOP: no PROFILE in tools/hosts/pi_start_panelpro.sh" >&2; exit 1; }
REMOTE="$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" \
  "ls -d ~/.jmri/${PROFILE%%.*}.jmri/profile/*/user-interface.xml 2>/dev/null")" || true
n="$(grep -c . <<<"$REMOTE" || true)"
[[ "$n" == 1 ]] || { echo "STOP: expected one user-interface.xml in ~/.jmri/${PROFILE%%.*}.jmri on $PI_HOST, found $n:" >&2; echo "$REMOTE" >&2; exit 1; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/hart_pi_windows.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
if (( CHECK )); then
  scp -q -o BatchMode=yes "$PI_HOST:$REMOTE" "$TMP/user-interface.xml"
  python3 "$ROOT/tools/hosts/panel_window_sizes.py" "$TMP/user-interface.xml" --check
  exit $?
fi

"$ROOT/tools/hosts/pi_quit_panelpro.sh"
scp -q -o BatchMode=yes "$PI_HOST:$REMOTE" "$TMP/user-interface.xml"
python3 "$ROOT/tools/hosts/panel_window_sizes.py" "$TMP/user-interface.xml"
STAMP="$(date +%Y%m%d-%H%M%S)"
ssh -o BatchMode=yes "$PI_HOST" "cp -p '$REMOTE' '$REMOTE.hart-$STAMP.bak'"
scp -q -o BatchMode=yes "$TMP/user-interface.xml" "$PI_HOST:$REMOTE"
echo "Pi: $REMOTE updated; its previous copy is $REMOTE.hart-$STAMP.bak"
"$ROOT/tools/hosts/pi_start_panelpro.sh"
