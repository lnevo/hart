#!/usr/bin/env python3
"""Follow a CATS points leg along the drawn track to the block it leads to.

    trace_leg(cells, (24, 8), "BOTTOM")  ->  "Track EH-2"

``cells`` maps (x, y) to a SECTION element (see ``track_cells``). The walk
leaves the plant cell by the leg edge and follows each cell's track piece
to its other end, through SHARED jumps, until it meets a BLOCK whose NAME is
not the plant's own OS block. It returns None when the drawing is ambiguous
(it enters another plant at its points) or ends without a name.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from digicon_lib import TRACK_ENDS, points_edge

OPPOSITE = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
STEP = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
MAX_STEPS = 200


def track_cells(trackplan: ET.Element) -> dict[tuple[int, int], ET.Element]:
    return {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in trackplan.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }


def tracks(sec: ET.Element) -> list[str]:
    return [(t.text or "").strip() for t in sec.findall("TRACKGROUP/TRACK") if (t.text or "").strip()]


def edge_element(sec: ET.Element, edge: str) -> ET.Element | None:
    for e in sec.findall("SEC_EDGE"):
        if e.get("EDGE") == edge:
            return e
    return None


def block_name(sec: ET.Element, edge: str) -> str | None:
    e = edge_element(sec, edge)
    blk = e.find("BLOCK") if e is not None else None
    return (blk.get("NAME") or None) if blk is not None else None


def plant_edges(sec: ET.Element) -> tuple[str | None, list[str]]:
    """(points edge, leg edges) of a cell; points is None when the cell is not a plant."""
    kinds = tracks(sec)
    pts = points_edge(kinds)
    if pts is None:
        return None, []
    used = set().union(*(TRACK_ENDS[k] for k in kinds))
    return pts, [e for e in ("LEFT", "RIGHT", "TOP", "BOTTOM") if e in used and e != pts]


def plant_os(cells: dict[tuple[int, int], ET.Element], xy: tuple[int, int]) -> str | None:
    """The OS block of a plant: a name on the cell's own edges, else the first one past its points."""
    sec = cells[xy]
    for e in sec.findall("SEC_EDGE"):
        blk = e.find("BLOCK")
        if blk is not None and blk.get("NAME"):
            return blk.get("NAME")
    pts, _legs = plant_edges(sec)
    return trace_leg(cells, xy, pts, own="") if pts else None


def _shared(sec: ET.Element, edge: str) -> tuple[tuple[int, int], str] | None:
    e = edge_element(sec, edge)
    sh = e.find("SHARED") if e is not None else None
    if sh is None:
        return None
    return (int(sh.get("X")), int(sh.get("Y"))), (sh.text or "").strip()


def trace_leg(
    cells: dict[tuple[int, int], ET.Element],
    xy: tuple[int, int],
    leg: str,
    own: str | None = None,
) -> str | None:
    """Name of the first block other than ``own`` (default: the plant's OS) reached through ``leg``."""
    own = own if own is not None else plant_os(cells, xy)
    sec = cells[xy]
    name = block_name(sec, leg)
    if name and name != own:
        return name
    out = leg
    for _ in range(MAX_STEPS):
        jump = _shared(sec, out)
        if jump is not None:
            nxt, enter = jump
        else:
            dx, dy = STEP[out]
            nxt, enter = (xy[0] + dx, xy[1] + dy), OPPOSITE[out]
        sec = cells.get(nxt)
        if sec is None:
            return None
        xy = nxt
        name = block_name(sec, enter)
        if name and name != own:
            return name
        kinds = tracks(sec)
        if points_edge(kinds) == enter:
            return None  # entered another plant at its points: either leg could follow
        ends = [TRACK_ENDS[k] for k in kinds if enter in TRACK_ENDS.get(k, ())]
        if len(ends) != 1:
            return None
        out = next(e for e in ends[0] if e != enter)
        name = block_name(sec, out)
        if name and name != own:
            return name
    return None
