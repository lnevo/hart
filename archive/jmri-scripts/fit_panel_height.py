#!/usr/bin/env python3
"""
Adjust LayoutEditor panel height to track geometry.

Default (--height-only): set panelheight/windowheight/height from lowest track Y
plus bottom margin; does not move geometry.

Without --height-only: also rebase Y coordinates (legacy behavior; shifts layout up).

Usage:
  python3 fit_panel_height.py panel.xml [--height-only] [--bottom 32]
"""
from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET

Y_ATTRS = frozenset({"y", "ya", "yb", "yc", "yd", "ycen"})


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


def _collect_y(layout: ET.Element) -> list[float]:
    ys: list[float] = []
    for elem in layout.iter():
        if elem is layout or not _is_geometry(elem):
            continue
        for attr in Y_ATTRS:
            v = elem.get(attr)
            if v is None:
                continue
            try:
                ys.append(float(v))
            except ValueError:
                pass
    return ys


def _shift_y(layout: ET.Element, delta: float) -> int:
    n = 0
    for elem in layout.iter():
        if elem is layout or not _is_geometry(elem):
            continue
        for attr in Y_ATTRS:
            v = elem.get(attr)
            if v is None:
                continue
            try:
                elem.set(attr, str(round(float(v) - delta, 3)))
                n += 1
            except ValueError:
                pass
    return n


def fit_height(
    layout: ET.Element,
    top_margin: float = 24.0,
    bottom_margin: float = 32.0,
    height_only: bool = False,
) -> tuple[int, float, float]:
    ys = _collect_y(layout)
    if not ys:
        raise SystemExit("No Y coordinates found in layout")
    ymin, ymax = min(ys), max(ys)
    if height_only:
        new_h = int(math.ceil(ymax + bottom_margin))
    else:
        shift = ymin - top_margin
        if abs(shift) > 1e-6:
            _shift_y(layout, shift)
            ymin, ymax = ymin - shift, ymax - shift
        new_h = int(math.ceil(ymax - ymin + top_margin + bottom_margin))
    for attr in ("height", "panelheight", "windowheight"):
        layout.set(attr, str(new_h))
    return new_h, ymin, ymax


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit LayoutEditor panel height to track geometry.")
    ap.add_argument("input", help="Panel XML path")
    ap.add_argument("output", nargs="?", help="Output path (default: overwrite input)")
    ap.add_argument(
        "--height-only",
        action="store_true",
        help="Only reduce panelheight; do not shift track Y coordinates",
    )
    ap.add_argument("--top", type=float, default=24.0, help="Top margin when rebasing Y (non-height-only)")
    ap.add_argument("--bottom", type=float, default=32.0, help="Bottom margin below lowest track Y")
    args = ap.parse_args()
    out = args.output or args.input

    tree = ET.parse(args.input)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.input}")

    new_h, ymin, ymax = fit_height(
        layout, args.top, args.bottom, height_only=args.height_only
    )
    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {out}")
    mode = "height-only" if args.height_only else "rebase+height"
    print(f"  Mode: {mode}")
    print(f"  Track Y range: ~{ymin:.1f}–{ymax:.1f}")
    print(f"  panelheight/windowheight: {new_h}")


if __name__ == "__main__":
    main()
