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


def _describe(e):
    # Formatting an exception can itself raise (a broken __str__ or toString).
    try:
        return "%s" % (e,)
    except (Exception, SystemExit, java.lang.Throwable):
        try:
            return "%s (its message could not be printed)" % (type(e).__name__,)
        except (Exception, SystemExit, java.lang.Throwable):
            return "a failure whose message could not be printed"


def _run_one():
    f = open(CMD)
    try:
        src = f.read()
    finally:
        f.close()
    if os.path.exists(LAST):
        os.remove(LAST)
    os.rename(CMD, LAST)
    env = {"jmri": jmri, "java": java, "RESULT": None}
    try:
        exec(src, env)
        text = "ok\n%s" % (env.get("RESULT"),)
    except (Exception, SystemExit, java.lang.Throwable) as e:
        # A Java exception is not a Python Exception in Jython, and a java.lang.Error is not a
        # java.lang.Exception; uncaught, either ends the thread. So does a command's sys.exit().
        try:
            text = "error\n%s" % traceback.format_exc()
        except (Exception, SystemExit, java.lang.Throwable):
            text = "error\n%s" % _describe(e)
    _write_out(text)


def _poll(standing):
    """Handle a waiting command; return None, or the message of what went wrong.

    `standing` is the failure of the pass before. While one stands the result file is left
    alone, so the error result written for it stays readable until a retry replaces it."""
    try:
        if os.path.exists(CMD):
            if standing is None and os.path.exists(OUT):
                os.remove(OUT)
            _run_one()
        return None
    except (Exception, SystemExit, java.lang.Throwable) as e:
        return _describe(e)


def _report(failure):
    # Stay alive for the next command, but leave the failure in the JMRI log and, when the
    # result can be written at all, where the caller waits for it.
    try:
        print("jmri_cmd_watcher: command handling failed: %s" % failure)
    except (Exception, SystemExit, java.lang.Throwable):
        pass
    try:
        if os.path.exists(CMD):
            state = "The command is still waiting and is tried again."
        else:
            state = "The command file is gone (it ran, or was removed) and is not run again."
        _write_out("error\njmri_cmd_watcher: command handling failed: %s\n%s\n" % (failure, state))
    except (Exception, SystemExit, java.lang.Throwable) as e:
        try:
            print("jmri_cmd_watcher: no result could be written: %s" % _describe(e))
        except (Exception, SystemExit, java.lang.Throwable):
            pass


def _loop():
    f = open(READY, "w")
    f.write("ready")
    f.close()
    standing = None
    while True:
        failure = _poll(standing)
        # Once per failure: a failure that persists is retried every pass, and is reported
        # again only when its message changes or after it has cleared.
        if failure is not None and failure != standing:
            _report(failure)
        standing = failure
        time.sleep(0.5)


_t = threading.Thread(target=_loop, name="jmri_cmd_watcher")
_t.setDaemon(True)
_t.start()
print("jmri_cmd_watcher started")
