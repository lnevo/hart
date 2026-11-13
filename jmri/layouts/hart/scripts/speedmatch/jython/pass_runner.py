# pass_runner.py - one timed pass through a stretch of a route, to place a switch on the plan
# (Jython 2.7, runs inside the Pi's JMRI through jmri_cmd_watcher). Built by make_job.py pass:
# liverule.py, the settings and jobkit.py are in front of this file.
#
# The loco is started from rest at one step, every sensor event is logged, and the loco is
# stopped with its own throttle (speed 0 in end_job) once TO_S
# and the sensor after it have lit, or after MAX_S seconds. infer_block_lengths.py
# --pass-log turns the log into the centre of OS Switch 7 and OS Switch 13.
#
# Safety, as in step_runner.py: own throttle only, no emergency stop, no power, no turnouts, no
# CV calls; a guard sensor lighting, /tmp/speedrun.kill, a stall (STALL seconds without a
# route sensor event) and MAX_S end the run; a guard that is not found or is already ACTIVE
# stops it before the loco moves.
#
# Settings: LOGF, P_ID, P_FWD, P_STEP, FUNCS, GUARD, ROUTE, ORDER, FROM_S, TO_S, AFTER_S (the
# sensor after TO_S, whose lighting ends the pass), PATH (the sensors FROM_S .. TO_S the loco is
# expected to light, in order; any other route sensor lighting after FROM_S and before TO_S is
# the wrong way and ends the run), MAX_S, STALL.
seen = {}   # sensor -> True once it lit after the loco was sent off
go = [False]
def on_active(n, now):
    # called by jobkit's SL under its lock, once per sensor lighting
    if not go[0]: return
    seen[n] = True
    if why[0]: return
    if n == AFTER_S and seen.get(TO_S): why[0] = "passed"
    # a route sensor off the expected path while FROM has been reached and TO has not: wrong way
    elif n in ORDER and n not in PATH and seen.get(FROM_S) and not seen.get(TO_S): why[0] = "wrong way"
HOOK[0] = on_active
def run():
    t = None; tl = None
    try:
        if not claim(): return
        found = scan(GUARD, [FROM_S], lambda un: un.startswith("BS ") and un not in ("BS W-1", "BS W-2"),
                     lambda n, isg, s: SL(n, isg))
        if not check_guards(GUARD, found): return
        for n in (FROM_S, TO_S, AFTER_S):
            if n not in ORDER: why[0] = "not a route sensor: " + n; return
        if FROM_S not in found: why[0] = "sensor not found: " + FROM_S; return
        t, tl = request_throttle(P_ID)
        if t is None: return
        if not set_direction(t, P_FWD): return
        for fn in FUNCS: getattr(t, "setF%d" % fn)(True)
        L("RUN loco=%s direction=%s" % (P_ID, "forward" if P_FWD else "reverse"))
        L("CFG route=%s mode=pass step=%d max_s=%g" % (ROUTE, P_STEP, MAX_S))
        time.sleep(1.0)
        L("PATH %s" % ",".join(PATH))
        L("PASS step=%d from=%s to=%s" % (P_STEP, FROM_S, TO_S))
        last[0] = time.time(); t0 = last[0]; go[0] = True
        if found[FROM_S].getKnownState() == 2: seen[FROM_S] = True   # started inside FROM's block
        t.setSpeedSetting(P_STEP / 126.0)
        while not why[0] and not ab.is_set():
            if os.path.exists("/tmp/speedrun.kill"): why[0] = "killed"; break
            if time.time() - t0 > MAX_S: why[0] = "max"; break
            if time.time() - last[0] > STALL: why[0] = "stalled"; break
            time.sleep(0.1)
    except java.lang.Throwable, e: why[0] = why[0] or "error"; L("ERROR %s" % e)
    except Exception, e: why[0] = why[0] or "error"; L("ERROR %s" % e)
    finally:
        go[0] = False
        L("PASSDONE reason=%s" % (why[0] or "ended").replace(" ", "_"))
        end_job(t, tl, FUNCS)
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
