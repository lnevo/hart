#!/usr/bin/env python3
"""
Trim working/new_panel.xml: remove everything to the right of anchor point A233 (x=548.75).
- Remove all positionable points with x > 548.75
- Remove all track segments that reference any removed point (connect1name or connect2name)
- Remove all layout turnouts with xcen > 548.75
- Convert A233 from ANCHOR to END_BUMPER (single connection F35515-S-0), set eastboundsensor for cut end
"""
import os
import sys
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_DEFAULT_PANEL = os.path.join(layout_paths()["working"], "new_panel.xml")
CUTOFF_X = 548.75
A233_IDENT = "A233"


def find_layout(root):
    for elem in root.iter():
        if elem.tag and "LayoutEditor" in (elem.tag or ""):
            return elem
    return None


def main():
    path = _DEFAULT_PANEL if len(sys.argv) < 2 else sys.argv[1]
    tree = ET.parse(path)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("LayoutEditor not found")
        sys.exit(1)

    # Collect positionable points and their x
    points_right = set()  # idents with x > CUTOFF_X
    point_elements = {}   # ident -> element
    for child in list(layout):
        tag = (child.tag or "").strip().lower()
        if "positionablepoint" in tag:
            ident = child.get("ident")
            if not ident:
                continue
            point_elements[ident] = child
            x_s = child.get("x")
            if x_s:
                try:
                    if float(x_s) > CUTOFF_X:
                        points_right.add(ident)
                except ValueError:
                    pass

    # Collect layout turnouts with xcen > CUTOFF_X
    turnouts_right = set()
    for child in list(layout):
        tag = (child.tag or "").strip().lower()
        if "layoutturnout" in tag:
            ident = child.get("ident")
            xc = child.get("xcen")
            if ident and xc:
                try:
                    if float(xc) > CUTOFF_X:
                        turnouts_right.add(ident)
                except ValueError:
                    pass

    remove_points = points_right
    remove_turnouts = turnouts_right

    # Segments to remove: reference any removed point or removed turnout
    to_remove = []
    for child in layout:
        tag = (child.tag or "").strip().lower()
        if tag == "tracksegment":
            c1 = child.get("connect1name") or ""
            c2 = child.get("connect2name") or ""
            if c1 in remove_points or c2 in remove_points or c1 in remove_turnouts or c2 in remove_turnouts:
                to_remove.append(child)
        elif "layoutturnout" in tag and (child.get("ident") or "") in remove_turnouts:
            to_remove.append(child)
        elif "positionablepoint" in tag and (child.get("ident") or "") in remove_points:
            to_remove.append(child)

    for elem in to_remove:
        layout.remove(elem)

    # Convert A233 to END_BUMPER: keep only F35515-S-0 connection
    a233 = point_elements.get(A233_IDENT)
    if a233 is not None and a233 in list(layout):  # still in layout
        a233.set("type", "END_BUMPER")
        a233.set("connect1name", "F35515-S-0")
        if a233.get("connect2name"):
            del a233.attrib["connect2name"]
        # East end of track (cut side) gets boundary sensor for entry/exit
        a233.set("eastboundsensor", "NX A233")

    # Write back
    tree.write(
        path,
        encoding="unicode",
        default_namespace=None,
        method="xml",
        xml_declaration=True,
    )
    print(f"Trimmed {path}: removed {len([e for e in to_remove if (e.tag or '').strip().lower() == 'tracksegment'])} segments, "
          f"{len([e for e in to_remove if 'positionablepoint' in (e.tag or '').lower()])} points, "
          f"{len([e for e in to_remove if 'layoutturnout' in (e.tag or '').lower()])} turnouts. A233 -> END_BUMPER.")


if __name__ == "__main__":
    main()
