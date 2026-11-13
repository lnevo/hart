# move_to.py - run one loco until a block sensor lights, then stop it (Jython 2.7, runs in
# the Pi's JMRI through jmri_cmd_watcher). Positions a loco before a run. Built by
# make_job.py move; the first version was the 2026-11-08 move_to.py (docs/jmri/speedmatching/).
#
# Safety as in step_runner.py: the loco is stopped only with its own throttle at speed 0
# (no emergency stop, no power, no turnouts); a guard sensor lighting, /tmp/speedrun.kill
# and MAX_S seconds all end the run; a guard that is not found or is already ACTIVE stops
# it before it moves.
#
# Settings (globals set in front of this file):
#   LOGF        log file path
#   P_ID        roster id
#   P_FWD       True = throttle forward
#   P_STEP      throttle step (126-step scale)
#   UNTIL       sensors (user or system names); the run ends when ANY of them is ACTIVE for
#               8 checks in a row (0.8 s)
#   GUARD       sensors that abort the run
#   FUNCS       function numbers to switch on (0 = lights)
#   MAX_S       longest the run may take, seconds
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
NAMES = {1: "UNKNOWN", 2: "ACTIVE", 4: "INACTIVE", 8: "INCONSISTENT"}
class SL(java.beans.PropertyChangeListener):
    def __init__(self, n): self.n = n
    def propertyChange(self, e):
        if e.getPropertyName() != "KnownState": return
        st = e.getNewValue(); L("SENS %s %s" % (self.n, NAMES.get(st, "STATE%s" % st)))
        if self.n in GUARD and st == 2: why[0] = "guard " + self.n; ab.set()
def run():
    t = None; tl = None
    try:
        if os.path.exists("/tmp/speedrun.active"): why[0] = "another runner is active"; return
        a = open("/tmp/speedrun.active", "w"); a.write(LOGF); a.close(); own[0] = True
        sm = jmri.InstanceManager.sensorManagerInstance()
        until = []
        for n in list(UNTIL) + list(GUARD):
            s = sm.getSensor(n)
            if s is None: why[0] = "sensor not found: " + n; return
            l = SL(n); s.addPropertyChangeListener(l); reg.append((s, l))
            if n in GUARD:
                if s.getKnownState() == 2: why[0] = "guard already ACTIVE: " + n; return
            else: until.append(s)
        if not GUARD: L("NO GUARD")
        re = jmri.jmrit.roster.Roster.getDefault().getEntryForId(P_ID)
        tl = TL(); jmri.InstanceManager.throttleManagerInstance().requestThrottle(re, tl, False); tl.ev.wait(10)
        if tl.t is None: L("NO THROTTLE %s" % tl.err); return
        t = tl.t; t.setIsForward(P_FWD)
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        time.sleep(1.0)
        t.setSpeedSetting(P_STEP / 126.0); L("GO %s step %d until %s" % (P_ID, P_STEP, ",".join(UNTIL))); t0 = time.time()
        ok = 0
        while not ab.is_set() and time.time() - t0 < MAX_S:
            if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; break
            if [s for s in until if s.getKnownState() == 2]:
                ok += 1
                if ok >= 8: why[0] = "reached"; break
            else: ok = 0
            time.sleep(0.1)
        if not why[0]: why[0] = "time"
    except Exception, e: L("ERROR %s" % e)
    finally:
        L("STOP " + why[0])
        if t is not None:
            t.setSpeedSetting(0.0); L("speed 0")           # 1. stop with its own throttle
            for fn in FUNCS:                               # 2. every function off
                try: getattr(t, "setF%d" % fn)(False); L("F%d off" % fn)
                except Exception, e: L("F%d off failed %s" % (fn, e))
            try: t.release(tl); L("throttle released")     # 3. give the throttle back
            except Exception, e: L("release failed %s" % e)
        for s, l in reg: s.removePropertyChangeListener(l)
        if own[0]:
            try: os.remove("/tmp/speedrun.active")
            except Exception, e: pass
        L("END")
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
