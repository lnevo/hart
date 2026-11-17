"""XML assembly of the Layout Editor build: the main and upper turnouts, blocks, sensors, signals and LogixNG added to
the tables, the panel put in place, and the staging guard that the three-level candidate holds the staging
candidate unchanged."""
from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib import paths, tables  # noqa: E402
from hartlib import level_devices  # noqa: E402  the main and upper virtual names and the sensors-clear LogixNG
from hartlib import level_masts as level_masts_lib  # noqa: E402  main_upper_masts.csv and its virtual names
from le_common import BLOCK_SYS, BuildError, DEVICE_MAP, LAYOUT_BLOCK_FIRST, read_csv, slots_module, STAGING, TURNOUT_SYS  # noqa: E402
from approval import canon_sorted, element_label  # noqa: E402  as the approval fingerprints read an element


# Blocks added after the cut-over take the next numbers at the end (owner, 2026-11-16: append), so no main or upper
# system name shifts: BLOCK_NUMBERED_AS gives a renamed block the sort place of the name it replaces, and
# APPENDED_BLOCKS come last, in this order. The balloon loop's split: Loop 1 keeps the loop's numbers; double
# crossover 225's corners: a keeps OS Switch 225's.
BLOCK_NUMBERED_AS = {"Track 107 Loop 1": "Track 107 Loop", "OS Switch 225a": "OS Switch 225"}
APPENDED_BLOCKS = ("Track 107 Loop 2", "OS Switch 225b", "OS Switch 225c", "OS Switch 225d")
COMMENT = "Main and upper level, internal until the import (device map name; build_layout_le.py)"


# ---------------------------------------------------------------- tables

def place(parent: ET.Element, new: list[ET.Element], depth: int, after: ET.Element | None = None) -> None:
    """Insert `new` into `parent` after `after` (default: at the end), indented as JMRI writes."""
    kids = list(parent)
    idx = kids.index(after) + 1 if after is not None else len(kids)
    prev = kids[idx - 1] if idx else None
    pad = "\n" + "  " * depth
    tail = prev.tail if prev is not None else parent.text
    for k, el in enumerate(new):
        ET.indent(el, space="  ", level=depth)
        parent.insert(idx + k, el)
        el.tail = pad
    if new:
        if prev is not None:
            prev.tail = pad
        else:
            parent.text = pad
        new[-1].tail = tail


def bean(tag: str, attrs: dict, sysname: str, user: str, *children) -> ET.Element:
    el = ET.Element(tag, attrs)
    ET.SubElement(el, "systemName").text = sysname
    ET.SubElement(el, "userName").text = user
    for t, v in children:
        ET.SubElement(el, t).text = v
    return el


def r1(v: float) -> str:
    return f"{round(v, 1):.1f}"


def block_sort(name: str):
    kind = 0 if name.startswith("OS ") else 1
    tail = name.split(" ")[-1].split("+")[0]
    digits = "".join(c for c in tail if c.isdigit())
    return (kind, int(digits or 0), name)


# Whether the three-level panel joins staging's helix tracks to the main and upper levels by hidden segments. On
# (owner, 2026-11-17, the helix-join release): joined plainly, with no route-flow entries; staging's own pairs change
# as stock SML discovery finds them (10RA, 10RB, 12R and 14R pair to 16L; 36RB->40RB is lost), accepted. Masts 38RA
# and 40RA stand at the helix-entrance anchors, protecting Track 135-H2 and Track 135-H1. Off, every helix end stays
# an end bumper (the 2026-11-16 cut-over) and the staging guard accepts no difference.
JOIN_HELIX = True
# Retired (owner, 2026-11-17): the hand-wired Digicon desk's yard-ladder buttons, internal turnouts IT:HART:YL:*
# and the routes IO:AUTO:0201-0210 they fire. No desk or panel uses them; the cut-over candidate leaves them out.
RETIRED_TURNOUT_PREFIX = "IT:HART:YL:"


