"""Shared by the CATS tests: the live desks (generated from the schematic since the CATS cut-over) and their bound
plants by OS block.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cats/scripts"))

import digicon_trace as trace  # noqa: E402

sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import devices, tables_build  # noqa: E402

CTC = ROOT / "cats/panels/HART_CTC.xml"
ABS = ROOT / "cats/panels/HART_ABS.xml"
LIVE = (CTC, ABS)


def cells(path: Path) -> dict[tuple[int, int], ET.Element]:
    """(x, y) -> SECTION of a desk's track plan."""
    return trace.track_cells(ET.parse(path).getroot().find("TRACKPLAN"))


def plants(path: Path) -> tuple[dict[tuple[int, int], ET.Element], dict[str, tuple[int, int]]]:
    """(cells, OS block -> plant cell) for every bound plant of a desk (the dark main and upper plants bind nothing)."""
    c = cells(path)
    return c, trace.desk_plants(c, bound=True, level_turnouts=tables_build.level_turnouts(
        [r.cells() for r in devices.load()]))


def routes(path: Path, os_block: str) -> dict[str, tuple[str | None, bool]]:
    """{command (close or throw): (block that leg leads to, NORMAL)} of the bound plant in `os_block`."""
    c, p = plants(path)
    xy = p[os_block]
    out = {}
    for ri in c[xy].iter("ROUTEINFO"):
        cmd = (ri.find("ROUTECOMMAND/IOSPEC").text or "").strip()
        out[cmd] = (trace.trace_leg(c, xy, ri.get("ROUTEID"), own=os_block), ri.get("NORMAL") == "true")
    return out
