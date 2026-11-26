#!/usr/bin/env python3
"""Render the true JMRI Layout Editor geometry (turnouts + track segments)
from a JMRI panel XML to PNG(s).

Uses real LE coordinates (positionablepoint x/y and layoutturnout
xa/ya..xd/yd leg endpoints), so paths are fully contiguous and every turnout
is shown exactly as wired. Supports a whole-layout render and a set of
professional, zoomed control-point views.

Usage:
    # whole layout
    python3 jmri/layouts/hart/scripts/render_le_layout.py <panel.xml> <out.png>
    # full professional view set into a directory
    python3 jmri/layouts/hart/scripts/render_le_layout.py <panel.xml> --all-views <out_dir>
    # single custom window
    python3 jmri/layouts/hart/scripts/render_le_layout.py <panel.xml> <out.png> \
        --title "West Yard" --xwin 440 630
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict

from PIL import Image, ImageDraw, ImageFont

try:            # mast icon sizes, as build_layout_le.py places them; the schematic's signals file
    from hartlib import layer_files, tables
except ImportError:     # run as a script: find the repo's hartlib above this file
    sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                    if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
    from hartlib import layer_files, tables

BG = (18, 20, 24)
MAIN = (228, 231, 236)      # mainline track
SIDE = (128, 134, 144)      # non-mainline (yard/siding) track
THRU = (232, 236, 242)      # turnout continuing legs (A/B)
DIVERGE = (95, 205, 255)    # turnout diverging legs (C/D)
POINT = (255, 190, 60)      # turnout center / control point
SIGNAL = (255, 105, 125)    # signal mast icon / facing marker
# with --kinds: a field mast (hardware on the layout) red, a virtual one (JMRI only, for Dispatcher) blue, a planned
# one (placeholder, no hardware yet) violet (amber would read as a turnout's control point); a mast the signals file
# does not list grey
KINDS_FILE = layer_files.path("signals")      # the schematic's signals file; --kinds-sheet picks its section
KINDS_SHEET = "staging"
KIND_COLOUR = {"field": SIGNAL, "virtual": (110, 170, 255), "planned": (190, 130, 255)}
UNLISTED = (150, 150, 150)
STATION = (110, 220, 180)   # Dispatcher station control pair
ANCHOR = (66, 72, 82)
OSNUM = (255, 255, 255)
OSSUB = (150, 230, 160)
SWID = (120, 200, 255)
BLKTXT = (140, 150, 162)
TITLE = (255, 255, 255)
SUBTITLE = (170, 176, 186)

# Professional panel views. Each: (title, subtitle, xmin, xmax) in LE coords.
VIEWS = {
    "01_overview": ("HART CTC — Full Railroad", "all 20 control points", None, None),
    "02_brick_plane": ("West End — Brick & Plane", "OS 100 / 101 / 102", 210, 430),
    "03_west_yard_engine": ("West Yard Ladder & Engine Terminal",
                            "OS 116-119 (Switch 116/117/118/119) + Scale-T13", 435, 640),
    "04_south_yard": ("South Yard Ladder", "OS 103-106 + Yard Tracks 1-5", 600, 900),
    "05_east_end": ("East End Ladder", "OS 107-112 + 111 crossover / East Lead", 1050, 1410),
    "06_princess_loops": ("Princess & East Loops",
                          "OS 113-115 + McKees Rocks / McKeesport", 1470, 1680),
}


Point = tuple[float, float]


class Segment(NamedTuple):
    """One drawn piece of track: a straight segment, or one chord of a curve (only the middle one carries the
    block name)."""
    a: Point
    b: Point
    main: bool
    block: str


class TurnoutRow(TypedDict):
    ident: str
    cen: Point
    block: str
    tn: str
    type: str


class MastIcon(TypedDict):
    name: str
    x: float
    y: float
    degrees: int
    hidden: bool
    size: tuple[int, int]
    kind: NotRequired[str | None]     # set by --kinds: the signals file's kind, None for a mast it does not list


class StationIcon(TypedDict):
    name: str
    x: float
    y: float


class Shape(TypedDict):
    type: str
    outline: list[Point]


Label = tuple[str, float, float, int, bool]    # text, x, y, size, bold
Decor = tuple[list[Label], list[Shape]]


def _font(size: int, bold: bool = False):
    cands = [
        ("/usr/share/fonts/truetype/macos/Inter-Bold.ttf" if bold
         else "/usr/share/fonts/truetype/macos/Inter-Regular.ttf"),
        "/usr/share/fonts/truetype/macos/JetBrainsMono-Regular.ttf",
    ]
    for p in cands:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def bezier_points(a, controls, b, n=16):
    """Points along a JMRI Bezier track segment (end, control points, end), for drawing."""
    ctrl = [a, *controls, b]
    out = []
    for i in range(n + 1):
        t = i / n
        pts = list(ctrl)
        while len(pts) > 1:      # de Casteljau, any number of control points
            pts = [((1 - t) * p[0] + t * q[0], (1 - t) * p[1] + t * q[1]) for p, q in zip(pts, pts[1:])]
        out.append(pts[0])
    return out


def arc_points(a, b, angle, flip, n=16):
    """Points along a Layout Editor circle arc (arc="yes" circle="yes") from end 1 to end 2, as
    TrackSegmentView.calculateTrackSegmentAngle draws it: from end 2 (end 1 when flipped), `angle` degrees
    counterclockwise on screen."""
    a1, a2 = (b, a) if flip else (a, b)
    half = math.radians(angle) / 2
    dx, dy = a2[0] - a1[0], a2[1] - a1[1]
    r = math.hypot(dx, dy) / 2 / math.sin(half)
    start = math.atan2(dx, dy) - half
    cx, cy = a2[0] - math.cos(start) * r, a2[1] + math.sin(start) * r
    pts = [(cx + r * math.cos(start + math.radians(angle) * i / n), cy - r * math.sin(start + math.radians(angle) * i / n))
           for i in range(n + 1)]
    return pts if flip else pts[::-1]


def find_panel(src: Path, panel: str | None = None, root=None):
    """The <LayoutEditor> element named `panel` (default: the live HART panel); `root` saves parsing src again."""
    root = ET.parse(src).getroot() if root is None else root
    names = (panel,) if panel else ("HART Railroad", "HART")
    return next(e for e in root.iter("LayoutEditor") if e.get("name") in names)


def icon_box(signal):
    """(width, height) of a mast icon's box: its upright size turned to its degrees, as JMRI's rotate gives it."""
    w, h = signal.get("size") or tables.MAST_ICON_DWARF
    th = math.radians(signal["degrees"])
    return w * abs(math.cos(th)) + h * abs(math.sin(th)), w * abs(math.sin(th)) + h * abs(math.cos(th))


def shape_outline(points, kind, n=8):
    """The outline Layout Editor draws for a layoutShape (LayoutShapeView.draw): from the middle of each side, a
    Straight point is a corner and a Curve point a quadratic curve through the side middles; an Open shape's first
    and last points are always Straight and it is not closed. `points` is [(x, y, type)]."""
    cnt = len(points)
    if cnt < 2:
        return [(p[0], p[1]) for p in points]
    out = []
    for i, (x, y, typ) in enumerate(points):
        prev, nxt = points[i - 1], points[(i + 1) % cnt]
        mid_l = ((prev[0] + x) / 2, (prev[1] + y) / 2)
        mid_r = ((x + nxt[0]) / 2, (y + nxt[1]) / 2)
        if kind == "Open" and i in (0, cnt - 1):
            typ = "Straight"
        if typ == "Curve":
            out += [((1 - t) ** 2 * mid_l[0] + 2 * (1 - t) * t * x + t * t * mid_r[0],
                     (1 - t) ** 2 * mid_l[1] + 2 * (1 - t) * t * y + t * t * mid_r[1]) for t in
                    (k / n for k in range(n + 1))]
        elif kind == "Open":
            out += ([] if i == 0 else [mid_l]) + [(x, y)] + ([] if i == cnt - 1 else [mid_r])
        else:
            out += [mid_l, (x, y), mid_r]
    if kind != "Open":
        out.append(out[0])
    return out


def load_decor(src: Path, panel: str | None = None, root=None):
    """The panel's text labels [(text, x, y, size, bold)] and shapes [{"type", "outline"}], each outline the
    points Layout Editor draws through."""
    le = find_panel(src, panel, root)
    labels = [(lb.get("text") or "", float(lb.get("x") or 0), float(lb.get("y") or 0), int(lb.get("size") or 10),
               lb.get("style") == "1") for lb in le.findall("positionablelabel") if lb.get("text")]
    shapes = []
    for sh in le.findall("layoutShape"):
        pts = [(float(p.get("x")), float(p.get("y")), p.get("type") or "Straight") for p in sh.iter("point")]
        if pts:
            shapes.append({"type": sh.get("type") or "Open", "outline": shape_outline(pts, sh.get("type") or "Open")})
    return labels, shapes


Geometry = tuple[dict[str, Point], dict[tuple[str, str], Point], list[TurnoutRow], list[Segment], list[MastIcon],
                 list[StationIcon]]


def load_geometry(src: Path, panel: str | None = None, curves: bool = False,
                  root: ET.Element | None = None) -> Geometry:
    """`curves` draws Bezier and arc track as curves; off, every segment is a straight chord (the site's overview
    image)."""
    root = ET.parse(src).getroot() if root is None else root
    le = find_panel(src, panel, root)
    system = tables.mast_system_names(root)
    pp = {p.get("ident"): (float(p.get("x")), float(p.get("y")))
          for p in le.findall("positionablepoint")}
    legs: dict[tuple[str, str], Point] = {}
    turnouts: list[TurnoutRow] = []
    for t in le.findall("layoutturnout"):
        ident = t.get("ident")
        for leg, (ax, ay) in (("TURNOUT_A", ("xa", "ya")),
                              ("TURNOUT_B", ("xb", "yb")),
                              ("TURNOUT_C", ("xc", "yc")),
                              ("TURNOUT_D", ("xd", "yd"))):
            if t.get(ax) and t.get(ay):
                legs[(ident, leg)] = (float(t.get(ax)), float(t.get(ay)))
        turnouts.append({
            "ident": ident,
            "cen": (float(t.get("xcen")), float(t.get("ycen"))),
            "block": t.get("blockname") or "",
            "tn": t.get("turnoutname") or "",
            "type": t.get("type") or "",
        })

    def resolve(name, typ):
        if typ == "POS_POINT":
            return pp.get(name)
        if typ and typ.startswith("TURNOUT"):
            return legs.get((name, typ))
        return None

    segs: list[Segment] = []
    for s in le.findall("tracksegment"):
        if s.get("hidden") == "yes":
            # Hidden track (the virtual K-1/K-2 wrap at Princess) is not drawn in PanelPro either.
            continue
        a = resolve(s.get("connect1name"), s.get("type1"))
        b = resolve(s.get("connect2name"), s.get("type2"))
        if a and b:
            main = s.get("mainline") == "yes"
            block = s.get("blockname") or ""
            controls = [(float(c.get("x")), float(c.get("y")))
                        for c in sorted(s.iter("controlpoint"), key=lambda c: int(c.get("index") or 0))]
            curve = None
            if curves and s.get("bezier") == "yes" and controls:
                curve = bezier_points(a, controls, b)
            elif curves and s.get("arc") == "yes" and s.get("circle") == "yes":
                # JMRI draws a circle arc stored with no angle (or 0) as 90 degrees
                curve = arc_points(a, b, float(s.get("angle") or 0) or 90.0, s.get("flip") == "yes")
            if curve:
                mid = (len(curve) - 1) // 2
                # one piece carries the block name, so a curve weighs as much as a straight in the label's place
                segs.extend(Segment(p, q, main, block if i == mid else "")
                            for i, (p, q) in enumerate(zip(curve, curve[1:])))
            else:
                segs.append(Segment(a, b, main, block))
    drawn = {s.a for s in segs} | {s.b for s in segs}
    pp = {k: v for k, v in pp.items() if v in drawn}
    signals: list[MastIcon] = []
    for icon in le.findall("signalmasticon"):
        try:
            signals.append({
                "name": icon.get("signalmast") or "",
                "x": float(icon.get("x") or "0"),
                "y": float(icon.get("y") or "0"),
                "degrees": int(float(icon.get("degrees") or "0")) % 360,
                "hidden": icon.get("hidden") == "yes",
                "size": tables.mast_icon_size(system.get(icon.get("signalmast") or "", ""))[0],
            })
        except ValueError:
            continue
    stations: list[StationIcon] = []
    for icon in le.findall("sensoricon"):
        sensor = icon.get("sensor") or ""
        if not sensor.startswith("MoveTo") or not sensor.endswith("_stored"):
            continue
        try:
            stations.append({
                "name": icon.get("text") or sensor.removeprefix("MoveTo").removesuffix("_stored"),
                "x": float(icon.get("x") or "0"),
                "y": float(icon.get("y") or "0"),
            })
        except ValueError:
            continue
    return pp, legs, turnouts, segs, signals, stations


# Image layout, in image pixels: the margin round the drawing, and the band above it for the title.
PAD = 34
TOP = 78
OVERVIEW_W = 2000     # the whole layout's target width
WINDOW_W = 1500       # a --xwin or VIEWS window's target width


class Visible(NamedTuple):
    """What lies in one view's x window (all of it for the overview)."""
    segs: list[Segment]
    turnouts: list[TurnoutRow]
    signals: list[MastIcon]
    stations: list[StationIcon]


