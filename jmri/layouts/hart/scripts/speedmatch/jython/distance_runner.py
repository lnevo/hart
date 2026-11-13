# distance_runner.py - speed profile runner, distance mode: one continuous pass through all
# the steps, each measured over a distance instead of a reading count (Jython 2.7, runs inside
# the Pi's JMRI). make_job.py steps --mode distance puts liverule.py, the settings and jobkit.py
# in front of this file.
#
# Safety, as in step_runner.py and never to be loosened:
#   * the loco is stopped only with its own throttle at speed 0 (in end_job, after the last
#     step or when anything ends the run); no emergency stop, no track power, no turnouts, no
#     CV or programmer calls
#   * a guard sensor going ACTIVE ends the run; one that is not found, or is already ACTIVE at
#     the start, stops the run before the loco moves
#   * /tmp/speedrun.kill ends the run
#   * no route sensor event for STALL seconds ends the run (a stall at or below
#     STALL_SKIP_BELOW only skips that creep step)
#
# How a step goes: STEP n (speed set), SETTLE n (wait for the momentum, liverule.settle_time),
# then the next ACTIVE of a route sensor starts MEASURE n. Each block crossed whole (entry to
# entry, trusted length, travel order) is a BLOCK line. The step ends (liverule.DistanceStep)
# when the blocks add up to TARGET_MM over at least MIN_BLOCKS blocks, or after MAX_S seconds of
# measuring; spread over REL earns one more TARGET_MM reading if the time allows.
#
# Settings (globals set in front of this file):
#   LOGF, P_ID, P_FWD, FUNCS, GUARD, ROUTE, ORDER, LENGTHS, MID   as in step_runner.py
#   STEPS_LIST      steps in order, one pass
#   WARM_S, WARM_STEP   seconds at WARM_STEP before the first step (0 = none)
#   TARGET_MM, MIN_BLOCKS, MAX_S, REL   the end rule
#   CV3, CV4        the loco's momentum CVs, for the settle time
#   STALL0, STALL_CAP, STALL_SKIP_BELOW   as in step_runner.py
# Needs liverule.py and jobkit.py in front of it (make_job.py pastes them); the route listener
# SL and the waits (pause) come from jobkit.py.
import json
reader = SpanReader(ORDER, LENGTHS, 0, True)   # whole blocks, one steady direction
phase = ["idle"]     # idle, warmup, settle or measure
cur = [0]; mstart = [None]; trk = [None]
def on_active(n, now):
    # called by jobkit's SL under its lock, once per sensor lighting
    if phase[0] != "measure" or n not in ORDER: return
    b = reader.feed(now, n)
    if mstart[0] is None:
        mstart[0] = now
        L("MEASURE %d from=%s" % (cur[0], n))
    if b is not None:
        L("BLOCK %d block=%s mm=%.1f dt=%.2f mm_s=%.1f" % (cur[0], b[4].replace(" ", "_"), b[2], b[1], b[0]))
        trk[0].add(b[2], b[1])
HOOK[0] = on_active
def run():
    t = None; tl = None
    try:
        if not claim(): return
        found = scan(GUARD, [], lambda un: un.startswith("BS ") and un not in ("BS W-1", "BS W-2"),
                     lambda n, isg, s: SL(n, isg))
        if not check_guards(GUARD, found): return
        t, tl = request_throttle(P_ID)
        if t is None: return
        t.setIsForward(P_FWD)
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        L("RUN loco=%s direction=%s" % (P_ID, "forward" if P_FWD else "reverse"))
        L("CFG route=%s mode=distance steps=%s target_mm=%g min_blocks=%d max_s=%g rel=%g warm_s=%g warm_step=%d cv3=%d cv4=%d mid=%s" % (
            ROUTE, ",".join([str(x) for x in STEPS_LIST]), TARGET_MM, MIN_BLOCKS, MAX_S, REL,
            WARM_S, WARM_STEP, CV3, CV4, MID.replace(" ", "_")))
        L("LENGTHS " + json.dumps(LENGTHS))
        time.sleep(1.0)
        stall = min(STALL0, STALL_CAP)
        prev = 0
        if WARM_S > 0:
            phase[0] = "warmup"; last[0] = time.time()
            t.setSpeedSetting(WARM_STEP / 126.0); L("WARMUP %d secs=%g" % (WARM_STEP, WARM_S))
            r = pause(WARM_S, stall)
            if r != "ok":
                if r == "stall": why[0] = "stall %ds in warm-up" % stall
                return
            L("WARMUP_DONE")
            prev = WARM_STEP
        for st in STEPS_LIST:
            secs = settle_time(CV3, CV4, prev, st)
            lock.acquire()   # STEP line, reader restart and phase change happen between two events
            try:
                L("STEP %d" % st)
                reader.restart(1); trk[0] = DistanceStep(TARGET_MM, MIN_BLOCKS, MAX_S, REL)
                cur[0] = st; mstart[0] = None; phase[0] = "settle"; last[0] = time.time()
            finally:
                lock.release()
            t.setSpeedSetting(st / 126.0)
            L("SETTLE %d secs=%.1f" % (st, secs))
            r = pause(secs, stall)
            if r == "abort": return
            reason = ""
            if r == "stall": reason = "stalled"
            else:
                lock.acquire()
                try:
                    phase[0] = "measure"; last[0] = time.time()
                finally:
                    lock.release()
                while True:
                    if ab.is_set(): return
                    if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; return
                    lock.acquire()
                    try:
                        done = False
                        if mstart[0] is not None:
                            done, reason = trk[0].check(time.time() - mstart[0])
                            if trk[0].extra_new:
                                trk[0].extra_new = False
                                L("EXTRA %d relsd=%.4f" % (st, trk[0].relsd))
                    finally:
                        lock.release()
                    if done: break
                    if time.time() - last[0] > stall: reason = "stalled"; break
                    time.sleep(0.1)
            # freeze at the decision: later events belong to the next step
            lock.acquire()
            try:
                phase[0] = "idle"; blocks = list(trk[0].blocks)
                L("FREEZE %d" % st)   # no block counts after this line, whatever the log shows next
                el = (time.time() - mstart[0]) if mstart[0] is not None else 0.0
            finally:
                lock.release()
            n, mm, s, v, rsd = aggregate(blocks)
            L("STEPDONE %d reason=%s n=%d mm=%.1f s=%.2f mm_s=%.1f relsd=%.4f" % (st, reason, n, mm, s, v, rsd))
            if reason == "stalled":
                if stall_action(st, STALL_SKIP_BELOW) != "skip":
                    why[0] = "stall %ds at step %d" % (stall, st); return
            interval = None
            if reason == "settled" and n: interval = el / float(n)
            stall = next_stall(STALL0, STALL_CAP, interval)
            prev = st
        why[0] = "all steps complete"
    except java.lang.Throwable, e: L("ERROR %s" % e)
    except Exception, e: L("ERROR %s" % e)
    finally:
        phase[0] = "idle"
        end_job(t, tl, FUNCS)
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
