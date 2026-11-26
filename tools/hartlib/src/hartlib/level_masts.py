"""Every level's signal masts: schematic/masts.csv, one row per mast with its `level` (the level is
a column, never a file per level), written by tools/schematic/build_masts.py from the mast and head rows (every
level's build_device_map.py writes) of
The device master: its reader (read) and the naming rules the file keeps.

Columns (FIELDS):
- level: 1 staging, 2 main, 3 upper.
- mast, cp, switch, facing, protects, dir, leg: the mast, the control point of its switch (its place id in the file,
  st:barn or cp:107, which read gives as the name: hartlib.places), the switch it stands at (a
  turnout mast; none for an anchor mast, an intermediate or a virtual mast), the block it faces and the block it
  protects (the OS block of its switch unless the row names one), east or west, and the leg (LEGS) that tells apart
  two masts on one facing and protected block pair (none needs one today).
- system_name, head_system_names: its JMRI name and its heads' (system=user pairs, ";" between), and
  device_system_name the device map's system_name: the same on staging, the planned physical mast on main and upper.
- the plan facts (PLAN_FIELDS): where the drawing puts the mast, for the masts the mast rule places from a block
  layer of its own (staging today: device_map_masts.py, read by build_masts.py): toward (the switch its run is toward), run (that switch and the
  far end, ";" between), names (the track names of its plan edge), edge_cm and cm_from_toward (the run's length and
  the mast's distance from its toward end), schematic_edge and schematic_toward_node (the plan graph's edge and node).
  A row has all of them or none: main and upper's are empty, since build_signals.py places those masts from the plan
  graph and the device map's tracks. The signal's name, kind (field, planned, virtual) and head count follow from the
  other columns (signal_name, signal_kind, head_count).

Heads: a head's system name comes from its user name and level (head_name: "Head 2L Top" on level 1 is
IH:HART:C1:2L_Top, "Head 108R Top" on level 2 IH:HART:C3:108R_Top, hartlib.level_devices.head_name), so it stays the
same when a draft plant changes; only a wired head (an LCOS head, IH and digits: wiring.csv) has another.
signal_coordinator.py enrols and publishes a head only when its name is IH and digits (_is_lcos_ih_sys), so no
internal head reaches MQTT or the field.

A virtual mast (a hidden VirtualSignalMast, IF$vsm:basic:one-low($<n>)) stands where a visible
mast's route reaches a buffer stop, as the destination of that route; it has no heads. Its ordinal is fixed once given
and comes from its level's own thousand: staging $1001 up, main $2001 up and upper $3001 up, so no level's new mast
can take another's number and a main or upper one is known by its name alone (is_level_virtual).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import paths, places
from .level_devices import HEAD, HEAD_PREFIX  # noqa: F401  the main and upper head names, re-exported here

PATH = paths.LAYOUT_DATA / "schematic" / "masts.csv"
LEVELS = (1, 2, 3)                   # staging, main, upper
MAST_FIELDS = ["mast", "cp", "switch", "facing", "protects", "dir", "leg", "system_name", "head_system_names",
               "device_system_name"]
PLAN_FIELDS = ["toward", "run", "names", "edge_cm", "cm_from_toward", "schematic_edge", "schematic_toward_node"]
FIELDS = ["level", *MAST_FIELDS, *PLAN_FIELDS]
LIST = ";"                           # between the items of a run, names or head_system_names cell
# `leg` of two masts sharing one facing and protected block pair, by their names' last letter
LEGS = {"A": "normal", "B": "diverging"}
# a level's internal head prefix, data by level: staging's C1, main and upper's C3 (hartlib.level_devices); every
# level's builder names its heads by head_name
HEAD_PREFIXES = {1: "IH:HART:C1:", 2: HEAD_PREFIX, 3: HEAD_PREFIX}
# a mast's user name on any level: a home signal's (Mast 2L), a staging intermediate's by milepost
# (Mast 67) or a main or upper one's with its line code (Mast A83); a head's is its mast's key
MAST_USER = re.compile(r"Mast (\d+[LR]?[A-Z]?|[AB]\d+)")
HEAD_USER = re.compile(r"Head (\d+[LR]?[A-Z]?|[AB]\d+)(?: (Top|Bottom))?")
WIRED_HEAD = re.compile(r"IH\d+")    # an LCOS head: signal_coordinator.py publishes IH and digits to MQTT
# A masts.csv row may name a wired (LCOS) head only where it is the row's planned physical head at its place (its
# device_system_name's): a head swapped in by its device row, its assignment field (build_masts.file_rows checks the
# row). Staging's rows are bound to their physical masts (device_system_name the same), and main and upper's heads stay
# internal until such a swap, so nothing else of theirs reaches MQTT: any other wired head stops
# the read.
SHSM = re.compile(r"IF\$shsm:(\w+):([\w-]+)((?:\(IH[^()]+\))+)")    # a SignalHeadSignalMast over its heads

VIRTUAL = re.compile(r"IF\$vsm:basic:one-low\(\$(\d+)\)")
VIRTUAL_BASE = {1: 1000, 2: 2000, 3: 3000}      # a level's virtual mast ordinals run from base + 1 to base + 999


def virtual_ordinal(system_name: str) -> int | None:
    """The ordinal of a virtual mast's system name, None for any other name."""
    m = VIRTUAL.fullmatch(system_name or "")
    return int(m.group(1)) if m else None


