#!/usr/bin/env bash
# Paint the "HART Railroad" Layout Editor panel of a checkout's tables.xml to a PNG, in the sandbox profile.
#   HART_SANDBOX=<sandbox> tools/hosts/sandbox/panel_snapshot.sh <checkout root> <out.png>
# PanelPro starts on the sandbox profile with that checkout's tables (Start Up scripts off), paints the whole panel
# at 100% (the window is grown to hold it; Layout Editor paints track only inside the window) and quits without
# storing. Start the sandbox broker first (README.md).
set -euo pipefail
ROOT="$(cd "$1" && pwd)"
export HART_SNAPSHOT_OUT="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/sandbox_env.sh"
source "$ROOT/tools/hosts/profile_tables_guard.sh"
source "$ROOT/tools/hosts/panelpro_session.sh"
rm -f "$HART_SNAPSHOT_OUT" "$HART_SNAPSHOT_OUT.done" "$HART_SNAPSHOT_OUT.error"
pp_profile
pp_refuse_running "Quit CATS/PanelPro first."
pp_begin "$HERE/panel_snapshot.py"
pp_launch "$RUN/snapshot_panelpro.log"
pp_wait_exit 600 || true
[[ ! -f "$HART_SNAPSHOT_OUT.error" ]] || { echo "$(cat "$HART_SNAPSHOT_OUT.error"); log: $RUN/snapshot_panelpro.log" >&2; exit 1; }
[[ -f "$HART_SNAPSHOT_OUT.done" ]] || { echo "no snapshot written; log: $RUN/snapshot_panelpro.log" >&2; exit 1; }
echo "wrote $HART_SNAPSHOT_OUT ($(cat "$HART_SNAPSHOT_OUT.done"))"
