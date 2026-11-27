"""What render_le_layout.py draws, read from a JMRI panel file: the Layout Editor's anchors, turnout legs, track
segments (straight, or the points of a Bezier or circle arc), signal mast icons and Dispatcher station sensors, and
the panel's own labels and shapes. CPython; imported through render_le_layout.py, which puts hartlib on the path."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict

from hartlib import tables
from hartlib.errors import HartlibError

Point = tuple[float, float]


class RenderError(HartlibError, ValueError):
    """A panel file the renderer cannot draw: no such panel, or an item whose numbers do not read; the message says
    which."""


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
Legs = dict[tuple[str, str], Point]
Geometry = tuple[dict[str, Point], Legs, list[TurnoutRow], list[Segment], list[MastIcon], list[StationIcon]]

TURNOUT_LEGS = (("TURNOUT_A", ("xa", "ya")), ("TURNOUT_B", ("xb", "yb")),
                ("TURNOUT_C", ("xc", "yc")), ("TURNOUT_D", ("xd", "yd")))


def number(el: ET.Element, attr: str, default: str | None = None) -> float:
    """Attribute `attr` of panel item `el` as a number (`default` when it has none); RenderError naming the item
    when it is missing with no default, or not a number."""
    text = el.get(attr) or default
    if text is None:
        raise RenderError(f"<{el.tag} {_item(el)}>: no {attr}")
    try:
        return float(text)
    except ValueError as exc:
        raise RenderError(f"<{el.tag} {_item(el)}>: {attr}={text!r} is not a number") from exc


def _item(el: ET.Element) -> str:
    """The attribute that names a panel item, for messages."""
    for attr in ("ident", "signalmast", "sensor", "text"):
        if el.get(attr):
            return f'{attr}="{el.get(attr)}"'
    return "(unnamed)"


def bezier_points(a: Point, controls: list[Point], b: Point, n: int = 16) -> list[Point]:
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


def arc_points(a: Point, b: Point, angle: float, flip: bool, n: int = 16) -> list[Point]:
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


def find_panel(src: Path, panel: str | None = None, root: ET.Element | None = None) -> ET.Element:
    """The <LayoutEditor> element named `panel` (default: the live HART panel); `root` saves parsing src again.
    RenderError when the file has no such panel."""
    root = ET.parse(src).getroot() if root is None else root
    names = (panel,) if panel else ("HART Railroad", "HART")
    found = next((e for e in root.iter("LayoutEditor") if e.get("name") in names), None)
    if found is None:
        raise RenderError(f"{src}: no Layout Editor panel named {' or '.join(names)}")
    return found


def icon_box(signal: MastIcon) -> Point:
    """(width, height) of a mast icon's box: its upright size turned to its degrees, as JMRI's rotate gives it."""
    w, h = signal.get("size") or tables.MAST_ICON_DWARF
    th = math.radians(signal["degrees"])
    return w * abs(math.cos(th)) + h * abs(math.sin(th)), w * abs(math.sin(th)) + h * abs(math.cos(th))


def shape_outline(points: list[tuple[float, float, str]], kind: str, n: int = 8) -> list[Point]:
    """The outline Layout Editor draws for a layoutShape (LayoutShapeView.draw): from the middle of each side, a
    Straight point is a corner and a Curve point a quadratic curve through the side middles; an Open shape's first
    and last points are always Straight and it is not closed. `points` is [(x, y, type)]."""
    cnt = len(points)
    if cnt < 2:
        return [(p[0], p[1]) for p in points]
    out: list[Point] = []
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


def load_decor(src: Path, panel: str | None = None, root: ET.Element | None = None) -> Decor:
    """The panel's text labels [(text, x, y, size, bold)] and shapes [{"type", "outline"}], each outline the
    points Layout Editor draws through. RenderError on a label or shape point whose numbers do not read."""
    le = find_panel(src, panel, root)
    labels = [(lb.get("text") or "", number(lb, "x", "0"), number(lb, "y", "0"), int(number(lb, "size", "10")),
               lb.get("style") == "1") for lb in le.findall("positionablelabel") if lb.get("text")]
    shapes: list[Shape] = []
    for sh in le.findall("layoutShape"):
        pts = [(number(p, "x"), number(p, "y"), p.get("type") or "Straight") for p in sh.iter("point")]
        if pts:
            shapes.append({"type": sh.get("type") or "Open", "outline": shape_outline(pts, sh.get("type") or "Open")})
    return labels, shapes


def _turnouts(le: ET.Element) -> tuple[Legs, list[TurnoutRow]]:
    """Each turnout's leg ends, by (ident, TURNOUT_A..D), and its row (centre, block, turnout name, type)."""
    legs: Legs = {}
    turnouts: list[TurnoutRow] = []
    for t in le.findall("layoutturnout"):
        ident = t.get("ident") or ""
        for leg, (ax, ay) in TURNOUT_LEGS:
            if t.get(ax) and t.get(ay):
                legs[(ident, leg)] = (number(t, ax), number(t, ay))
        turnouts.append({"ident": ident, "cen": (number(t, "xcen"), number(t, "ycen")),
                         "block": t.get("blockname") or "", "tn": t.get("turnoutname") or "", "type": t.get("type") or ""})
    return legs, turnouts


