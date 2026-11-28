#!/usr/bin/env bash
# Desktop launcher "Monitor LCOS": one lxterminal running tmux session "lcos",
# window 1 follows the bridge log, window 2 shows every MQTT message on the Pi's broker.
# Opening it again reattaches to the running session instead of starting a second one.
set -euo pipefail
SESSION=lcos

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" -n bridge -c "$HOME/lcos-bridge" "./bridge log; exec bash"
  tmux new-window -t "$SESSION" -n mqtt "mosquitto_sub -h 127.0.0.1 -t '#' -v; exec bash"
  tmux select-window -t "$SESSION:bridge"
fi

exec lxterminal --title="Monitor LCOS" --command="tmux attach-session -t $SESSION"