class Frame(NamedTuple):
    """The panel area a view draws, and how panel coordinates map to image pixels. A NamedTuple, not a dataclass:
    build_layout_index.py loads this file without registering it in sys.modules, where dataclasses look."""
    bx0: float
    by0: float
    bx1: float
    by1: float
    scale: float
    width: int
    height: int

    def x(self, v: float) -> float:
        return PAD + (v - self.bx0) * self.scale

    def y(self, v: float) -> float:
        return TOP + (v - self.by0) * self.scale

    def pt(self, p: Point) -> Point:
        return (self.x(p[0]), self.y(p[1]))


def _x_window(pp: Mapping[str, Point], turnouts: Sequence[TurnoutRow], segs: Sequence[Segment],
              decor: Decor | None) -> tuple[float, float]:
    """The overview's x window: every anchor and turnout, and with decor the whole drawing."""
    allx = [p[0] for p in pp.values()] + [t["cen"][0] for t in turnouts]
    if decor:       # the whole drawing, arcs too (a turnback's far point need not be an anchor of the window)
        allx += [q[0] for s in segs for q in (s.a, s.b)]
        allx += [lb[1] for lb in decor[0]] + [q[0] for sh in decor[1] for q in sh["outline"]]
    return min(allx), max(allx)


def _visible(turnouts: Sequence[TurnoutRow], segs: Sequence[Segment], signals: Sequence[MastIcon],
             stations: Sequence[StationIcon], xmin: float, xmax: float) -> Visible:
    def inside(x: float) -> bool:
        return xmin - PAD <= x <= xmax + PAD

    return Visible(segs=[s for s in segs if inside(s.a[0]) or inside(s.b[0])],
                   turnouts=[t for t in turnouts if inside(t["cen"][0])],
                   signals=[s for s in signals if inside(s["x"])],
                   stations=[s for s in stations if inside(s["x"])])


