#!/usr/bin/env bash
# Pi desktop: CATS ABS (Digicon reference). SECSIGNAL names are unbound from
# JMRI masts so Layout Editor SML owns aspects. No HOLD_ONLY.
# Pi GUI is Xwayland on :1 (not :0); override if already set in the session.
export DISPLAY="${DISPLAY:-:1}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export WIRINGPI_GPIOMEM=1
export _JAVA_AWT_WM_NONREPARENTING="${_JAVA_AWT_WM_NONREPARENTING:-1}"
exec /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master_ABS.xml
