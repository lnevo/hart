#!/usr/bin/env python3
"""Neville station-map control points as Digicon panels (for critique).

Builds one small panel per CP, plus a single stacked review board with
space between each CP so they can be read together.

    python3 cats/scripts/build_hart_cp_panels.py
    python3 cats/scripts/build_hart_cp_panels.py --only 100,102,103
    CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/cp/HART_cp_all.xml

Outputs:
  cats/panels/cp/HART_cp_<id>.xml   (single CP)
  cats/panels/cp/HART_cp_all.xml    (all CPs stacked, spaced)
  cats/screenshots/cp/HART_cp_*.png
  cats/docs/CP_PANELS.md
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hart_digicon_from_le as le  # noqa: E402

OUT_DIR = ROOT / "cats/panels/cp"
SHOT_DIR = ROOT / "cats/screenshots/cp"
INDEX = ROOT / "cats/docs/CP_PANELS.md"
OUT_ALL = OUT_DIR / "HART_cp_all.xml"
WIDTH, HEIGHT = "900", "420"
# Wide review board: CPs left->right with padding (avoids left-edge clip)
ALL_WIDTH, ALL_HEIGHT = "10000", "720"
GAP_COLS = 5  # empty columns between CPs
PAD_X = 8  # empty cols before first CP (CATS clips label text at left)
PAD_Y = 2  # row 0 banner, content from PAD_Y

BuildFn = Callable[[], None]


def _clear() -> None:
    le.GRID.clear()
    le.PLANTS.clear()
    le.ANCHORS.clear()
    le.ANON.clear()
    le.LABELS.clear()


def _shift_1() -> None:
    g = {(x + 1, y + 1): v for (x, y), v in le.GRID.items()}
    p = {(x + 1, y + 1): v for (x, y), v in le.PLANTS.items()}
    a = {((x + 1, y + 1), e): n for ((x, y), e), n in le.ANCHORS.items()}
    n = {((x + 1, y + 1), e) for (x, y), e in le.ANON}
    labs = [(x + 1, y + 1, t) for x, y, t in le.LABELS]
    le.GRID.clear(); le.GRID.update(g)
    le.PLANTS.clear(); le.PLANTS.update(p)
    le.ANCHORS.clear(); le.ANCHORS.update(a)
    le.ANON.clear(); le.ANON.update(n)
    le.LABELS.clear(); le.LABELS.extend(labs)


def _run(x0: int, x1: int, y: int, name: str) -> None:
    for x in range(x0, x1 + 1):
        le.H((x, y))
    le.nm((x0, y), "LEFT", name)


def _stub_e(x: int, y: int) -> None:
    le.an((x, y), "RIGHT")


def _stub_w(x: int, y: int) -> None:
    le.an((x, y), "LEFT")


# ---------------------------------------------------------------------------
# West Yard sheet
# ---------------------------------------------------------------------------

def build_101() -> None:
    """West Yard map: W-2 merges up into W-1 at 101."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    # W-1 -> 101 -> Brick (H+LB: SP left, normal right, W-2 on BOTTOM)
    _run(0, 1, 1, "W-1")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1))
    nm((2, 1), "LEFT", "OS 101")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 101", "RIGHT", "TOL38")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 6, 1, "to Brick")
    _stub_e(6, 1)
    # W-2 below into plant BOTTOM
    _run(0, 2, 2, "W-2")
    cut((2, 2), "RIGHT", (3, 2), "LEFT")
    H((3, 2))
    nm((3, 2), "LEFT", "W-2")
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    le.LABELS[:] = [
        (2, 0, "CP 101"),
        (4, 0, "WEST YARD"),
        (0, 0, "W-1"),
        (0, 3, "W-2 merges ^ into W-1"),
        (5, 0, "-> Brick / 100"),
    ]


