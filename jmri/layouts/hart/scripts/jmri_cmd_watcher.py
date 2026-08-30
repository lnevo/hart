# jmri_cmd_watcher.py - temporary automation channel for agent-driven JMRI work.
#
# Polls /tmp/jmri_cmd.py; when it appears, executes it inside this JMRI
# session (Jython), renames it to /tmp/jmri_cmd.last and writes status +
# any RESULT variable to /tmp/jmri_cmd.out. Remove this script from the
# profile Start Up when the automation session is over.

import os
import time
import traceback
import threading

import java
import jmri

CMD = "/tmp/jmri_cmd.py"
OUT = "/tmp/jmri_cmd.out"
LAST = "/tmp/jmri_cmd.last"
READY = "/tmp/jmri_watcher.ready"


def _run_one():
    src = open(CMD).read()
    if os.path.exists(LAST):
        os.remove(LAST)
    os.rename(CMD, LAST)
    env = {"jmri": jmri, "java": java, "RESULT": None}
    try:
        exec(src, env)
        out = open(OUT, "w")
        out.write("ok\n%s" % (env.get("RESULT"),))
        out.close()
    except Exception:
        out = open(OUT, "w")
        out.write("error\n%s" % traceback.format_exc())
        out.close()


def _loop():
    f = open(READY, "w")
    f.write("ready")
    f.close()
    while True:
        try:
            if os.path.exists(CMD):
                if os.path.exists(OUT):
                    os.remove(OUT)
                _run_one()
        except Exception:
            pass
        time.sleep(0.5)


_t = threading.Thread(target=_loop, name="jmri_cmd_watcher")
_t.setDaemon(True)
_t.start()
print "jmri_cmd_watcher started"
