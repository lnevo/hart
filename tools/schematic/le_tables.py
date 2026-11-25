"""XML assembly of the Layout Editor build: the main and upper turnouts, blocks, sensors, signals and LogixNG added to
the tables, and the panel put in place."""
from __future__ import annotations

import copy
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib import devices, paths, railroad, tables  # noqa: E402
from hartlib import level_devices  # noqa: E402  the main and upper virtual names and the sensors-clear LogixNG
from hartlib import level_masts as level_masts_lib  # noqa: E402  masts.csv and its virtual names
from hartlib.tables_build import with_direction  # noqa: E402  a mast's comment names the way it faces
from le_common import (  # noqa: E402
    BLOCK_SYS, BuildError, DEVICE_MAP, LAYOUT_BLOCK_FIRST, main_upper_device_map, TURNOUT_SYS,
)


# Blocks added after the cut-over take the next numbers at the end (owner, 2026-11-16: append), so no main or upper
# system name shifts. block_numbering.csv holds them: a renamed block gets the sort place of the name it replaces
# (numbered_as), an appended one comes last in append_order, and a retired one (a block gone from the levels, such as
# the main and upper helix pieces joined into one staging block per helix track on 2026-11-20) keeps its number
# taken, unused, so no block after it is renumbered. Read and checked here, so a stale row stops the build. A live
# block is given by its device ID (naming-layers step 5), its name the name store's, so a rename changes no row; a
# retired block has no ID any more, so its row gives the name it had (retired), and numbered_as is the name whose
# sort place a block takes (a name no block has now).
NUMBERING = paths.LAYOUT_DATA / "schematic" / "block_numbering.csv"
NUMBERING_COLUMNS = ["id", "numbered_as", "append_order", "retired", "notes"]


