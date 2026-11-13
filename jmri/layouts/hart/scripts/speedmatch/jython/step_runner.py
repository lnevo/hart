# step_runner.py - speed profile runner, runs inside the Pi's JMRI (Jython 2.7).
#
# Dropped through jmri_cmd_watcher by make_job.py / drop_job.sh, which put the settings
# and liverule.py in front of this file. Nothing here is imported; the watcher runs the
# whole job as one script. Replaces the 2026-11-08 runner (docs/jmri/speedmatching/).
#
# Safety, as in the 2026-11-08 runner and never to be loosened:
#   * the loco is stopped only with its own throttle at speed 0 (in the finally block);
#     no emergency stop, no track power, no turnouts, no CV or programmer calls
#   * a guard sensor going ACTIVE ends the run
#   * /tmp/speedrun.kill ends the run
#   * no sensor event for STALL seconds ends the run (a stall below STALL_SKIP_BELOW only
#     skips that creep step)
#
# Settings (globals set in front of this file):
#   LOGF            log file path
#   P_ID            roster id, e.g. "CSX 2738"
#   P_FWD           True = throttle forward, False = throttle reverse  (the DIRECTION setting)
#   FUNCS           function numbers to switch on (0 = lights, needed for detection)
#   GUARD           sensors that abort the run
#   REF, MID        lap counter for the warm-up: REF lit again after MID was lit in between
#   ORDER           block sensor names around the loop in one direction
#   LENGTHS         dict sensor -> length in mm, None when the length is not trusted
#   STEPS_LIST      steps to measure, in order (a repeated step is measured again)
#   WARM_STEP, WARM_LAPS   middle step and number of laps before measuring (0 = none)
#   STOP_K, STOP_REL, MAX_READINGS, SETTLE_EVENTS, LOW_MAX, HIGH_SPAN   see liverule.py
#   STALL0, STALL_SKIP_BELOW, STEP_MAX_S   seconds without an event; creep step limit;
#                                         wall-clock limit for one step
import time, threading, os, java, jmri
f = open(LOGF, "a")
def L(m): f.write("%.3f %s\n" % (time.time(), m)); f.flush()
class TL(jmri.ThrottleListener):
    def __init__(self): self.t = None; self.ev = threading.Event(); self.err = None
    def notifyThrottleFound(self, t): self.t = t; self.ev.set()
    def notifyFailedThrottleRequest(self, a, r): self.err = "fail %s" % r; self.ev.set()
    def notifyDecisionRequired(self, a, d): self.err = "decision %s" % d; self.ev.set()
    def notifyStealThrottleRequired(self, a): self.err = "steal"; self.ev.set()
reg = []; last = [time.time()]; mid = [False]; ref = [0]; ab = threading.Event(); why = [""]
state = {}
reader = SpanReader(ORDER, LENGTHS, SETTLE_EVENTS)
readings = []        # speeds of the current step
phase = ["idle"]     # idle, warmup or measure
class SL(java.beans.PropertyChangeListener):
    def __init__(self, n): self.n = n
    def propertyChange(self, e):
        if e.getPropertyName() != "KnownState": return
        st = e.getNewValue(); now = time.time()
        L("SENS %s %s" % (self.n, "ACTIVE" if st == 2 else "INACTIVE")); last[0] = now
        if self.n in GUARD and st == 2: why[0] = "guard " + self.n; ab.set()
        if st == 2 and state.get(self.n) != 2:
            if phase[0] == "warmup":
                if self.n == MID: mid[0] = True
                if self.n == REF and mid[0]: ref[0] += 1; mid[0] = False; L("WARMUP_LAP %d" % ref[0])
            elif phase[0] == "measure":
                r = reader.feed(now, self.n)
                if r is not None:
                    readings.append(r[0])
                    L("READ %d %.1f dt=%.2f mm=%.1f blocks=%d" % (len(readings), r[0], r[1], r[2], r[3]))
        if st in (0, 2, 4): state[self.n] = st
