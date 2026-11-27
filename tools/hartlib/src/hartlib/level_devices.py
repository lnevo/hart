"""The naming rule of the main and upper levels' virtual JMRI devices, in one place.

The main and upper physical plant is not reviewed yet, so every main and upper turnout, block sensor, signal head and
mast in tables.xml and on the CATS desks is an internal device whose system name comes from its own user name, never
from the device map's draft physical address or from drawing order: adding a block or a switch elsewhere changes no
other device's name. The device master (column jmri_name) maps each to its planned physical
device, so a physical device is later swapped in by that mapping alone.

- Turnout "Switch <n>": TURNOUT_PREFIX + n (IT:HART:C3:107).
- Block "<name>": its occupancy sensor SENSOR_PREFIX + block_key (IS:HART:C3:B:107-109, IS:HART:C3:B:107_Loop_2,
  IS:HART:C3:B:OS225b), user name occupancy_user ("BS 107-109", "BS Switch 225b").
- Head "Head <mast>[ Top|Bottom]": head_name (IH:HART:C3:108LA, IH:HART:C3:108R_Top).
- The LogixNG that sets every block sensor INACTIVE when the tables load (CLEAR_*; startup_logixng.start_logixng, from
  each row's start)
  and its reader clear_sensors; the same LogixNG sets every virtual turnout to its startup position, Closed except
  where the main route runs through the diverging leg, read by turnout_states.

Used by tools/schematic/build_device_map.py (and its device_map_masts.py), hartlib.tables_build, build_cats_panel.py,
hartlib.level_masts, tools/audit/check_layout_facts.py and www/scripts/tables_page.py.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# The levels this naming rule is for, main and upper: their beans are virtual until their plant is wired
LEVELS = ("2", "3")
TURNOUT_PREFIX = "IT:HART:C3:"
SENSOR_PREFIX = "IS:HART:C3:B:"
HEAD_PREFIX = "IH:HART:C3:"
# a device-map head's user name: a home signal's (Head 108LA, Head 108R Top) or an intermediate's, named from its
# milepost with the line code, A main and B upper (Head A87)
HEAD_USER = re.compile(r"Head (\d+[LR][A-Z]?|[AB]\d+)(?: (Top|Bottom))?")
MAST_USER = re.compile(r"Mast (\d+[LR][A-Z]?|[AB]\d+)")     # a main or upper mast's user name: its heads' key
HEAD = re.compile(re.escape(HEAD_PREFIX) + r"(?:\d+[LR][A-Z]?|[AB]\d+)(?:_Top|_Bottom)?")    # its virtual system name
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

# The sensors-clear LogixNG. LogixNG system names with "$" may hold any characters
# (LogixNG_Manager.validSystemNameFormat, JMRI 5.16), so these are named, not numbered.
CLEAR_LOGIXNG = "IQ$HART:C3:BlockSensorsClear"
CLEAR_CONDITIONAL = "IQC$HART:C3:BlockSensorsClear"
CLEAR_MANY = "IQDA$HART:C3:BlockSensorsClear"
CLEAR_ACTION = "IQDA$HART:C3:B:"          # + the block key: one ActionSensor per sensor
CLEAR_USER = "Main and upper block sensors clear on start"
TURNOUT_ACTION = "IQDA$HART:C3:T:"          # + the switch number: one ActionTurnout per virtual turnout, same LogixNG
CLEAR_PREFIX = re.compile(r"IQ(?:C|DA)?\$HART:C3:")
# The JMRI word the startup LogixNG sets for a device-master row's start (hartlib.devices.START)
START_ENUM = {"inactive": "Inactive", "closed": "Closed", "thrown": "Thrown"}

# The words of the main and upper beans' comments, which build_device_map.py writes into each row's bean_comment
# (device_map_rows.bean_cells) and hartlib.tables_build.master_beans puts on the bean. Staging's form: the parts joined
# by " | ", the place first; a bean no field device drives says
# VIRTUAL_NOTE, as a staging head on an internal name does, then the planned physical device, a draft.
VIRTUAL_NOTE = "internal, not wired"
UNPLACED_NOTE = "not on a node yet"     # a head or mast with no board room on the draft plant (ADR-024, ADR-028)


def planned_note(planned: str) -> str:
    """The part of a main or upper comment that names the planned physical device (the device map's system name, a
    draft): "planned M2T3308 (draft)"; for a head or mast with none, UNPLACED_NOTE."""
    return f"planned {planned} (draft)" if planned else UNPLACED_NOTE


def block_key(block: str) -> str:
    """The stable key of a main or upper block, from its user name alone: "Track " dropped, "OS Switch " shortened to
    "OS", spaces to "_" ("Track 107 Loop 2" -> 107_Loop_2, "OS Switch 225b" -> OS225b). ValueError on a name that
    would give a key with anything but letters, digits, "-" and "_"."""
    key = ("OS" + block.removeprefix("OS Switch ") if block.startswith("OS Switch ") else
           block.removeprefix("Track ")).replace(" ", "_")
    if not _KEY.fullmatch(key) or key == block:
        raise ValueError(f"block {block!r} gives no clean sensor key ({key!r})")
    return key


def block_sensor(block: str) -> str:
    """The virtual occupancy sensor of a main or upper block: IS:HART:C3:B:<block_key>."""
    return SENSOR_PREFIX + block_key(block)


def occupancy_user(block: str) -> str:
    """The occupancy sensor's user name of a block: "BS " + the name less "Track "; "BS Switch <n>" for
    "OS Switch <n>" (ADR-005)."""
    return "BS " + (block.removeprefix("OS ") if block.startswith("OS Switch ") else block.removeprefix("Track "))


def is_block_sensor(system_name: str) -> bool:
    return (system_name or "").startswith(SENSOR_PREFIX)


# Every main and upper name, by rule, for references to a device that is no longer in the tables. System names: the
# prefixes above, the build's blocks (BLOCK_PREFIX) and a mast over virtual heads (its system name holds the head's).
# User names: the main and upper switch numbers, 101 to 245, after the device kind, as the device
# map writes them ("Switch 107", "Track 107-109", "OS Switch 225b", "BS 107-109", "Mast <n><L|R>", "Head 108R Top"),
# and intermediates by line code and milepost ("Mast A87", "Head B88"), and the helix blocks' virtual occupancy sensors
# ("BS Helix Outer"; the blocks themselves, "Track Helix Outer", are staging's beans).
# Staging numbers stop at 40, and its masts 2035 and 2036 have four digits.
BLOCK_PREFIX = "IB:C3:"
# the main and upper layout blocks: ILB1001 up (hartlib.block_numbering numbers them with the blocks); staging's stop
# well below
LAYOUT_BLOCK_FIRST = 1001
LEVEL_USER = re.compile(r"(?:Switch|OS Switch|Track|BS|BS Switch|Mast|Head) [12]\d\d(?!\d).*|(?:Mast|Head) [AB]\d+(?: .*)?"
                        r"|BS Helix .+")


def is_level_name(name: str) -> bool:
    """Whether `name` (a system or user name) is a main or upper device's by the naming rule, present or not."""
    name = (name or "").strip()
    return (name.startswith((TURNOUT_PREFIX, SENSOR_PREFIX, HEAD_PREFIX, BLOCK_PREFIX)) or HEAD_PREFIX in name
            or bool(CLEAR_PREFIX.match(name)) or bool(LEVEL_USER.fullmatch(name)))


