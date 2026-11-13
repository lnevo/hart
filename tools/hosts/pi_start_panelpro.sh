#!/usr/bin/env bash
# Start PanelPro on the Pi's desktop, the way its PanelPro.desktop icon does, and wait
# until JMRI is up. Start only: it refuses when PanelPro is already running, and it
# never stops, restarts or edits anything. Quitting stays a deliberate, separate step
# (PanelPro's own Quit, answering its Store prompt).
#
# Usage: tools/hosts/pi_start_panelpro.sh            (host from HART_PI_SSH, default "pi")
set -euo pipefail
source "$(cd "$(dirname "$0")/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
PROFILE="TCS_MQTT.3f32a166"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" bash -s -- "$PROFILE" <<'REMOTE'
set -euo pipefail
profile="$1"
if pgrep -f "org.jmri.profile=$profile" >/dev/null; then
  echo "PanelPro is already running on the Pi; nothing started." >&2
  exit 3
fi
export DISPLAY=:0 XDG_RUNTIME_DIR="/run/user/$(id -u)" WAYLAND_DISPLAY=wayland-0
export WIRINGPI_GPIOMEM=1 _JAVA_AWT_WM_NONREPARENTING=1
cd "$HOME/JMRI"
marker=$(mktemp)
setsid nohup ./PanelPro -p "$profile" >/tmp/panelpro_start.out 2>&1 </dev/null &
for i in $(seq 1 90); do
  log="$HOME/.jmri/log/session.log"
  if [[ "$log" -nt "$marker" ]] && grep -aq "PanelPro version .* starts" "$log" \
     && pgrep -f "org.jmri.profile=$profile" >/dev/null; then
    break
  fi
  sleep 1
done
rm -f "$marker"
if ! pgrep -f "org.jmri.profile=$profile" >/dev/null; then
  echo "PanelPro did not start; see /tmp/panelpro_start.out on the Pi." >&2
  exit 1
fi
echo "PanelPro started on the Pi (profile $profile)."
REMOTE