def virtual_level(system_name: str) -> int | None:
    """The level whose thousand a virtual mast's ordinal is in (VIRTUAL_BASE), None for another name or an ordinal in
    no level's thousand."""
    n = virtual_ordinal(system_name)
    return next((lv for lv, b in VIRTUAL_BASE.items() if n is not None and b < n < b + 1000), None)


def is_level_virtual(system_name: str) -> bool:
    """A main or upper virtual mast (its ordinal in the main or upper thousand)."""
    return virtual_level(system_name) in (2, 3)


def mast_heads(system_name: str) -> list[str]:
    """The head names in a SignalHeadSignalMast's system name, in order."""
    return re.findall(r"\((IH[^()]+)\)", system_name or "")


def is_level_head(system_name: str) -> bool:
    """A main or upper internal head (IH:HART:C3:...)."""
    return bool(HEAD.fullmatch(system_name or ""))


def is_level_mast(system_name: str) -> bool:
    """A mast whose heads are all main and upper internal heads."""
    heads = mast_heads(system_name)
    return bool(heads) and all(is_level_head(h) for h in heads)


def head_name(user: str, level: int) -> str:
    """The internal system name of a head from its user name and level: "Head 24RA Top" on level 1 ->
    IH:HART:C1:24RA_Top, "Head 108LA" on level 2 -> IH:HART:C3:108LA. ValueError on a user name that is not
    Head <key>[ Top| Bottom] or a level that is not one of LEVELS."""
    m = HEAD_USER.fullmatch(user or "")
    if not m or level not in HEAD_PREFIXES:
        raise ValueError(f"head {user!r} on level {level!r} is not named Head <mast key>[ Top| Bottom] on one of "
                         f"levels {', '.join(map(str, LEVELS))}")
    return HEAD_PREFIXES[level] + m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")


def head_problem(system: str, user: str, level: int, wired_ok: bool) -> str | None:
    """What is wrong with a head of a level's mast (`system` its JMRI name, `user` its user name), None when it is its
    internal name, or a wired LCOS head (IH and digits) where `wired_ok` (a field head: a device row's assignment
    field, or in masts.csv the row's planned physical head at its place, row_problems)."""
    try:
        internal = head_name(user, level)
    except ValueError as exc:
        return str(exc)
    if system == internal:
        return None
    if WIRED_HEAD.fullmatch(system or ""):
        return None if wired_ok else (f"head {user} is the wired LCOS head {system!r}, but a level {level} head is "
                                      f"internal ({internal}) until it is a field head, so nothing reaches MQTT")
    return f"head {user} is {system!r}, neither its internal name {internal} nor a wired IH<digits>"


def signal_name(mast: str) -> str:
    """The signal a mast shows on the drawings: its name less "Mast "."""
    return mast.removeprefix("Mast ")


def signal_kind(row: dict) -> str:
    """virtual for a hidden mast, field when a head is wired (an LCOS head), planned otherwise."""
    if row["system_name"].startswith("IF$vsm:"):
        return "virtual"
    return "field" if any(WIRED_HEAD.fullmatch(h) for h in mast_heads(row["system_name"])) else "planned"


def head_count(row: dict) -> int:
    """The heads the drawings show: one for a hidden mast, else its heads."""
    return 1 if row["system_name"].startswith("IF$vsm:") else len(mast_heads(row["system_name"]))


def placed(row: dict) -> bool:
    """A row with plan facts (PLAN_FIELDS): the drawing places it from them."""
    return bool(row["toward"] or row["run"])


