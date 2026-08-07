#!/usr/bin/env python3
"""
Create a new panel from mac_jmri2.xml with 90° and 180° circle arc segments
converted to hexagonal curves (straight segments approximating the arc).
- 90° arc → 2 straight segments (1 intermediate point at 45° along arc)
- 180° arc → 3 straight segments (2 intermediate points at 60°, 120°)
"""
import os
import sys
import xml.etree.ElementTree as ET
import math
import shutil

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_PATHS = layout_paths()
SOURCE = _PATHS["authoritative"]
OUTPUT = os.path.join(_PATHS["working"], "mac_jmri2_hex.xml")
HEX_ANGLES_90 = [45]   # degrees along arc for intermediate points (90° total)
HEX_ANGLES_180 = [60, 120]  # for 180° arc


def find_layout(root):
    for e in root.iter():
        if e.tag and "LayoutEditor" in (e.tag or ""):
            return e
    return None


def get_point_coords(layout):
    """Return dict ident -> (x, y) for all positionable points (ANCHOR, etc.)."""
    coords = {}
    for c in layout:
        tag = (c.tag or "").strip().lower()
        if "positionablepoint" not in tag:
            continue
        ident = c.get("ident")
        x_s = c.get("x")
        y_s = c.get("y")
        if ident and x_s is not None and y_s is not None:
            try:
                coords[ident] = (float(x_s), float(y_s))
            except ValueError:
                pass
    return coords


def arc_center_radius(x1, y1, x2, y2, angle_deg, flip):
    """Given chord P1-P2 and subtended angle (90 or 180), return (cx, cy, R)."""
    dx = x2 - x1
    dy = y2 - y1
    c = math.hypot(dx, dy)
    if c < 1e-6:
        return (x1, y1), 0.0
    theta = math.radians(angle_deg)
    half = theta / 2
    R = c / (2 * math.sin(half))
    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2
    # perpendicular unit vector (right of chord direction)
    perp_x = -dy / c
    perp_y = dx / c
    # distance from midpoint to center
    m = R * math.cos(half)
    sign = -1 if (flip and flip.lower() == "yes") else 1
    cx = mx + sign * perp_x * m
    cy = my + sign * perp_y * m
    return (cx, cy), R


def points_on_arc(cx, cy, R, x1, y1, angle_deg, steps_deg):
    """Yield (x, y) for start point, each step along the arc, then end point."""
    alpha = math.atan2(y1 - cy, x1 - cx)
    yield (x1, y1)
    for step in steps_deg:
        beta = alpha + math.radians(step)
        yield (cx + R * math.cos(beta), cy + R * math.sin(beta))
    # end point
    beta_end = alpha + math.radians(angle_deg)
    yield (cx + R * math.cos(beta_end), cy + R * math.sin(beta_end))