def _extent(view: Visible, decor: Decor | None, xmin: float, xmax: float) -> list[Point]:
    """Every point the view draws; their box (plus PAD) is the picture's panel area."""
    pts: list[Point] = []
    for s in view.segs:
        pts += [s.a, s.b]
    for t in view.turnouts:
        pts.append(t["cen"])
    for signal in view.signals:
        pts.append((signal["x"], signal["y"]))
        if decor:       # the icon's whole box, as Layout Editor draws it from its top left corner
            bw, bh = icon_box(signal)
            pts.append((signal["x"] + bw, signal["y"] + bh))
    for station in view.stations:
        pts.append((station["x"], station["y"]))
    if decor:           # the panel's own labels and shapes, in the window, count toward the picture's size
        labels, shapes = decor
        for text, x, y, size, _bold in labels:
            if xmin - PAD <= x <= xmax + PAD:
                pts += [(x, y), (x + 0.6 * size * len(text), y + size)]
        for shape in shapes:
            pts += [q for q in shape["outline"] if xmin - PAD <= q[0] <= xmax + PAD]
    return pts


def _frame(pts: Sequence[Point], target_w: int, fixed_scale: float | None) -> Frame:
    bx0 = min(p[0] for p in pts) - PAD
    bx1 = max(p[0] for p in pts) + PAD
    by0 = min(p[1] for p in pts) - PAD
    by1 = max(p[1] for p in pts) + PAD
    scale = (target_w - 2 * PAD) / (bx1 - bx0)
    scale = max(scale, 1.0) if fixed_scale is None else fixed_scale
    return Frame(bx0, by0, bx1, by1, scale, width=int((bx1 - bx0) * scale + 2 * PAD),
                 height=int((by1 - by0) * scale + TOP + PAD))