def head_name(user: str) -> str:
    """The virtual system name of a main or upper head, from its user name: "Head 108LA" -> IH:HART:C3:108LA,
    "Head 108R Top" -> IH:HART:C3:108R_Top. ValueError on any other user name."""
    m = HEAD_USER.fullmatch(user or "")
    if not m:
        raise ValueError(f"head {user!r} is not named Head <number><L|R>[letter] or Head <A|B><number>, [ Top| Bottom]")
    return HEAD_PREFIX + m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")


def clear_action(sensor: str) -> str:
    """The ActionSensor of the sensors-clear LogixNG that sets `sensor` (IS:HART:C3:B:<key>)."""
    if not is_block_sensor(sensor):
        raise ValueError(f"{sensor!r} is not a main or upper virtual block sensor")
    return CLEAR_ACTION + sensor.removeprefix(SENSOR_PREFIX)


def turnout_action(turnout: str) -> str:
    """The ActionTurnout of the startup LogixNG that sets `turnout` (IT:HART:C3:<n>)."""
    if not turnout.startswith(TURNOUT_PREFIX):
        raise ValueError(f"{turnout!r} is not a main or upper virtual turnout")
    return TURNOUT_ACTION + turnout.removeprefix(TURNOUT_PREFIX)


def _check_turnout_action(a: ET.Element) -> tuple[str, str]:
    """(turnout, "Closed" or "Thrown") of a startup ActionTurnout; ValueError on any other state or a turnout that is
    not a main or upper virtual one (the LogixNG must never command a field turnout)."""
    turnout, state = a.findtext("namedBean/name") or "", a.findtext("state/enum") or ""
    if not turnout.startswith(TURNOUT_PREFIX) or state not in ("Closed", "Thrown"):
        raise ValueError(f"{a.findtext('systemName')}: sets {turnout or 'no turnout'} {state or 'to nothing'}; a startup "
                         f"action sets a {TURNOUT_PREFIX}* turnout Closed or Thrown")
    return turnout, state


