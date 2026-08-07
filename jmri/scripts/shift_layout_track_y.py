#!/usr/bin/env python3
"""
Shift LayoutEditor track geometry on Y (turnouts, anchors, bezier control points).

Does not move positionablelabel elements (area / DCC labels are added separately
in build_linear4_device_mapping.py).

Usage:
  python3 jmri/scripts/shift_layout_track_y.py panel.xml --delta 61.53
  python3 jmri/scripts/shift_layout_track_y.py panel.xml --align-anchor EB70 --target-y 168.11
  python3 jmri/scripts/shift_layout_track_y.py panel.xml --delta 61.53 --bottom-margin 32
"""
from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET

Y_ATTRS = frozenset({"y", "ya", "yb", "yc", "yd", "ycen"})
GEOMETRY_TAGS = frozenset(
    {
        "tracksegment",
        "layoutturnout",
        "layoutslip",
        "layoutxing",
        "positionablepoint",
        "controlpoint",
        "levelxing",
    }
)


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag or ""
    return tag.split("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _find_layout(root: ET.Element) -> ET.Element | None:
    layout = root.find(".//LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if elem.tag and "LayoutEditor" in elem.tag:
                return elem
    return layout


def _fmt_y(y: float) -> str:
    r = round(y, 2)
    return str(int(r)) if r == int(r) else str(r)


def _is_geometry(elem: ET.Element) -> bool:
    return _local_tag(elem) in GEOMETRY_TAGS


def _collect_y(layout: ET.Element) -> list[float]:
    ys: list[float] = []
    for elem in layout.iter():
        if elem is layout or not _is_geometry(elem):
            continue
        attrs = Y_ATTRS if _local_tag(elem) != "controlpoint" else frozenset({"y"})
        for attr in attrs:
            v = elem.get(attr)
            if v is None:
                continue
            try:
                ys.append(float(v))
            except ValueError:
                pass
    return ys


def shift_track_y(layout: ET.Element, delta: float) -> int:
    """Positive delta moves track down."""
    n = 0
    for elem in layout.iter():
        if elem is layout or not _is_geometry(elem):
            continue
        attrs = Y_ATTRS if _local_tag(elem) != "controlpoint" else frozenset({"y"})
        for attr in attrs:
            v = elem.get(attr)
            if v is None:
                continue
            try:
                elem.set(attr, _fmt_y(float(v) + delta))
                n += 1
            except ValueError:
                pass
    return n


def _anchor_y(layout: ET.Element, ident: str) -> float | None:
    for pp in layout.findall("positionablepoint"):
        if pp.get("ident") == ident:
            try:
                return float(pp.get("y") or 0)
            except ValueError:
                return None
    return None


def fit_panel_height(layout: ET.Element, *, bottom_margin: float) -> int:
    ys = _collect_y(layout)
    if not ys:
        raise SystemExit("No track Y coordinates found")
    new_h = int(math.ceil(max(ys) + bottom_margin))
    for attr in ("height", "panelheight", "windowheight"):
        layout.set(attr, str(new_h))
    return new_h


def main() -> None:
    ap = argparse.ArgumentParser(description="Shift track geometry Y in a panel XML")
    ap.add_argument("input", help="Panel XML (blocked or layout-only)")
    ap.add_argument("output", nargs="?", help="Output path (default: overwrite input)")
    ap.add_argument("--delta", type=float, help="Y shift in pixels (positive = down)")
    ap.add_argument("--align-anchor", metavar="IDENT", help="Anchor ident for --target-y")
    ap.add_argument("--target-y", type=float, help="Target Y for --align-anchor")
    ap.add_argument(
        "--bottom-margin",
        type=float,
        default=32.0,
        help="Set panelheight to max track Y + this margin (default 32)",
    )
    ap.add_argument("--no-resize", action="store_true", help="Do not update panelheight")
    args = ap.parse_args()

    if args.delta is None:
        if not args.align_anchor or args.target_y is None:
            ap.error("Provide --delta or both --align-anchor and --target-y")
        tree = ET.parse(args.input)
        layout = _find_layout(tree.getroot())
        if layout is None:
            raise SystemExit(f"No LayoutEditor in {args.input}")
        current = _anchor_y(layout, args.align_anchor)
        if current is None:
            raise SystemExit(f"Anchor {args.align_anchor!r} not found")
        args.delta = args.target_y - current
        print(f"Align {args.align_anchor}: {current:.2f} → {args.target_y:.2f} (delta {args.delta:.2f})")

    tree = ET.parse(args.input)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.input}")

    n = shift_track_y(layout, args.delta)
    new_h = None
    if not args.no_resize:
        new_h = fit_panel_height(layout, bottom_margin=args.bottom_margin)

    out = args.output or args.input
    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    msg = f"Shifted {n} Y attribute(s) by {args.delta:+.2f} in {out}"
    if new_h is not None:
        msg += f"; panelheight={new_h}"
    print(msg)


if __name__ == "__main__":
    main()
