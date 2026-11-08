"""Rename every JMRI roster ID to "<road name> <road number>".

Runs inside the Pi's JMRI (drop it through jmri_cmd_watcher). WiThrottle,
Engine Driver and the CS-105 sync all show the roster ID, so the ID carries
the road name. Entries without road data, or whose new ID already exists,
are skipped. Loco file names are kept. Dispatcher traininfo files name
trains by roster ID, so rewrite them too if a renamed entry appears there
(only Percy, NWR 06, does). Run the CS-105 sync with --rename afterwards.
"""
import jmri
roster = jmri.jmrit.roster.Roster.getDefault()
log = []
changes = []
for re in list(roster.getAllEntries()):
    road, num = (re.getRoadName() or "").strip(), (re.getRoadNumber() or "").strip()
    if not road or not num:
        log.append("SKIP %s: road=%r number=%r" % (re.getId(), road, num)); continue
    new = "%s %s" % (road, num)
    if re.getId() == new:
        log.append("OK   %s" % new); continue
    if roster.getEntryForId(new) is not None:
        log.append("SKIP %s: %r already exists" % (re.getId(), new)); continue
    changes.append((re, new))
for re, new in changes:
    old = re.getId()
    re.setId(new)
    re.updateFile()
    log.append("RENAMED %s -> %s (%s)" % (old, new, re.getFileName()))
if changes:
    roster.writeRoster()
    log.append("roster.xml written, %d renamed" % len(changes))
RESULT = "\n".join(log)
