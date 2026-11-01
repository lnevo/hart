#!/usr/bin/env bash
# Legacy desktop wrapper. Prefer CATS CTC / CATS ABS icons.
# Pi GUI is Xwayland on :0; override if already set in the session.
export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export WIRINGPI_GPIOMEM=1
export _JAVA_AWT_WM_NONREPARENTING="${_JAVA_AWT_WM_NONREPARENTING:-1}"
exec /home/pi/JMRI_UserFiles/cats/launch/launch_cats.sh "${1:-/home/pi/JMRI_UserFiles/cats/panels/HART_CTC.xml}"
