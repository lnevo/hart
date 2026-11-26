#!/usr/bin/env python3
"""
Polish LayoutEditor geometry: straighten selected segments, align anchor Y values, round coords.

Usage:
  python3 polish_layout_geometry.py panel.xml
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET

COORD_ATTRS = frozenset(
    {"x", "y", "xa", "ya", "xb", "yb", "xc", "yc", "xd", "yd", "xcen", "ycen"}
)

# JMRI schema: integers on LayoutEditor panel/window attrs (not geometry floats)
LAYOUTEDITOR_INT_ATTRS = frozenset(
    {
        "x",
        "y",
        "height",
        "width",
        "windowheight",
        "windowwidth",
        "panelheight",
        "panelwidth",
        "gridSize",
        "gridSize2nd",
        "redBackground",
        "greenBackground",
        "blueBackground",
        "mainlinetrackwidth",
        "sidetrackwidth",
        "turnoutcirclesize",
    }
)

GEOMETRY_TAGS = frozenset(
    {
        "positionablepoint",
        "tracksegment",
        "layoutturnout",
        "levelxing",
        "layoutslip",
        "layoutturntable",
        "layoutshape",
        "controlpoint",
    }
)

# Segments to force straight (remove bezier/arc and control points)
STRAIGHTEN_SEGMENTS = frozenset({"F4-S-0", "F25-S-0"})

# Anchors on the upper main line — share one Y after polish
ALIGN_Y_GROUPS = [
    ("upper_main", ("A13", "A35", "A42"), None),  # None = use median Y
]


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


def _format_coord(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if places == 0 or rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _fix_layouteditor_integers(layout_elem: ET.Element) -> int:
    n = 0
    for attr in LAYOUTEDITOR_INT_ATTRS:
        v = layout_elem.get(attr)
        if v is None:
            continue
        try:
            layout_elem.set(attr, str(int(round(float(v)))))
            n += 1
        except ValueError:
            pass
    return n


def _round_coords(layout: ET.Element, places: int = 2) -> int:
    n = 0
    for elem in layout.iter():
        tag = _local_tag(elem)
        if tag == "layouteditor":
            continue
        if tag not in GEOMETRY_TAGS and tag != "controlpoint":
            continue
        for attr in COORD_ATTRS:
            v = elem.get(attr)
            if v is None:
                continue
            try:
                elem.set(attr, _format_coord(float(v), places))
                n += 1
            except ValueError:
                pass
    return n


def _straighten_segment(seg: ET.Element) -> None:
    for key in list(seg.attrib):
        if key in ("bezier", "arc", "circle", "flip", "angle", "hideConLines"):
            del seg.attrib[key]
    for ch in list(seg):
        if _local_tag(ch) == "controlpoints":
            seg.remove(ch)


def _set_anchor_y(layout: ET.Element, ident: str, y: float) -> bool:
    for elem in layout.iter():
        if _local_tag(elem) != "positionablepoint":
            continue
        if elem.get("ident") != ident:
            continue
        elem.set("y", _format_coord(y, 2))
        return True
    return False


def _anchor_y(layout: ET.Element, ident: str) -> float | None:
    for elem in layout.iter():
        if _local_tag(elem) == "positionablepoint" and elem.get("ident") == ident:
            v = elem.get("y")
            if v is not None:
                return float(v)
    return None


def polish(layout: ET.Element) -> list[str]:
    log: list[str] = []
    for ident in STRAIGHTEN_SEGMENTS:
        for seg in layout.iter():
            if _local_tag(seg) == "tracksegment" and seg.get("ident") == ident:
                _straighten_segment(seg)
                log.append(f"  Straightened {ident} (removed bezier/controls)")
                break

    for _name, idents, fixed_y in ALIGN_Y_GROUPS:
        ys = []
        for ident in idents:
            y = _anchor_y(layout, ident)
            if y is not None:
                ys.append(y)
        if not ys:
            continue
        target = fixed_y if fixed_y is not None else round(sum(ys) / len(ys), 2)
        for ident in idents:
            if _set_anchor_y(layout, ident, target):
                log.append(f"  Aligned {ident} y={target}")
        # F27: optional straighten after anchor moves
        for seg in layout.iter():
            if _local_tag(seg) == "tracksegment" and seg.get("ident") == "F27-S-0":
                _straighten_segment(seg)
                log.append("  Straightened F27-S-0")

    n_int = _fix_layouteditor_integers(layout)
    if n_int:
        log.append(f"  Normalized {n_int} LayoutEditor integer attribute(s)")
    n = _round_coords(layout)
    log.append(f"  Rounded {n} geometry coordinate attribute(s) to 2 decimals")
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description="Polish layout segment/anchor geometry.")
    ap.add_argument("panel", help="Panel XML path")
    ap.add_argument("-o", "--output", help="Output path (default: overwrite)")
    args = ap.parse_args()
    out = args.output or args.panel

    tree = ET.parse(args.panel)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.panel}")

    log = polish(layout)
    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {out}")
    for line in log:
        print(line)


if __name__ == "__main__":
    main()
