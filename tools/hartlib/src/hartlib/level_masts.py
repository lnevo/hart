"""The main and upper levels' control-point masts: main_upper_masts.csv (written by
tools/schematic/build_main_upper_masts.py from the device map) and the virtual names they stand on.

The main and upper physical plant is not reviewed yet, so their heads and masts are virtual (owner, 2026-11-17): each
head's system name comes from its user name, never from the device map's draft physical head, so it stays the same
when the draft changes. "Head 108LA" is IH:HART:C3:108LA and "Head 108R Top" IH:HART:C3:108R_Top (hartlib.level_devices.head_name), and
each mast's system name names those heads, IF$shsm:basic:<type>(IH:HART:C3:...)(...). signal_coordinator.py enrols
and publishes a head only when its name is IH and digits (_is_lcos_ih_sys), so none of these reaches MQTT or the
field. The device map (jmri_name column) maps each to its planned physical head. One place for the file, its reader
and that rule: build_device_map.py, build_main_upper_masts.py, build_layout_le.py, audit_panel_contracts.py and
polish_hart_layout_editor.py use it.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from . import paths
from .level_devices import HEAD, HEAD_USER, head_name  # noqa: F401  the naming rule, re-exported here

PATH = paths.LAYOUT_DATA / "schematic" / "main_upper_masts.csv"
FIELDS = ["mast", "cp", "switch", "facing", "protects", "leg", "system_name", "head_system_names",
          "device_system_name"]


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
    """The file's rows, each with `heads`: [(virtual system name, user name)] from head_system_names. Stops with
    ValueError on a row whose heads are not system=user pairs of virtual heads named by their user names and matching
    its mast's system name."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        heads = [tuple(h.split("=", 1)) for h in (r.get("head_system_names") or "").split(";") if h]
        if not heads or any(len(h) != 2 or not is_level_head(h[0]) or HEAD_USER.fullmatch(h[1]) is None
                            or head_name(h[1]) != h[0] for h in heads) or \
                [h for h, _u in heads] != mast_heads(r.get("system_name", "")):
            raise ValueError(f"{path.name}: mast {r.get('mast')}: heads {r.get('head_system_names')!r} are not "
                             "system=user pairs of its system name's virtual heads")
        r["heads"] = heads
    return rows


def names(path: Path = PATH) -> set[str]:
    return {r["mast"] for r in read(path)}