def wait(cond, stall):
    """Poll until cond() is true. Returns "ok", "abort" or "stall"."""
    while not cond():
        if ab.is_set(): return "abort"
        if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; return "abort"
        if time.time() - last[0] > stall: return "stall"
        time.sleep(0.1)
    return "ok"
def run():
    t = None
    try:
        sm = jmri.InstanceManager.sensorManagerInstance()
        for s in sm.getNamedBeanSet():
            un = s.getUserName() or ""
            if un.startswith("BS ") and (un not in ("BS W-1", "BS W-2") or un in GUARD):
                l = SL(un); s.addPropertyChangeListener(l); reg.append((s, l))
        re = jmri.jmrit.roster.Roster.getDefault().getEntryForId(P_ID)
        tl = TL(); jmri.InstanceManager.throttleManagerInstance().requestThrottle(re, tl, False); tl.ev.wait(10)
        if tl.t is None: L("NO THROTTLE %s" % tl.err); return
        t = tl.t; t.setIsForward(P_FWD)
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        L("RUN loco=%s direction=%s" % (P_ID, "forward" if P_FWD else "reverse"))
        L("CFG k=%d rel=%.3f max=%d settle=%d low_max=%d high_span=%d warm=%d@%d" % (
            STOP_K, STOP_REL, MAX_READINGS, SETTLE_EVENTS, LOW_MAX, HIGH_SPAN, WARM_LAPS, WARM_STEP))
        time.sleep(1.0)
        stall = STALL0
        if WARM_LAPS > 0:
            phase[0] = "warmup"; ref[0] = 0; mid[0] = False; last[0] = time.time()
            t.setSpeedSetting(WARM_STEP / 126.0); L("WARMUP %d laps=%d" % (WARM_STEP, WARM_LAPS))
            # the first REF ends a partial lap, so WARM_LAPS full laps need WARM_LAPS + 1
            r = wait(lambda: ref[0] >= WARM_LAPS + 1, stall)
            if r != "ok":
                if r == "stall": why[0] = "stall %ds in warm-up" % stall
                return
            L("WARMUP_DONE")
        for st in STEPS_LIST:
            reader.restart(span_for_step(st, LOW_MAX, HIGH_SPAN))
            del readings[:]
            phase[0] = "measure"; t0 = time.time(); last[0] = t0
            t.setSpeedSetting(st / 126.0)
            L("STEP %d" % st)
            reason = ""
            while True:
                r = wait(lambda: len(readings) >= STOP_K or time.time() - t0 > STEP_MAX_S, stall)
                if r == "abort": return
                if r == "stall":
                    if st <= STALL_SKIP_BELOW:
                        reason = "stalled"; break
                    why[0] = "stall %ds at step %d" % (stall, st); return
                move, reason = should_move_on(readings, STOP_K, STOP_REL, MAX_READINGS)
                if move: break
                if time.time() - t0 > STEP_MAX_S: reason = "time"; break
                # not settled yet: wait for one more reading
                n0 = len(readings)
                r = wait(lambda: len(readings) > n0 or time.time() - t0 > STEP_MAX_S, stall)
                if r == "abort": return
                if r == "stall":
                    if st <= STALL_SKIP_BELOW: reason = "stalled"; break
                    why[0] = "stall %ds at step %d" % (stall, st); return
            if readings:
                w = readings[-STOP_K:]
                L("STEPDONE %d reason=%s n=%d median=%.1f relsd=%.4f" % (st, reason, len(readings), median(w), rel_stdev(w)))
            else:
                L("STEPDONE %d reason=%s n=0" % (st, reason))
            stall = max(STALL0, 4 * (time.time() - t0) / float(max(1, len(readings))))
        why[0] = "all steps complete"
    except Exception, e: L("ERROR %s" % e)
    finally:
        phase[0] = "idle"
        L("STOP " + why[0])
        if t is not None: t.setSpeedSetting(0.0); L("speed 0")
        for s, l in reg: s.removePropertyChangeListener(l)
        L("END")
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
