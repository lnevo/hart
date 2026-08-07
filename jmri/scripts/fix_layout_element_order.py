#!/usr/bin/env python3
"""Fix LayoutEditor child order: JMRI expects all track segments, then all positionable points.
Moves any positionablepoint that appears before the last tracksegment to after all track segments.
"""
import xml.etree.ElementTree as ET
import sys

def find_layout(root):
    for elem in root.iter():
        if elem.tag and "LayoutEditor" in (elem.tag or ""):
            return elem
    return None

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "new_panel.xml"
    tree = ET.parse(path)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("LayoutEditor not found")
        sys.exit(1)

    # Group children by type (keep order within group). Preserve any other types (e.g. positionablelabel).
    opts = []
    labels = []
    turnouts = []
    segments = []
    points = []
    other = []
    for child in layout:
        tag = (child.tag or "").strip().lower()
        if "layouttrackdrawingoptions" in tag:
            opts.append(child)
        elif "positionablelabel" in tag:
            labels.append(child)
        elif "layoutturnout" in tag:
            turnouts.append(child)
        elif tag == "tracksegment":
            segments.append(child)
        elif "positionablepoint" in tag:
            points.append(child)
        else:
            other.append(child)

    # Rebuild layout: opts, labels, turnouts, segments, points, other
    for child in list(layout):
        layout.remove(child)
    for elem in opts + labels + turnouts + segments + points + other:
        layout.append(elem)

    tree.write(path, encoding="unicode", default_namespace=None, method="xml", xml_declaration=True)
    print(f"Reordered {path}: {len(segments)} segments, then {len(points)} points")

if __name__ == "__main__":
    main()
