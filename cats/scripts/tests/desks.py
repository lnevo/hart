"""Shared by the CATS tests: the live desks (generated from the schematic since the CATS cut-over), their bound plants
by OS block, and the last hand-wired desks read from git (hartlib.hand_drawn) for the tests that compare old with new.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cats/scripts"))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))

import digicon_trace as trace  # noqa: E402
from hartlib import hand_drawn  # noqa: E402

CTC = ROOT / "cats/panels/HART_CTC.xml"
ABS = ROOT / "cats/panels/HART_ABS.xml"
LIVE = (CTC, ABS)


def hand_wired(name: str) -> Path:
    """The last hand-wired desk `name` (HART_CTC.xml or HART_ABS.xml), from git. Skips the test only when git does
    not have it (hartlib.hand_drawn.skip_unless_available); a bad name raises."""
    return hand_drawn.skip_unless_available(name)


def cells(path: Path) -> dict[tuple[int, int], ET.Element]:
    """(x, y) -> SECTION of a desk's track plan."""
    return trace.track_cells(ET.parse(path).getroot().find("TRACKPLAN"))


def plants(path: Path) -> tuple[dict[tuple[int, int], ET.Element], dict[str, tuple[int, int]]]:
    """(cells, OS block -> plant cell) for every bound plant of a desk (the dark main and upper plants bind nothing)."""
    c = cells(path)
    return c, trace.desk_plants(c, bound=True)


def routes(path: Path, os_block: str) -> dict[str, tuple[str | None, bool]]:
    """{command (close or throw): (block that leg leads to, NORMAL)} of the bound plant in `os_block`."""
    c, p = plants(path)
    xy = p[os_block]
    out = {}
    for ri in c[xy].iter("ROUTEINFO"):
        cmd = (ri.find("ROUTECOMMAND/IOSPEC").text or "").strip()
        out[cmd] = (trace.trace_leg(c, xy, ri.get("ROUTEID"), own=os_block), ri.get("NORMAL") == "true")
    return out
