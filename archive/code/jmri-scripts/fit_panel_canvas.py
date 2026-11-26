#!/usr/bin/env python3
"""
Fit LayoutEditor canvas (panelwidth/panelheight) to track geometry without moving coordinates.

Optionally align windowwidth/windowheight to the panel size (drops extra scroll chrome).

Usage:
  python3 fit_panel_canvas.py panel.xml
  python3 fit_panel_canvas.py panel.xml --width 1254 --height 319
  python3 fit_panel_canvas.py panel.xml --margin-x 50 --margin-y 28
"""
from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET

COORD_ATTRS = {
    "x": "x",
    "y": "y",
    "xa": "x",
    "ya": "y",
    "xb": "x",
    "yb": "y",
    "xc": "x",
    "yc": "y",
    "xd": "x",
    "yd": "y",
    "xcen": "x",
    "ycen": "y",
}


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag or ""
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _find_layout(root: ET.Element) -> ET.Element | None:
    layout = root.find(".//LayoutEditor")
    if layout is None:
        layout = root.find(".//{*}LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if elem.tag and "LayoutEditor" in elem.tag:
                return elem
    return layout


def _is_geometry(elem: ET.Element) -> bool:
    t = _local_tag(elem)
    return t in (
        "tracksegment",
        "layoutturnout",
        "layoutslip",
        "layoutxing",
        "positionablepoint",
        "controlpoint",
        "levelxing",
    )


def _bbox(layout: ET.Element) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for elem in layout.iter():
        if elem is layout or not _is_geometry(elem):
            continue
        for attr, axis in COORD_ATTRS.items():
            v = elem.get(attr)
            if v is None:
                continue
            try:
                val = float(v)
            except ValueError:
                continue
            if axis == "x":
                xs.append(val)
            else:
                ys.append(val)
    if not xs or not ys:
        raise SystemExit("No track geometry coordinates found")
    return min(xs), min(ys), max(xs), max(ys)


def fit_canvas(
    layout: ET.Element,
    *,
    width: int | None = None,
    height: int | None = None,
    margin_left: float = 0.0,
    margin_right: float = 50.0,
    margin_top: float = 0.0,
    margin_bottom: float = 28.0,
    match_window: bool = True,
) -> tuple[int, int, float, float, float, float]:
    xmin, ymin, xmax, ymax = _bbox(layout)
    new_w = width if width is not None else int(math.ceil(xmax - xmin + margin_left + margin_right))
    new_h = height if height is not None else int(math.ceil(ymax - ymin + margin_top + margin_bottom))
    layout.set("panelwidth", str(new_w))
    layout.set("panelheight", str(new_h))
    if match_window:
        layout.set("windowwidth", str(new_w))
        layout.set("windowheight", str(new_h))
    # Legacy attrs some panels still read
    layout.set("width", str(new_w))
    layout.set("height", str(new_h))
    return new_w, new_h, xmin, ymin, xmax, ymax


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit LayoutEditor canvas to track bbox.")
    ap.add_argument("input", help="Panel XML path")
    ap.add_argument("output", nargs="?", help="Output path (default: overwrite)")
    ap.add_argument("--width", type=int, help="Force panel width")
    ap.add_argument("--height", type=int, help="Force panel height")
    ap.add_argument("--margin-left", type=float, default=0.0)
    ap.add_argument("--margin-right", type=float, default=50.0)
    ap.add_argument("--margin-top", type=float, default=0.0)
    ap.add_argument("--margin-bottom", type=float, default=28.0)
    ap.add_argument(
        "--keep-window",
        action="store_true",
        help="Do not change windowwidth/windowheight (only panel size)",
    )
    args = ap.parse_args()
    out = args.output or args.input

    tree = ET.parse(args.input)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.input}")

    new_w, new_h, xmin, ymin, xmax, ymax = fit_canvas(
        layout,
        width=args.width,
        height=args.height,
        margin_left=args.margin_left,
        margin_right=args.margin_right,
        margin_top=args.margin_top,
        margin_bottom=args.margin_bottom,
        match_window=not args.keep_window,
    )
    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {out}")
    print(f"  Track bbox: x {xmin:.1f}–{xmax:.1f}, y {ymin:.1f}–{ymax:.1f}")
    print(f"  panelwidth/panelheight: {new_w} x {new_h}")
    if not args.keep_window:
        print(f"  windowwidth/windowheight matched panel")


if __name__ == "__main__":
    main()
