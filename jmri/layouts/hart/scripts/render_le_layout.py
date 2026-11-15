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
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:            # mast icon sizes, as build_layout_le.py places them
    from hartlib import tables
except ImportError:     # run as a script: find the repo's hartlib above this file
    sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                    if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
    from hartlib import tables

BG = (18, 20, 24)
MAIN = (228, 231, 236)      # mainline track
SIDE = (128, 134, 144)      # non-mainline (yard/siding) track
THRU = (232, 236, 242)      # turnout continuing legs (A/B)
DIVERGE = (95, 205, 255)    # turnout diverging legs (C/D)
POINT = (255, 190, 60)      # turnout center / control point
SIGNAL = (255, 105, 125)    # signal mast icon / facing marker
# with --kinds: a field mast (hardware on the layout) red, a virtual one (JMRI only, for Dispatcher) blue, a planned
# one (placeholder, no hardware yet) amber; a mast the signals file does not list stays red
KINDS_FILE = Path(__file__).resolve().parents[1] / "data/schematic/staging.signals.json"
KIND_COLOUR = {"field": SIGNAL, "virtual": (110, 170, 255), "planned": (240, 180, 60)}
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


def load_geometry(src: Path, panel: str | None = None, curves: bool = False, root=None):
    """`curves` draws Bezier and arc track as curves; off, every segment is a straight chord (the site's overview
    image)."""
    root = ET.parse(src).getroot() if root is None else root
    le = find_panel(src, panel, root)
    system = tables.mast_system_names(root)
    pp = {p.get("ident"): (float(p.get("x")), float(p.get("y")))
          for p in le.findall("positionablepoint")}
    legs = {}
    turnouts = []
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

    segs = []
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
                segs.extend((p, q, main, block if i == mid else "")
                            for i, (p, q) in enumerate(zip(curve, curve[1:])))
            else:
                segs.append((a, b, main, block))
    drawn = {a for a, _b, _m, _blk in segs} | {b for _a, b, _m, _blk in segs}
    pp = {k: v for k, v in pp.items() if v in drawn}
    signals = []
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
    stations = []
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


