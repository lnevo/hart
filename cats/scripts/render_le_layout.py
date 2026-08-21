#!/usr/bin/env python3
"""Render the true JMRI Layout Editor geometry (turnouts + track segments)
from a JMRI panel XML to PNG(s).

Uses real LE coordinates (positionablepoint x/y and layoutturnout
xa/ya..xd/yd leg endpoints), so paths are fully contiguous and every turnout
is shown exactly as wired. Supports a whole-layout render and a set of
professional, zoomed control-point views.

Usage:
    # whole layout
    python3 cats/scripts/render_le_layout.py <panel.xml> <out.png>
    # full professional view set into a directory
    python3 cats/scripts/render_le_layout.py <panel.xml> --all-views <out_dir>
    # single custom window
    python3 cats/scripts/render_le_layout.py <panel.xml> <out.png> \
        --title "West Yard" --xwin 440 630
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (18, 20, 24)
MAIN = (228, 231, 236)      # mainline track
SIDE = (128, 134, 144)      # non-mainline (yard/siding) track
THRU = (232, 236, 242)      # turnout continuing legs (A/B)
DIVERGE = (95, 205, 255)    # turnout diverging legs (C/D)
POINT = (255, 190, 60)      # turnout center / control point
SIGNAL = (255, 105, 125)    # signal mast icon / facing marker
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
                            "OS 116-119 (Switch 116/117/118/119) + Yard T1-T13", 435, 640),
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


def load_geometry(src: Path):
    root = ET.parse(src).getroot()
    le = root.find("LayoutEditor")
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
        a = resolve(s.get("connect1name"), s.get("type1"))
        b = resolve(s.get("connect2name"), s.get("type2"))
        if a and b:
            segs.append((a, b, s.get("mainline") == "yes", s.get("blockname") or ""))
    signals = []
    for icon in le.findall("signalmasticon"):
        try:
            signals.append({
                "name": icon.get("signalmast") or "",
                "x": float(icon.get("x") or "0"),
                "y": float(icon.get("y") or "0"),
                "degrees": int(float(icon.get("degrees") or "0")) % 360,
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
    xmin=None, xmax=None
):
    pad = 34
    if xmin is None:
        allx = [p[0] for p in pp.values()] + [t["cen"][0] for t in turnouts]
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
    for station in vstations:
        pts.append((station["x"], station["y"]))
    if not pts:
        return
    bx0 = min(p[0] for p in pts) - pad
    bx1 = max(p[0] for p in pts) + pad
    by0 = min(p[1] for p in pts) - pad
    by1 = max(p[1] for p in pts) + pad

    scale = (target_w - 2 * pad) / (bx1 - bx0)
    scale = max(scale, 1.0)
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
    for bl, mids in blk_pts.items():
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

    # turnouts (control points) — draw legs + points first
    f_os = _font(19, bold=True)
    f_sub = _font(13)
    f_id = _font(12)
    for t in vturn:
        cx, cy = t["cen"]
        for leg in ("TURNOUT_A", "TURNOUT_B", "TURNOUT_C", "TURNOUT_D"):
            lp = legs.get((t["ident"], leg))
            if lp:
                col = THRU if leg in ("TURNOUT_A", "TURNOUT_B") else DIVERGE
                d.line([(X(cx), Y(cy)), (X(lp[0]), Y(lp[1]))], fill=col, width=5)
        d.ellipse([X(cx) - 6, Y(cy) - 6, X(cx) + 6, Y(cy) + 6], fill=POINT)

    # labels with simple anti-collision (stagger above/below the point)
    placed_lbl = []  # (px, py) top-left of a 3-line label block (~52px tall)
    for t in sorted(vturn, key=lambda tt: tt["cen"][0]):
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

    # Display-only signal markers. The stem points in the mast's facing
    # direction (0=north, 90=east, 180=south, 270=west).
    f_sig = _font(10)
    vectors = {0: (0, -1), 90: (1, 0), 180: (0, 1), 270: (-1, 0)}
    for signal in vsignals:
        px, py = X(signal["x"]), Y(signal["y"])
        dx, dy = vectors.get(signal["degrees"], (0, -1))
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=SIGNAL)
        d.line([(px, py), (px + 18 * dx, py + 18 * dy)], fill=SIGNAL, width=4)
        tx = px + (8 if dx >= 0 else -8)
        ty = py + (9 if dy >= 0 else -20)
        anchor = "la" if dx >= 0 else "ra"
        d.text((tx, ty), signal["name"], font=f_sig, fill=SIGNAL, anchor=anchor)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path, nargs="?")
    ap.add_argument("--all-views", type=Path, metavar="OUTDIR")
    ap.add_argument("--title", default="HART Layout")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--xwin", type=float, nargs=2, metavar=("XMIN", "XMAX"))
    args = ap.parse_args()

    pp, legs, turnouts, segs, signals, stations = load_geometry(args.src)

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
        args.out, args.title, args.subtitle, xmin, xmax
    )


if __name__ == "__main__":
    main()