def load_numbering(path: Path = NUMBERING, names=None) -> tuple[dict, tuple, tuple]:
    """(BLOCK_NUMBERED_AS, APPENDED_BLOCKS, RETIRED_BLOCKS) from block_numbering.csv, by block name. A row gives a
    main or upper block's id and exactly one of numbered_as or append_order, or no id and the retired block's name in
    retired; blocks are listed once, append_order counts 1, 2, 3 ... without a gap, and a name a block is numbered as is
    not itself a listed block. Each id is named by `names` (hartlib.devices.user_names, default the repo's), on
    level 2 or 3; BuildError on an id neither level has."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or list(rows[0]) != NUMBERING_COLUMNS:
        raise BuildError(f"{path.name}: expected the columns {', '.join(NUMBERING_COLUMNS)}")
    if names is None and any(r["id"].strip() for r in rows):
        names = devices.user_names()
    numbered, appended, retired, seen = {}, {}, [], set()
    for n, r in enumerate(rows, 2):
        ident, as_, order, gone = (r[c].strip() for c in ("id", "numbered_as", "append_order", "retired"))
        if bool(ident) == bool(gone):
            raise BuildError(f"{path.name} line {n}: give a block's id, or a retired block's old name in retired")
        name = gone or next((names[(lv, ident)] for lv in ("2", "3") if (lv, ident) in names), "")
        if not name:
            raise BuildError(f"{path.name} line {n}: {ident} is no main or upper device of the device master (a new "
                             "export dropped it: give the block's new id)")
        if name in seen:
            raise BuildError(f"{path.name} line {n}: block {name!r} is listed twice")
        seen.add(name)
        if gone and (as_ or order):
            raise BuildError(f"{path.name} line {n} ({name}): a retired block holds its number; no numbered_as or "
                             "append_order")
        if not gone and bool(as_) == bool(order):
            raise BuildError(f"{path.name} line {n} ({name}): give exactly one of numbered_as, append_order")
        if gone:
            retired.append(name)
        elif as_:
            numbered[name] = as_
        elif not order.isdigit():
            raise BuildError(f"{path.name} line {n} ({name}): append_order {order!r} is not a whole number")
        else:
            appended[int(order)] = name
    if sorted(appended) != list(range(1, len(appended) + 1)):
        raise BuildError(f"{path.name}: append_order must count 1, 2, 3 ... without a gap or repeat, got "
                         f"{sorted(appended)}")
    clash = sorted(set(numbered.values()) & seen)
    if clash:
        raise BuildError(f"{path.name}: {', '.join(clash)} is both a block and the name another is numbered as")
    return numbered, tuple(appended[k] for k in sorted(appended)), tuple(retired)


NUMBERING_NAMES = ("BLOCK_NUMBERED_AS", "APPENDED_BLOCKS", "RETIRED_BLOCKS")


def __getattr__(name: str):
    """BLOCK_NUMBERED_AS, APPENDED_BLOCKS and RETIRED_BLOCKS, read from block_numbering.csv on first use, not at
    import: they name their blocks through the device master, and a master that does not load must not stop every
    importer of this module before device-map can rebuild it or say what is wrong."""
    if name in NUMBERING_NAMES:
        values = dict(zip(NUMBERING_NAMES, load_numbering()))
        globals().update(values)
        return values[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def numbering() -> tuple[dict, tuple, tuple]:
    """(BLOCK_NUMBERED_AS, APPENDED_BLOCKS, RETIRED_BLOCKS), read once on first use (a test may patch them)."""
    g = globals()
    if not all(n in g for n in NUMBERING_NAMES):
        __getattr__(NUMBERING_NAMES[0])
    return tuple(g[n] for n in NUMBERING_NAMES)
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


# Retired (owner, 2026-11-17): the hand-wired Digicon desk's yard-ladder buttons, internal turnouts IT:HART:YL:*
# and the routes IO:AUTO:0201-0210 they fire. No desk or panel uses them; the build leaves them out.
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
    # by system or user name, anywhere: any text or attribute value of any element
    left = [el.tag for el in root.iter() if isinstance(el.tag, str) and tables.names_any(
        el, users, lambda v: RETIRED_TURNOUT_PREFIX in v, references_only=False, deep=False)]
    if left:
        raise BuildError(f"yard ladder: {RETIRED_TURNOUT_PREFIX}* still named by {sorted(set(left))}")
    return gone


def replace(parent: ET.Element, old: ET.Element, new: ET.Element, depth: int) -> None:
    """Put `new` where `old` stands in `parent`, indented as JMRI writes."""
    idx = list(parent).index(old)
    ET.indent(new, space="  ", level=depth)
    new.tail = old.tail
    parent.remove(old)
    parent.insert(idx, new)


def canon(el: ET.Element) -> str:
    """An element as text without layout whitespace."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.tail = None
        if c.text is not None and not c.text.strip():
            c.text = None
    return ET.tostring(e, encoding="unicode")


def is_level_bean(el: ET.Element) -> bool:
    """A turnout, sensor, block, layout block, signal head or signal mast add_level_objects or add_level_signals adds
    (by its internal system name; a layout block, whose system name JMRI could also give a block added in PanelPro, by
    its user name, the block's, which follows the main and upper naming rule, level_devices.is_level_name)."""
    sysname = (el.findtext("systemName") or el.get("systemName") or "").strip()
    if el.tag == "signalhead":
        return level_masts_lib.is_level_head(sysname)
    if el.tag == "signalmast":
        return level_masts_lib.is_level_mast(sysname)
    if el.tag == "virtualsignalmast":
        return level_masts_lib.is_level_virtual(sysname)
    if el.tag == "turnout":
        return sysname.startswith(TURNOUT_SYS)
    if el.tag == "sensor":
        return level_devices.is_block_sensor(sysname)
    if el.tag in ("LogixNG", "ConditionalNG", "DigitalMany", "ActionSensor", "ActionTurnout"):
        return bool(level_devices.CLEAR_PREFIX.match(sysname))
    if el.tag == "block":
        return sysname.startswith(BLOCK_SYS)
    if el.tag == "layoutblock":
        return sysname.startswith("ILB") and level_devices.is_level_name(tables.user_name(el))
    return False


