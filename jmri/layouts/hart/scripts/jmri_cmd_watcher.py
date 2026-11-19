# jmri_cmd_watcher.py - automation channel for agent-driven JMRI work.
#
# Polls /tmp/jmri_cmd.py; when it appears, executes it inside this JMRI
# session (Jython), renames it to /tmp/jmri_cmd.last and writes status +
# any RESULT variable to /tmp/jmri_cmd.out. It is a standing part of the Pi
# Start Up. Whatever is dropped there runs with JMRI's full access, so the
# AGENTS.md rules on field turnouts and track/cmd apply to it.

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


def _write_out(text):
    # Same as the command drops: write a temp name, then rename, so a reader that
    # finds OUT never sees a half-written result.
    tmp = OUT + ".tmp"
    out = open(tmp, "w")
    try:
        out.write(text)
    finally:
        out.close()
    os.rename(tmp, OUT)


def _run_one():
    src = open(CMD).read()
    if os.path.exists(LAST):
        os.remove(LAST)
    os.rename(CMD, LAST)
    env = {"jmri": jmri, "java": java, "RESULT": None}
    try:
        exec(src, env)
        text = "ok\n%s" % (env.get("RESULT"),)
    except (Exception, java.lang.Exception):
        # A Java exception is not a Python Exception in Jython; uncaught, it ends the thread.
        text = "error\n%s" % traceback.format_exc()
    _write_out(text)


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
        except (Exception, java.lang.Exception) as e:
            # Stay alive for the next command, but leave the failure in the JMRI log.
            print("jmri_cmd_watcher: command handling failed: %s" % e)
        time.sleep(0.5)


_t = threading.Thread(target=_loop, name="jmri_cmd_watcher")
_t.setDaemon(True)
_t.start()
print("jmri_cmd_watcher started")