def _draw_title(d: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    d.text((PAD, 18), title, font=_font(30, bold=True), fill=TITLE)
    d.text((PAD, 52), subtitle, font=_font(16), fill=SUBTITLE)


def _draw_tracks(d: ImageDraw.ImageDraw, f: Frame, segs: Sequence[Segment]) -> None:
    for s in segs:
        d.line([f.pt(s.a), f.pt(s.b)], fill=MAIN if s.main else SIDE, width=6 if s.main else 3)


def _draw_block_labels(d: ImageDraw.ImageDraw, f: Frame, segs: Sequence[Segment]) -> None:
    """One label per block at its pieces' averaged midpoint, nudged up when it would sit on the last one."""
    blk_pts: defaultdict[str, list[Point]] = defaultdict(list)
    for s in segs:
        if s.block:
            blk_pts[s.block].append(((s.a[0] + s.b[0]) / 2, (s.a[1] + s.b[1]) / 2))
    f_blk = _font(12)
    placed: list[Point] = []
    for bl, mids in blk_pts.items():
        if bl.startswith("OS "):
            continue  # OS shown on the control point marker
        mx = sum(m[0] for m in mids) / len(mids)
        my = sum(m[1] for m in mids) / len(mids)
        px, py = f.x(mx), f.y(my) - 12
        if any(abs(px - qx) < 60 and abs(py - qy) < 12 for qx, qy in placed):
            py -= 13
        placed.append((px, py))
        d.text((px, py), bl, font=f_blk, fill=BLKTXT, anchor="mm")


def _draw_anchors(d: ImageDraw.ImageDraw, f: Frame, pp: Mapping[str, Point]) -> None:
    for x, y in pp.values():
        if f.bx0 <= x <= f.bx1 and f.by0 <= y <= f.by1:
            d.ellipse([f.x(x) - 2, f.y(y) - 2, f.x(x) + 2, f.y(y) + 2], fill=ANCHOR)


def _orient(p: Point, q: Point, r: Point) -> int:
    v = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if abs(v) < 1e-9:
        return 0
    return 1 if v > 0 else 2


def _on_seg(p: Point, q: Point, r: Point) -> bool:
    return (min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9
            and min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9)


def _crosses(p: Point, q: Point, r: Point, s: Point) -> bool:
    """Whether segment p-q meets segment r-s."""
    o1, o2 = _orient(p, q, r), _orient(p, q, s)
    o3, o4 = _orient(r, s, p), _orient(r, s, q)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_seg(p, r, q):
        return True
    if o2 == 0 and _on_seg(p, s, q):
        return True
    if o3 == 0 and _on_seg(r, p, s):
        return True
    if o4 == 0 and _on_seg(r, q, s):
        return True
    return False


def _xover_diagonals(a: Point, b: Point, c: Point, dd: Point, ttype: str) -> tuple[Point, Point, Point, Point]:
    """The two diagonals of a double crossover: the pair that forms the diamond. JMRI RH/LH naming can be mirrored
    in LE, so the type decides only when neither pair crosses."""
    rh_pair = (a, dd, b, c)  # A-D & B-C
    lh_pair = (a, c, b, dd)  # A-C & B-D
    if _crosses(*rh_pair):
        return rh_pair
    if _crosses(*lh_pair):
        return lh_pair
    return rh_pair if "RH" in ttype else lh_pair


def _draw_turnouts(d: ImageDraw.ImageDraw, f: Frame, legs: Mapping[tuple[str, str], Point],
                   turnouts: Sequence[TurnoutRow], decor: Decor | None) -> None:
    """Each turnout's legs and its control point. A crossover is not drawn as a star from its centre (that makes
    SW-7 / SW-23 / SW-35 look like broken geometry): its two parallels A-B and D-C, then its diagonals."""
    for t in turnouts:
        cx, cy = t["cen"]
        ident = t["ident"]
        ttype = (t.get("type") or "").upper()
        a = legs.get((ident, "TURNOUT_A"))
        b = legs.get((ident, "TURNOUT_B"))
        c = legs.get((ident, "TURNOUT_C"))
        dd = legs.get((ident, "TURNOUT_D"))
        if "XOVER" in ttype and a and b and c and dd:
            d.line([f.pt(a), f.pt(b)], fill=THRU, width=5)
            d.line([f.pt(dd), f.pt(c)], fill=THRU, width=5)
            if decor and ttype in ("RH_XOVER", "LH_XOVER"):
                # a single crossover: one diagonal, from the middle of A-B to the middle of C-D (as JMRI draws it)
                d.line([f.pt(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)), f.pt(((c[0] + dd[0]) / 2, (c[1] + dd[1]) / 2))],
                       fill=DIVERGE, width=5)
                d.ellipse([f.x(cx) - 6, f.y(cy) - 6, f.x(cx) + 6, f.y(cy) + 6], fill=POINT)
                continue
            d1, d2, d3, d4 = _xover_diagonals(a, b, c, dd, ttype)
            d.line([f.pt(d1), f.pt(d2)], fill=DIVERGE, width=5)
            d.line([f.pt(d3), f.pt(d4)], fill=DIVERGE, width=5)
        else:
            for leg, lp in (("TURNOUT_A", a), ("TURNOUT_B", b), ("TURNOUT_C", c), ("TURNOUT_D", dd)):
                if lp:
                    col = THRU if leg in ("TURNOUT_A", "TURNOUT_B") else DIVERGE
                    d.line([(f.x(cx), f.y(cy)), (f.x(lp[0]), f.y(lp[1]))], fill=col, width=5)
        d.ellipse([f.x(cx) - 6, f.y(cy) - 6, f.x(cx) + 6, f.y(cy) + 6], fill=POINT)


