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
#   TRIGGER    loop sensor user name whose lighting sends speed 0 (make_job refuses system names)
#   GUARD      sensors that abort the run
#   FUNCS      function numbers to switch on (0 = lights)
#   MAX_S      longest the loco may run before the trigger lights, seconds
#   SETTLE_S   seconds of logging after the speed-0 command
#   QUIET_S    the logging also ends once no sensor event came for this long after the command
# Needs jobkit.py in front of it (make_job.py pastes it): L, NAMES, reg, why, ab, hit, claim,
# scan, check_guards, request_throttle, guard_hit, end_job.
box = {"t": None, "stop": None, "last": None, "armed": False, "trig": None}  # throttle, stop time, last event time
lock = threading.Lock()
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
    def __init__(self, n, isg, bean): self.n = n; self.isg = isg; self.bean = bean
    def propertyChange(self, e):
        if e.getPropertyName() != "KnownState": return
        st = e.getNewValue()
        try:
            # the trigger is the resolved bean, however it was named; it acts only once armed
            istr = box["trig"] is not None and self.bean == box["trig"]
            if istr and st == 2:
                if not box["armed"]: L("TRIGGER %s lit before arming, ignored" % self.n)
                elif box["stop"] is None: send_stop("trigger " + self.n)
            L("SENS %s %s" % (self.n, NAMES.get(st, "STATE%s" % st)))
            if box["stop"] is not None: box["last"] = time.time()
            if self.isg and st == 2: guard_hit(self.n)
        except java.lang.Throwable, ex: L("LISTENER ERROR %s" % ex)
        except Exception, ex: L("LISTENER ERROR %s" % ex)
def run():
    t = None; tl = None
    try:
        if not claim(): return
        found = scan(GUARD, [TRIGGER], lambda un: un.startswith("BS "), lambda n, isg, s: SL(n, isg, s))
        if TRIGGER not in found: why[0] = "trigger sensor not found: " + TRIGGER; return
        trig = found[TRIGGER]; box["trig"] = trig
        tname = trig.getUserName() or trig.getSystemName()   # the name the log and the table use
        for g in GUARD:
            if g in found and found[g] == trig: why[0] = "trigger is also a guard: " + g; return
        if not check_guards(GUARD, found): return
        if trig.getKnownState() == 2: why[0] = "trigger already ACTIVE: " + tname; return
        t, tl = request_throttle(P_ID)
        if t is None: return
        if not set_direction(t, P_FWD): return
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        L("STOPTEST loco=%s direction=%s step=%d trigger=%s" % (P_ID, "forward" if P_FWD else "reverse", P_STEP, tname))
        time.sleep(1.0)
        t.setSpeedSetting(P_STEP / 126.0); L("GO %s step %d" % (P_ID, P_STEP)); t0 = time.time()
        # arm only now: a trigger event before GO must not "stop" a loco that has not started
        box["t"] = t; box["armed"] = True
        if trig.getKnownState() == 2 and box["stop"] is None:
            why[0] = "trigger ACTIVE when armed: " + tname; return   # finally: speed 0, no measurement
        while box["stop"] is None and not ab.is_set() and time.time() - t0 < MAX_S:
            if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; break
            time.sleep(0.02)
        if box["stop"] is None:
            if not why[0]: why[0] = "time: trigger not reached in %d s" % MAX_S
            return
        why[0] = "settled"
        # keep logging after the command: SETTLE_S seconds, or QUIET_S without an event
        while True:
            now = time.time()
            if ab.is_set(): why[0] = "settled, then guard %s" % hit[0]; break
            if now - box["stop"] >= SETTLE_S: why[0] = "settle time"; break
            if now - box["last"] >= QUIET_S: why[0] = "quiet"; break
            if os.path.exists("/tmp/speedrun.kill"): why[0] = "settled, then killed"; break
            time.sleep(0.1)
    except java.lang.Throwable, e: L("ERROR %s" % e)
    except Exception, e: L("ERROR %s" % e)
    finally:
        end_job(t, tl, FUNCS)
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
