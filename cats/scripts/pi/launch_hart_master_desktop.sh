#!/usr/bin/env bash
# Pi desktop: HART Master (CTC)
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export WIRINGPI_GPIOMEM=1
export CATS_FORCE_LAUNCH=1
mkdir -p /home/pi/hart/logs
nohup /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/sheets/HART_Master.xml \
  >/home/pi/hart/logs/cats_master_nohup.log 2>&1 &
exit 0