def level_names(root: ET.Element) -> set[str]:
    """The system and user names of every main and upper object a build added to tables `root` (is_level_bean)."""
    return {n for sec in tables.elements(root) for el in tables.elements(sec) if is_level_bean(el)
            for n in (tables.system_name(el), tables.user_name(el)) if n}


STRIPPED = ("main and upper objects", "Signal Mast Logic from a main or upper mast",
            "Signal Mast Logic destinations naming a main or upper object",
            "Signal Mast Logic left with no destination", "block paths naming a main or upper object",
            "staging block detectors naming a main or upper sensor")


def strip_build_owned(root: ET.Element) -> dict[str, int]:
    """Take out of tables `root` (edited in place) what a build added and what stock JMRI derived from it, so a build
    can start from tables a cut-over wrote (tables.xml): every main and upper object (is_level_bean: turnouts, block
    sensors, blocks, layout blocks, heads, masts and the sensors-clear LogixNG); the Signal Mast Logic whose source is
    one of their masts; each destination of another mast's logic that names one of them, and a logic left with none;
    and each path of another block that names one of them, and the occupancy sensor of a staging block (or its layout
    block) that is one of them: a helix block, whose detector the build binds (add_level_objects). "Names" is by the
    fields where JMRI keeps a bean reference
    (hartlib.tables.names_any), and a name counts when it is one of those objects' or follows the main and upper
    naming rule (level_devices.is_level_name), so a reference to one that is no longer in the tables goes too. Stock
    discovery and a PanelPro load derive the logic and the paths again from the panel the build draws. Everything else
    stays as it is, the main panel too (the build replaces it), and so do the properties discovery sets on a staging
    mast (intermediateSignal): discovery sets them again. Returns the counts
    taken out, keyed by STRIPPED; stops when any of those references is left."""
    names = level_names(root)
    owned = lambda el: tables.names_any(el, names, level_devices.is_level_name)       # noqa: E731
    counts = dict.fromkeys(STRIPPED, 0)
    for sec in list(tables.elements(root)):
        for el in [el for el in tables.elements(sec) if is_level_bean(el)]:
            tables.remove_child(sec, el)
            counts[STRIPPED[0]] += 1
    for box in root.findall("signalmastlogics"):
        for logic in list(box.findall("signalmastlogic")):
            source = tables.text(logic, "sourceSignalMast") or (logic.get("source") or "").strip()
            if source in names or level_devices.is_level_name(source):
                tables.remove_child(box, logic)
                counts[STRIPPED[1]] += 1
                continue
            gone = [d for d in logic.findall("destinationMast") if owned(d)]
            for d in gone:
                tables.remove_child(logic, d)
                counts[STRIPPED[2]] += 1
            if gone and logic.find("destinationMast") is None:
                tables.remove_child(box, logic)
                counts[STRIPPED[3]] += 1
    for block in tables.blocks(root):
        for path in [p for p in block.findall("path") if owned(p)]:
            tables.remove_child(block, path)
            counts[STRIPPED[4]] += 1
    level_sensor = lambda n: n in names or level_devices.is_level_name(n)      # noqa: E731
    for block in tables.blocks(root):
        occ = block.find("occupancysensor")
        if occ is not None and level_sensor((occ.text or "").strip()):
            tables.remove_child(block, occ)
            counts[STRIPPED[5]] += 1
    for lb in tables.layout_blocks(root):
        if level_sensor((lb.get("occupancysensor") or "").strip()):
            del lb.attrib["occupancysensor"]
            counts[STRIPPED[5]] += 1
    left = sorted({sec.tag for sec in tables.elements(root) for el in tables.elements(sec) if is_level_bean(el)} |
                  {"signalmastlogics" for logic in tables.mast_logics(root) if owned(logic)} |
                  {"block paths" for b in tables.blocks(root) for p in b.findall("path") if owned(p)})
    if left:
        raise BuildError(f"taking out what an earlier build added left some of it in {', '.join(left)}")
    return counts