def read(path: Path = PATH, *, levels: tuple[int, ...] | None = None) -> list[dict[str, Any]]:
    """The rows of `levels` (every level when None), in file order, each with `level` an int, its `line` and `heads`:
    [(system name, user name)] from head_system_names. The whole file is checked whatever `levels` is. Stops with
    railroad.FactsError (a ValueError), naming the file and the line, on a header that is not FIELDS, a short or long
    row, a level not in LEVELS, no mast name or one out of MAST_USER, a mast name a second time (on any level), a dir
    that is not east or west, a leg not in LEGS, a row with some plan facts and not all (or a run that is not two
    ends, or lengths that are not numbers), and on heads that are not system=user pairs of its system name's heads,
    each its level's internal name or a wired LCOS head that is the row's planned physical head at its place (its
    device_system_name's: a field head). A virtual mast (IF$vsm) is in its level's thousand, has no
    heads, the same device_system_name, no switch and no protected block."""
    from . import railroad                  # railroad imports this module, so not at the top
    if not isinstance(path, (str, Path)):           # read(levels) by position: say so, never guess
        raise TypeError(f"level_masts.read takes the path, then levels= by keyword, not {path!r}")
    path = Path(path)
    if levels is not None and set(levels) - set(LEVELS):
        raise railroad.FactsError(f"{path.name}: levels {sorted(set(levels) - set(LEVELS))} are not "
                                  f"{', '.join(map(str, LEVELS))}")
    try:
        with path.open(encoding="utf-8") as fh:
            header = fh.readline().rstrip("\r\n").split(",")
    except OSError as exc:
        raise railroad.FactsError(f"{path}: cannot read it ({exc.strerror})") from exc
    if header != FIELDS:
        raise railroad.FactsError(f"{path.name} line 1: columns {','.join(header)}, not {','.join(FIELDS)}")
    rows: list[dict[str, Any]] = []
    first: dict[str, int] = {}              # mast -> its line
    table = places.table(places.lists_beside(path))    # a copy's cp cells by the lists beside it
    for line, r in railroad.read_rows(path, FIELDS):
        where = f"{path.name} line {line}"
        bad = row_problems(r)
        if bad:
            raise railroad.FactsError(f"{where}: mast {r['mast'] or '(none)'}: {bad}")
        if r["mast"] in first:
            raise railroad.FactsError(f"{where}: mast {r['mast']} is on line {first[r['mast']]} already")
        first[r["mast"]] = line
        table.with_names(r, where)             # the cp cell holds place ids (hartlib.places)
        row: dict[str, Any] = {**r, "level": int(r["level"]), "line": line,
                               "heads": [tuple(h.split("=", 1)) for h in r["head_system_names"].split(LIST) if h]}
        if levels is None or row["level"] in levels:
            rows.append(row)
    return rows


def row_problems(r: dict) -> str:
    """What breaks the file's rules in one row (its cells as strings), "" when nothing does (read)."""
    if r["level"] not in {str(lv) for lv in LEVELS}:
        return f"level {r['level']!r} is not one of {', '.join(map(str, LEVELS))}"
    level = int(r["level"])
    if not MAST_USER.fullmatch(r["mast"]):
        return f"the name {r['mast']!r} is not Mast <number>[L|R][letter] or Mast <A|B><milepost number>"
    if r["dir"] not in ("east", "west"):
        return f"dir {r['dir']!r} is not east or west"
    if r["leg"] not in ("", *LEGS.values()):
        return f"leg {r['leg']!r} is not one of {', '.join(LEGS.values())} or empty"
    facts = [r[c] for c in PLAN_FIELDS]
    if any(facts) and not all(facts[:2] + facts[3:]):     # names may be empty (a plan edge with no names)
        return f"plan facts {dict(zip(PLAN_FIELDS, facts))}: a row has all of them (names may be empty) or none"
    if any(facts):
        ends = r["run"].split(LIST)
        try:
            float(r["edge_cm"]), float(r["cm_from_toward"])
        except ValueError:
            return f"edge_cm {r['edge_cm']!r} and cm_from_toward {r['cm_from_toward']!r} are not numbers"
        if len(ends) != 2 or not ends[0]:
            return f"run {r['run']!r} is not <toward>;<far end>"
    heads = [tuple(h.split("=", 1)) for h in r["head_system_names"].split(LIST) if h]
    if r["system_name"].startswith("IF$vsm:"):
        if virtual_level(r["system_name"]) != level or heads or r["device_system_name"] != r["system_name"] \
                or r["switch"] or r["protects"]:
            return (f"virtual mast {r['system_name']!r} is a VirtualSignalMast of its level's thousand with no heads, "
                    "its device_system_name the same, standing at a buffer stop (no switch, nothing protected)")
        return ""
    if not SHSM.fullmatch(r["system_name"]):
        return f"system name {r['system_name']!r} is neither IF$shsm:<aspects>:<type>(<heads>) nor IF$vsm"
    if not r["facing"] or not r["protects"]:
        return "a visible mast faces a block and protects one"
    if not heads or any(len(h) != 2 for h in heads) or [h for h, _u in heads] != mast_heads(r["system_name"]):
        return f"heads {r['head_system_names']!r} are not system=user pairs of its system name's heads"
    planned = mast_heads(r["device_system_name"])     # the planned physical mast's heads, in order
    bad = [p for p in (head_problem(h, u, level, i < len(planned) and planned[i] == h)
                       for i, (h, u) in enumerate(heads)) if p]
    return "; ".join(bad)


def names(path: Path = PATH, *, levels: tuple[int, ...] | None = None) -> set[str]:
    return {r["mast"] for r in read(path, levels=levels)}


def visible_names(path: Path = PATH, *, levels: tuple[int, ...] | None = None) -> set[str]:
    """The masts a panel or desk draws: every row of `levels` but the hidden virtual ones."""
    return {r["mast"] for r in read(path, levels=levels) if not r["system_name"].startswith("IF$vsm:")}
