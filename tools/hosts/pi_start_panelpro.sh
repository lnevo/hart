#!/usr/bin/env bash
# Start PanelPro on the Pi's desktop, the way its PanelPro.desktop icon does, and wait
# until JMRI is up. Start only: it refuses when PanelPro, CATS or another JMRI app is
# already running on the profile, and it never stops, restarts or edits anything. Quitting
# stays a deliberate, separate step (PanelPro's own Quit, answering its Store prompt). It
# clears the quit-for-deploy marker that pi_quit_panelpro.sh leaves.
#
# What counts as running on the profile: pi/jmri_profile_match.sh, sent to the Pi ahead
# of the remote part below.
#
# Exit: 0 started · 1 did not start, or the Pi's processes could not be listed · 3 already running.
# Usage: tools/hosts/pi_start_panelpro.sh            (host from HART_PI_SSH, default "pi")
set -euo pipefail
HOSTS="$(cd "$(dirname "$0")" && pwd)"
source "$(cd "$HOSTS/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
PROFILE="$HART_PI_PROFILE"

read -r -d '' REMOTE <<'REMOTE' || true
set -euo pipefail
profile="$1"
state=0
jmri_profile_running "$profile" || state=$?
if [[ "$state" -eq 0 ]]; then
  rm -f "$HOME/.hart_panelpro_quit_for_deploy"
  echo "PanelPro is already running on the Pi; nothing started." >&2
  exit 3
elif [[ "$state" -ne 1 ]]; then
  echo "Cannot tell whether JMRI runs on the Pi (ps could not list its processes); nothing started." >&2
  exit 1
fi
export DISPLAY=:0 XDG_RUNTIME_DIR="/run/user/$(id -u)" WAYLAND_DISPLAY=wayland-0
export WIRINGPI_GPIOMEM=1 _JAVA_AWT_WM_NONREPARENTING=1
cd "$HOME/JMRI"
marker=$(mktemp)
setsid nohup ./PanelPro -p "$profile" >/tmp/panelpro_start.out 2>&1 </dev/null &
for i in $(seq 1 90); do
  log="$HOME/.jmri/log/session.log"
  if [[ "$log" -nt "$marker" ]] && grep -aq "PanelPro version .* starts" "$log" \
     && jmri_profile_running "$profile"; then
    break
  fi
  sleep 1
done
rm -f "$marker"
if ! jmri_profile_running "$profile"; then
  echo "PanelPro did not start; see /tmp/panelpro_start.out on the Pi." >&2
  exit 1
fi
# Cleared only once PanelPro is up, so a failed start keeps the restart intent.
rm -f "$HOME/.hart_panelpro_quit_for_deploy"
echo "PanelPro started on the Pi (profile $profile)."
REMOTE

{ cat "$HOSTS/pi/jmri_profile_match.sh"; printf '%s\n' "$REMOTE"; } \
  | ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" bash -s -- "$PROFILE"