def retire_yard_ladder(root: ET.Element) -> int:
    """Take the yard-ladder internal turnouts, and every route one of them controls or sets, out of tables `root`;
    the count taken out. Stops when any other reference to one is left."""
    gone, users = 0, set()
    for sec in root.findall("turnouts"):
        for t in [t for t in sec.findall("turnout")
                  if (t.findtext("systemName") or "").startswith(RETIRED_TURNOUT_PREFIX)]:
            users |= {t.findtext("userName")} - {None, ""}
            sec.remove(t)
            gone += 1
    for sec in root.findall("routes"):
        for r in [r for r in sec.findall("route")
                  if (r.get("controlTurnout") or "").startswith(RETIRED_TURNOUT_PREFIX) or
                  any((o.get("systemName") or "").startswith(RETIRED_TURNOUT_PREFIX)
                      for o in r.findall("routeOutputTurnout"))]:
            sec.remove(r)
            gone += 1
    named = lambda v: RETIRED_TURNOUT_PREFIX in v or v.strip() in users      # by system or user name
    left = [el.tag for el in root.iter() if named(el.text or "") or any(named(v) for v in el.attrib.values())]
    if left:
        raise BuildError(f"yard ladder: {RETIRED_TURNOUT_PREFIX}* still named by {sorted(set(left))}")
    return gone


def bind_sensors(gen_le: ET.Element, sensors: list[dict]) -> int:
    """Bind each Entry/Exit sensor of sensors.csv in the same slot of the new panel: the same ident and slot, since
    staging keeps the live idents and leg letters. Stops unless that slot is there and resolves to the same facing
    and protected blocks as frozen. Returns how many."""
    gen_ix = slots_module().Index(gen_le)
    bad = []
    for row in sorted(sensors, key=lambda r: (r["ident"], r["slot"])):
        ident, slot, sensor, kind = row["ident"], row["slot"], row["sensor"], row["kind"]
        have = gen_ix.turnouts if kind == "turnout" else gen_ix.points
        if ident not in have:
            bad.append(f"{sensor}: live {kind} {ident} is not on the new panel")
            continue
        want_type = "END_BUMPER" if kind == "end bumper" else "ANCHOR"
        if kind != "turnout" and have[ident].get("type") != want_type:
            bad.append(f"{sensor}: {ident} is a {have[ident].get('type')} on the new panel, live a {want_type}")
            continue
        if kind == "turnout" and not have[ident].get(f"connect{slot.lower()}name"):
            bad.append(f"{sensor}: turnout {ident} has no leg {slot} on the new panel")
            continue
        want, got = (row["facing"], list(row["protects"])), tuple(gen_ix.blocks(kind, ident, slot))
        if want != (got[0], list(got[1])):
            bad.append(f"{sensor}: {ident} {slot} faces {got[0]} and protects {got[1]} on the new panel, live "
                       f"{want[0]} and {want[1]}")
            continue
        if kind == "turnout":
            el = ET.SubElement(have[ident], f"sensor{slot}")
            el.text = sensor
        else:
            have[ident].set(f"{slot}boundsensor", sensor)
    if bad:
        raise BuildError("Entry/Exit sensors not placed for certain: " + "; ".join(bad))
    return len(sensors)


def replace(parent: ET.Element, old: ET.Element, new: ET.Element, depth: int) -> None:
    """Put `new` where `old` stands in `parent`, indented as JMRI writes."""
    idx = list(parent).index(old)
    ET.indent(new, space="  ", level=depth)
    new.tail = old.tail
    parent.remove(old)
    parent.insert(idx, new)