def build_100() -> None:
    """West Yard map: Brick 100 — Main West east; diverge down to Plane."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    _clear()
    _run(0, 1, 1, "from 101")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 100")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 100", "RIGHT", "TOL3")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 7, 1, "Main West")
    _stub_e(7, 1)
    # down to Plane
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "to Plane")
    _run(4, 6, 2, "to Plane")
    _stub_e(6, 2)
    le.LABELS[:] = [
        (2, 0, "CP 100  Brick"),
        (5, 0, "Main West -> East End"),
        (4, 3, "v to Plane (102)"),
        (0, 0, "<- from 101"),
    ]


def build_102() -> None:
    """West Yard map: Plane 102 — West Lead east; Main East down-right."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 1, 1, "from Brick")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1))
    nm((2, 1), "LEFT", "OS 102")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 102", "RIGHT", "TOL42")
    # Map: West Lead continues east (use RIGHT); Main East peels down (BOTTOM)
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 8, 1, "West Lead")
    _stub_e(8, 1)
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    H((3, 2))
    nm((3, 2), "LEFT", "Main East")
    le.GRID[(4, 2)] = ["UPPERBACKSLASH"]
    cut((3, 2), "RIGHT", (4, 2), "LEFT")
    nm((4, 2), "RIGHT", "Main East")
    _run(5, 8, 2, "Main East")
    _stub_e(8, 2)
    le.LABELS[:] = [
        (2, 0, "CP 102  Plane"),
        (0, 0, "<- from Brick / 100"),
        (5, 0, "West Lead -> South Yard"),
        (5, 3, "Main East -> East End"),
    ]


def build_117() -> None:
    """West/South Yard maps: Barn crossover West Lead ↔ Main East."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    _clear()
    _run(0, 2, 1, "West Lead")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 117")
    plant((4, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 117", "RIGHT", "TO117")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 8, 1, "West Lead")
    _stub_e(8, 1)
    # mate on Main East
    cut((4, 1), "BOTTOM", (4, 2), "TOP")
    H((3, 2)); nm((3, 2), "LEFT", "OS 117b")
    plant((4, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 117b", "RIGHT", "TO117")
    cut((4, 2), "RIGHT", (5, 2), "LEFT")
    _run(5, 8, 2, "Main East")
    _stub_e(8, 2)
    _run(0, 2, 2, "Main East")
    cut((2, 2), "RIGHT", (3, 2), "LEFT")
    le.LABELS[:] = [
        (3, 0, "CP 117  Barn"),
        (0, 0, "West Lead <- Plane"),
        (6, 0, "West Lead -> South Yard"),
        (0, 3, "Main East <- Plane"),
        (6, 3, "Main East -> East End"),
    ]


# ---------------------------------------------------------------------------
# South Yard sheet
# ---------------------------------------------------------------------------

def build_116_et() -> None:
    """South Yard map: EH-3/2/3 hang off West Lead at 116 / TO1."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 2, "West Lead")
    cut((2, 2), "RIGHT", (3, 2), "LEFT")
    H((3, 2))
    nm((3, 2), "LEFT", "OS 116")
    # H+US: SP LEFT; TOP = ET; RIGHT = continue West Lead
    plant((4, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 116", "RIGHT", "TO1")
    cut((4, 2), "RIGHT", (5, 2), "LEFT")
    _run(5, 8, 2, "West Lead")
    _stub_e(8, 2)
    # ET stubs above (TOP leg)
    cut((4, 2), "TOP", (4, 1), "BOTTOM")
    H((4, 1))
    nm((4, 1), "LEFT", "OS 118")
    plant((5, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 118", "RIGHT", "TO11")
    cut((5, 1), "RIGHT", (6, 1), "LEFT")
    H((6, 1))
    nm((6, 1), "LEFT", "EH-3")
    cut((6, 1), "RIGHT", (7, 1), "LEFT")
    H((7, 1))
    nm((7, 1), "LEFT", "OS 119")
    plant((8, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 119", "RIGHT", "TO10")
    cut((8, 1), "RIGHT", (9, 1), "LEFT")
    H((9, 1))
    nm((9, 1), "LEFT", "EH-2")
    cut((9, 1), "RIGHT", (10, 1), "LEFT")
    H((10, 1))
    nm((10, 1), "LEFT", "EH-1")
    _stub_e(10, 1)
    le.LABELS[:] = [
        (3, 0, "CP 116 / ET"),
        (0, 0, "West Lead <- Barn / Plane"),
        (6, 0, "West Lead -> 103 / S-1"),
        (6, 3, "EH-3 EH-2 EH-1 (above lead)"),
    ]


def build_103() -> None:
    """South Yard map: 103 — West Lead continues as S-1; ladder down to 104."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    _clear()
    _run(0, 2, 1, "West Lead")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 103")
    plant((4, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 103", "RIGHT", "TOR14")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 10, 1, "S-1")
    _stub_e(10, 1)
    le.GRID[(4, 2)] = ["UPPERBACKSLASH"]
    cut((4, 1), "BOTTOM", (4, 2), "TOP")
    nm((4, 2), "RIGHT", "to 104")
    _run(5, 7, 2, "to 104 / S-2")
    _stub_e(7, 2)
    le.LABELS[:] = [
        (3, 0, "CP 103"),
        (0, 0, "West Lead <- Plane"),
        (6, 0, "Track S-1 -> East End"),
        (5, 3, "ladder v to 104"),
    ]


def build_104() -> None:
    """South Yard map: 104 — ladder to S-2; continue ladder to 105."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    _clear()
    _run(0, 1, 1, "from 103")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 104")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 104", "RIGHT", "TOL15")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 9, 1, "S-2")
    _stub_e(9, 1)
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "to 105")
    _run(4, 6, 2, "to 105 / S-3")
    _stub_e(6, 2)
    le.LABELS[:] = [
        (2, 0, "CP 104"),
        (0, 0, "<- ladder from 103"),
        (5, 0, "Track S-2 -> East End"),
        (4, 3, "ladder v to 105"),
    ]


def build_105() -> None:
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 1, 1, "from 104")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 105")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 105", "RIGHT", "TOL17")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 9, 1, "S-3")
    _stub_e(9, 1)
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "to 106")
    _run(4, 6, 2, "to 106 / S-4")
    _stub_e(6, 2)
    le.LABELS[:] = [
        (2, 0, "CP 105"),
        (0, 0, "<- ladder from 104"),
        (5, 0, "Track S-3 -> East End"),
        (4, 3, "ladder v to 106"),
    ]