def numbered_blocks(blocks, require_listed: bool = False) -> list:
    """The main and upper blocks in the order their system names are numbered: by block_sort (a block in
    BLOCK_NUMBERED_AS in the place of the name it replaces), then APPENDED_BLOCKS. Give it RETIRED_BLOCKS too to keep
    their numbers taken. With require_listed (the build), a block named in block_numbering.csv that is not among
    `blocks` stops it: the row is stale."""
    blocks = set(blocks)
    numbered_as, appended, retired = numbering()
    missing = sorted((set(numbered_as) | set(appended) | set(retired)) - blocks) if require_listed else []
    if missing:
        raise BuildError(f"{NUMBERING.name} names {', '.join(missing)}, which the main and upper levels no longer "
                         "have; take the row out or rename it")
    tail = [b for b in appended if b in blocks]
    return sorted(blocks - set(tail), key=lambda b: block_sort(numbered_as.get(b, b))) + tail


def level_sensors(path: Path = DEVICE_MAP) -> dict:
    """{block: (sensor system name, sensor user name, comment)} for every main and upper block of the device map:
    its occupancy row's virtual sensor (jmri_name, hartlib.level_devices.block_sensor) and, in the comment, the planned
    detector or why there is none. A part (the device master's part_of: a link inside an OS block) takes its OS block's
    sensor (owner, 2026-11-20). Stops on a block with no occupancy row, a row whose jmri_name is not the block's, or a
    part whose block has none."""
    device = main_upper_device_map(path)               # read and checked by hartlib.railroad
    occ = device.occupancy                             # {block: the occupancy row serving it}, by its blocks column
    out, bad = {}, []
    for block in device.blocks:
        o = occ.get(block)
        try:
            want = level_devices.block_sensor(block)
        except ValueError as exc:
            bad.append(str(exc))
            continue
        if o is None or o.jmri_name != want:
            bad.append(f"{block}: no occupancy row {level_devices.occupancy_user(block)} with jmri_name {want}")
            continue
        planned = f"planned {o.system_name} (draft)" if o.system_name else o.notes
        out[block] = (want, o.user_name, f"{SENSOR_COMMENT}; {planned}")
    try:
        parts = devices.part_lines(("2", "3"), path)
    except railroad.FactsError as exc:
        raise BuildError(f"{paths.rel(path)}: {exc}") from None
    for line, r in parts:
        if r["part_of"] not in out:
            bad.append(f"part {r['user_name']} (level {r['level']}) is part of {r['part_of']}, which has no occupancy "
                       "sensor")
            continue
        out[r["user_name"]] = out[r["part_of"]]
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    return out


SENSOR_COMMENT = "Main and upper level occupancy, virtual (device map; build_layout_le.py)"


def add_level_sensors(root: ET.Element, sensors: dict) -> int:
    """Each main and upper block's virtual occupancy sensor (`sensors`: level_sensors) in the internal sensor
    section, as staging's internal sensors are stored, and bound to its block and layout block by user name as
    staging's are (<occupancysensor> after <permissive> in the block's full pass, the occupancysensor attribute after
    systemName on the layout block). Only blocks in `root` are bound; stops on a sensor name already taken or a block
    already bound. A sensor two blocks share (a part and its OS block) is added once. The system names of the sensors
    added, in the order added."""
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
    beans, once = [], {}
    for b in sorted(used, key=lambda b: sensors[b][0]):
        if sensors[b][0] in once:
            continue
        once[sensors[b][0]] = b
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
    return list(once)


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


