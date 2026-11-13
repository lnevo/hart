# jobkit.py - what the three movers (step_runner.py, move_to.py, stop_test.py) share, run
# inside the Pi's JMRI (Jython 2.7). make_job.py pastes it in front of the runner, after the
# settings, the way it pastes liverule.py; nothing is imported. Needs LOGF (log file path) from
# the settings.
#
# Safety, for every runner that uses it and never to be loosened:
#   * the loco is stopped only with its own throttle at speed 0 (end_job); no e-stop,
#     no track power, no turnouts, no CV or programmer calls
#   * a guard sensor (found by user or system name) that is missing or already ACTIVE stops the
#     run before the loco moves
#   * /tmp/speedrun.active is held by claim() and removed by end_job() only by the run that
#     made it
#
# Names the runner may use: L, NAMES, reg, why, ab, own, hit, claim, scan, check_guards,
# request_throttle, guard_hit, end_job, TL.
import time, threading, os, java, jmri
f = open(LOGF, "a")
def L(m): f.write("%.3f %s\n" % (time.time(), m)); f.flush()
# JMRI sensor states: UNKNOWN 1, ACTIVE 2, INACTIVE 4, INCONSISTENT 8
NAMES = {1: "UNKNOWN", 2: "ACTIVE", 4: "INACTIVE", 8: "INCONSISTENT"}
reg = []; why = [""]; ab = threading.Event(); own = [False]; hit = [""]
class TL(jmri.ThrottleListener):
    # gave_up: the caller stopped waiting; a throttle that arrives later is released at once
    def __init__(self): self.t = None; self.ev = threading.Event(); self.err = None; self.gave_up = False; self.lk = threading.Lock()
    def notifyThrottleFound(self, t):
        self.lk.acquire()
        try:
            late = self.gave_up
            if not late: self.t = t; self.ev.set()
        finally:
            self.lk.release()
        if late:
            try: t.release(self); L("late throttle released")
            except java.lang.Throwable, e: L("late release failed %s" % e)
            except Exception, e: L("late release failed %s" % e)
    def notifyFailedThrottleRequest(self, a, r): self.err = "fail %s" % r; self.ev.set()
    def notifyDecisionRequired(self, a, d): self.err = "decision %s" % d; self.ev.set()
    def notifyStealThrottleRequired(self, a): self.err = "steal"; self.ev.set()
def claim():
    """Take /tmp/speedrun.active, or say why not."""
    if os.path.exists("/tmp/speedrun.active"): why[0] = "another runner is active"; return False
    a = open("/tmp/speedrun.active", "w"); a.write(LOGF); a.close(); own[0] = True
    return True
def guard_hit(name):
    """A guard sensor lit: remember the first one and end the run."""
    hit[0] = hit[0] or name
    why[0] = why[0] or ("guard " + name)
    ab.set()
def scan(guard, extra, want, factory):
    """Find sensors by user or system name and listen to them. One listener per bean:
    factory(name, isg, bean) with name = the user name (else the system name), isg = the bean
    is a guard under either name. A bean is listened to when it is a guard, is in extra, or
    want(user name) is true. Returns {given name: bean} for every guard and extra name found."""
    found = {}
    for s in jmri.InstanceManager.sensorManagerInstance().getNamedBeanSet():
        un = s.getUserName() or ""; sn = s.getSystemName()
        isg = (un in guard) or (sn in guard)
        isx = (un in extra) or (sn in extra)
        for n in list(guard) + list(extra):
            if n == un or n == sn: found[n] = s
        if isg or isx or want(un):
            l = factory(un or sn, isg, s); s.addPropertyChangeListener(l); reg.append((s, l))
    return found
def check_guards(guard, found):
    """Every guard found and not lit; logs NO GUARD for an empty list."""
    for g in guard:
        if g not in found: why[0] = "guard sensor not found: " + g; return False
        if found[g].getKnownState() == 2: why[0] = "guard already ACTIVE: " + g; return False
    if not guard: L("NO GUARD")
    return True
def request_throttle(rid):
    """The throttle of roster entry rid, or None (why says so: roster entry or no throttle)."""
    re = jmri.jmrit.roster.Roster.getDefault().getEntryForId(rid)
    if re is None: why[0] = "roster entry not found: " + rid; return None, None
    tl = TL(); jmri.InstanceManager.throttleManagerInstance().requestThrottle(re, tl, False); tl.ev.wait(10)
    tl.lk.acquire()
    try:
        if tl.t is None: tl.gave_up = True
    finally:
        tl.lk.release()
    if tl.t is None:
        L("NO THROTTLE %s" % tl.err); why[0] = why[0] or "no throttle"; return None, tl
    return tl.t, tl
def end_job(t, tl, funcs):
    """The end of every run: STOP line, 1. speed 0 on the loco's own throttle, 2. every
    function off, 3. throttle released, then listeners removed, marker removed, END."""
    L("STOP " + why[0])
    if t is not None:
        try: t.setSpeedSetting(0.0); L("speed 0")
        except java.lang.Throwable, e: L("speed 0 failed %s" % e)
        except Exception, e: L("speed 0 failed %s" % e)
        for fn in funcs:
            try: getattr(t, "setF%d" % fn)(False); L("F%d off" % fn)
            except java.lang.Throwable, e: L("F%d off failed %s" % (fn, e))
            except Exception, e: L("F%d off failed %s" % (fn, e))
        try: t.release(tl); L("throttle released")
        except java.lang.Throwable, e: L("release failed %s" % e)
        except Exception, e: L("release failed %s" % e)
    for s, l in reg:
        try: s.removePropertyChangeListener(l)
        except java.lang.Throwable, e: L("listener removal failed %s" % e)
        except Exception, e: L("listener removal failed %s" % e)
    if own[0]:
        try: os.remove("/tmp/speedrun.active")
        except Exception, e: pass
    L("END")
