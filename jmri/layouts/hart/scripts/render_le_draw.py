"""How render_le_layout.py draws a view: the colours, the frame that maps panel coordinates to image pixels, each
layer (track, block labels, anchors, turnouts and their labels, the panel's own labels and shapes, masts, stations,
legend) and render_view, which draws one view to a PNG. CPython; imported through render_le_layout.py, which puts
hartlib on the path."""
from __future__ import annotations

import functools
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from render_le_geometry import Decor, MastIcon, Point, Segment, StationIcon, TurnoutRow, icon_box

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


@functools.lru_cache(maxsize=None)
def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """The font at `size`, made once: Inter (bold or regular), else JetBrains Mono, else PIL's own font where neither
    is installed."""
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


LEGEND_LINE = 26      # a line swatch's length; its text starts 6 px after it
LEGEND_DOT = 10       # a dot swatch's size; its text starts 8 px after it


def _draw_legend(d: ImageDraw.ImageDraw, height: int, signals: Sequence[MastIcon],
                 legend: Sequence[LegendEntry]) -> None:
    """The legend: `legend`'s swatches in its first row (render_le_layout.LEGEND_ROW), the mast kinds above it
    when --kinds coloured the masts, and the Dispatcher station swatch."""
    f_id = _font(12)
    ly = height - 22
    for e in legend:
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
    fixed_scale: float | None = None, *, legend: Sequence[LegendEntry],
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
    _draw_legend(d, f.height, view.signals, legend)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(
        f"wrote {out}  ({f.width}x{f.height})  turnouts={len(view.turnouts)} "
        f"segments={len(view.segs)} signals={len(view.signals)} stations={len(view.stations)}"
    )
