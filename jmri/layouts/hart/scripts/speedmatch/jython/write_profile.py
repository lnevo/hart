# write_profile.py - write measured speeds into a roster entry's speed profile (Jython 2.7,
# runs in the Pi's JMRI through jmri_cmd_watcher). Dispatcher reads this profile. Built by
# make_job.py profile from the payload of profile_to_roster.py.
#
# It touches only the roster entry: no throttle, no power, no turnout, no CV or programmer.
# Dry run unless APPLY is True: it then logs the old and the new profile and changes nothing.
# On apply it clears the entry's profile, sets the points, and saves the entry
# (RosterEntry.updateFile) and the roster index (Roster.writeRoster).
#
# Units (JMRI 5.16 RosterSpeedProfile): the key of a point is the throttle setting times 1000
# (step / 126 * 1000, rounded), the speeds are mm/s (the Dispatcher synthetic profile is
# 100..1000 with 40..400).
#
# Settings (globals set in front of this file):
#   LOGF     log file path
#   P_ID     roster id
#   POINTS   list of dicts {key, step, forward, reverse}   (key = throttle * 1000, mm/s)
#   APPLY    True writes; anything else is a dry run
import time, threading, os, java, jmri
f = open(LOGF, "a")
def L(m): f.write("%.3f %s\n" % (time.time(), m)); f.flush()
own = [False]
def dump(sp):
    """The points of a RosterSpeedProfile as (key, forward, reverse) tuples."""
    out = []
    if sp is None: return out
    m = sp.getProfileSpeeds()
    for k in m.keySet():
        ss = m.get(k)
        out.append((int(k), float(ss.getForwardSpeed()), float(ss.getReverseSpeed())))
    return out
def show(label, pts):
    L("%s %d points" % (label, len(pts)))
    for k, fw, rv in pts: L("  %s key=%d forward=%.1f reverse=%.1f" % (label, k, fw, rv))
def rounded(pts): return [(k, round(fw, 1), round(rv, 1)) for k, fw, rv in pts]
def run():
    why = ""
    try:
        if os.path.exists("/tmp/speedrun.active"): why = "another runner is active"; return
        a = open("/tmp/speedrun.active", "w"); a.write(LOGF); a.close(); own[0] = True
        L("PROFILE loco=%s apply=%s" % (P_ID, APPLY is True))
        if not POINTS: why = "no points"; return
        for p in POINTS:
            if p["key"] <= 0 or p["forward"] <= 0 or p["reverse"] <= 0: why = "bad point %s" % p; return
        re = jmri.jmrit.roster.Roster.getDefault().getEntryForId(P_ID)
        if re is None: why = "roster entry not found: " + P_ID; return
        old = dump(re.getSpeedProfile())
        show("OLD", old)
        new = sorted([(int(p["key"]), float(p["forward"]), float(p["reverse"])) for p in POINTS])
        show("NEW", new)
        if APPLY is not True:
            why = "dry run: nothing changed (set APPLY = True)"; return
        sp = re.getSpeedProfile()
        if sp is None:
            sp = jmri.jmrit.roster.RosterSpeedProfile(re); re.setSpeedProfile(sp)
        sp.clearCurrentProfile()
        for k, fw, rv in new: sp.setSpeed(k, fw, rv)
        re.updateFile()
        jmri.jmrit.roster.Roster.getDefault().writeRoster()
        got = dump(re.getSpeedProfile())
        show("NOW", got)
        why = "written" if rounded(got) == rounded(new) else "written but the profile read back differs"
    except java.lang.Throwable, e: L("ERROR %s" % e); why = "error"
    except Exception, e: L("ERROR %s" % e); why = "error"
    finally:
        L("STOP " + why)
        if own[0]:
            try: os.remove("/tmp/speedrun.active")
            except Exception, e: pass
        L("END")
th = threading.Thread(target=run); th.setDaemon(True); th.start()
RESULT = "started"
