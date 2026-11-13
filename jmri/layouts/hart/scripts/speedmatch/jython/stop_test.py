# stop_test.py - stop test of one loco, runs inside the Pi's JMRI (Jython 2.7) through
# jmri_cmd_watcher. Built by make_job.py stoptest. It repeats the 2026-11-08 momentum test
# (docs/jmri/speedmatching/profile-2026-11-08/): the loco starts from rest at one step, and
# when the TRIGGER sensor lights it gets speed 0 from its own throttle. Every block sensor
# event is logged with a time stamp, before and after the command, until things settle.
# stoptest_compare.py turns the logs of two locos into the comparison table.
#
# Consist: a consist is driven through its lead loco only. Give the lead's roster id as
# P_ID (the CS-105 consist makes the followers follow); the log then shows the consist.
#
# Safety, as in step_runner.py and never to be loosened:
#   * the loco is stopped only with its own throttle at speed 0 (no e-stop, no track
#     power, no turnouts, no CV or programmer calls)
#   * a guard sensor lighting ends the run (speed 0), and one that is not found or is already
#     ACTIVE stops the run before the loco moves; so does a TRIGGER that is not found, is
#     already ACTIVE, or is also a guard
#   * /tmp/speedrun.kill and MAX_S seconds (the loco never reached the trigger) end the run
#   * /tmp/speedrun.active is held while the job runs, so no other job starts
#
# Settings (globals set in front of this file):
#   LOGF       log file path
#   P_ID       roster id (the consist lead for a consist)
#   P_FWD      True = throttle forward
#   P_STEP     throttle step (126-step scale)
#   TRIGGER    sensor (user or system name) whose lighting sends speed 0
#   GUARD      sensors that abort the run
#   FUNCS      function numbers to switch on (0 = lights)
#   MAX_S      longest the loco may run before the trigger lights, seconds
#   SETTLE_S   seconds of logging after the speed-0 command
#   QUIET_S    the logging also ends once no sensor event came for this long after the command
import time, threading, os, java, jmri
f = open(LOGF, "a")
def L(m): f.write("%.3f %s\n" % (time.time(), m)); f.flush()
class TL(jmri.ThrottleListener):
    def __init__(self): self.t = None; self.ev = threading.Event(); self.err = None
    def notifyThrottleFound(self, t): self.t = t; self.ev.set()
    def notifyFailedThrottleRequest(self, a, r): self.err = "fail %s" % r; self.ev.set()
    def notifyDecisionRequired(self, a, d): self.err = "decision %s" % d; self.ev.set()
    def notifyStealThrottleRequired(self, a): self.err = "steal"; self.ev.set()
reg = []; why = [""]; ab = threading.Event(); own = [False]   # own: this run made /tmp/speedrun.active
box = {"t": None, "stop": None, "last": None}                 # throttle, stop time, last event time
lock = threading.Lock()
NAMES = {1: "UNKNOWN", 2: "ACTIVE", 4: "INACTIVE", 8: "INCONSISTENT"}
def send_stop(reason):
    # speed 0 on the loco's own throttle, once; called from the sensor event
    lock.acquire()
    try:
        if box["stop"] is not None or box["t"] is None: return
        box["stop"] = time.time(); box["last"] = box["stop"]
        box["t"].setSpeedSetting(0.0)
        L("STOPCMD %s" % reason)
    finally:
        lock.release()
class SL(java.beans.PropertyChangeListener):
    def __init__(self, n, isg, istr): self.n = n; self.isg = isg; self.istr = istr
    def propertyChange(self, e):
        if e.getPropertyName() != "KnownState": return
        st = e.getNewValue()
        try:
            if self.istr and st == 2 and box["stop"] is None: send_stop("trigger " + self.n)
            L("SENS %s %s" % (self.n, NAMES.get(st, "STATE%s" % st)))
            if box["stop"] is not None: box["last"] = time.time()
            if self.isg and st == 2:
                why[0] = why[0] or ("guard " + self.n); ab.set()
        except java.lang.Throwable, ex: L("LISTENER ERROR %s" % ex)
        except Exception, ex: L("LISTENER ERROR %s" % ex)