def canon(el: ET.Element) -> str:
    """An element as text without layout whitespace: what must match between the two candidates."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.tail = None
        if c.text is not None and not c.text.strip():
            c.text = None
    return ET.tostring(e, encoding="unicode")




def is_level_bean(el: ET.Element) -> bool:
    """A turnout, sensor, block, layout block, signal head or signal mast add_level_objects or add_level_signals adds
    (by its internal system name)."""
    sysname = (el.findtext("systemName") or el.get("systemName") or "").strip()
    if el.tag == "signalhead":
        return level_masts_lib.is_level_head(sysname)
    if el.tag == "signalmast":
        return level_masts_lib.is_level_mast(sysname)
    if el.tag == "turnout":
        return sysname.startswith(TURNOUT_SYS)
    if el.tag == "sensor":
        return level_devices.is_block_sensor(sysname)
    if el.tag in ("LogixNG", "ConditionalNG", "DigitalMany", "ActionSensor"):
        return bool(level_devices.CLEAR_PREFIX.match(sysname))
    if el.tag == "block":
        return sysname.startswith(BLOCK_SYS)
    if el.tag == "layoutblock":
        return sysname.startswith("ILB") and sysname[3:].isdigit() and int(sysname[3:]) >= LAYOUT_BLOCK_FIRST
    return False


def level_items(P, panel_el: ET.Element) -> set:
    """ids of the panel elements that belong to main and upper, by the plugin's own band of each: their turnouts,
    points, track segments (and the hidden helix and connector joins, drawn with no band), circles, labels (band
    titles have no band either: every one but staging's) and block contents icons. The plugin writes its labels and
    block contents icons in P.labels and P.bcis order, before the carried items, so the n-th of each on the panel is
    the n-th of the plugin's (checked by text and block)."""
    mine = {P.name(t["ident"]) for t in P.turnouts if t["band"] != 0} | \
        {P.name(k) for k, p in P.points.items() if p["band"] != 0} | \
        {P.name(s["ident"]) for s in P.segments if s.get("band") != 0} | \
        {P.name(sh["ident"]) for sh in P.shapes if sh["band"] != 0}
    staging_title = next((i for i, lb in enumerate(P.labels) if lb.get("kind") == "title"), None)
    if staging_title is None:
        raise BuildError("staging guard: the plugin wrote no band title")
    labels = [el for el in panel_el.findall("positionablelabel")
              if not (el.get("hidden") == "yes" and el.get("text") == tables.GENERATED_PANEL_MARKER)]
    bcis = panel_el.findall("BlockContentsIcon")
    if len(labels) < len(P.labels) or len(bcis) != len(P.bcis):
        raise BuildError(f"staging guard: the panel holds {len(labels)} labels and {len(bcis)} block contents icons, "
                         f"the plugin wrote {len(P.labels)} and {len(P.bcis)}")
    out = {id(el) for el in panel_el if el.get("ident") in mine}
    level_masts_ = {m["mast"] for m in P.masts if m["band"] != 0}
    out |= {id(el) for el in panel_el.findall("signalmasticon") if el.get("signalmast") in level_masts_}
    for i, (el, lb) in enumerate(zip(labels, P.labels)):
        if el.get("text") != lb["text"]:
            raise BuildError(f"staging guard: label {i} on the panel reads {el.get('text')!r}, the plugin wrote "
                             f"{lb['text']!r}")
        if lb["band"] != 0 and i != staging_title:
            out.add(id(el))
    for el, b in zip(bcis, P.bcis):
        if el.get("blockcontents") != b["block"]:
            raise BuildError(f"staging guard: a block contents icon on the panel is {el.get('blockcontents')}, the "
                             f"plugin wrote {b['block']}")
        if b["band"] != 0:
            out.add(id(el))
    return out


# What the three-level candidate may change on the staging candidate's panel (owner, 2026-11-16): its size, and
# what the helix joins change: the staging helix tracks run on to the main level instead of ending at a buffer stop,
# so each of their end bumpers becomes an anchor where the hidden join starts (same place, same mast slot), and the
# track segment reaching it is reconnected to it (helix_join_changes). Masts 38RA and 40RA stay in that slot, so
# their icons do not change.
PANEL_SIZE_ATTRS = ("panelheight", "windowheight", "panelwidth", "windowwidth")


def helix_join_changes(missing: list, extra: list, new_le: ET.Element, P, ends: set, joins: set) -> list[str]:
    """Take out of `missing` (staging-candidate elements not in the three-level panel) and `extra` (the reverse) the
    changes the helix joins make, and only those: a staging end bumper in `ends` that the three-level panel draws as
    an anchor in `joins` at the same place, with the same attributes but its ident, its type ANCHOR and one more
    connection, a hidden join segment (P.joins) starting there; and a track segment that ends at that bumper, with
    the same attributes but that connection, now the anchor. Returns them as notes; anything else stays."""
    notes = []
    segs = {el.get("ident"): el for el in new_le.findall("tracksegment")}
    join_segs = {P.name(i) for i in P.joins}
    anchors = {(el.get("x"), el.get("y")): el for el in extra
               if el.tag == "positionablepoint" and el.get("ident") in joins}
    rename = {}
    for old in [el for el in missing if el.tag == "positionablepoint" and el.get("ident") in ends]:
        new = anchors.get((old.get("x"), old.get("y")))
        if new is None or len(old) or len(new):
            continue
        added = {k: v for k, v in new.attrib.items() if k not in old.attrib}
        want = dict(old.attrib, ident=new.get("ident"), type="ANCHOR")
        seg = segs.get(added.get("connect2name"))
        if set(added) != {"connect2name"} or old.get("type") != "END_BUMPER" or \
                {k: new.get(k) for k in want} != want or seg is None or seg.get("ident") not in join_segs or \
                seg.get("hidden") != "yes" or new.get("ident") not in (seg.get("connect1name"), seg.get("connect2name")):
            continue
        rename[old.get("ident")] = new.get("ident")
        missing.remove(old)
        extra.remove(new)
        notes.append(f"end bumper {old.get('ident')} -> anchor {new.get('ident')} (hidden join {seg.get('ident')} to "
                     f"{seg.get('blockname')}" + (f", {old.get('eastboundsignalmast') or old.get('westboundsignalmast')}"
                                                  if old.get("eastboundsignalmast") or old.get("westboundsignalmast")
                                                  else "") + ")")
    by_ident = {el.get("ident"): el for el in extra if el.tag == "tracksegment"}
    for old in [el for el in missing if el.tag == "tracksegment"]:
        at = [k for k in ("connect1name", "connect2name") if old.get(k) in rename]
        new = by_ident.get(old.get("ident"))
        if len(at) != 1 or new is None or len(old) != len(new) or \
                any(canon_sorted(a) != canon_sorted(b) for a, b in zip(old, new)):
            continue
        if dict(new.attrib) != dict(old.attrib, **{at[0]: rename[old.get(at[0])]}):
            continue
        missing.remove(old)
        extra.remove(new)
        notes.append(f"track segment {old.get('ident')} {at[0]} {old.get(at[0])} -> {new.get(at[0])}")
    return notes


def check_staging_unchanged(base, data: bytes, P, panel_name: str) -> list[str]:
    """Stop with BuildError unless the three-level candidate `data` holds the staging candidate (`base`: build()'s
    result for --levels staging --as-live) unchanged: every bean, every other panel and every element of the staging
    panel (track, mast icons, labels, block contents icons, carried items), but the main and upper objects added
    (level_items), the panel size (PANEL_SIZE_ATTRS: three levels are taller) and, only with JOIN_HELIX on, the
    helix-join changes the owner accepted then (helix_join_changes). Returns those helix-join changes, as notes
    (none while JOIN_HELIX is off: every staging element as in the staging candidate, byte for byte)."""
    S = base[1]
    old_root, new_root = tables.loads(base[0]).root, tables.loads(data).root
    bad = []
    if [c.tag for c in old_root] != [c.tag for c in new_root]:
        raise BuildError("staging guard: the top-level sections of the two candidates differ")
    for old, new in zip(old_root, new_root):
        if old.tag == "LayoutEditor" and old.get("name") == panel_name:
            continue
        if old.attrib != new.attrib:
            bad.append(f"<{old.tag}> attributes differ")
        kept = [canon(c) for c in new if not is_level_bean(c)]
        if kept != [canon(c) for c in old]:
            bad.append(f"<{old.tag} {old.get('class') or old.get('name') or ''}> differs beyond the added main and "
                       "upper beans")
    old_le, new_le = tables.layout_editor(old_root, panel_name), tables.layout_editor(new_root, panel_name)
    for k in sorted(set(old_le.attrib) | set(new_le.attrib)):
        if old_le.get(k) != new_le.get(k) and k not in PANEL_SIZE_ATTRS:
            bad.append(f"panel attribute {k}: {old_le.get(k)} -> {new_le.get(k)}")
    ends = {S.name(k) for k, p in S.points.items() if p["type"] == "END_BUMPER"} - \
        {P.name(k) for k, p in P.points.items() if p["type"] == "END_BUMPER"}
    joins = {P.name(i) for (b, i) in P.join_ends if b == 0}     # the staging anchors the hidden joins start at
    if not JOIN_HELIX and (ends or joins):      # main and upper keep their own joins (their connector letters)
        bad.append(f"JOIN_HELIX is off, but staging end bumpers {sorted(ends)} are joined, at {sorted(joins)}")
    level = level_items(P, new_le)
    old_els = defaultdict(list)
    for el in old_le:
        old_els[canon(el)].append(el)
    extra = []
    for el in new_le:
        if id(el) in level:
            continue
        got = old_els.get(canon(el))
        if got:
            got.pop()
        else:
            extra.append(el)
    missing = [el for v in old_els.values() for el in v]
    # unjoined (JOIN_HELIX off), no difference is accepted: staging byte for byte
    notes = helix_join_changes(missing, extra, new_le, P, ends, joins) if JOIN_HELIX else []
    if len(notes) != 2 * len(ends):
        bad.append(f"{len(ends)} staging end bumpers ({', '.join(sorted(ends))}) are joined to the next level, but "
                   f"only these helix-join changes are as expected: {notes}")
    for i, el in enumerate(missing + extra):
        bad.append(f"{element_label(el, i)} {'gone or changed' if el in missing else 'new or changed'}")
    if bad:
        raise BuildError("staging guard: the three-level candidate changes the approved staging panel: " +
                         "; ".join(bad[:20]) + (f" (and {len(bad) - 20} more)" if len(bad) > 20 else ""))
    return notes


def insert_first_panel(root: ET.Element, new: ET.Element, depth: int) -> None:
    """Put `new` before the first Layout Editor panel of `root` (where the hand-drawn panel stood, before the
    Dispatcher System panel), indented as JMRI writes."""
    first = tables.layout_editors(root)[0]
    idx = list(root).index(first)
    ET.indent(new, space="  ", level=depth)
    new.tail = root[idx - 1].tail if idx else root.text
    root.insert(idx, new)


def numbered_blocks(blocks) -> list:
    """The main and upper blocks in the order their system names are numbered: by block_sort (a block in
    BLOCK_NUMBERED_AS in the place of the name it replaces), then APPENDED_BLOCKS."""
    blocks = set(blocks)
    tail = [b for b in APPENDED_BLOCKS if b in blocks]
    return sorted(blocks - set(tail), key=lambda b: block_sort(BLOCK_NUMBERED_AS.get(b, b))) + tail


def level_sensors(path: Path = DEVICE_MAP) -> dict:
    """{block: (sensor system name, sensor user name, comment)} for every main and upper block of the device map:
    its occupancy row's virtual sensor (jmri_name, hartlib.level_devices.block_sensor) and, in the comment, the planned
    detector or why there is none. Stops on a block with no occupancy row or a row whose jmri_name is not the
    block's."""
    try:
        rows = read_csv(path)
    except OSError as exc:
        raise BuildError(f"cannot read the device map {path}: {exc}") from None
    occ = {r["user_name"]: r for r in rows if r["layer"] == "occupancy"}
    out, bad = {}, []
    for r in rows:
        if r["layer"] != "block":
            continue
        block = r["user_name"]
        o = occ.get(level_devices.occupancy_user(block))
        try:
            want = level_devices.block_sensor(block)
        except ValueError as exc:
            bad.append(str(exc))
            continue
        if o is None or o.get("jmri_name") != want:
            bad.append(f"{block}: no occupancy row {level_devices.occupancy_user(block)} with jmri_name {want}")
            continue
        planned = f"planned {o['system_name']} (draft)" if o["system_name"] else o["notes"]
        out[block] = (want, o["user_name"], f"{SENSOR_COMMENT}; {planned}")
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    return out


SENSOR_COMMENT = "Main and upper level occupancy, virtual (device map; build_layout_le.py)"


def add_level_sensors(root: ET.Element, sensors: dict) -> int:
    """Each main and upper block's virtual occupancy sensor (`sensors`: level_sensors) in the internal sensor
    section, as staging's internal sensors are stored, and bound to its block and layout block by user name as
    staging's are (<occupancysensor> after <permissive> in the block's full pass, the occupancysensor attribute after
    systemName on the layout block). Only blocks in `root` are bound; stops on a sensor name already taken or a block
    already bound. The system names of the sensors added, in the order added."""
    internal = next((s for s in root.findall("sensors") if "InternalSensorManager" in (s.get("class") or "")), None)
    if internal is None:
        raise BuildError("the tables have no internal sensor section")
    blocks = {tables.user_name(b): b for b in tables.blocks(root)}
    lbs = {tables.user_name(b): b for b in tables.layout_blocks(root)}
    used = sorted(b for b in sensors if b in blocks)
    taken = {x for s in tables.sensors(root) for x in (tables.system_name(s), tables.user_name(s))}
    clash = sorted({x for b in used for x in sensors[b][:2]} & taken)
    if clash:
        raise BuildError(f"main and upper occupancy sensor names already in the tables: {clash}")
    bound = sorted(b for b in used if blocks[b].find("occupancysensor") is not None or
                   (b in lbs and lbs[b].get("occupancysensor")))
    if bound:
        raise BuildError(f"main and upper blocks already have an occupancy sensor: {bound}")
    beans = []
    for b in sorted(used, key=lambda b: sensors[b][0]):
        system, user, comment = sensors[b]
        el = ET.Element("sensor", {"inverted": "false"})
        for tag, text in (("systemName", system), ("userName", user), ("comment", comment)):
            ET.SubElement(el, tag).text = text
        beans.append(el)
    place(internal, beans, 2)
    for b in used:
        el, user = blocks[b], sensors[b][1]
        kids = list(el)
        after = next((i for i, c in enumerate(kids) if c.tag == "permissive"), None)
        if not after:                       # also 0: a full-pass block starts with its systemName
            raise BuildError(f"block {b} has no <permissive> after its names to put its occupancy sensor after")
        occ = ET.Element("occupancysensor")
        occ.text = user
        occ.tail = kids[after].tail                 # the sensor takes permissive's place in the indentation
        kids[after].tail = kids[after - 1].tail
        el.insert(after + 1, occ)
        if b in lbs:
            lb = lbs[b]
            attrs = list(lb.attrib.items())
            lb.attrib.clear()
            for k, v in attrs[:1] + [("occupancysensor", user)] + attrs[1:]:
                lb.set(k, v)
    return [sensors[b][0] for b in sorted(used, key=lambda b: sensors[b][0])]


# The main and upper virtual block sensors start clear (owner, 2026-11-17): a LogixNG in the tables, stock JMRI, sets
# every one INACTIVE once when the tables load (a ConditionalNG executes at startup unless told not to:
# DefaultLogixNG.execute, executeAtStartup defaults to yes), so the masts are not held at Stop by UNKNOWN blocks. The
# internal sensor manager's default state stays as it is for the other internal sensors. Its names are
# hartlib.level_devices' CLEAR_*.
MALE_DEBUGGER = "jmri.jmrit.logixng.tools.debugger.configurexml.DebuggerMaleDigitalActionSocketXml"
MALE_ACTION = "jmri.jmrit.logixng.implementation.configurexml.DefaultMaleDigitalActionSocketXml"


def male_socket(el: ET.Element) -> None:
    """The <MaleSocket> PanelPro 5.16 stores under a digital action (as on IQDA:AUTO:0001 in tables.xml)."""
    m = ET.SubElement(el, "MaleSocket")
    ET.SubElement(m, "AbstractDebuggerMaleSocket", {"class": MALE_DEBUGGER})
    a = ET.SubElement(m, "AbstractMaleSocket", {"enabled": "yes", "locked": "no", "system": "no",
                                                "catchAbortExecution": "no", "class": MALE_ACTION})
    ET.SubElement(a, "errorHandling").text = "Default"


def add_level_clear(root: ET.Element, sensors: list[str]) -> None:
    """The LogixNG that sets each of `sensors` (system names of the main and upper virtual block sensors) INACTIVE
    when the tables load (hartlib.level_devices: LogixNG CLEAR_LOGIXNG, its ConditionalNG CLEAR_CONDITIONAL, a
    DigitalMany CLEAR_MANY and an ActionSensor per sensor, clear_action), stored as PanelPro 5.16 stores them. Stops
    when the tables have no LogixNG sections or hold these names already."""
    secs = {tag: root.find(tag) for tag in ("LogixNGs", "LogixNGConditionalNGs", "LogixNGDigitalActions")}
    if any(v is None for v in secs.values()):
        raise BuildError(f"the tables have no {', '.join(k for k, v in secs.items() if v is None)} section")
    if any(level_devices.CLEAR_PREFIX.match(e.findtext("systemName") or "") for v in secs.values() for e in v):
        raise BuildError("the tables already hold the main and upper sensors-clear LogixNG")
    sensors = sorted(sensors)
    if not sensors or not all(level_devices.is_block_sensor(x) for x in sensors):
        raise BuildError(f"sensors-clear LogixNG: not all main and upper virtual sensors: {sensors[:3]}")
    lx = ET.Element("LogixNG", {"enabled": "yes", "inline": "no"})
    ET.SubElement(lx, "systemName").text = level_devices.CLEAR_LOGIXNG
    ET.SubElement(lx, "userName").text = level_devices.CLEAR_USER
    ET.SubElement(ET.SubElement(lx, "ConditionalNGs"), "systemName").text = level_devices.CLEAR_CONDITIONAL
    last = [e for e in secs["LogixNGs"] if e.tag == "LogixNG"]
    place(secs["LogixNGs"], [lx], 2, last[-1] if last else None)
    cn = ET.Element("ConditionalNG", {"enabled": "yes"})
    ET.SubElement(cn, "systemName").text = level_devices.CLEAR_CONDITIONAL
    ET.SubElement(cn, "userName").text = level_devices.CLEAR_USER
    ET.SubElement(cn, "thread").text = "0"
    sock = ET.SubElement(cn, "Socket")
    ET.SubElement(sock, "socketName").text = "A"
    ET.SubElement(sock, "systemName").text = level_devices.CLEAR_MANY
    place(secs["LogixNGConditionalNGs"], [cn], 2)
    many = ET.Element("DigitalMany", {"class": "jmri.jmrit.logixng.actions.configurexml.DigitalManyXml"})
    ET.SubElement(many, "systemName").text = level_devices.CLEAR_MANY
    acts = ET.SubElement(many, "Actions")
    actions = []
    for i, sensor in enumerate(sensors, 1):
        name = level_devices.clear_action(sensor)
        s = ET.SubElement(acts, "Socket")
        ET.SubElement(s, "socketName").text = f"A{i}"
        ET.SubElement(s, "systemName").text = name
        a = ET.Element("ActionSensor", {"class": "jmri.jmrit.logixng.actions.configurexml.ActionSensorXml"})
        ET.SubElement(a, "systemName").text = name
        nb = ET.SubElement(a, "namedBean")
        ET.SubElement(nb, "addressing").text = "Direct"
        ET.SubElement(nb, "name").text = sensor
        ET.SubElement(nb, "listenToMemory").text = "no"
        st = ET.SubElement(a, "state")
        ET.SubElement(st, "addressing").text = "Direct"
        ET.SubElement(st, "enum").text = "Inactive"
        ET.SubElement(st, "listenToMemory").text = "no"
        male_socket(a)
        actions.append(a)
    male_socket(many)
    place(secs["LogixNGDigitalActions"], [many] + actions, 2)


def add_level_objects(root: ET.Element, P, names: dict, lengths: dict, staging_blocks: set) -> None:
    """Main and upper: their turnouts, blocks and layout blocks in the tables, under the device-map user names
    (level_names) on internal system names (TURNOUT_SYS, BLOCK_SYS, ILB from LAYOUT_BLOCK_FIRST), so nothing reaches
    MQTT or the field, and each block's virtual occupancy sensor (add_level_sensors), set clear on load
    (add_level_clear). Stops on a block the device map gives no sensor."""
    new_turnouts = sorted({t for k, v in names.items() if k != STAGING for t in v["turnouts"].values()},
                          key=lambda s: block_sort("OS " + s))
    new_blocks = numbered_blocks(b for b in P.blocks if b not in staging_blocks)
    if set(new_blocks) - set(lengths):
        raise BuildError(f"blocks with no source: {sorted(set(new_blocks) - set(lengths))}")
    taken_users = {tables.user_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                   + tables.layout_blocks(root)}
    taken_sys = {tables.system_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                 + tables.layout_blocks(root)}
    turnout_sys = {t: TURNOUT_SYS + t.split(" ", 1)[1] for t in new_turnouts}
    block_sys = {b: f"{BLOCK_SYS}{i:04d}" for i, b in enumerate(new_blocks, 1)}
    lb_sys = {b: f"ILB{LAYOUT_BLOCK_FIRST + i}" for i, b in enumerate(new_blocks)}
    new_users = new_turnouts + new_blocks
    new_sys = list(turnout_sys.values()) + list(block_sys.values()) + list(lb_sys.values())
    clash = sorted((set(new_users) & taken_users) | (set(new_sys) & taken_sys))
    if clash or len(set(new_users)) != len(new_users) or len(set(new_sys)) != len(new_sys):
        raise BuildError(f"names collide: {clash}")

    internal = next(s for s in root.findall("turnouts") if "InternalTurnoutManager" in (s.get("class") or ""))
    place(internal, [bean("turnout", {"feedback": "DIRECT", "inverted": "false", "automate": "Off"}, turnout_sys[t],
                          t, ("comment", COMMENT)) for t in new_turnouts], 2)
    blocks_el = root.find("blocks")
    short = tables.blocks(root, full=False)
    if not short:
        raise BuildError("the live tables have no names-only block pass to add to")
    last_short = short[-1]
    place(blocks_el, [bean("block", {"systemName": block_sys[b]}, block_sys[b], b) for b in new_blocks], 2, last_short)
    place(blocks_el, [bean("block", {"systemName": block_sys[b], "length": r1(lengths[b]), "curve": "0"},
                           block_sys[b], b, ("comment", COMMENT), ("permissive", "no")) for b in new_blocks], 2)
    place(root.find("layoutblocks"),
          [bean("layoutblock", {"systemName": lb_sys[b], "occupiedsense": "2", "trackcolor": "gray",
                                "occupiedcolor": "red", "extracolor": "white"}, lb_sys[b], b) for b in new_blocks], 2)
    sensors = level_sensors()
    if set(new_blocks) - set(sensors):
        raise BuildError(f"main and upper blocks with no occupancy row in the device map: "
                         f"{sorted(set(new_blocks) - set(sensors))}")
    added = add_level_sensors(root, {b: sensors[b] for b in new_blocks})
    if sorted(added) != sorted(sensors[b][0] for b in new_blocks):
        raise BuildError("main and upper blocks whose sensor was not added (no such block in the tables): "
                         f"{sorted({sensors[b][0] for b in new_blocks} - set(added))}")
    add_level_clear(root, added)


SIGNAL_NOTE = "virtual (device map); planned"     # + the planned physical head or mast, a draft
HEAD_CLASS = "jmri.implementation.configurexml.VirtualSignalHeadXml"
MAST_CLASS = "jmri.implementation.configurexml.SignalHeadSignalMastXml"


def add_level_signals(root: ET.Element, rows: list[dict]) -> None:
    """Main and upper: each mast of main_upper_masts.csv as a SignalHeadSignalMast over VirtualSignalHeads, under
    the device map's user names on its virtual system names (jmri_name, from the head's user name; read_level_masts
    checks them), so nothing reaches MQTT or the field; each comment gives its CP, switch and the planned physical
    device (the device map's system_name, a draft). Stops on a name already in the tables."""
    heads_el, masts_el = root.find("signalheads"), root.find("signalmasts")
    if heads_el is None or masts_el is None:
        raise BuildError("the live tables have no signalheads or signalmasts section")
    taken = {tables.system_name(e) for e in heads_el.findall("signalhead") + masts_el.findall("signalmast")} | \
        {tables.user_name(e) for e in heads_el.findall("signalhead") + masts_el.findall("signalmast")}
    heads, masts = [], []
    for r in rows:
        where = f"{r['cp']} | Switch {r['switch']}"
        device = dict(zip([h for h, _u in r["heads"]], level_masts_lib.mast_heads(r["device_system_name"])))
        for h, user in r["heads"]:
            el = ET.Element("signalhead", {"class": HEAD_CLASS})
            ET.SubElement(el, "systemName").text = h
            ET.SubElement(el, "userName").text = user
            ET.SubElement(el, "comment").text = f"{where} | {SIGNAL_NOTE} {device.get(h, '?')}"
            heads.append(el)
        el = ET.Element("signalmast", {"class": MAST_CLASS})
        ET.SubElement(el, "systemName").text = r["system_name"]
        ET.SubElement(el, "userName").text = r["mast"]
        ET.SubElement(el, "comment").text = f"{where} | {SIGNAL_NOTE} {r['device_system_name']}"
        ET.SubElement(el, "unlit", {"allowed": "no"})
        masts.append(el)
    new = [x for e in heads + masts for x in (e.findtext("systemName"), e.findtext("userName"))]
    clash = sorted(set(new) & taken)
    if clash or len(set(new)) != len(new):
        raise BuildError(f"main and upper signal names collide: {clash or 'among themselves'}")
    place(heads_el, heads, 2)
    place(masts_el, masts, 2)