def add_level_clear(root: ET.Element, sensors: list[str], turnouts: dict[str, str] | None = None) -> None:
    """The LogixNG that sets each of `sensors` (system names of the main and upper virtual block sensors) INACTIVE
    when the tables load (hartlib.level_devices: LogixNG CLEAR_LOGIXNG, its ConditionalNG CLEAR_CONDITIONAL, a
    DigitalMany CLEAR_MANY and an ActionSensor per sensor, clear_action), and each of `turnouts` ({virtual turnout:
    "Closed" or "Thrown"}) to its startup position (an ActionTurnout, turnout_action), stored as PanelPro 5.16 stores
    them. Stops when the tables have no LogixNG sections or hold these names already."""
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
    for i, (turnout, state) in enumerate(sorted((turnouts or {}).items()), len(sensors) + 1):
        if state not in ("Closed", "Thrown"):
            raise BuildError(f"startup position of {turnout}: {state!r}, not Closed or Thrown")
        name = level_devices.turnout_action(turnout)
        s = ET.SubElement(acts, "Socket")
        ET.SubElement(s, "socketName").text = f"A{i}"
        ET.SubElement(s, "systemName").text = name
        a = ET.Element("ActionTurnout", {"class": "jmri.jmrit.logixng.actions.configurexml.ActionTurnoutXml"})
        ET.SubElement(a, "systemName").text = name
        nb = ET.SubElement(a, "namedBean")
        ET.SubElement(nb, "addressing").text = "Direct"
        ET.SubElement(nb, "name").text = turnout
        ET.SubElement(nb, "listenToMemory").text = "no"
        st = ET.SubElement(a, "state")
        ET.SubElement(st, "addressing").text = "Direct"
        ET.SubElement(st, "enum").text = state
        ET.SubElement(st, "listenToMemory").text = "no"
        male_socket(a)
        actions.append(a)
    male_socket(many)
    place(secs["LogixNGDigitalActions"], [many] + actions, 2)


def band_blocks(nm: dict) -> set[str]:
    """Every block one band's names (`nm`: the plugin's names of a band) give its track: its OS blocks, a double
    crossover's corner blocks and each track's blocks."""
    return set(nm["os"].values()) | {b for v in nm.get("xover_blocks", {}).values() for b in v.values()} | \
        {b for v in nm["blocks"].values() for b in v}


def bean_names(root: ET.Element) -> dict[str, set[str]]:
    """{turnouts, blocks, masts}: the names a panel can bind in tables `root` (a turnout's system or user name, a
    layout block's user name, a mast's system or user name)."""
    return dict(turnouts=set(tables.by_any_name(tables.turnouts(root))),
                blocks={tables.user_name(b) for b in tables.layout_blocks(root)},
                masts=set(tables.mast_system_names(root)))


def drawn_blocks(P, bands: set[int]) -> set[str]:
    """The blocks the plugin drew on `bands` (band indexes): its track segments' and turnouts' legs'."""
    return {s["block"] for s in P.segments if s.get("band") in bands and s.get("block")} | \
        {b for t in P.turnouts if t.get("band") in bands for b in (t.get("blocks") or {}).values() if b}


def check_bound(root: ET.Element, P, names: dict, base_keys: set, base_ix: set, base: dict, base_name: str) -> None:
    """One check for every level once the build's beans are in tables `root`: each turnout, block and mast a band's
    names bind (`names`: {band key: names}) is a bean, for a band of a level the base holds (`base_keys`) of the base
    itself (`base`: bean_names of the tables before the build added any, `base_name`), for the rest of `root`; the
    bands of those levels (`base_ix`, band indexes) draw only blocks their names hold; and each block the panel draws
    (P.blocks) is a bean of `root`. BuildError names each by band."""
    if base_keys - set(names):
        raise BuildError(f"the base's bands {sorted(base_keys - set(names))} are not among the bands named "
                         f"{sorted(names)}")
    built = bean_names(root)
    bad = []
    for key, nm in names.items():
        have = base if key in base_keys else built
        lost = [f"turnouts {sorted(t for t in set(nm['turnouts'].values()) if t not in have['turnouts'])}",
                f"blocks {sorted(b for b in band_blocks(nm) if b not in have['blocks'])}",
                f"masts {sorted(m['mast'] for m in nm.get('masts', []) if m['mast'] not in have['masts'])}"]
        lost = [x for x in lost if not x.endswith(" []")]
        if lost:
            bad.append(f"{key}: {', '.join(lost)}")
    own = {b for k in base_keys for b in band_blocks(names[k])}
    stray = sorted(drawn_blocks(P, base_ix) - own)
    if stray:
        bad.append(f"{', '.join(sorted(base_keys))} draws blocks its names do not hold: {stray}")
    drawn = sorted(set(P.blocks) - built["blocks"])
    if drawn:
        bad.append(f"the panel draws blocks {drawn}")
    if bad:
        raise BuildError(f"names the panel binds that are no bean of {base_name} or of the levels the build adds: "
                         + "; ".join(bad))