def build_106() -> None:
    """South Yard map: 106 — S-4 east; ladder continues to S-5."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 1, 1, "from 105")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 106")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 106", "RIGHT", "TOL19")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 9, 1, "S-4")
    _stub_e(9, 1)
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "S-5")
    _run(4, 9, 2, "S-5")
    _stub_e(9, 2)
    le.LABELS[:] = [
        (2, 0, "CP 106"),
        (0, 0, "<- ladder from 105"),
        (5, 0, "Track S-4 -> East End"),
        (5, 3, "Track S-5 -> East End"),
    ]


# ---------------------------------------------------------------------------
# East End sheet
# ---------------------------------------------------------------------------

def build_111() -> None:
    """East End map: 111 crossover Main West ↔ Main East / S-1 band."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 1, "Main West")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 111b")
    plant((4, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 111a", "RIGHT", "TO111")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 9, 1, "Main West")
    _stub_e(9, 1)
    cut((4, 1), "BOTTOM", (4, 2), "TOP")
    _run(0, 3, 2, "Main East")
    cut((3, 2), "RIGHT", (4, 2), "LEFT")
    nm((4, 2), "LEFT", "OS 111a")
    cut((4, 2), "RIGHT", (5, 2), "LEFT")
    _run(5, 9, 2, "Main East")
    _stub_e(9, 2)
    le.LABELS[:] = [
        (3, 0, "CP 111"),
        (0, 0, "Main West <- Brick"),
        (6, 0, "Main West -> Princess"),
        (0, 3, "Main East / S-1 band"),
        (6, 3, "-> Princess"),
    ]


def build_110() -> None:
    """East End map: 110 on Main East / S-1 — ladder down toward 109...107."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 1, "Main East")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 110")
    plant((4, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 110", "RIGHT", "TOL6")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 9, 1, "Main East")
    _stub_e(9, 1)
    le.GRID[(4, 2)] = ["UPPERBACKSLASH"]
    cut((4, 1), "BOTTOM", (4, 2), "TOP")
    nm((4, 2), "RIGHT", "to 109")
    _run(5, 7, 2, "to 109 / S-2")
    _stub_e(7, 2)
    le.LABELS[:] = [
        (3, 0, "CP 110"),
        (0, 0, "Main East <- Barn"),
        (6, 0, "Main East -> Princess"),
        (5, 3, "ladder v 109->108->107"),
    ]


def build_109() -> None:
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 1, 1, "from 110")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 109")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 109", "RIGHT", "TOR7")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 8, 1, "S-2")
    _stub_e(8, 1)
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "to 108")
    _run(4, 6, 2, "to 108 / S-3")
    _stub_e(6, 2)
    le.LABELS[:] = [
        (2, 0, "CP 109"),
        (0, 0, "<- ladder from 110"),
        (5, 0, "Track S-2 (Aristech)"),
        (4, 3, "ladder v to 108"),
    ]


def build_108() -> None:
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 1, 1, "from 109")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 108")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 108", "RIGHT", "TOR9")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 8, 1, "S-3")
    _stub_e(8, 1)
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "to 107")
    _run(4, 6, 2, "to 107 / S-4")
    _stub_e(6, 2)
    le.LABELS[:] = [
        (2, 0, "CP 108"),
        (0, 0, "<- ladder from 109"),
        (5, 0, "Track S-3 (Ferrellgas / Stucki)"),
        (4, 3, "ladder v to 107"),
    ]


def build_107() -> None:
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 1, 1, "from 108")
    cut((1, 1), "RIGHT", (2, 1), "LEFT")
    H((2, 1)); nm((2, 1), "LEFT", "OS 107")
    plant((3, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 107", "RIGHT", "TOR11")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    _run(4, 8, 1, "S-4")
    _stub_e(8, 1)
    le.GRID[(3, 2)] = ["UPPERBACKSLASH"]
    cut((3, 1), "BOTTOM", (3, 2), "TOP")
    nm((3, 2), "RIGHT", "S-5")
    _run(4, 8, 2, "S-5")
    _stub_e(8, 2)
    le.LABELS[:] = [
        (2, 0, "CP 107"),
        (0, 0, "<- ladder from 108"),
        (5, 0, "Track S-4 (Kosmos)"),
        (5, 3, "Track S-5 (Calgon)"),
    ]


def build_112() -> None:
    """East End map: 112 — Main East -> East Lead; diverge to Barn Main East."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 1, "Main East")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 112")
    plant((4, 1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 112", "RIGHT", "TOL23")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 9, 1, "East Lead")
    _stub_e(9, 1)
    cut((4, 1), "BOTTOM", (4, 2), "TOP")
    _run(0, 3, 2, "Main East")
    cut((3, 2), "RIGHT", (4, 2), "LEFT")
    nm((4, 2), "LEFT", "to Barn")
    _stub_w(0, 2)
    le.LABELS[:] = [
        (3, 0, "CP 112"),
        (0, 0, "Main East <- 110 / East End"),
        (6, 0, "East Lead -> Princess"),
        (1, 3, "Main East -> Barn (bypass)"),
    ]


# ---------------------------------------------------------------------------
# Shenango sheet
# ---------------------------------------------------------------------------

def build_113() -> None:
    """Shenango map: Princess 113 crossover Main West ↔ Main East."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 1, "Main West")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 113b")
    plant((4, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 113b", "RIGHT", "TO113")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 9, 1, "Main West")
    _stub_e(9, 1)
    _run(0, 2, 2, "Main East")
    cut((2, 2), "RIGHT", (3, 2), "LEFT")
    H((3, 2)); nm((3, 2), "LEFT", "OS 113a")
    plant((4, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 113a", "RIGHT", "TO113")
    cut((4, 2), "TOP", (4, 1), "BOTTOM")
    cut((4, 2), "RIGHT", (5, 2), "LEFT")
    _run(5, 9, 2, "Main East")
    _stub_e(9, 2)
    le.LABELS[:] = [
        (3, 0, "CP 113  Princess"),
        (0, 0, "<- East End"),
        (6, 0, "-> 115 / K-1"),
        (6, 3, "-> 114 / K-2"),
    ]


def build_115() -> None:
    """Shenango map: 115 — Main West -> Track K-1 (McKee's Rocks)."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 1, "Main West")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 115")
    plant((4, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 115", "RIGHT", "TOL29")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 10, 1, "K-1")
    _stub_e(10, 1)
    le.LABELS[:] = [
        (3, 0, "CP 115"),
        (0, 0, "Main West <- Princess 113"),
        (6, 0, "Track K-1 -> McKee's Rocks / Scully"),
    ]


def build_114() -> None:
    """Shenango map: 114 — Main East -> Track K-2 (McKeesport)."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut
    _clear()
    _run(0, 2, 1, "Main East")
    cut((2, 1), "RIGHT", (3, 1), "LEFT")
    H((3, 1)); nm((3, 1), "LEFT", "OS 114")
    plant((4, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 114", "RIGHT", "TOR36")
    nm((4, 1), "RIGHT", "OS 114")
    cut((4, 1), "RIGHT", (5, 1), "LEFT")
    _run(5, 10, 1, "K-2")
    _stub_e(10, 1)
    le.LABELS[:] = [
        (3, 0, "CP 114"),
        (0, 0, "Main East <- Princess 113"),
        (6, 0, "Track K-2 -> McKeesport / Demmler"),
    ]


# Registry: id -> (sheet, title, builder)
CPS: list[tuple[str, str, str, BuildFn]] = [
    ("101", "West Yard", "CP 101 — W-1 / W-2 merge", build_101),
    ("100", "West Yard", "CP 100 — Brick (Main West / to Plane)", build_100),
    ("102", "West Yard", "CP 102 — Plane (West Lead / Main East)", build_102),
    ("117", "West Yard", "CP 117 — Barn crossover", build_117),
    ("116", "South Yard", "CP 116 — West Lead / EH-3...3", build_116_et),
    ("103", "South Yard", "CP 103 — West Lead -> S-1 + ladder", build_103),
    ("104", "South Yard", "CP 104 — ladder -> S-2", build_104),
    ("105", "South Yard", "CP 105 — ladder -> S-3", build_105),
    ("106", "South Yard", "CP 106 — S-4 + S-5", build_106),
    ("111", "East End", "CP 111 — Main West ↔ Main East", build_111),
    ("110", "East End", "CP 110 — Main East / S-1 + EE ladder", build_110),
    ("109", "East End", "CP 109 — ladder -> S-2", build_109),
    ("108", "East End", "CP 108 — ladder -> S-3", build_108),
    ("107", "East End", "CP 107 — S-4 + S-5", build_107),
    ("112", "East End", "CP 112 — East Lead / Main East to Barn", build_112),
    ("113", "Shenango", "CP 113 — Princess crossover", build_113),
    ("115", "Shenango", "CP 115 — Main West -> K-1", build_115),
    ("114", "Shenango", "CP 114 — Main East -> K-2", build_114),
]


def _emit_xml(out: Path, width: str, height: str) -> list[str]:
    """Wire current le.* grid (already 1-based) and write panel XML."""
    root = ET.parse(le.ARM).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    for old in list(root.findall("TRACKPLAN")):
        root.remove(old)
    if root.find(le.COMPRESSION_OFF_TAG) is None:
        root.append(ET.Element(le.COMPRESSION_OFF_TAG))

    tp = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(le.GRID.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        tp.append(le.make_section(x, y, tracks))
    cols = max(c[0] for c in le.GRID) + 2
    rows = max(c[1] for c in le.GRID) + 2
    tp.set("COLUMNS", str(cols))
    tp.set("ROWS", str(rows))
    disc = {n: "CTC" for n in set(le.ANCHORS.values())}
    le.wire(tp, disc)
    for blk in tp.iter("BLOCK"):
        name = blk.get("NAME") or ""
        blk.set("STATION", name)
    root.append(tp)
    root.set("WIDTH", width)
    root.set("HEIGHT", height)
    errs = le.verify(tp)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(out, encoding="UTF-8", xml_declaration=True)
    return errs


def _write_panel(cp_id: str, title: str) -> tuple[Path, list[str]]:
    _shift_1()
    out = OUT_DIR / f"HART_cp_{cp_id}.xml"
    errs = _emit_xml(out, WIDTH, HEIGHT)
    return out, errs


def _snapshot() -> tuple[
    dict[tuple[int, int], list[str]],
    dict[tuple[int, int], tuple[str, str, str]],
    dict[tuple[tuple[int, int], str], str],
    set[tuple[tuple[int, int], str]],
    list[tuple[int, int, str]],
]:
    return (
        dict(le.GRID),
        dict(le.PLANTS),
        dict(le.ANCHORS),
        set(le.ANON),
        list(le.LABELS),
    )


def _ascii(text: str) -> str:
    """CATS label font lacks many Unicode glyphs (shows as tofu / looks clipped)."""
    return (
        text.replace("->", "->")
        .replace("<-", "<-")
        .replace("v", "v")
        .replace("^", "^")
        .replace("...", "...")
        .replace("—", "-")
        .replace("–", "-")
        .replace("══", "==")
        .replace("═", "=")
    )


def _compose_all(
    selected: list[tuple[str, str, str, BuildFn]],
) -> tuple[Path, list[str]]:
    """Place every CP left->right with GAP_COLS between; PAD_X avoids left clip."""
    mg: dict[tuple[int, int], list[str]] = {}
    mp: dict[tuple[int, int], tuple[str, str, str]] = {}
    ma: dict[tuple[tuple[int, int], str], str] = {}
    mn: set[tuple[tuple[int, int], str]] = set()
    ml: list[tuple[int, int, str]] = []

    x_cursor = PAD_X
    for cp_id, sheet, title, builder in selected:
        _clear()
        builder()
        grid, plants, anchors, anon, labels = _snapshot()
        if not grid and not labels:
            continue
        ys = [y for _, y in grid] + [y for _, y, _ in labels]
        xs = [x for x, _ in grid] + [x for x, _, _ in labels]
        min_x = min(xs) if xs else 0
        max_x = max(xs) if xs else 0
        min_y = min(ys) if ys else 0
        # Banner above this CP; tracks top-aligned under it
        ml.append((x_cursor, 0, _ascii(f"== {title} [{sheet}] ==")))
        dx = x_cursor - min_x
        dy = PAD_Y - min_y
        for (x, y), tracks in grid.items():
            mg[(x + dx, y + dy)] = list(tracks)
        for (x, y), plant in plants.items():
            mp[(x + dx, y + dy)] = plant
        for (xy, e), name in anchors.items():
            x, y = xy
            ma[((x + dx, y + dy), e)] = name
        for xy, e in anon:
            x, y = xy
            mn.add(((x + dx, y + dy), e))
        for x, y, text in labels:
            ml.append((x + dx, y + dy, _ascii(text)))
        x_cursor += (max_x - min_x + 1) + GAP_COLS

    _clear()
    le.GRID.update(mg)
    le.PLANTS.update(mp)
    le.ANCHORS.update(ma)
    le.ANON.update(mn)
    le.LABELS.extend(ml)
    _shift_1()
    errs = _emit_xml(OUT_ALL, ALL_WIDTH, ALL_HEIGHT)
    return OUT_ALL, errs


def _write_index(results: list[tuple[str, str, str, Path, list[str], Path | None]]) -> None:
    lines = [
        "# HART control-point Digicon panels (critique set)",
        "",
        "Each panel is **one CP** drawn to the Neville station-map sheet language.",
        "Critique these individually before we reassemble the full Digicon.",
        "",
        "Station maps: `cats/docs/station_maps/`",
        "",
        "Rebuild: `python3 cats/scripts/build_hart_cp_panels.py`",
        "",
        "**All CPs left-to-right (spaced):** "
        "[`HART_cp_all.xml`](../panels/cp/HART_cp_all.xml) · "
        "[schematic](../screenshots/cp/HART_cp_all.png)",
        "",
        "```bash",
        "CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/cp/HART_cp_all.xml",
        "```",
        "",
        "Launch one: `CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/cp/HART_cp_100.xml`",
        "",
        "| CP | Sheet | Title | Panel | Schematic | Verify |",
        "|----|-------|-------|-------|-----------|--------|",
    ]
    for cp_id, sheet, title, panel, errs, shot in results:
        ok = "PASS" if not errs else f"FAIL ({len(errs)})"
        panel_rel = panel.relative_to(ROOT / "cats")
        shot_cell = (
            f"[png](../{shot.relative_to(ROOT / 'cats')})"
            if shot and shot.exists()
            else "—"
        )
        lines.append(
            f"| **{cp_id}** | {sheet} | {title} | "
            f"[`{panel.name}`](../{panel_rel}) | {shot_cell} | {ok} |"
        )
    lines += [
        "",
        "## Suggested review order",
        "",
        "1. West Yard: **101 -> 100 -> 102 -> 117** (matches West Yard sheet left->right)",
        "2. South Yard: **116/ET -> 103 -> 104 -> 105 -> 106**",
        "3. East End: **111 -> 110 -> 109 -> 108 -> 107 -> 112**",
        "4. Shenango: **113 -> 115 -> 114**",
        "",
        "For each CP, confirm: plant geometry, which tracks join, and destination labels",
        "(`to Brick`, `West Lead`, `S-1`, `K-1`, ...) against the station-map PNG.",
        "",
    ]
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="Comma-separated CP ids (e.g. 100,102,103)")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()

    only = {x.strip() for x in args.only.split(",")} if args.only else None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    import subprocess

    selected = [
        row for row in CPS if only is None or row[0] in only
    ]
    results: list[tuple[str, str, str, Path, list[str], Path | None]] = []
    n_fail = 0
    for cp_id, sheet, title, builder in selected:
        builder()
        panel, errs = _write_panel(cp_id, title)
        shot: Path | None = None
        if errs:
            n_fail += 1
            print(f"FAIL CP {cp_id}: {errs[:5]}{'...' if len(errs) > 5 else ''}", file=sys.stderr)
        else:
            print(f"OK   CP {cp_id} -> {panel.relative_to(ROOT)}")
        if not args.no_render:
            shot = SHOT_DIR / f"HART_cp_{cp_id}.png"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "cats/scripts/render_cats_panel.py"),
                    str(panel),
                    str(shot),
                ],
                check=False,
                capture_output=True,
            )
        results.append((cp_id, sheet, title, panel, errs, shot))

    all_panel, all_errs = _compose_all(selected)
    if all_errs:
        n_fail += 1
        print(f"FAIL ALL: {all_errs[:8]}{'...' if len(all_errs) > 8 else ''}", file=sys.stderr)
    else:
        print(f"OK   ALL -> {all_panel.relative_to(ROOT)}")
    if not args.no_render:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "cats/scripts/render_cats_panel.py"),
                str(all_panel),
                str(SHOT_DIR / "HART_cp_all.png"),
            ],
            check=False,
            capture_output=True,
        )

    _write_index(results)
    print(f"wrote {INDEX.relative_to(ROOT)}  ({len(results)} panels + all, {n_fail} FAIL)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
