#!/usr/bin/env python3
"""
Build an isolated track schematic panel by SUBSETTING the full layout.
Keeps only the 7 turnouts (TOL35427, TOL35312, TOL35299, TOR35239, TOL35240,
TOL35242, TOL35244) and all track segments and positionable points that
connect them. Everything else in the LayoutEditor is removed. Sensors, turnouts,
blocks, layoutblocks stay unchanged so the panel references the same elements.

Usage: python3 build_schematic_panel.py [source.xml] [new_panel.xml]
Default: mac_jmri_blocked.xml -> new_panel.xml
"""
import copy
import os
import sys
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_PATHS = layout_paths()
DEFAULT_SOURCE = _PATHS["output"]
DEFAULT_OUTPUT = os.path.join(_PATHS["working"], "new_panel.xml")

# Turnouts to include (section we want to keep)
KEEP_TURNOUTS = {
    "TOL35427", "TOL35312", "TOL35299",
    "TOR35239", "TOL35240", "TOL35242", "TOL35244",
}


def ns(tag):
    return tag.split("}")[-1] if "}" in str(tag) else tag


def find_layout(root):
    for c in root:
        if "LayoutEditor" in ns(c.tag):
            return c
    return None


def get_turnout_idents(layout):
    """All layout turnout idents in the layout."""
    out = set()
    for elem in layout.iter():
        tag = ns(elem.tag) if hasattr(elem, "tag") else ""
        if tag != "layoutturnout":
            continue
        ident = elem.get("ident") or elem.get("turnoutname")
        if ident:
            out.add(ident)
    return out


def compute_keep_sets(layout):
    """
    From the full layout, compute which layoutturnouts, tracksegments, and
    positionablepoints to keep so we have a connected subgraph containing
    exactly our 7 turnouts and all track/points that connect them. We never
    keep a segment that references a turnout we're removing (no dangling refs).
    """
    all_turnouts = get_turnout_idents(layout)
    seg_to_nodes = {}  # segment ident -> (connect1name, connect2name)
    for elem in layout.iter():
        tag = ns(elem.tag) if hasattr(elem, "tag") else ""
        if tag != "tracksegment":
            continue
        ident = elem.get("ident")
        if not ident:
            continue
        c1 = elem.get("connect1name") or ""
        c2 = elem.get("connect2name") or ""
        seg_to_nodes[ident] = (c1, c2)

    keep_turnouts = set(KEEP_TURNOUTS)
    keep_points = set()
    keep_segments = set()

    # Only keep segments whose BOTH endpoints are in (keep_turnouts U keep_points).
    # Never keep a segment that connects to a turnout we're removing (no dangling refs).
    # Other endpoint is OK if it's kept, or if it's a point (we'll add it); not OK if it's a removed turnout.
    def other_end_is_ok(other):
        if not other:
            return True
        if other in keep_turnouts or other in keep_points:
            return True
        if other in all_turnouts:
            return False  # turnout we're not keeping
        return True  # assume it's a point

    changed = True
    while changed:
        changed = False
        for seg_ident, (c1, c2) in seg_to_nodes.items():
            if seg_ident in keep_segments:
                continue
            # Reject if either endpoint is a turnout we're not keeping
            if c1 in all_turnouts and c1 not in keep_turnouts:
                continue
            if c2 in all_turnouts and c2 not in keep_turnouts:
                continue
            c1_ok = c1 in keep_turnouts or c1 in keep_points
            c2_ok = c2 in keep_turnouts or c2 in keep_points
            if c1_ok and c2_ok:
                keep_segments.add(seg_ident)
                changed = True
                if c1 and c1 not in keep_turnouts:
                    keep_points.add(c1)
                if c2 and c2 not in keep_turnouts:
                    keep_points.add(c2)
            elif c1_ok and other_end_is_ok(c2):
                keep_segments.add(seg_ident)
                changed = True
                if c2 and c2 not in keep_turnouts:
                    keep_points.add(c2)
            elif c2_ok and other_end_is_ok(c1):
                keep_segments.add(seg_ident)
                changed = True
                if c1 and c1 not in keep_turnouts:
                    keep_points.add(c1)
    return keep_turnouts, keep_segments, keep_points


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE
    output = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT
    if not os.path.isfile(source):
        print(f"Source not found: {source}")
        sys.exit(1)

    tree = ET.parse(source)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("LayoutEditor not found")
        sys.exit(1)

    keep_turnouts, keep_segments, keep_points = compute_keep_sets(layout)
    print(f"Keeping {len(keep_turnouts)} turnouts, {len(keep_segments)} segments, {len(keep_points)} points")

    # Full copy of the panel (same sensors, turnouts, blocks, layoutblocks, etc.)
    new_root = copy.deepcopy(root)
    new_layout = find_layout(new_root)
    if new_layout is None:
        print("LayoutEditor not found in copy")
        sys.exit(1)

    # Remove layout elements that are not in our keep sets. Iterate over a list
    # of children to remove so we don't modify while iterating.
    to_remove = []
    for child in new_layout:
        tag = ns(child.tag)
        if tag == "layoutturnout":
            ident = child.get("ident") or child.get("turnoutname")
            if ident not in keep_turnouts:
                to_remove.append(child)
        elif tag == "tracksegment":
            ident = child.get("ident")
            if ident not in keep_segments:
                to_remove.append(child)
        elif tag == "positionablepoint":
            ident = child.get("ident")
            if ident not in keep_points:
                to_remove.append(child)
        elif tag == "positionablelabel" or "positionable" in tag.lower():
            # Remove labels/overlays so we have a clean schematic
            to_remove.append(child)
        # keep: layoutTrackDrawingOptions and any other non-track items we didn't list

    for elem in to_remove:
        new_layout.remove(elem)

    out_tree = ET.ElementTree(new_root)
    ET.indent(out_tree, space="  ", level=0)
    with open(output, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n')
        out_tree.write(f, encoding="unicode", default_namespace=None, method="xml", xml_declaration=False)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