def turnout_states(root: ET.Element) -> dict[str, str]:
    """{virtual turnout: "Closed" or "Thrown"} the startup LogixNG in tables `root` sets: the ActionTurnouts its
    DigitalMany's sockets name ({} when none). ValueError on an action _check_turnout_action refuses."""
    acts = root.find("LogixNGDigitalActions")
    if acts is None:
        return {}
    by_name = {e.findtext("systemName"): e for e in acts}
    many = by_name.get(CLEAR_MANY)
    if many is None:
        return {}
    out = {}
    for sock in many.findall("Actions/Socket"):
        a = by_name.get(sock.findtext("systemName") or "")
        if a is not None and a.tag == "ActionTurnout":
            turnout, state = _check_turnout_action(a)
            out[turnout] = state
    return out

def clear_sensors(root: ET.Element) -> list[str]:
    """The sensors the sensors-clear LogixNG in tables `root` sets INACTIVE, in its order ([] when the tables have
    none). ValueError when its DigitalMany names an action that is missing or is not an ActionSensor setting a sensor
    Inactive."""
    acts = root.find("LogixNGDigitalActions")
    if acts is None:
        return []
    by_name = {e.findtext("systemName"): e for e in acts}
    many = by_name.get(CLEAR_MANY)
    if many is None:
        return []
    out = []
    for sock in many.findall("Actions/Socket"):
        name = sock.findtext("systemName") or ""
        a = by_name.get(name)
        if name.startswith(TURNOUT_ACTION) and a is not None and a.tag == "ActionTurnout":
            _check_turnout_action(a)    # a virtual turnout's startup position (turnout_states)
            continue
        if a is None or a.tag != "ActionSensor" or a.findtext("state/enum") != "Inactive":
            raise ValueError(f"{CLEAR_MANY}: socket {sock.findtext('socketName')} names {name or 'no action'}, which "
                             "is not an ActionSensor setting a sensor Inactive")
        out.append(a.findtext("namedBean/name") or "")
    return out


def field_detected(root: ET.Element) -> dict[str, str]:
    """{block system name: its occupancy sensor's system name} of the main and upper blocks (BLOCK_PREFIX) in tables
    `root` whose occupancy sensor is not a virtual block sensor: a detector swapped to its field sensor by its device
    row (ADR-028, a field assignment). The PanelPro smoke test (Jython, no hartlib) takes them from
    run_panelpro_smoke_test.sh, which reads the tables.xml it loads, so it holds such a block to that sensor and every
    other one to its virtual sensor. A block with no occupancy sensor is not here. ValueError on a block whose
    occupancy sensor names no sensor bean of the tables."""
    from . import tables     # here: tables is the reader of a whole file, this module the naming rule
    sensors = tables.by_any_name(tables.sensors(root))
    out = {}
    for b in tables.blocks(root):
        name, sensor = tables.system_name(b), tables.text(b, "occupancysensor")
        if not name.startswith(BLOCK_PREFIX) or not sensor:
            continue
        bean = sensors.get(sensor)
        if bean is None:
            raise ValueError(f"block {name} ({tables.user_name(b)}): its occupancy sensor {sensor!r} is no sensor of "
                             "the tables")
        if not is_block_sensor(tables.system_name(bean)):
            out[name] = tables.system_name(bean)
    return out


def main(argv: list[str] | None = None) -> int:
    """python3 -m hartlib.level_devices field-detected TABLES: one line "<block system name> <sensor system name>"
    per main or upper block on a field sensor (field_detected), for run_panelpro_smoke_test.sh."""
    import argparse
    import sys
    from . import tables
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.level_devices")
    ap.add_argument("what", choices=("field-detected",))
    ap.add_argument("tables")
    args = ap.parse_args(argv)
    try:
        found = field_detected(tables.read(args.tables))
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"level_devices: {exc}", file=sys.stderr)
        return 1
    for block, sensor in sorted(found.items()):
        print(f"{block} {sensor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