def render_view(
    pp, legs, turnouts, segs, signals, stations, out: Path, title: str, subtitle: str,
    xmin=None, xmax=None, decor=None, fixed_scale=None
):
    """`decor` is load_decor's (labels, shapes): the panel drawn as Layout Editor shows it, its own labels and
    shapes in place of the block and turnout text this view makes up, and a single crossover with its one diagonal
    (without it, every crossover is drawn with two diagonals, as the site's overview image has it)."""
    pad = 34
    if xmin is None:
        allx = [p[0] for p in pp.values()] + [t["cen"][0] for t in turnouts]
        if decor:       # the whole drawing, arcs too (a turnback's far point need not be an anchor of the window)
            allx += [q[0] for a, b, _m, _blk in segs for q in (a, b)]
            allx += [lb[1] for lb in decor[0]] + [q[0] for sh in decor[1] for q in sh["outline"]]
        xmin, xmax = min(allx), max(allx)
        target_w = 2000
    else:
        target_w = 1500

    def seg_in(a, b):
        return (xmin - pad <= a[0] <= xmax + pad) or (xmin - pad <= b[0] <= xmax + pad)

    vsegs = [s for s in segs if seg_in(s[0], s[1])]
    vturn = [t for t in turnouts if xmin - pad <= t["cen"][0] <= xmax + pad]
    vsignals = [s for s in signals if xmin - pad <= s["x"] <= xmax + pad]
    vstations = [s for s in stations if xmin - pad <= s["x"] <= xmax + pad]

    pts = []
    for a, b, _m, _bl in vsegs:
        pts += [a, b]
    for t in vturn:
        pts.append(t["cen"])
    for signal in vsignals:
        pts.append((signal["x"], signal["y"]))
        if decor:       # the icon's whole box, as Layout Editor draws it from its top left corner
            bw, bh = icon_box(signal)
            pts.append((signal["x"] + bw, signal["y"] + bh))
    for station in vstations:
        pts.append((station["x"], station["y"]))
    if decor:           # the panel's own labels and shapes, in the window, count toward the picture's size
        labels, shapes = decor
        for text, x, y, size, _bold in labels:
            if xmin - pad <= x <= xmax + pad:
                pts += [(x, y), (x + 0.6 * size * len(text), y + size)]
        for shape in shapes:
            pts += [q for q in shape["outline"] if xmin - pad <= q[0] <= xmax + pad]
    if not pts:
        return
    bx0 = min(p[0] for p in pts) - pad
    bx1 = max(p[0] for p in pts) + pad
    by0 = min(p[1] for p in pts) - pad
    by1 = max(p[1] for p in pts) + pad

    scale = (target_w - 2 * pad) / (bx1 - bx0)
    scale = max(scale, 1.0) if fixed_scale is None else fixed_scale
    W = int((bx1 - bx0) * scale + 2 * pad)
    top = 78
    H = int((by1 - by0) * scale + top + pad)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def X(v):
        return pad + (v - bx0) * scale

    def Y(v):
        return top + (v - by0) * scale

    d.text((pad, 18), title, font=_font(30, bold=True), fill=TITLE)
    d.text((pad, 52), subtitle, font=_font(16), fill=SUBTITLE)

    # track segments
    for a, b, main, _bl in vsegs:
        d.line([(X(a[0]), Y(a[1])), (X(b[0]), Y(b[1]))],
               fill=MAIN if main else SIDE, width=6 if main else 3)

    # block-name labels: one per block at averaged segment midpoint
    blk_pts = defaultdict(list)
    for a, b, _m, bl in vsegs:
        if bl:
            blk_pts[bl].append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    f_blk = _font(12)
    placed = []
    for bl, mids in ([] if decor else blk_pts.items()):
        if bl.startswith("OS "):
            continue  # OS shown on the control point marker
        mx = sum(m[0] for m in mids) / len(mids)
        my = sum(m[1] for m in mids) / len(mids)
        px, py = X(mx), Y(my) - 12
        if any(abs(px - qx) < 60 and abs(py - qy) < 12 for qx, qy in placed):
            py -= 13
        placed.append((px, py))
        d.text((px, py), bl, font=f_blk, fill=BLKTXT, anchor="mm")

    # anchors
    for _n, (x, y) in pp.items():
        if bx0 <= x <= bx1 and by0 <= y <= by1:
            d.ellipse([X(x) - 2, Y(y) - 2, X(x) + 2, Y(y) + 2], fill=ANCHOR)

    # turnouts (control points) — draw legs + points first.
    # Crossovers (RH/LH_XOVER) must NOT be drawn as a star from the center —
    # that makes SW-7 / SW-23 / SW-35 look like broken geometry. Draw the two
    # continuing parallels (A–B, D–C) and the correct thrown diagonals instead.
    f_os = _font(19, bold=True)
    f_sub = _font(13)
    f_id = _font(12)
    for t in vturn:
        cx, cy = t["cen"]
        ident = t["ident"]
        ttype = (t.get("type") or "").upper()
        a = legs.get((ident, "TURNOUT_A"))
        b = legs.get((ident, "TURNOUT_B"))
        c = legs.get((ident, "TURNOUT_C"))
        dd = legs.get((ident, "TURNOUT_D"))
        if "XOVER" in ttype and a and b and c and dd:
            def _pt(p):
                return (X(p[0]), Y(p[1]))

            def _orient(p, q, r):
                v = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
                if abs(v) < 1e-9:
                    return 0
                return 1 if v > 0 else 2

            def _on_seg(p, q, r):
                return (
                    min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9
                    and min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9
                )

            def _crosses(p, q, r, s):
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

            # Continuing routes (parallel rails)
            d.line([_pt(a), _pt(b)], fill=THRU, width=5)
            d.line([_pt(dd), _pt(c)], fill=THRU, width=5)
            if decor and ttype in ("RH_XOVER", "LH_XOVER"):
                # a single crossover: one diagonal, from the middle of A-B to the middle of C-D (as JMRI draws it)
                d.line([_pt(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)), _pt(((c[0] + dd[0]) / 2, (c[1] + dd[1]) / 2))],
                       fill=DIVERGE, width=5)
                d.ellipse([X(cx) - 6, Y(cy) - 6, X(cx) + 6, Y(cy) + 6], fill=POINT)
                continue
            # Pick the diagonal pair that actually forms the diamond. JMRI RH/LH
            # naming can be mirrored in LE so type alone is not enough.
            rh_pair = (a, dd, b, c)  # A–D & B–C
            lh_pair = (a, c, b, dd)  # A–C & B–D
            if _crosses(*rh_pair):
                d1, d2, d3, d4 = rh_pair
            elif _crosses(*lh_pair):
                d1, d2, d3, d4 = lh_pair
            elif "RH" in ttype:
                d1, d2, d3, d4 = rh_pair
            else:
                d1, d2, d3, d4 = lh_pair
            d.line([_pt(d1), _pt(d2)], fill=DIVERGE, width=5)
            d.line([_pt(d3), _pt(d4)], fill=DIVERGE, width=5)
        else:
            for leg, lp in (
                ("TURNOUT_A", a),
                ("TURNOUT_B", b),
                ("TURNOUT_C", c),
                ("TURNOUT_D", dd),
            ):
                if lp:
                    col = THRU if leg in ("TURNOUT_A", "TURNOUT_B") else DIVERGE
                    d.line([(X(cx), Y(cy)), (X(lp[0]), Y(lp[1]))], fill=col, width=5)
        d.ellipse([X(cx) - 6, Y(cy) - 6, X(cx) + 6, Y(cy) + 6], fill=POINT)

    # labels with simple anti-collision (stagger above/below the point)
    placed_lbl = []  # (px, py) top-left of a 3-line label block (~52px tall)
    for t in ([] if decor else sorted(vturn, key=lambda tt: tt["cen"][0])):
        cx, cy = t["cen"]
        block = t["block"]
        osnum, area = block, ""
        if block.startswith("OS ") and "(" in block:
            osnum = block[:block.index("(")].strip()
            area = block[block.index("(") + 1:block.rindex(")")]
        lx = X(cx) + 9
        above = Y(cy) - 52
        below = Y(cy) + 12
        ly = above
        # if this label would collide with a nearby placed one, try below
        if any(abs(lx - qx) < 96 and abs(ly - qy) < 52 for qx, qy in placed_lbl):
            ly = below
            if any(abs(lx - qx) < 96 and abs(ly - qy) < 52 for qx, qy in placed_lbl):
                ly = above - 54
        placed_lbl.append((lx, ly))
        d.text((lx, ly), osnum, font=f_os, fill=OSNUM)
        if area:
            d.text((lx, ly + 20), area, font=f_sub, fill=OSSUB)
        d.text((lx, ly + 36), f"{t['tn']} · {t['ident']}", font=f_id, fill=SWID)

    if decor:
        labels, shapes = decor
        for shape in shapes:
            outline = [(X(x), Y(y)) for x, y in shape["outline"]]
            if shape["type"] == "Filled" and len(outline) > 2:
                d.polygon(outline, fill=SIDE)
            if len(outline) > 1:
                d.line(outline, fill=MAIN, width=3)
        for text, x, y, size, bold in labels:
            d.text((X(x), Y(y)), text, font=_font(max(8, round(size * scale)), bold=bold), fill=TITLE if bold else BLKTXT)

    # Display-only signal markers. The stem points in the mast's facing
    # direction (0=north, 90=east, 180=south, 270=west). With decor (the panel as Layout Editor shows it) the
    # marker sits where the icon does: x, y is its top left corner of the turned box of its upright size (a dwarf
    # 12 x 17, a high mast 12 x 40: hartlib.tables.mast_icon_size), and a hidden icon is drawn hollow.
    f_sig = _font(10)
    for signal in vsignals:
        colour = KIND_COLOUR.get(signal.get("kind"), SIGNAL)
        th = math.radians(signal["degrees"])
        dx, dy = math.sin(th), -math.cos(th)
        px, py = X(signal["x"]), Y(signal["y"])
        if decor:
            bw, bh = icon_box(signal)
            px, py = X(signal["x"] + bw / 2), Y(signal["y"] + bh / 2)
            r = 3
            d.ellipse([px - r, py - r, px + r, py + r], outline=colour, width=1,
                      fill=None if signal.get("hidden") else colour)
            d.line([(px, py), (px + 9 * dx * scale, py + 9 * dy * scale)], fill=colour, width=2)
            continue
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=colour)
        d.line([(px, py), (px + 18 * dx, py + 18 * dy)], fill=colour, width=4)
        tx = px + (8 if dx >= 0 else -8)
        ty = py + (9 if dy >= 0 else -20)
        anchor = "la" if dx >= 0 else "ra"
        d.text((tx, ty), signal["name"], font=f_sig, fill=colour, anchor=anchor)

    f_station = _font(10, bold=True)
    for station in vstations:
        px, py = X(station["x"]), Y(station["y"])
        d.rounded_rectangle(
            [px - 6, py - 5, px + 18, py + 7],
            radius=3,
            outline=STATION,
            width=2,
        )
        d.text((px + 24, py + 1), station["name"], font=f_station, fill=STATION, anchor="lm")

    # legend
    ly = H - 22
    d.line([(pad, ly), (pad + 26, ly)], fill=MAIN, width=6)
    d.text((pad + 32, ly - 7), "mainline", font=f_id, fill=SUBTITLE)
    d.line([(pad + 120, ly), (pad + 146, ly)], fill=SIDE, width=3)
    d.text((pad + 152, ly - 7), "yard/siding", font=f_id, fill=SUBTITLE)
    d.line([(pad + 250, ly), (pad + 276, ly)], fill=DIVERGE, width=5)
    d.text((pad + 282, ly - 7), "diverging leg", font=f_id, fill=SUBTITLE)
    d.ellipse([pad + 400, ly - 5, pad + 410, ly + 5], fill=POINT)
    d.text((pad + 418, ly - 7), "control point (turnout)", font=f_id, fill=SUBTITLE)
    d.ellipse([pad + 590, ly - 5, pad + 600, ly + 5], fill=SIGNAL)
    d.text((pad + 608, ly - 7), "signal facing", font=f_id, fill=SUBTITLE)
    if any(s.get("kind") for s in vsignals):
        kx = pad + 900
        for kind in ("field", "virtual", "planned"):
            d.ellipse([kx, ly - 5, kx + 10, ly + 5], fill=KIND_COLOUR[kind])
            d.text((kx + 16, ly - 7), f"{kind} mast", font=f_id, fill=SUBTITLE)
            kx += 110
    d.rounded_rectangle(
        [pad + 720, ly - 5, pad + 744, ly + 7],
        radius=3,
        outline=STATION,
        width=2,
    )
    d.text((pad + 752, ly - 7), "Dispatcher station", font=f_id, fill=SUBTITLE)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(
        f"wrote {out}  ({W}x{H})  turnouts={len(vturn)} "
        f"segments={len(vsegs)} signals={len(vsignals)} stations={len(vstations)}"
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


def mast_kinds(path):
    """{mast user name: kind} from a schematic signals file (its `signals` list: mast, kind; names take the
    layer-1 `mast_prefix`, "Mast " on this railroad). Stops on a file it cannot read."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data["signals"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise SystemExit(f"--kinds {path}: cannot read a signals list ({e})")
    prefix = data.get("mast_prefix", "Mast ")
    out = {}
    for r in rows:
        if not isinstance(r, dict) or not r.get("mast") or r.get("kind") not in KIND_COLOUR:
            raise SystemExit(f"--kinds {path}: each signal needs a mast and a kind of {', '.join(KIND_COLOUR)}: {r!r}")
        out[prefix + r["mast"]] = r["kind"]
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
                         "(default: the staging signals file)")
    args = ap.parse_args()

    root = ET.parse(args.src).getroot()
    pp, legs, turnouts, segs, signals, stations = load_geometry(args.src, args.panel, args.curves, root)
    if args.kinds:
        kinds = mast_kinds(args.kinds)
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
