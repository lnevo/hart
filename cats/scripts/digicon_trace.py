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
from typing import Collection

from digicon_lib import TRACK_ENDS, cell_edges, points_edge

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


class PlantError(ValueError):
    """The desk does not say clearly which OS block a plant is in."""


def plant_edges(sec: ET.Element) -> tuple[str | None, list[str]]:
    """(points edge, leg edges) of a cell; points is None when the cell is not a plant."""
    kinds = tracks(sec)
    pts = points_edge(kinds)
    if pts is None:
        return None, []
    return pts, [e for e in cell_edges(kinds) if e != pts]


def plant_os(cells: dict[tuple[int, int], ET.Element], xy: tuple[int, int]) -> str:
    """The OS block of the plant at ``xy``.

    A name on the frog cell's own edges wins (it names that cell's side). With
    none there, the OS is the first name past the points that is also the
    first name along at least one leg: an OS spans the frog, so its name shows
    on both sides. A leg's neighbouring block is never taken. Raises PlantError
    when the cell has two names or no name passes that test.
    """
    sec = cells[xy]
    own = {b.get("NAME") for b in sec.iter("BLOCK") if b.get("NAME")}
    if len(own) > 1:
        raise PlantError(f"plant at {xy} carries several block names: {sorted(own)}")
    if own:
        return own.pop()
    pts, legs = plant_edges(sec)
    if pts is None:
        raise PlantError(f"cell {xy} is not a plant")
    behind = trace_leg(cells, xy, pts, own="")
    ahead = {trace_leg(cells, xy, leg, own="") for leg in legs}
    if behind is None or behind not in ahead:
        raise PlantError(f"plant at {xy}: no block name on the frog cell, and the first name past "
                         f"the points ({behind}) is not on either leg ({sorted(map(str, ahead))})")
    return behind


def plant_users(sec: ET.Element) -> set[str]:
    """The turnout USER_NAME of every IOSPEC on a plant cell's routes (empty for a plant bound to nothing)."""
    return {io.get("USER_NAME") or "" for io in sec.findall("SEC_EDGE/SWITCHPOINTS/ROUTEINFO/*/IOSPEC")} - {""}


def desk_plants(cells: dict[tuple[int, int], ET.Element], bound: bool = False,
                level_turnouts: Collection[str] = ()) -> dict[str, tuple[int, int]]:
    """OS block -> its plant cell, for every wired plant (SWITCHPOINTS with ROUTEINFO); with `bound`, only the plants
    whose routes command a staging turnout: not one of `level_turnouts` (the main and upper turnouts' user names, from
    the device master's rows: hartlib.tables_build.level_turnouts). On the generated desks the main and upper plants
    (level_plants) command those turnouts, whatever bean their rows give, or nothing, and a crossover's halves there
    share one OS block."""
    out: dict[str, tuple[int, int]] = {}
    level = set(level_turnouts)
    for xy, sec in cells.items():
        if sec.find("SEC_EDGE/SWITCHPOINTS/ROUTEINFO") is None:
            continue
        if bound and (not plant_users(sec) or plant_users(sec) & level):
            continue
        os_name = plant_os(cells, xy)
        if os_name in out:
            raise PlantError(f"plants at {out[os_name]} and {xy} are both in {os_name}")
        out[os_name] = xy
    return out


def level_plants(cells: dict[tuple[int, int], ET.Element],
                 level_turnouts: Collection[str]) -> list[tuple[str, tuple[int, int], str]]:
    """(OS block, plant cell, points edge) for every set of points commanding a main or upper turnout (one of
    `level_turnouts`, their user names from the device master's rows), in cell order: a crossover's halves there are
    two plants in one OS block, and a double crossover's cells hold two points each (its OS is then the first block
    name out through the points, which its OS reaches past)."""
    out = []
    level = set(level_turnouts)
    for xy, sec in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if not plant_users(sec) & level:
            continue
        edges = [se.get("EDGE") for se in sec.findall("SEC_EDGE") if se.find("SWITCHPOINTS/ROUTEINFO") is not None]
        for edge in edges:
            os_name = plant_os(cells, xy) if len(edges) == 1 else trace_leg(cells, xy, edge, own="")
            if os_name is None:
                raise PlantError(f"points at {xy} {edge}: no block name out through them")
            out.append((os_name, xy, edge))
    return out


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
    inside: frozenset = frozenset(),
) -> str | None:
    """Name of the first block other than ``own`` (default: the plant's OS) and the blocks ``inside`` it (parts of
    it, each a block of its own on the desk) reached through ``leg``."""
    own = own if own is not None else plant_os(cells, xy)
    skip = {own} | set(inside)
    sec = cells[xy]
    name = block_name(sec, leg)
    if name and name not in skip:
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
        if name and name not in skip:
            return name
        kinds = tracks(sec)
        if points_edge(kinds) == enter:
            return None  # entered another plant at its points: either leg could follow
        ends = [TRACK_ENDS[k] for k in kinds if enter in TRACK_ENDS.get(k, ())]
        if len(ends) != 1:
            return None
        out = next(e for e in ends[0] if e != enter)
        name = block_name(sec, out)
        if name and name not in skip:
            return name
    return None
