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
# Needs jobkit.py in front of it (make_job.py pastes it): L, NAMES, reg, why, ab, claim, scan,
# check_guards, request_throttle, guard_hit, end_job.
class SL(java.beans.PropertyChangeListener):
    def __init__(self, n, isg): self.n = n; self.isg = isg
    def propertyChange(self, e):
        if e.getPropertyName() != "KnownState": return
        st = e.getNewValue(); L("SENS %s %s" % (self.n, NAMES.get(st, "STATE%s" % st)))
        if self.isg and st == 2: guard_hit(self.n)
def run():
    t = None; tl = None
    try:
        if not claim(): return
        found = scan(GUARD, UNTIL, lambda un: False, lambda n, isg, s: SL(n, isg))
        for n in UNTIL:
            if n not in found: why[0] = "sensor not found: " + n; return
        if not check_guards(GUARD, found): return
        until = [found[n] for n in UNTIL]
        t, tl = request_throttle(P_ID)
        if t is None: return
        if not set_direction(t, P_FWD): return
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
    except java.lang.Throwable, e: L("ERROR %s" % e)
    except Exception, e: L("ERROR %s" % e)
    finally:
        end_job(t, tl, FUNCS)
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
