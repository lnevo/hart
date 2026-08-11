#!/usr/bin/env bash
# Pi desktop: CATS ABS-RO (hold / listen-only spectator)
# Pi GUI is Xwayland on :1 (not :0); override if already set in the session.
export DISPLAY="${DISPLAY:-:1}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export WIRINGPI_GPIOMEM=1
export CATS_FORCE_LAUNCH=1
mkdir -p /home/pi/hart/logs
nohup /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master_ABS_hold.xml \
  >/home/pi/hart/logs/cats_master_abs_hold_nohup.log 2>&1 &
exit 0