# A turnout's label: three lines (OS number, area, switch name and ident) in a block TURNOUT_LABEL_H tall, placed
# above its point, else below, else higher still, so it does not sit on a label placed before it.
TURNOUT_LABEL_W = 96
TURNOUT_LABEL_H = 52


def _draw_turnout_labels(d: ImageDraw.ImageDraw, f: Frame, turnouts: Sequence[TurnoutRow]) -> None:
    f_os, f_sub, f_id = _font(19, bold=True), _font(13), _font(12)
    placed: list[Point] = []  # top left of each label block
    for t in sorted(turnouts, key=lambda tt: tt["cen"][0]):
        cx, cy = t["cen"]
        block = t["block"]
        osnum, area = block, ""
        if block.startswith("OS ") and "(" in block:
            osnum = block[:block.index("(")].strip()
            area = block[block.index("(") + 1:block.rindex(")")]
        lx = f.x(cx) + 9
        above = f.y(cy) - TURNOUT_LABEL_H
        below = f.y(cy) + 12

        def clash(ly: float, lx: float = lx) -> bool:
            return any(abs(lx - qx) < TURNOUT_LABEL_W and abs(ly - qy) < TURNOUT_LABEL_H for qx, qy in placed)

        ly = above
        if clash(ly):
            ly = below
            if clash(ly):
                ly = above - 54
        placed.append((lx, ly))
        d.text((lx, ly), osnum, font=f_os, fill=OSNUM)
        if area:
            d.text((lx, ly + 20), area, font=f_sub, fill=OSSUB)
        d.text((lx, ly + 36), f"{t['tn']} · {t['ident']}", font=f_id, fill=SWID)


