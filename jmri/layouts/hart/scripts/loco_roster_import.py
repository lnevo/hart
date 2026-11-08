# loco_roster_import.py - create DecoderPro roster entries for new locomotives.
#
# Stage 4 of the intake workflow (wiki/pipelines/intake-stages.md). `cars.py locos
# publish` writes jmri/layouts/hart/data/new_locos.json; tools/ops/loco_roster_import.sh
# drops this script into the Pi's JMRI through jmri_cmd_watcher with that list embedded.
# It also runs under CPython, where it only prints the plan (what the unit tests cover).
#
# Per entry: skip it if the roster already has the ID, otherwise create it with the road
# name and number, maker, model, DCC address, long/short flag, photo and icon, and write
# the roster file with JMRI's own RosterEntry.writeFile(null, null) (the call JMRI's ECoS
# import uses). The decoder is left as the NMRA standard until the loco is on the bench.
#
# Config, set in the exec globals by the wrapper:
#   LOCO_IMPORT_APPLY=True   create the entries (default False = plan only)
#   LOCO_IMPORT_JSON='[...]' the contents of new_locos.json
#
# Never commands track or publishes track/cmd.

import json
import sys


def plan(entries, existing_ids):
    """One action per entry: create, or skip when the roster already has the ID."""
    actions = []
    for entry in entries:
        action = "skip" if entry["id"] in existing_ids else "create"
        actions.append({"entry": entry, "action": action})
    return actions


def describe(action):
    e = action["entry"]
    return "%-7s %s  address %s (%s)  %s %s" % (
        action["action"], e["id"], e["dcc_address"],
        "long" if e["long_address"] else "short", e.get("mfg", ""), e.get("model", ""))


def _jmri_available():
    if not sys.platform.startswith("java"):
        return False
    try:
        import jmri
        return hasattr(jmri, "InstanceManager")
    except ImportError:
        return False


def _jmri_run(entries, apply=False):
    from jmri.jmrit.roster import Roster, RosterEntry

    lines = []

    def log(msg):
        lines.append(msg)
        print(msg)

    roster = Roster.getDefault()
    existing = set(str(e.getId()) for e in roster.getAllEntries())
    actions = plan(entries, existing)
    created = 0
    for a in actions:
        log(describe(a))
        if a["action"] != "create" or not apply:
            continue
        e = a["entry"]
        re_ = RosterEntry()
        re_.setId(str(e["id"]))
        re_.setRoadName(str(e["road_name"]))
        re_.setRoadNumber(str(e["road_number"]))
        re_.setMfg(str(e.get("mfg", "")))
        re_.setModel(str(e.get("model", "")))
        re_.setDccAddress(str(e["dcc_address"]))
        re_.setLongAddress(bool(e["long_address"]))
        re_.setComment(str(e.get("comment", "")))
        re_.setImagePath(str(e["image"]))
        re_.setIconPath(str(e["image"]))
        re_.ensureFilenameExists()
        re_.writeFile(None, None)
        roster.addEntry(re_)
        created += 1
    if created:
        roster.writeRoster()
    log("done: %d created" % created)
    if apply and created:
        log("next: roster_rename_road_ids.py is not needed (IDs are road + number already);")
        log("      run ensure_dispatcher_roster_profiles.py, then cs105_roster_sync.sh --apply")
    return "\n".join(lines)


def _cli(argv):
    path = argv[0] if argv else "jmri/layouts/hart/data/new_locos.json"
    with open(path) as fh:
        entries = json.load(fh)
    existing = set(argv[1].split(",")) if len(argv) > 1 else set()
    for a in plan(entries, existing):
        print(describe(a))
    return 0


if _jmri_available():
    _g = globals()
    RESULT = _jmri_run(json.loads(_g.get("LOCO_IMPORT_JSON") or "[]"),
                       apply=bool(_g.get("LOCO_IMPORT_APPLY", False)))
elif __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
