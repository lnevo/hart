# preflight.py - READ the decoder's CVs on the programming track (Jython 2.7, runs in the
# Pi's JMRI through jmri_cmd_watcher, like step_runner.py). It writes nothing.
#
# This is a separate step BEFORE the loco goes to the loop. HART has no RailCom, so a read
# on the main is not possible: the read uses the global (service mode) programmer, which
# needs the loco alone on the programming track. Only readCV is called; this file has no
# CV write call, no ops-mode programmer, no throttle, no power and no turnout, and a test
# checks that.
#
# The result is a LOGF with lines "<epoch> CV <n> <value>" (or "CV <n> FAIL <status>"),
# ending with END. preflight_compare.py compares it with the roster entry.
#
# Settings (globals set in front of this file by make_job.py):
#   LOGF       log file path
#   P_ID       roster id (for the log only)
#   CVS        list of CV numbers to read
#   CV_WAIT    seconds to wait for each read
import time, threading, jmri
f = open(LOGF, "a")
def L(m): f.write("%.3f %s\n" % (time.time(), m)); f.flush()
class PL(jmri.ProgListener):
    def __init__(self): self.ev = threading.Event(); self.value = None; self.status = None
    def programmingOpReply(self, value, status): self.value = value; self.status = status; self.ev.set()
def run():
    try:
        L("PREFLIGHT %s cvs=%d" % (P_ID, len(CVS)))
        gpm = jmri.InstanceManager.getNullableDefault(jmri.GlobalProgrammerManager)
        prog = gpm.getGlobalProgrammer() if gpm is not None else None
        if prog is None: L("NO PROGRAMMER (no service mode programmer in this JMRI)"); return
        L("PROGRAMMER %s" % prog.getClass().getName())
        for cv in CVS:
            pl = PL()
            try:
                prog.readCV(str(cv), pl)
            except Exception, e:
                L("CV %d FAIL %s" % (cv, e)); continue
            if not pl.ev.wait(CV_WAIT): L("CV %d FAIL timeout" % cv); continue
            if pl.status == 0 and pl.value is not None and pl.value >= 0: L("CV %d %d" % (cv, pl.value))
            else: L("CV %d FAIL status %s" % (cv, pl.status))
    except Exception, e: L("ERROR %s" % e)
    finally:
        L("END")
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
