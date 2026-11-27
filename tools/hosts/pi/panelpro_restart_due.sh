#!/usr/bin/env bash
# Runs on the Pi (sync_hart_package.sh pipes it over ssh after a Pi deploy, with
# jmri_profile_match.sh ahead of it). Decides whether to start PanelPro again because
# `pi_quit_panelpro.sh --for-deploy` stopped it for the deploy. A plain quit leaves no
# marker, so PanelPro the owner closed stays closed.
#
# The marker ~/.hart_panelpro_quit_for_deploy counts only while it is younger than
# MAX_AGE_S. If PanelPro, CATS or another JMRI app is already running, nothing is started
# (PanelPro and CATS must never share the profile) and the marker is cleared.
#
# Prints one word: yes · no (no marker) · running · stale · unknown (pgrep could not tell;
# the marker is kept).
# Usage: panelpro_restart_due.sh [MAX_AGE_S]   (default 7200)
set -euo pipefail
# Run from a file (the tests), it loads the helper beside it; over ssh the deploy sends the helper first.
if ! declare -F jmri_app_running >/dev/null; then
  source "$(dirname "${BASH_SOURCE[0]}")/jmri_profile_match.sh"
fi
max_age="${1:-7200}"
marker="$HOME/.hart_panelpro_quit_for_deploy"

if [[ ! -f "$marker" ]]; then
  echo no
  exit 0
fi
state=0
jmri_app_running || state=$?
if [[ "$state" -eq 0 ]]; then
  rm -f "$marker"
  echo running
  exit 0
elif [[ "$state" -ne 1 ]]; then
  echo unknown
  exit 0
fi
# date -r FILE gives the mtime with GNU (Pi) and BSD (Mac tests) date alike.
age=$(( $(date +%s) - $(date -r "$marker" +%s) ))
if (( age > max_age )); then
  rm -f "$marker"
  echo stale
  exit 0
fi
echo yes
