#!/usr/bin/env python3
"""
Add the 5 turnouts (TOR35284, TOR35228, TOR35232, TOR35230, TOR35283) that had track removed,
plus a straight horizontal track segment from each turnout's open leg to x=548.75 (A233 x).
Uses mac_jmri2.xml for turnout and segment definitions.
"""
import os
import sys
import xml.etree.ElementTree as ET
import copy

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_PATHS = layout_paths()
CUTOFF_X = 548.75
PANEL = os.path.join(_PATHS["working"], "new_panel.xml")
SOURCE = _PATHS["authoritative"]

# Turnout ident -> (segment_ident, type1 e.g. TURNOUT_C, blockname, y at cut line)
TURNOUT_STUBS = {
    "TOR35232": ("T-ER-TOR35232", "TURNOUT_C", "Block_131", 408.22),   # was to A226
    "TOR35228": ("T-ER-TOR35228", "TURNOUT_C", "Block_125", 391.65),   # was to A232
    "TOR35230": ("T-ER-TOR35230", "TURNOUT_C", "Block_132", 399.94),   # was to A231
    "TOR35284": ("T-EL-TOR35284", "TURNOUT_B", "Block_129", 383.31),  # was to A227
    "TOR35283": ("T-I-TOR35283",  "TURNOUT_A", "Block_122", 374.92),   # was to A234
}


def find_layout(root):
    for e in root.iter():
        if e.tag and "LayoutEditor" in (e.tag or ""):
            return e
    return None


def find_layoutturnout(layout, ident):
    for c in layout:
        if (c.tag or "").strip().lower().startswith("layoutturnout") and (c.get("ident") or "") == ident:
            return c
    return None


def main():
    panel_path = sys.argv[1] if len(sys.argv) > 1 else PANEL
    source_path = sys.argv[2] if len(sys.argv) > 2 else SOURCE

    src = ET.parse(source_path).getroot()
    src_layout = find_layout(src)
    if src_layout is None:
        print("Source LayoutEditor not found")
        sys.exit(1)

    tree = ET.parse(panel_path)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("Panel LayoutEditor not found")
        sys.exit(1)

    # Collect existing idents in panel
    panel_seg_idents = set()
    panel_point_idents = set()
    for c in layout:
        tag = (c.tag or "").strip().lower()
        ident = c.get("ident") or ""
        if tag == "tracksegment":
            panel_seg_idents.add(ident)
        if "positionablepoint" in tag:
            panel_point_idents.add(ident)

    last_turnout_idx = -1
    last_segment_idx = -1
    last_point_idx = -1
    for i, c in enumerate(layout):
        tag = (c.tag or "").strip().lower()
        if "layoutturnout" in tag:
            last_turnout_idx = i
        if tag == "tracksegment":
            last_segment_idx = i
        if "positionablepoint" in tag:
            last_point_idx = i

    added_turnouts = []
    added_segments = []
    added_points = []

    for to_ident, (seg_ident, type1, blockname, y_cut) in TURNOUT_STUBS.items():
        if to_ident in {c.get("ident") or "" for c in layout if (c.tag or "").strip().lower().startswith("layoutturnout")}:
            continue
        if seg_ident in panel_seg_idents:
            continue
        cut_ident = f"CUT-{to_ident}"
        if cut_ident in panel_point_idents:
            continue

        # Copy layoutturnout from source
        to_elem = find_layoutturnout(src_layout, to_ident)
        if to_elem is None:
            continue
        to_copy = copy.deepcopy(to_elem)
        layout.insert(last_turnout_idx + 1, to_copy)
        last_turnout_idx += 1
        added_turnouts.append(to_ident)

        # New END_BUMPER at (CUTOFF_X, y_cut)
        pt = ET.Element("positionablepoint")
        pt.set("ident", cut_ident)
        pt.set("type", "END_BUMPER")
        pt.set("x", str(CUTOFF_X))
        pt.set("y", str(y_cut))
        pt.set("connect1name", seg_ident)
        pt.set("class", "jmri.jmrit.display.layoutEditor.configurexml.PositionablePointXml")

        # Segment: turnout leg -> CUT point (straight horizontal)
        seg = ET.Element("tracksegment")
        seg.set("ident", seg_ident)
        seg.set("blockname", blockname)
        seg.set("connect1name", to_ident)
        seg.set("type1", type1)
        seg.set("connect2name", cut_ident)
        seg.set("type2", "POS_POINT")
        seg.set("dashed", "no")
        seg.set("mainline", "yes")
        seg.set("hidden", "no")
        seg.set("class", "jmri.jmrit.display.layoutEditor.configurexml.TrackSegmentXml")

        layout.insert(last_segment_idx + 1, seg)
        last_segment_idx += 1
        layout.insert(last_point_idx + 1, pt)
        last_point_idx += 1
        added_segments.append(seg_ident)
        added_points.append(cut_ident)
        panel_seg_idents.add(seg_ident)
        panel_point_idents.add(cut_ident)

    tree.write(panel_path, encoding="unicode", default_namespace=None, method="xml", xml_declaration=True)
    print(f"Added {len(added_turnouts)} layout turnouts, {len(added_segments)} segments, {len(added_points)} end bumpers at x={CUTOFF_X}")


if __name__ == "__main__":
    main()
