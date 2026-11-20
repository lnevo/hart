"""The main and upper levels' control-point masts: main_upper_masts.csv (written by
tools/schematic/build_main_upper_masts.py from the device map) and the virtual names they stand on.

The main and upper physical plant is not reviewed yet, so their heads and masts are virtual (owner, 2026-11-17): each
head's system name comes from its user name, never from the device map's draft physical head, so it stays the same
when the draft changes. "Head 108LA" is IH:HART:C3:108LA and "Head 108R Top" IH:HART:C3:108R_Top (hartlib.level_devices.head_name), and
each mast's system name names those heads, IF$shsm:basic:<type>(IH:HART:C3:...)(...). signal_coordinator.py enrols
and publishes a head only when its name is IH and digits (_is_lcos_ih_sys), so none of these reaches MQTT or the
field. The device map (jmri_name column) maps each to its planned physical head.

A virtual mast (a hidden VirtualSignalMast, IF$vsm:basic:one-low($<n>), owner 2026-11-20) stands where a visible
mast's route reaches a buffer stop, as the destination of that route; it has no heads. Its ordinal is fixed once given
and comes from its level's own thousand: staging $1001 up (build_staging_masts.py), main $2001 up and upper $3001 up,
so no level's new mast can take another's number and a main or upper one is known by its name alone
(is_level_virtual). One place for the file, its reader
and that rule: build_device_map.py, build_main_upper_masts.py, build_layout_le.py and
audit_panel_contracts.py use it.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import paths
from .level_devices import HEAD, HEAD_USER, head_name  # noqa: F401  the naming rule, re-exported here

PATH = paths.LAYOUT_DATA / "schematic" / "main_upper_masts.csv"
FIELDS = ["mast", "cp", "switch", "facing", "protects", "dir", "leg", "system_name", "head_system_names",
          "device_system_name"]


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
    return bool(HEAD.fullmatch(system_name or ""))


def is_level_mast(system_name: str) -> bool:
    """A mast whose heads are all main and upper virtual heads."""
    heads = mast_heads(system_name)
    return bool(heads) and all(is_level_head(h) for h in heads)


def read(path: Path = PATH) -> list[dict]:
    """The file's rows, each with `heads`: [(virtual system name, user name)] from head_system_names. Read through
    railroad.read_rows, so the header must hold every FIELDS column and every row must have exactly the header's
    fields: a short row stops the read as a long one does, since the file is written whole by its build and a cut
    row is a damaged file. Stops with railroad.FactsError (a ValueError), naming the file and the line, on those, on
    a row with no mast name or a dir that is not east or west, on a mast name a second time, and on a row whose heads
    are not system=user pairs of virtual heads named by their user names and matching its mast's system name. A
    virtual mast (IF$vsm) has no heads, the same device_system_name, no switch and no protected block."""
    from . import railroad                  # railroad imports this module, so not at the top
    rows, first = [], {}
    for line, r in railroad.read_rows(path, FIELDS):
        where = f"{path.name} line {line}"
        if not r["mast"]:
            raise railroad.FactsError(f"{where}: no mast name")
        if r["mast"] in first:
            raise railroad.FactsError(f"{where}: mast {r['mast']} is on line {first[r['mast']]} already")
        first[r["mast"]] = line
        if r["dir"] not in railroad.MAST_DIRS:
            raise railroad.FactsError(f"{where}: mast {r['mast']}: dir {r['dir']!r} is not one of "
                                      f"{', '.join(railroad.MAST_DIRS)}")
        heads = [tuple(h.split("=", 1)) for h in r["head_system_names"].split(";") if h]
        if r["system_name"].startswith("IF$vsm:"):
            if not is_level_virtual(r["system_name"]) or heads or r["device_system_name"] != r["system_name"] \
                    or r["switch"] or r["protects"]:
                raise railroad.FactsError(f"{where}: virtual mast {r['mast']}: {r['system_name']!r} is a main or "
                                          "upper VirtualSignalMast with no heads, its device_system_name the same, "
                                          "standing at a buffer stop (no switch, nothing protected)")
            r["heads"] = []
            rows.append(r)
            continue
        if not heads or any(len(h) != 2 or not is_level_head(h[0]) or HEAD_USER.fullmatch(h[1]) is None
                            or head_name(h[1]) != h[0] for h in heads) or \
                [h for h, _u in heads] != mast_heads(r["system_name"]):
            raise railroad.FactsError(f"{where}: mast {r['mast']}: heads {r['head_system_names']!r} are not "
                                      "system=user pairs of its system name's virtual heads")
        r["heads"] = heads
        rows.append(r)
    return rows


def names(path: Path = PATH) -> set[str]:
    return {r["mast"] for r in read(path)}
