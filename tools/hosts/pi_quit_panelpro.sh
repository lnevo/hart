#!/usr/bin/env bash
# Quit PanelPro on the Pi with PanelPro's own Quit, answering "No" to its Store prompt, so a
# deploy (or make ops-pull) can run. The counterpart of pi_start_panelpro.sh.
#
# It drops a Jython file for jmri_cmd_watcher.py (part of the Pi Start Up) that calls
# Apps.handleQuit() and then clicks "No" only on JMRI's store-on-quit dialog
# (StoreAndCompareDialog: "Table and/or panel changes have been made since the last
# store"). Any other dialog is left alone and reported, and the script fails so a person
# answers it. It never stores tables, never answers Yes, and publishes nothing.
#
# Usage: tools/hosts/pi_quit_panelpro.sh            (host from HART_PI_SSH, default "pi")
#        tools/hosts/pi_quit_panelpro.sh --print    (print the Jython it would drop, no ssh)
set -euo pipefail
PI_HOST="${HART_PI_SSH:-pi}"
PROFILE="TCS_MQTT.3f32a166"

read -r -d '' JYTHON <<'PY' || true
import time
from java.awt import Window
from java.lang import Runnable
from javax.swing import AbstractButton, JDialog, JLabel, SwingUtilities

LOG = "/tmp/pi_quit_panelpro.log"
STORE_PROMPT = "Table and/or panel changes have been made since the last store"


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
        from apps import Apps
        Apps.handleQuit()


class _Click(Runnable):
    def __init__(self, button):
        self.button = button

    def run(self):
        self.button.doClick()


open(LOG, "w").close()
note("quit requested")
SwingUtilities.invokeLater(_Quit())
answered = False
for _ in range(60):
    time.sleep(0.5)
    for w in Window.getWindows():
        if not (isinstance(w, JDialog) and w.isShowing()):
            continue
        labels, buttons = [], []
        walk(w.getContentPane(), labels, buttons)
        text = " ".join(labels)
        names = [unicode(b.getText()) for b in buttons]
        if STORE_PROMPT in text and not answered:
            no = [b for b in buttons if unicode(b.getText()) == "No"]
            if len(no) == 1:
                SwingUtilities.invokeLater(_Click(no[0]))
                answered = True
                note("store prompt answered No")
                continue
        if STORE_PROMPT not in text:
            note("OTHER DIALOG %s | %s | %s" % (w.getTitle(), text[:200], ", ".join(names)))
RESULT = "done"
PY

if [[ "${1:-}" == "--print" ]]; then
  printf '%s\n' "$JYTHON"
  exit 0
fi

running() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$PI_HOST" "pgrep -f 'org.jmri.profile=$PROFILE' >/dev/null"
}

if ! running; then
  echo "PanelPro is not running on the Pi; nothing to quit."
  exit 0
fi

ssh -o BatchMode=yes "$PI_HOST" 'test -f /tmp/jmri_watcher.ready && ! test -e /tmp/jmri_cmd.py' || {
  echo "jmri_cmd_watcher is not ready on the Pi (or a command is pending); quit PanelPro by hand." >&2
  exit 2
}

printf '%s\n' "$JYTHON" | ssh -o BatchMode=yes "$PI_HOST" \
  'cat > /tmp/jmri_cmd.tmp && mv /tmp/jmri_cmd.tmp /tmp/jmri_cmd.py'

for _ in $(seq 1 90); do
  sleep 1
  if ! running; then
    ssh -o BatchMode=yes "$PI_HOST" 'cat /tmp/pi_quit_panelpro.log 2>/dev/null' || true
    echo "PanelPro quit on the Pi."
    exit 0
  fi
done

ssh -o BatchMode=yes "$PI_HOST" 'cat /tmp/pi_quit_panelpro.log 2>/dev/null' || true
echo "PanelPro is still running on the Pi after 90 s; a dialog may need a person (see above)." >&2
exit 1