def _draw_decor(d: ImageDraw.ImageDraw, f: Frame, decor: Decor) -> None:
    """The panel's own shapes, then its labels, at the panel's font size times the scale."""
    labels, shapes = decor
    for shape in shapes:
        outline = [f.pt(q) for q in shape["outline"]]
        if shape["type"] == "Filled" and len(outline) > 2:
            d.polygon(outline, fill=SIDE)
        if len(outline) > 1:
            d.line(outline, fill=MAIN, width=3)
    for text, x, y, size, bold in labels:
        d.text((f.x(x), f.y(y)), text, font=_font(max(8, round(size * f.scale)), bold=bold),
               fill=TITLE if bold else BLKTXT)


def _draw_signals(d: ImageDraw.ImageDraw, f: Frame, signals: Sequence[MastIcon], decor: Decor | None) -> None:
    """Display-only signal markers. The stem points in the mast's facing direction (0=north, 90=east, 180=south,
    270=west). With decor (the panel as Layout Editor shows it) the marker sits where the icon does: x, y is its top
    left corner of the turned box of its upright size (a dwarf 12 x 17, a high mast 12 x 40:
    hartlib.tables.mast_icon_size), and a hidden icon is drawn hollow."""
    f_sig = _font(10)
    for signal in signals:
        colour = (KIND_COLOUR.get(signal["kind"] or "", UNLISTED) if "kind" in signal else SIGNAL)
        th = math.radians(signal["degrees"])
        dx, dy = math.sin(th), -math.cos(th)
        px, py = f.x(signal["x"]), f.y(signal["y"])
        if decor:
            bw, bh = icon_box(signal)
            px, py = f.x(signal["x"] + bw / 2), f.y(signal["y"] + bh / 2)
            r = 3
            d.ellipse([px - r, py - r, px + r, py + r], outline=colour, width=1,
                      fill=None if signal.get("hidden") else colour)
            d.line([(px, py), (px + 9 * dx * f.scale, py + 9 * dy * f.scale)], fill=colour, width=2)
            continue
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=colour)
        d.line([(px, py), (px + 18 * dx, py + 18 * dy)], fill=colour, width=4)
        tx = px + (8 if dx >= 0 else -8)
        ty = py + (9 if dy >= 0 else -20)
        anchor = "la" if dx >= 0 else "ra"
        d.text((tx, ty), signal["name"], font=f_sig, fill=colour, anchor=anchor)


def _draw_stations(d: ImageDraw.ImageDraw, f: Frame, stations: Sequence[StationIcon]) -> None:
    f_station = _font(10, bold=True)
    for station in stations:
        px, py = f.x(station["x"]), f.y(station["y"])
        d.rounded_rectangle([px - 6, py - 5, px + 18, py + 7], radius=3, outline=STATION, width=2)
        d.text((px + 24, py + 1), station["name"], font=f_station, fill=STATION, anchor="lm")


class LegendEntry(NamedTuple):
    """One swatch of the legend's first row: `x` from PAD, a line `width` wide or a dot (width 0), then `text`."""
    x: int
    colour: tuple[int, int, int]
    width: int
    text: str


