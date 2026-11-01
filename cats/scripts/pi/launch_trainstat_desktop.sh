#!/usr/bin/env bash
# Desktop launcher for TrainStat — returns immediately.
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

alert() {
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --width=360 --title="TrainStat" --text="$1" 2>/dev/null || true
  fi
}

if pgrep -f "trainStat\.TrainStat" >/dev/null 2>&1; then
  alert "TrainStat is already running."
  exit 1
fi

if [[ ! -x /home/pi/JMRI_UserFiles/cats/launch/launch_trainstat.sh ]]; then
  alert "Missing /home/pi/JMRI_UserFiles/cats/launch/launch_trainstat.sh"
  exit 1
fi

if ! DISPLAY="${DISPLAY}" xdpyinfo >/dev/null 2>&1; then
  if DISPLAY=:0 xdpyinfo >/dev/null 2>&1; then
    export DISPLAY=:0
  elif DISPLAY=:1 xdpyinfo >/dev/null 2>&1; then
    export DISPLAY=:1
  else
    alert "No X display found (:0/:1)."
    exit 1
  fi
fi

mkdir -p /home/pi/JMRI_UserFiles/cats/logs
nohup /home/pi/JMRI_UserFiles/cats/launch/launch_trainstat.sh \
  >/home/pi/JMRI_UserFiles/cats/logs/trainstat_desktop_nohup.log 2>&1 &
exit 0
