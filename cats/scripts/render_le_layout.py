#!/usr/bin/env python3
"""Render the true JMRI Layout Editor geometry (turnouts + track segments)
from a JMRI panel XML to a PNG.

Unlike the CATS grid render, this uses the real LE coordinates (positionable
point x/y and layoutturnout xa/ya..xd/yd leg endpoints), so it is fully
contiguous and shows every turnout and path exactly as the layout is wired.

Usage:
    python3 cats/scripts/render_le_layout.py jmri/layouts/hart/output/hart_prod.xml out.png
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TARGET_W = 2000
MARGIN = 70
BG = (18, 20, 24)
MAIN = (225, 228, 233)      # mainline track
SIDE = (120, 126, 136)      # non-mainline track
TURN = (95, 205, 255)       # turnout legs
POINT = (255, 190, 60)      # turnout center
ANCHOR = (70, 76, 86)
OSNAME = (150, 230, 160)
TITLE = (255, 255, 255)


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


def render(src: Path, out: Path) -> None:
    root = ET.parse(src).getroot()
    le = root.find("LayoutEditor")

    pp: dict[str, tuple[float, float]] = {}
    for p in le.findall("positionablepoint"):
        pp[p.get("ident")] = (float(p.get("x")), float(p.get("y")))

    legs: dict[tuple[str, str], tuple[float, float]] = {}
    turnouts = []
    for t in le.findall("layoutturnout"):
        ident = t.get("ident")
        cen = (float(t.get("xcen")), float(t.get("ycen")))
        for leg, (ax, ay) in (
            ("TURNOUT_A", ("xa", "ya")),
            ("TURNOUT_B", ("xb", "yb")),
            ("TURNOUT_C", ("xc", "yc")),
            ("TURNOUT_D", ("xd", "yd")),
        ):
            if t.get(ax) is not None and t.get(ay) is not None:
                legs[(ident, leg)] = (float(t.get(ax)), float(t.get(ay)))
        turnouts.append((ident, cen, t.get("blockname") or "", t.get("type") or ""))

    def resolve(name: str, typ: str):
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
            segs.append((a, b, s.get("mainline") == "yes"))

    pts = list(pp.values()) + list(legs.values()) + [c for _, c, _, _ in turnouts]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    scale = (TARGET_W - 2 * MARGIN) / (maxx - minx)
    W = TARGET_W
    H = int((maxy - miny) * scale + 2 * MARGIN + 40)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def X(v: float) -> float:
        return MARGIN + (v - minx) * scale

    def Y(v: float) -> float:
        return MARGIN + 40 + (v - miny) * scale

    f_title = _font(30, bold=True)
    f_lab = _font(13, bold=True)
    d.text((MARGIN, 22),
           f"HART Layout Editor geometry — {len(turnouts)} turnouts, "
           f"{len(segs)} track segments  ({src.name})",
           font=f_title, fill=TITLE)

    for (ax, ay), (bx, by), main in segs:
        d.line([(X(ax), Y(ay)), (X(bx), Y(by))],
               fill=MAIN if main else SIDE, width=5 if main else 3)

    for name, (x, y) in pp.items():
        d.ellipse([X(x) - 2, Y(y) - 2, X(x) + 2, Y(y) + 2], fill=ANCHOR)

    for ident, (cx, cy), block, ttype in turnouts:
        for leg in ("TURNOUT_A", "TURNOUT_B", "TURNOUT_C", "TURNOUT_D"):
            lp = legs.get((ident, leg))
            if lp:
                d.line([(X(cx), Y(cy)), (X(lp[0]), Y(lp[1]))], fill=TURN, width=4)
        d.ellipse([X(cx) - 5, Y(cy) - 5, X(cx) + 5, Y(cy) + 5], fill=POINT)
        short = block.replace("(", "").replace(")", "")
        d.text((X(cx) + 7, Y(cy) - 16), f"{ident}", font=f_lab, fill=TURN)
        if block:
            d.text((X(cx) + 7, Y(cy) + 3), short, font=f_lab, fill=OSNAME)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  ({W}x{H})  turnouts={len(turnouts)} segments={len(segs)} "
          f"anchors={len(pp)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: render_le_layout.py <panel.xml> <out.png>", file=sys.stderr)
        raise SystemExit(2)
    render(Path(sys.argv[1]), Path(sys.argv[2]))
