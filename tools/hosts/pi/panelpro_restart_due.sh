#!/usr/bin/env bash
# Runs on the Pi (sync_hart_package.sh pipes it over ssh). Decides whether a deploy should
# start PanelPro again because pi_quit_panelpro.sh stopped it for that deploy.
#
# The marker ~/.hart_panelpro_quit_for_deploy counts only while it is fresh: PanelPro not
# running, the marker younger than MAX_AGE_S, and PanelPro not started since it was written
# (the JMRI session log is older). Otherwise it is stale and removed: PanelPro was started
# by hand meanwhile, or the quit was for something else long ago, and an owner who closed
# PanelPro on purpose must not see it come back.
#
# Prints one word: yes · no (no marker) · running · stale.
# Usage: panelpro_restart_due.sh PROFILE [MAX_AGE_S]   (MAX_AGE_S defaults to 7200)
set -euo pipefail
profile="$1"
max_age="${2:-7200}"
marker="$HOME/.hart_panelpro_quit_for_deploy"
log="$HOME/.jmri/log/session.log"

if [[ ! -f "$marker" ]]; then
  echo no
  exit 0
fi
if pgrep -f "[o]rg.jmri.profile=$profile" >/dev/null; then
  rm -f "$marker"
  echo running
  exit 0
fi
# find -mmin works with GNU (Pi) and BSD (Mac tests) alike.
too_old="$(find "$marker" -mmin "+$(( max_age / 60 ))")"
if [[ -n "$too_old" ]] || [[ -f "$log" && "$log" -nt "$marker" ]]; then
  rm -f "$marker"
  echo stale
  exit 0
fi
echo yes