def main():
    src_path = sys.argv[1] if len(sys.argv) > 1 else SOURCE
    out_path = sys.argv[2] if len(sys.argv) > 2 else OUTPUT

    shutil.copy2(src_path, out_path)
    tree = ET.parse(out_path)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("LayoutEditor not found")
        sys.exit(1)

    coords = get_point_coords(layout)
    # Collect segment and point lists so we can reorder after edits
    segments = [c for c in layout if (c.tag or "").strip().lower() == "tracksegment"]
    points = [c for c in layout if "positionablepoint" in (c.tag or "").strip().lower()]

    arcs_done = []
    new_points = []
    arc_to_new_segments = {}  # arc element -> list of new segment elements
    arc_segments_to_remove = []

    for seg in segments:
        if seg.get("arc") != "yes" or seg.get("circle") != "yes":
            continue
        try:
            angle = float(seg.get("angle") or 0)
        except ValueError:
            continue
        if angle != 90.0 and angle != 180.0:
            continue
        ident = seg.get("ident")
        c1 = seg.get("connect1name")
        c2 = seg.get("connect2name")
        if c1 not in coords or c2 not in coords:
            continue
        x1, y1 = coords[c1]
        x2, y2 = coords[c2]
        flip = seg.get("flip") or "no"
        (cx, cy), R = arc_center_radius(x1, y1, x2, y2, angle, flip)
        if R < 1e-6:
            continue

        if angle == 90.0:
            steps = HEX_ANGLES_90
        else:
            steps = HEX_ANGLES_180

        pts = list(points_on_arc(cx, cy, R, x1, y1, angle, steps))
        # pts[0] = P1, pts[1..n-1] = intermediates, pts[-1] = P2
        n = len(pts)
        if n < 2:
            continue

        blockname = seg.get("blockname") or ""
        dashed = seg.get("dashed") or "no"
        mainline = seg.get("mainline") or "yes"
        hidden = seg.get("hidden") or "no"
        seg_class = seg.get("class") or "jmri.jmrit.display.layoutEditor.configurexml.TrackSegmentXml"

        new_seg_idents = [f"{ident}-H{i}" for i in range(n - 1)]
        intermediate_idents = [f"HEX-{ident}-{i}" for i in range(1, n - 1)]  # n-2 intermediates

        for i in range(n - 1):
            seg_el = ET.Element("tracksegment")
            seg_el.set("ident", new_seg_idents[i])
            seg_el.set("blockname", blockname)
            seg_el.set("connect1name", c1 if i == 0 else intermediate_idents[i - 1])
            seg_el.set("type1", "POS_POINT")
            seg_el.set("connect2name", intermediate_idents[i] if i < n - 2 else c2)
            seg_el.set("type2", "POS_POINT")
            seg_el.set("dashed", dashed)
            seg_el.set("mainline", mainline)
            seg_el.set("hidden", hidden)
            seg_el.set("hideConLines", "no")
            seg_el.set("class", seg_class)
            arc_to_new_segments.setdefault(seg, []).append(seg_el)

        for idx, (px, py) in enumerate(pts[1:-1]):
            pt_el = ET.Element("positionablepoint")
            pt_el.set("ident", intermediate_idents[idx])
            pt_el.set("type", "ANCHOR")
            pt_el.set("x", f"{px:.6g}")
            pt_el.set("y", f"{py:.6g}")
            pt_el.set("connect1name", new_seg_idents[idx])
            pt_el.set("connect2name", new_seg_idents[idx + 1])
            pt_el.set("class", "jmri.jmrit.display.layoutEditor.configurexml.PositionablePointXml")
            new_points.append(pt_el)
            coords[intermediate_idents[idx]] = (px, py)

        # Update endpoint P1: replace arc ident with first new segment
        for pt_el in points:
            if pt_el.get("ident") != c1:
                continue
            c1name = pt_el.get("connect1name")
            c2name = pt_el.get("connect2name")
            if c1name == ident:
                pt_el.set("connect1name", new_seg_idents[0])
            if c2name == ident:
                pt_el.set("connect2name", new_seg_idents[0])
            break
        for pt_el in points:
            if pt_el.get("ident") != c2:
                continue
            c1name = pt_el.get("connect1name")
            c2name = pt_el.get("connect2name")
            if c1name == ident:
                pt_el.set("connect1name", new_seg_idents[-1])
            if c2name == ident:
                pt_el.set("connect2name", new_seg_idents[-1])
            break

        arc_segments_to_remove.append(seg)
        arcs_done.append(ident)

    # Remove arc segments and insert new straight segments in their place
    for seg in arc_segments_to_remove:
        idx = list(layout).index(seg)
        layout.remove(seg)
        new_els = arc_to_new_segments.get(seg, [])
        for i, el in enumerate(new_els):
            layout.insert(idx + i, el)
    # Append new positionable points (after all segments, before or among points - JMRI wants segments then points)
    for pt_el in new_points:
        layout.append(pt_el)

    tree.write(out_path, encoding="unicode", default_namespace=None, method="xml", xml_declaration=True)
    # Restore original-style declaration and xml-stylesheet if missing
    with open(out_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if lines and "xml-stylesheet" not in "".join(lines[:3]):
        decl = lines[0]
        if "encoding=" in decl and "UTF-8" not in decl.upper():
            lines[0] = '<?xml version="1.0" encoding="UTF-8"?>\n'
        if "xml-stylesheet" not in "".join(lines[:3]):
            lines.insert(1, '<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n')
        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    print(f"Converted {len(arcs_done)} arc(s) to hexagon curves in {out_path}")
    print("Arcs:", ", ".join(arcs_done[:10]) + ("..." if len(arcs_done) > 10 else ""))


if __name__ == "__main__":
    main()