def add_level_objects(root: ET.Element, P, names: dict, lengths: dict, base_keys: set,
                      thrown: frozenset = frozenset()) -> None:
    """The levels the build adds (every band in `names` but `base_keys`, the bands of a level the base holds:
    le_common.BASE_LEVELS): their turnouts, blocks and layout blocks in the tables, under the device-map user names
    (level_names) on internal system names (TURNOUT_SYS, BLOCK_SYS, ILB from LAYOUT_BLOCK_FIRST), so nothing reaches
    MQTT or the field, and each block's virtual occupancy sensor (add_level_sensors), set clear on load
    (add_level_clear); a base band's block the panel draws on another level too (a helix block) is bound to the
    device map's sensor. Stops on a block the device map gives no sensor."""
    if not base_keys or base_keys - set(names):
        raise BuildError(f"the base's bands {sorted(base_keys)} are not all among the bands named {sorted(names)}")
    staging_blocks = {b for k in base_keys for b in band_blocks(names[k])}
    new_turnouts = sorted({t for k, v in names.items() if k not in base_keys for t in v["turnouts"].values()},
                          key=lambda s: block_sort("OS " + s))
    drawn = {b for b in P.blocks if b not in staging_blocks}
    retired = set(numbering()[2])
    if drawn & retired:
        raise BuildError(f"retired blocks drawn again: {sorted(drawn & retired)}; take them out of "
                         f"{NUMBERING.name}'s retired rows")
    order = numbered_blocks(drawn | retired, require_listed=True)       # a retired block keeps its number, unused
    new_blocks = [b for b in order if b not in retired]
    if set(new_blocks) - set(lengths):
        raise BuildError(f"blocks with no source: {sorted(set(new_blocks) - set(lengths))}")
    taken_users = {tables.user_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                   + tables.layout_blocks(root)}
    taken_sys = {tables.system_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                 + tables.layout_blocks(root)}
    turnout_sys = {t: TURNOUT_SYS + t.split(" ", 1)[1] for t in new_turnouts}
    block_sys = {b: f"{BLOCK_SYS}{i:04d}" for i, b in enumerate(order, 1) if b in drawn}
    lb_sys = {b: f"ILB{LAYOUT_BLOCK_FIRST + i}" for i, b in enumerate(order) if b in drawn}
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
    # a helix block: the staging block drawn on a level too, bound to the device map's sensor (owner, 2026-11-20)
    shared = sorted(b for b in staging_blocks & set(P.blocks) if b in sensors)
    added = add_level_sensors(root, {b: sensors[b] for b in new_blocks + shared})
    if sorted(added) != sorted({sensors[b][0] for b in new_blocks + shared}):
        raise BuildError("main and upper blocks whose sensor was not added (no such block in the tables): "
                         f"{sorted({sensors[b][0] for b in new_blocks + shared} - set(added))}")
    # every virtual turnout starts Closed, its normal leg B, except where the main route runs through leg C
    if set(thrown) - set(new_turnouts):
        raise BuildError(f"turnouts to start Thrown that the panel does not have: {sorted(set(thrown) - set(new_turnouts))}")
    add_level_clear(root, added, {turnout_sys[t]: "Thrown" if t in thrown else "Closed" for t in new_turnouts})