LEGEND_ROW = (
    LegendEntry(0, MAIN, 6, "mainline"),
    LegendEntry(120, SIDE, 3, "yard/siding"),
    LegendEntry(250, DIVERGE, 5, "diverging leg"),
    LegendEntry(400, POINT, 0, "control point (turnout)"),
    LegendEntry(590, SIGNAL, 0, "signal facing"),
)
LEGEND_LINE = 26      # a line swatch's length; its text starts 6 px after it
LEGEND_DOT = 10       # a dot swatch's size; its text starts 8 px after it


def _draw_legend(d: ImageDraw.ImageDraw, height: int, signals: Sequence[MastIcon]) -> None:
    f_id = _font(12)
    ly = height - 22
    for e in LEGEND_ROW:
        x = PAD + e.x
        if e.width:
            d.line([(x, ly), (x + LEGEND_LINE, ly)], fill=e.colour, width=e.width)
            d.text((x + LEGEND_LINE + 6, ly - 7), e.text, font=f_id, fill=SUBTITLE)
        else:
            d.ellipse([x, ly - 5, x + LEGEND_DOT, ly + 5], fill=e.colour)
            d.text((x + LEGEND_DOT + 8, ly - 7), e.text, font=f_id, fill=SUBTITLE)
    if any("kind" in s for s in signals):              # a second legend row, so it never runs off a narrow image
        kx: float = PAD
        ky = ly - 18
        entries = [(f"{k} mast", KIND_COLOUR[k]) for k in ("field", "virtual", "planned")]
        if any("kind" in s and s["kind"] not in KIND_COLOUR for s in signals):
            entries.append(("not in the signals file", UNLISTED))
        for text, colour in entries:
            d.ellipse([kx, ky - 5, kx + 10, ky + 5], fill=colour)
            d.text((kx + 16, ky - 7), text, font=f_id, fill=SUBTITLE)
            kx += 16 + d.textlength(text, font=f_id) + 24
    d.rounded_rectangle(
        [PAD + 720, ly - 5, PAD + 744, ly + 7],
        radius=3,
        outline=STATION,
        width=2,
    )
    d.text((PAD + 752, ly - 7), "Dispatcher station", font=f_id, fill=SUBTITLE)


def render_view(
    pp: Mapping[str, Point], legs: Mapping[tuple[str, str], Point], turnouts: Sequence[TurnoutRow],
    segs: Sequence[Segment], signals: Sequence[MastIcon], stations: Sequence[StationIcon], out: Path, title: str,
    subtitle: str, xmin: float | None = None, xmax: float | None = None, decor: Decor | None = None,
    fixed_scale: float | None = None,
) -> None:
    """Draw one view to `out`: the whole layout when xmin is None, else the window xmin..xmax.

    `decor` is load_decor's (labels, shapes): the panel drawn as Layout Editor shows it, its own labels and
    shapes in place of the block and turnout text this view makes up, and a single crossover with its one diagonal
    (without it, every crossover is drawn with two diagonals, as the site's overview image has it). Nothing is
    written when the window holds nothing."""
    if xmin is None:
        xmin, xmax = _x_window(pp, turnouts, segs, decor)
        target_w = OVERVIEW_W
    else:
        if xmax is None:
            raise ValueError("render_view: xmin given without xmax")
        target_w = WINDOW_W
    view = _visible(turnouts, segs, signals, stations, xmin, xmax)
    pts = _extent(view, decor, xmin, xmax)
    if not pts:
        return
    f = _frame(pts, target_w, fixed_scale)

    img = Image.new("RGB", (f.width, f.height), BG)
    d = ImageDraw.Draw(img)
    _draw_title(d, title, subtitle)
    _draw_tracks(d, f, view.segs)
    if not decor:
        _draw_block_labels(d, f, view.segs)
    _draw_anchors(d, f, pp)
    _draw_turnouts(d, f, legs, view.turnouts, decor)
    if decor:
        _draw_decor(d, f, decor)
    else:
        _draw_turnout_labels(d, f, view.turnouts)
    _draw_signals(d, f, view.signals, decor)
    _draw_stations(d, f, view.stations)
    _draw_legend(d, f.height, view.signals)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(
        f"wrote {out}  ({f.width}x{f.height})  turnouts={len(view.turnouts)} "
        f"segments={len(view.segs)} signals={len(view.signals)} stations={len(view.stations)}"
    )


def positive(text):
    """A --scale above zero."""
    try:
        v = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not v > 0 or math.isinf(v):
        raise argparse.ArgumentTypeError(f"{text!r}: the scale must be above zero")
    return v