def _curve(s: ET.Element, a: Point, b: Point) -> list[Point] | None:
    """The points a Bezier or circle-arc track segment is drawn through, None for one drawn straight."""
    controls = [(number(c, "x"), number(c, "y"))
                for c in sorted(s.iter("controlpoint"), key=lambda c: int(number(c, "index", "0")))]
    if s.get("bezier") == "yes" and controls:
        return bezier_points(a, controls, b)
    if s.get("arc") == "yes" and s.get("circle") == "yes":
        # JMRI draws a circle arc stored with no angle (or 0) as 90 degrees
        return arc_points(a, b, number(s, "angle", "0") or 90.0, s.get("flip") == "yes")
    return None


def _segments(le: ET.Element, pp: dict[str, Point], legs: Legs, curves: bool) -> list[Segment]:
    """The track segments drawn: a hidden one left out (as PanelPro does), one whose ends are not both found left
    out, and with `curves` a Bezier or arc as its chords, the middle one carrying the block name."""
    def resolve(name: str | None, typ: str | None) -> Point | None:
        if typ == "POS_POINT":
            return pp.get(name or "")
        if typ and typ.startswith("TURNOUT"):
            return legs.get((name or "", typ))
        return None

    segs: list[Segment] = []
    for s in le.findall("tracksegment"):
        if s.get("hidden") == "yes":
            # Hidden track (the virtual K-1/K-2 wrap at Princess) is not drawn in PanelPro either.
            continue
        a = resolve(s.get("connect1name"), s.get("type1"))
        b = resolve(s.get("connect2name"), s.get("type2"))
        if not (a and b):
            continue
        main = s.get("mainline") == "yes"
        block = s.get("blockname") or ""
        curve = _curve(s, a, b) if curves else None
        if curve:
            mid = (len(curve) - 1) // 2
            # one piece carries the block name, so a curve weighs as much as a straight in the label's place
            segs.extend(Segment(p, q, main, block if i == mid else "") for i, (p, q) in enumerate(zip(curve, curve[1:])))
        else:
            segs.append(Segment(a, b, main, block))
    return segs


def _mast_icons(le: ET.Element, system: dict[str, str]) -> list[MastIcon]:
    """Every signal mast icon, its size the icon size of its mast's system name (`system`: user name to system)."""
    return [{"name": icon.get("signalmast") or "", "x": number(icon, "x", "0"), "y": number(icon, "y", "0"),
             "degrees": int(number(icon, "degrees", "0")) % 360, "hidden": icon.get("hidden") == "yes",
             "size": tables.mast_icon_size(system.get(icon.get("signalmast") or "", ""))[0]}
            for icon in le.findall("signalmasticon")]


def _stations(le: ET.Element) -> list[StationIcon]:
    """Every Dispatcher station sensor icon (a MoveTo..._stored sensor), named by its text or its sensor's name.
    The prefix test is kept on purpose: this draws any panel file, old and trial ones whose sensors the device master
    lacks (docs/parked/UNPARK.md row 22)."""
    out: list[StationIcon] = []
    for icon in le.findall("sensoricon"):
        sensor = icon.get("sensor") or ""
        if sensor.startswith("MoveTo") and sensor.endswith("_stored"):
            out.append({"name": icon.get("text") or sensor.removeprefix("MoveTo").removesuffix("_stored"),
                        "x": number(icon, "x", "0"), "y": number(icon, "y", "0")})
    return out


def load_geometry(src: Path, panel: str | None = None, curves: bool = False,
                  root: ET.Element | None = None) -> Geometry:
    """(anchors drawn, turnout legs, turnouts, track segments, mast icons, station icons) of the panel. `curves`
    draws Bezier and arc track as curves; off, every segment is a straight chord (the site's overview image).
    RenderError on a panel the file lacks or an item whose numbers do not read."""
    root = ET.parse(src).getroot() if root is None else root
    le = find_panel(src, panel, root)
    pp = {p.get("ident") or "": (number(p, "x"), number(p, "y")) for p in le.findall("positionablepoint")}
    legs, turnouts = _turnouts(le)
    segs = _segments(le, pp, legs, curves)
    drawn = {s.a for s in segs} | {s.b for s in segs}
    pp = {k: v for k, v in pp.items() if v in drawn}
    return pp, legs, turnouts, segs, _mast_icons(le, tables.mast_system_names(root)), _stations(le)
