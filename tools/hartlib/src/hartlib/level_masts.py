"""The main and upper levels' control-point masts until the cut-over: main_upper_masts.csv (written by
tools/schematic/build_main_upper_masts.py from the device map) and the internal names they stand on.

Each head's system name is the device map's IH<four digits> with a 9 after "IH" (IH3332 -> IH93332), and each mast's
system name names those heads, so signal_coordinator.py never takes them for LCOS heads (its node "933" is not
octal). One place for the file, its reader and that rule: build_layout_le.py, audit_panel_contracts.py and
polish_hart_layout_editor.py use it.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from . import paths

PATH = paths.LAYOUT_DATA / "schematic" / "main_upper_masts.csv"
DEVICE_HEAD = re.compile(r"IH\d{4}")         # a device-map head: IH + node and signal, four digits
HEAD = re.compile(r"IH9\d{4}")               # its internal name until the cut-over
FIELDS = ["mast", "cp", "switch", "facing", "protects", "leg", "system_name", "head_system_names",
          "device_system_name"]


def internal_head(device_head: str) -> str:
    """The internal head name for a device-map head (IH3332 -> IH93332). Stops with ValueError on any other name."""
    if not DEVICE_HEAD.fullmatch(device_head):
        raise ValueError(f"head {device_head!r} is not a device-map head (IH and four digits)")
    return "IH9" + device_head[2:]


def mast_heads(system_name: str) -> list[str]:
    """The head names in a SignalHeadSignalMast's system name, in order."""
    return re.findall(r"\((IH\d+)\)", system_name or "")


def is_level_head(system_name: str) -> bool:
    return bool(HEAD.fullmatch(system_name or ""))


def is_level_mast(system_name: str) -> bool:
    """A mast whose heads are all main and upper internal heads."""
    heads = mast_heads(system_name)
    return bool(heads) and all(is_level_head(h) for h in heads)


def read(path: Path = PATH) -> list[dict]:
    """The file's rows, each with `heads`: [(internal system name, user name)] from head_system_names. Stops with
    ValueError on a row whose heads are not system=user pairs of internal heads matching its mast's system name."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        heads = [tuple(h.split("=", 1)) for h in (r.get("head_system_names") or "").split(";") if h]
        if not heads or any(len(h) != 2 or not is_level_head(h[0]) for h in heads) or \
                [h for h, _u in heads] != mast_heads(r.get("system_name", "")):
            raise ValueError(f"{path.name}: mast {r.get('mast')}: heads {r.get('head_system_names')!r} are not "
                             "system=user pairs of its system name's internal heads")
        r["heads"] = heads
    return rows


def names(path: Path = PATH) -> set[str]:
    return {r["mast"] for r in read(path)}