def mast_kinds(path, sheet=None):
    """{mast user name: kind} from a schematic signals file's `signals` list (mast, kind): hart's signals.json, a
    section per sheet (hartlib.layer_files), read at `sheet`'s section (staging when None), or a plain signals file (the plugin's signals
    command's output). Names take the layer-1 `mast_prefix` of `sheet`'s section of the plan_overrides.json beside a
    sectioned file, or of the NAME.plan_overrides.json beside a plain NAME.signals.json, or "Mast " when it sets none. Stops on a file it cannot use, a sheet it
    has no section for, a `sheet` given for a plain file, or a mast listed twice."""
    path = Path(path)
    prefix = "Mast "
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        sectioned = isinstance(data, dict) and data.get(layer_files.SECTIONS) is True
        if sectioned:
            sheet = sheet or KINDS_SHEET
            data = layer_files.section_of(layer_files.parse(text, "signals", str(path)), sheet, str(path))
        rows = data["signals"]
        if not isinstance(rows, list):
            raise TypeError("signals is not a list")
    except (OSError, ValueError, KeyError, TypeError) as e:          # a LayerFileError is a ValueError
        raise SystemExit(f"--kinds {path}: cannot read a signals list ({e})")
    if not sectioned and sheet is not None:
        raise SystemExit(f"--kinds-sheet {sheet}: {path.name} has no sections; the sheet applies only to a "
                         "sectioned signals.json")
    over = (layer_files.path("plan_overrides", path.parent) if sectioned
            else path.with_name(path.name.replace(".signals.json", ".plan_overrides.json")))
    if over.exists() and over != path:
        try:
            layer = (layer_files.read("plan_overrides", sheet, path.parent) if sectioned
                     else json.loads(over.read_text(encoding="utf-8")))
            prefix = layer.get("mast_prefix", prefix)
        except (OSError, ValueError, AttributeError) as e:
            raise SystemExit(f"--kinds: cannot read {over} for the mast prefix ({e})")
    out = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("mast") or r.get("kind") not in KIND_COLOUR:
            raise SystemExit(f"--kinds {path}: each signal needs a mast and a kind of {', '.join(KIND_COLOUR)}: {r!r}")
        name = prefix + r["mast"]
        if name in out:
            raise SystemExit(f"--kinds {path}: {name} is listed twice")
        out[name] = r["kind"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path, nargs="?")
    ap.add_argument("--all-views", type=Path, metavar="OUTDIR")
    ap.add_argument("--title", default="HART Layout")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--xwin", type=float, nargs=2, metavar=("XMIN", "XMAX"))
    ap.add_argument("--panel", help="Layout Editor panel name (default: HART Railroad)")
    ap.add_argument("--curves", action="store_true", help="draw Bezier and arc track as curves, not chords")
    ap.add_argument("--labels", action="store_true", help="draw the panel as Layout Editor shows it: its labels, shapes and single crossovers")
    ap.add_argument("--scale", type=positive, help="image pixels per panel pixel (1 draws the panel at 100%% zoom)")
    ap.add_argument("--kinds", type=Path, nargs="?", const=KINDS_FILE, metavar="SIGNALS_JSON",
                    help="colour mast icons by kind (field, virtual, planned) from a schematic signals file "
                         "(default: signals.json, its --kinds-sheet section)")
    ap.add_argument("--kinds-sheet", metavar="SHEET",
                    help=f"the section of a sectioned signals file to read (default: {KINDS_SHEET}); "
                         "refused for a plain signals file")
    args = ap.parse_args()

    root = ET.parse(args.src).getroot()
    pp, legs, turnouts, segs, signals, stations = load_geometry(args.src, args.panel, args.curves, root)
    if args.kinds:
        kinds = mast_kinds(args.kinds, args.kinds_sheet)
        unlisted = sorted(s["name"] for s in signals if s["name"] not in kinds)
        if unlisted:
            print(f"--kinds: not in {args.kinds.name}, drawn grey: {', '.join(unlisted)}")
        for s in signals:
            s["kind"] = kinds.get(s["name"])

    if args.all_views:
        for key, (title, subtitle, xmin, xmax) in VIEWS.items():
            render_view(pp, legs, turnouts, segs, signals, stations,
                        args.all_views / f"hart_ctc_{key}.png",
                        title, subtitle, xmin, xmax)
        return
    if not args.out:
        ap.error("out PNG path required unless --all-views is used")
    xmin = args.xwin[0] if args.xwin else None
    xmax = args.xwin[1] if args.xwin else None
    render_view(
        pp, legs, turnouts, segs, signals, stations,
        args.out, args.title, args.subtitle, xmin, xmax,
        decor=load_decor(args.src, args.panel, root) if args.labels else None,
        fixed_scale=args.scale,
    )


if __name__ == "__main__":
    main()
