# step_runner.py - speed profile runner, runs inside the Pi's JMRI (Jython 2.7).
#
# Dropped through jmri_cmd_watcher by make_job.py / drop_job.sh, which put the settings
# and liverule.py in front of this file. Nothing here is imported; the watcher runs the
# whole job as one script. Replaces the 2026-11-08 runner (docs/jmri/speedmatching/).
#
# Safety, as in the 2026-11-08 runner and never to be loosened:
#   * the loco is stopped only with its own throttle at speed 0 (in the finally block);
#     no emergency stop, no track power, no turnouts, no CV or programmer calls
#   * a guard sensor (any sensor, by user or system name) going ACTIVE ends the run; one that
#     is not found, or is already ACTIVE at the start, stops the run before the loco moves
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
#   ROUTE           the route's name (loop1, loop2), logged in the CFG line
#   ORDER           block sensor names around the route in one direction
#   LENGTHS         dict sensor -> length in mm, None when the length is not trusted
#   STEPS_LIST      steps to measure, in order (a repeated step is measured again)
#   WARM_STEP, WARM_LAPS   middle step and number of laps before measuring (0 = none)
#   STOP_K, STOP_REL, MAX_READINGS, SETTLE_EVENTS, LOW_MAX, HIGH_SPAN   see liverule.py
#   STALL0, STALL_CAP, STALL_SKIP_BELOW, STEP_MAX_S   seconds without an event (the limit
#       follows a settled step's reading interval, never above STALL_CAP, and a step that
#       stalled or had no readings never raises it); creep step limit; wall-clock limit
#       for one step
# Needs jobkit.py in front of it (make_job.py pastes it): L, why, ab, claim, scan, check_guards,
# request_throttle, end_job, and the shared route listener SL, last, lock, HOOK, wait.
import json
mid = [False]; ref = [0]
reader = SpanReader(ORDER, LENGTHS, SETTLE_EVENTS)
readings = []        # speeds of the current step
phase = ["idle"]     # idle, warmup or measure
def on_active(n, now):
    # called by jobkit's SL under its lock, once per sensor lighting
    if phase[0] == "warmup":
        if n == MID: mid[0] = True
        if n == REF and mid[0]: ref[0] += 1; mid[0] = False; L("WARMUP_LAP %d" % ref[0])
    elif phase[0] == "measure":
        r = reader.feed(now, n)
        if r is not None:
            readings.append(r[0])
            L("READ %d %.1f dt=%.2f mm=%.1f blocks=%d" % (len(readings), r[0], r[1], r[2], r[3]))
HOOK[0] = on_active
def run():
    t = None; tl = None
    try:
        if not claim(): return
        # one listener per bean, loop name first, so a guard that is also a loop sensor still
        # feeds the reader under its loop name
        found = scan(GUARD, [], lambda un: un.startswith("BS ") and un not in ("BS W-1", "BS W-2"),
                     lambda n, isg, s: SL(n, isg))
        if not check_guards(GUARD, found): return
        t, tl = request_throttle(P_ID)
        if t is None: return
        t.setIsForward(P_FWD)
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        L("RUN loco=%s direction=%s" % (P_ID, "forward" if P_FWD else "reverse"))
        L("CFG route=%s mid=%s k=%d rel=%.4f max=%d settle=%d low_max=%d high_span=%d warm=%d@%d" % (
            ROUTE, MID.replace(" ", "_"), STOP_K, STOP_REL, MAX_READINGS, SETTLE_EVENTS, LOW_MAX, HIGH_SPAN, WARM_LAPS, WARM_STEP))
        L("LENGTHS " + json.dumps(LENGTHS))
        time.sleep(1.0)
        stall = min(STALL0, STALL_CAP)
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
            lock.acquire()   # STEP line, reader restart and phase change happen between two events
            try:
                L("STEP %d" % st)
                reader.restart(span_for_step(st, LOW_MAX, HIGH_SPAN))
                del readings[:]
                phase[0] = "measure"; t0 = time.time(); last[0] = t0
            finally:
                lock.release()
            t.setSpeedSetting(st / 126.0)
            reason = ""
            while True:
                r = wait(lambda: len(readings) >= STOP_K or time.time() - t0 > STEP_MAX_S, stall)
                if r == "ok":
                    move, reason = should_move_on(readings, STOP_K, STOP_REL, MAX_READINGS)
                    if move: break
                    if time.time() - t0 > STEP_MAX_S: reason = "time"; break
                    # not settled yet: wait for one more reading
                    n0 = len(readings)
                    r = wait(lambda: len(readings) > n0 or time.time() - t0 > STEP_MAX_S, stall)
                if r == "abort": return
                if r == "stall":
                    if stall_action(st, STALL_SKIP_BELOW) == "skip": reason = "stalled"; break
                    why[0] = "stall %ds at step %d" % (stall, st); return
            # freeze the readings at the decision: later events belong to the next step
            lock.acquire()
            try:
                frozen = list(readings); phase[0] = "idle"
            finally:
                lock.release()
            if frozen:
                w = frozen[-STOP_K:]
                L("STEPDONE %d reason=%s n=%d median=%.1f relsd=%.4f" % (st, reason, len(frozen), median(w), rel_stdev(w)))
            else:
                L("STEPDONE %d reason=%s n=0" % (st, reason))
            # only a step that settled may set the limit; a stalled or empty one never raises it
            interval = None
            if reason == "settled" and frozen: interval = (time.time() - t0) / float(len(frozen))
            stall = next_stall(STALL0, STALL_CAP, interval)
        why[0] = "all steps complete"
    except java.lang.Throwable, e: L("ERROR %s" % e)
    except Exception, e: L("ERROR %s" % e)
    finally:
        phase[0] = "idle"
        end_job(t, tl, FUNCS)
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
