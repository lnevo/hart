#!/usr/bin/env bash
# Quit PanelPro on the Pi with PanelPro's own Quit, answering "No" to its Store prompt, so a
# deploy (or make ops-pull) can run. The counterpart of pi_start_panelpro.sh.
#
# It drops a Jython file for jmri_cmd_watcher.py (part of the Pi Start Up) that calls
# Apps.handleQuit() and clicks "No" only on JMRI's store-on-quit request
# (StoreAndCompareDialog: "...since the last store. Do you want to Store ALL tables and
# panels?", buttons No / Yes / Cancel). Any other modal dialog is left alone and reported,
# and the script exits 4 so a person looks at it. It never stores and publishes nothing.
#
# When it quits PanelPro it leaves ~/.hart_panelpro_quit_for_deploy on the Pi. A Pi deploy
# within 2 h starts PanelPro again (sync_hart_package.sh, pi/panelpro_restart_due.sh);
# after that, or once PanelPro has been started meanwhile, the marker is ignored and
# removed. Not running → no marker.
#
# Exit: 0 quit (or not running) · 1 still running after the wait · 2 watcher not ready or a
# command already pending · 3 the dropped Jython failed · 4 another dialog appeared.
#
# Usage: tools/hosts/pi_quit_panelpro.sh            (host from HART_PI_SSH, default "pi")
#        tools/hosts/pi_quit_panelpro.sh --print    (print the Jython it would drop, no ssh)
set -euo pipefail
source "$(cd "$(dirname "$0")/../env" && pwd)/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
PROFILE="TCS_MQTT.3f32a166"
WAIT_S=120

read -r -d '' JYTHON <<'PY' || true
import time
from java.awt import Window
from java.lang import Runnable
from javax.swing import AbstractButton, JDialog, JLabel, SwingUtilities

LOG = "/tmp/pi_quit_panelpro.log"
WAIT_S = 115
# JMRI 5.16 configurexml/swing Bundle.properties StoreAndCompareRequest. The permission-
# denied variant ("...since the last store but") is not this text and is not answered.
STORE_REQUEST = ("since the last store.<br>", "Store ALL tables and panels")
STORE_BUTTONS = ["Cancel", "No", "Yes"]


def note(text):
    f = open(LOG, "a")
    f.write(text + "\n")
    f.close()


def walk(c, labels, buttons):
    if isinstance(c, AbstractButton):
        buttons.append(c)
    elif isinstance(c, JLabel) and c.getText():
        labels.append(unicode(c.getText()))
    try:
        for k in c.getComponents():
            walk(k, labels, buttons)
    except Exception:
        pass


class _Quit(Runnable):
    def run(self):
        try:
            from apps import Apps
            Apps.handleQuit()
        except Exception, e:
            note("QUIT FAILED %s" % e)


class _Scan(Runnable):
    """Runs on the EDT: answers the store request, reports other modal dialogs once."""
    def __init__(self, seen):
        self.seen = seen

    def run(self):
        for w in Window.getWindows():
            if not (isinstance(w, JDialog) and w.isShowing()):
                continue
            labels, buttons = [], []
            walk(w.getContentPane(), labels, buttons)
            text = " ".join(labels)
            names = sorted([unicode(b.getText()) for b in buttons])
            key = id(w)
            if all(s in text for s in STORE_REQUEST) and names == STORE_BUTTONS:
                if key not in self.seen:
                    self.seen.add(key)
                    [b for b in buttons if unicode(b.getText()) == "No"][0].doClick()
                    note("store prompt answered No")
            elif w.isModal() and key not in self.seen:
                self.seen.add(key)
                note("OTHER DIALOG %s | %s | %s" % (w.getTitle(), text[:200], ", ".join(names)))


open(LOG, "w").close()
note("quit requested")
SwingUtilities.invokeLater(_Quit())
seen = set()
for _ in range(WAIT_S * 2):
    time.sleep(0.5)
    try:
        SwingUtilities.invokeAndWait(_Scan(seen))
    except Exception, e:
        note("scan error %s" % e)
RESULT = "done"
PY

if [[ "${1:-}" == "--print" ]]; then
  printf '%s\n' "$JYTHON"
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" bash -s -- \
  "$PROFILE" "$WAIT_S" "$(printf '%s\n' "$JYTHON" | base64 | tr -d '\n')" <<'REMOTE'
set -euo pipefail
profile="$1"; wait_s="$2"; jython_b64="$3"
CMD=/tmp/jmri_cmd.py OUT=/tmp/jmri_cmd.out READY=/tmp/jmri_watcher.ready LOG=/tmp/pi_quit_panelpro.log
pid=$(pgrep -f "[o]rg.jmri.profile=$profile" | head -1 || true)
if [[ -z "$pid" ]]; then
  echo "PanelPro is not running on the Pi; nothing to quit."
  exit 0
fi
# The ready file outlives PanelPro, so it only counts when this JVM wrote it.
started=$(( $(date +%s) - $(ps -o etimes= -p "$pid" | tr -d ' ') ))
if [[ ! -f "$READY" ]] || (( $(stat -c %Y "$READY") < started )); then
  echo "jmri_cmd_watcher is not running in this PanelPro; quit it by hand." >&2
  exit 2
fi
if [[ -e "$CMD" ]]; then
  echo "A command is already waiting in $CMD; quit PanelPro by hand." >&2
  exit 2
fi
rm -f "$OUT" "$LOG"
printf '%s' "$jython_b64" | base64 -d > "$CMD.tmp"
mv "$CMD.tmp" "$CMD"
status=1
for _ in $(seq 1 "$wait_s"); do
  sleep 1
  if [[ -f "$OUT" ]] && head -1 "$OUT" | grep -q '^error'; then status=3; break; fi
  if grep -qs '^QUIT FAILED' "$LOG"; then status=3; break; fi
  if grep -qs '^OTHER DIALOG' "$LOG"; then status=4; break; fi
  if ! pgrep -f "[o]rg.jmri.profile=$profile" >/dev/null; then status=0; break; fi
done
# Never leave an unread quit behind: the next PanelPro start would run it.
if [[ -e "$CMD" ]]; then rm -f "$CMD"; echo "removed the unread $CMD" >&2; fi
cat "$LOG" 2>/dev/null || true
case "$status" in
  0) date -Is > "$HOME/.hart_panelpro_quit_for_deploy"
     echo "PanelPro quit on the Pi (it starts again after the next Pi deploy)." ;;
  3) cat "$OUT" 2>/dev/null >&2 || true; echo "The quit command failed; see above." >&2 ;;
  4) echo "PanelPro showed another dialog (above); a person needs to answer it." >&2 ;;
  *) echo "PanelPro is still running on the Pi after ${wait_s} s." >&2 ;;
esac
exit "$status"
REMOTE