def run():
    t = None; tl = None
    try:
        if os.path.exists("/tmp/speedrun.active"): why[0] = "another runner is active"; return
        a = open("/tmp/speedrun.active", "w"); a.write(LOGF); a.close(); own[0] = True
        if TRIGGER in GUARD: why[0] = "trigger is also a guard: " + TRIGGER; return
        sm = jmri.InstanceManager.sensorManagerInstance()
        found = {}
        for s in sm.getNamedBeanSet():
            un = s.getUserName() or ""; sn = s.getSystemName()
            isg = (un in GUARD) or (sn in GUARD); istr = (un == TRIGGER) or (sn == TRIGGER)
            if un in GUARD: found[un] = s
            if sn in GUARD: found[sn] = s
            if istr: found["trigger"] = s
            if isg or istr or un.startswith("BS "):
                l = SL(un or sn, isg, istr); s.addPropertyChangeListener(l); reg.append((s, l))
        for g in GUARD:
            if g not in found: why[0] = "guard sensor not found: " + g; return
            if found[g].getKnownState() == 2: why[0] = "guard already ACTIVE: " + g; return
        if "trigger" not in found: why[0] = "trigger sensor not found: " + TRIGGER; return
        if found["trigger"].getKnownState() == 2: why[0] = "trigger already ACTIVE: " + TRIGGER; return
        if not GUARD: L("NO GUARD")
        re = jmri.jmrit.roster.Roster.getDefault().getEntryForId(P_ID)
        if re is None: why[0] = "roster entry not found: " + P_ID; return
        tl = TL(); jmri.InstanceManager.throttleManagerInstance().requestThrottle(re, tl, False); tl.ev.wait(10)
        if tl.t is None: L("NO THROTTLE %s" % tl.err); return
        t = tl.t; box["t"] = t; t.setIsForward(P_FWD)
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        L("STOPTEST loco=%s direction=%s step=%d trigger=%s" % (P_ID, "forward" if P_FWD else "reverse", P_STEP, TRIGGER))
        time.sleep(1.0)
        t.setSpeedSetting(P_STEP / 126.0); L("GO %s step %d" % (P_ID, P_STEP)); t0 = time.time()
        while box["stop"] is None and not ab.is_set() and time.time() - t0 < MAX_S:
            if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; break
            time.sleep(0.02)
        if box["stop"] is None:
            if not why[0]: why[0] = "time: trigger not reached in %d s" % MAX_S
            return
        if not why[0]: why[0] = "settled"
        # keep logging after the command: SETTLE_S seconds, or QUIET_S without an event
        while True:
            now = time.time()
            if now - box["stop"] >= SETTLE_S: why[0] = "settle time"; break
            if now - box["last"] >= QUIET_S: why[0] = "quiet"; break
            if ab.is_set(): break
            if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; break
            time.sleep(0.1)
    except java.lang.Throwable, e: L("ERROR %s" % e)
    except Exception, e: L("ERROR %s" % e)
    finally:
        L("STOP " + why[0])
        if t is not None:
            try: t.setSpeedSetting(0.0); L("speed 0")      # 1. stop with its own throttle
            except java.lang.Throwable, e: L("speed 0 failed %s" % e)
            except Exception, e: L("speed 0 failed %s" % e)
            for fn in FUNCS:                               # 2. every function off
                try: getattr(t, "setF%d" % fn)(False); L("F%d off" % fn)
                except java.lang.Throwable, e: L("F%d off failed %s" % (fn, e))
                except Exception, e: L("F%d off failed %s" % (fn, e))
            try: t.release(tl); L("throttle released")     # 3. give the throttle back
            except java.lang.Throwable, e: L("release failed %s" % e)
            except Exception, e: L("release failed %s" % e)
        for s, l in reg: s.removePropertyChangeListener(l)
        if own[0]:
            try: os.remove("/tmp/speedrun.active")
            except Exception, e: pass
        L("END")
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
