# Apply the HART synthetic speed profile to every DecoderPro roster entry
# that does not already have one. Run inside PanelPro (jmri_cmd_watcher or
# Scripting ▸ Script Entry). Existing measured profiles are left alone.
#
# Dispatcher System registration only lists locos with a speed profile.

from jmri.jmrit.roster import Roster, RosterSpeedProfile

STEPS = [
    (100, 40.0),
    (200, 80.0),
    (300, 120.0),
    (400, 160.0),
    (500, 200.0),
    (600, 240.0),
    (700, 280.0),
    (800, 320.0),
    (900, 360.0),
    (1000, 400.0),
]

roster = Roster.getDefault()
added = []
kept = []
for entry in roster.getAllEntries():
    existing = entry.getSpeedProfile()
    if existing is not None and existing.hasForwardSpeeds():
        kept.append(str(entry.getId()))
        continue
    profile = RosterSpeedProfile(entry)
    for step, mm_s in STEPS:
        profile.setSpeed(step, float(mm_s), float(mm_s))
    entry.setSpeedProfile(profile)
    entry.updateFile()
    added.append(str(entry.getId()))

roster.writeRoster()
RESULT = "added=%s kept=%s" % (added, kept)
print RESULT
