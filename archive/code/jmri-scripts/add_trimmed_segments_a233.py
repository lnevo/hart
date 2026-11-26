#!/usr/bin/env python3
"""
Add back the track segments that were removed by trim_panel_right_of_a233.py,
but with their length trimmed so they end at x=548.75 (same X as A233).
For each segment that had one endpoint left of 548.75 and one right:
  - Compute (548.75, y) where the segment crosses the vertical line (linear interpolation).
  - Create a new END_BUMPER point at (548.75, y).
  - Add the segment from the left endpoint to this new point (straight segment).
Uses mac_jmri2.xml as the source for segment definitions and point coordinates.
"""
import os
import sys
import copy
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_PATHS = layout_paths()
CUTOFF_X = 548.75
SOURCE_FILE = _PATHS["authoritative"]
PANEL_FILE = os.path.join(_PATHS["working"], "new_panel.xml")

# Segment idents we removed that we want to add back trimmed (must cross x=548.75)
SEGMENTS_TO_TRIM = [
    "F35512-S-0", "F35508-S-0", "F35510-S-0", "F35506-S-0", "F35504-S-0",
    "F35234-S-0", "F35264-S-0", "F35263-S-0",
]


def find_layout(root):
    for elem in root.iter():
        if elem.tag and "LayoutEditor" in (elem.tag or ""):
            return elem
    return None


def get_point_coords(layout):
    """Return dict ident -> (x, y)."""
    coords = {}
    for child in layout:
        tag = (child.tag or "").strip().lower()
        if "positionablepoint" not in tag:
            continue
        ident = child.get("ident")
        x_s, y_s = child.get("x"), child.get("y")
        if ident and x_s and y_s:
            try:
                coords[ident] = (float(x_s), float(y_s))
            except ValueError:
                pass
    return coords


def find_segment(layout, ident):
    for child in layout:
        tag = (child.tag or "").strip().lower()
        if tag == "tracksegment" and (child.get("ident") or "") == ident:
            return child
    return None


def y_at_x(x0, y0, x1, y1, x_target):
    """Linear interpolation: y at x_target on line (x0,y0)-(x1,y1)."""
    if abs(x1 - x0) < 1e-9:
        return (y0 + y1) / 2
    t = (x_target - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def main():
    panel_path = PANEL_FILE if len(sys.argv) < 2 else sys.argv[1]
    source_path = sys.argv[2] if len(sys.argv) > 2 else SOURCE_FILE

    source_tree = ET.parse(source_path)
    source_layout = find_layout(source_tree.getroot())
    if source_layout is None:
        print(f"LayoutEditor not found in {source_path}")
        sys.exit(1)
    source_coords = get_point_coords(source_layout)

    panel_tree = ET.parse(panel_path)
    panel_layout = find_layout(panel_tree.getroot())
    if panel_layout is None:
        print(f"LayoutEditor not found in {panel_path}")
        sys.exit(1)
    panel_coords = get_point_coords(panel_layout)

    # Build list of (segment_elem, left_ident, right_ident, y_cut) for segments that cross CUTOFF_X
    to_add = []
    for seg_ident in SEGMENTS_TO_TRIM:
        seg = find_segment(source_layout, seg_ident)
        if seg is None:
            continue
        c1 = seg.get("connect1name") or ""
        c2 = seg.get("connect2name") or ""
        if not c1 or not c2 or c1 not in source_coords or c2 not in source_coords:
            continue
        x1, y1 = source_coords[c1]
        x2, y2 = source_coords[c2]
        left = (c1, x1, y1) if x1 <= CUTOFF_X else (c2, x2, y2)
        right = (c2, x2, y2) if x1 <= CUTOFF_X else (c1, x1, y1)
        left_ident, xl, yl = left
        right_ident, xr, yr = right
        if xl > CUTOFF_X or xr <= CUTOFF_X:
            continue  # segment doesn't cross the line
        y_cut = y_at_x(xl, yl, xr, yr, CUTOFF_X)
        to_add.append((seg, seg_ident, left_ident, y_cut))

    # Which left endpoints exist in panel
    panel_idents = set()
    for child in panel_layout:
        tag = (child.tag or "").strip().lower()
        if "positionablepoint" in tag:
            panel_idents.add(child.get("ident") or "")

    new_segments = []
    new_points = []
    for seg, seg_ident, left_ident, y_cut in to_add:
        if left_ident not in panel_idents and left_ident not in panel_coords:
            continue
        cut_ident = f"CUT-{seg_ident}"
        if cut_ident in panel_idents:
            continue
        panel_idents.add(cut_ident)

        pt = ET.Element("positionablepoint")
        pt.set("ident", cut_ident)
        pt.set("type", "END_BUMPER")
        pt.set("x", str(CUTOFF_X))
        pt.set("y", str(round(y_cut, 6)))
        pt.set("connect1name", seg_ident)
        pt.set("eastboundsensor", f"NX {cut_ident}")
        pt.set("class", "jmri.jmrit.display.layoutEditor.configurexml.PositionablePointXml")

        new_seg = ET.Element("tracksegment")
        new_seg.set("ident", seg_ident)
        new_seg.set("blockname", seg.get("blockname") or "")
        new_seg.set("connect1name", left_ident)
        new_seg.set("type1", "POS_POINT")
        new_seg.set("connect2name", cut_ident)
        new_seg.set("type2", "POS_POINT")
        new_seg.set("dashed", seg.get("dashed") or "no")
        new_seg.set("mainline", seg.get("mainline") or "yes")
        new_seg.set("hidden", seg.get("hidden") or "no")
        new_seg.set("class", "jmri.jmrit.display.layoutEditor.configurexml.TrackSegmentXml")

        new_segments.append(new_seg)
        new_points.append(pt)

    # JMRI expects all track segments then all positionable points: insert segments after last tracksegment, points after last positionablepoint
    last_track = -1
    last_pt = -1
    for i, child in enumerate(panel_layout):
        tag = (child.tag or "").strip().lower()
        if tag == "tracksegment":
            last_track = i
        if "positionablepoint" in tag:
            last_pt = i
    insert_seg_at = last_track + 1
    insert_pt_at = last_pt + 1 if last_pt >= 0 else len(panel_layout)
    for new_seg in new_segments:
        panel_layout.insert(insert_seg_at, new_seg)
        insert_seg_at += 1
    for pt in new_points:
        panel_layout.insert(insert_pt_at, pt)
        insert_pt_at += 1
    added = len(new_segments)

    panel_tree.write(
        panel_path,
        encoding="unicode",
        default_namespace=None,
        method="xml",
        xml_declaration=True,
    )
    print(f"Added {added} trimmed segments (and {added} CUT endpoint bumpers) to {panel_path}")


if __name__ == "__main__":
    main()