SIGNAL_NOTE = "virtual (device map); planned"     # + the planned physical head or mast, a draft
UNPLANNED_NOTE = "virtual (device map); not on a node yet"    # no board room on the draft plant (ADR-024)


def signal_note(planned: str | None) -> str:
    """A main or upper head's or mast's comment after its place: the planned physical device (the device map's
    system name, a draft), or that it has none yet."""
    return f"{SIGNAL_NOTE} {planned}" if planned else UNPLANNED_NOTE
HEAD_CLASS = "jmri.implementation.configurexml.VirtualSignalHeadXml"
MAST_CLASS = "jmri.implementation.configurexml.SignalHeadSignalMastXml"
VIRTUAL_MAST_CLASS = "jmri.implementation.configurexml.VirtualSignalMastXml"


def add_level_signals(root: ET.Element, rows: list[dict]) -> None:
    """Main and upper: each of their masts in masts.csv as a SignalHeadSignalMast over VirtualSignalHeads, under
    the device map's user names on its virtual system names (jmri_name, from the head's user name; read_level_masts
    checks them), so nothing reaches MQTT or the field; each comment gives its CP, switch and the planned physical
    device (the device map's system_name, a draft). A virtual mast (a destination at a buffer stop, no heads) is a
    VirtualSignalMast, unlit allowed, as staging's are. Stops on a name already in the tables."""
    heads_el, masts_el = root.find("signalheads"), root.find("signalmasts")
    if heads_el is None or masts_el is None:
        raise BuildError("the live tables have no signalheads or signalmasts section")
    present = heads_el.findall("signalhead") + masts_el.findall("signalmast") + masts_el.findall("virtualsignalmast")
    taken = {tables.system_name(e) for e in present} | {tables.user_name(e) for e in present}
    heads, masts = [], []
    for r in rows:
        if level_masts_lib.is_level_virtual(r["system_name"]):    # a hidden destination mast at a buffer stop
            el = ET.Element("virtualsignalmast", {"class": VIRTUAL_MAST_CLASS})
            ET.SubElement(el, "systemName").text = r["system_name"]
            ET.SubElement(el, "userName").text = r["mast"]
            ET.SubElement(el, "comment").text = with_direction(" | ".join(x for x in (r["cp"], "buffer stop") if x),
                                                               r["dir"])
            ET.SubElement(el, "unlit", {"allowed": "yes"})
            masts.append(el)
            continue
        where = " | ".join(x for x in (r["cp"], f"Switch {r['switch']}" if r["switch"] else "intermediate") if x)
        device = dict(zip([h for h, _u in r["heads"]], level_masts_lib.mast_heads(r["device_system_name"])))
        for h, user in r["heads"]:
            el = ET.Element("signalhead", {"class": HEAD_CLASS})
            ET.SubElement(el, "systemName").text = h
            ET.SubElement(el, "userName").text = user
            ET.SubElement(el, "comment").text = f"{where} | {signal_note(device.get(h))}"
            heads.append(el)
        el = ET.Element("signalmast", {"class": MAST_CLASS})
        ET.SubElement(el, "systemName").text = r["system_name"]
        ET.SubElement(el, "userName").text = r["mast"]
        ET.SubElement(el, "comment").text = with_direction(f"{where} | {signal_note(r['device_system_name'])}",
                                                           r["dir"])
        ET.SubElement(el, "unlit", {"allowed": "no"})
        masts.append(el)
    new = [x for e in heads + masts for x in (e.findtext("systemName"), e.findtext("userName"))]
    clash = sorted(set(new) & taken)
    if clash or len(set(new)) != len(new):
        raise BuildError(f"main and upper signal names collide: {clash or 'among themselves'}")
    place(heads_el, heads, 2)
    place(masts_el, masts, 2)
