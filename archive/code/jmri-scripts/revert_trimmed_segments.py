#!/usr/bin/env python3
"""Revert the 'add trimmed segments' change: remove the 7 trimmed segments and 7 CUT points,
restore A233 to END_BUMPER with only F35515-S-0. This should fix the blank panel."""
import os
import sys
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_DEFAULT_PANEL = os.path.join(layout_paths()["working"], "new_panel.xml")

CUT_IDENTS = {
    "CUT-F35512-S-0", "CUT-F35508-S-0", "CUT-F35510-S-0", "CUT-F35506-S-0",
    "CUT-F35504-S-0", "CUT-F35234-S-0", "CUT-F35264-S-0",
}
TRIM_SEGMENT_IDENTS = {
    "F35512-S-0", "F35508-S-0", "F35510-S-0", "F35506-S-0",
    "F35504-S-0", "F35234-S-0", "F35264-S-0",
}


def find_layout(root):
    for elem in root.iter():
        if elem.tag and "LayoutEditor" in (elem.tag or ""):
            return elem
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PANEL
    tree = ET.parse(path)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("LayoutEditor not found")
        sys.exit(1)

    to_remove = []
    for child in list(layout):
        tag = (child.tag or "").strip().lower()
        ident = child.get("ident") or ""
        if tag == "tracksegment" and ident in TRIM_SEGMENT_IDENTS:
            to_remove.append(child)
        elif "positionablepoint" in tag and ident in CUT_IDENTS:
            to_remove.append(child)
    for elem in to_remove:
        layout.remove(elem)

    # A233 back to END_BUMPER, single connection
    for child in layout:
        if (child.tag or "").strip().lower().find("positionablepoint") >= 0 and (child.get("ident") or "") == "A233":
            child.set("type", "END_BUMPER")
            child.set("connect1name", "F35515-S-0")
            if child.get("connect2name"):
                del child.attrib["connect2name"]
            child.set("eastboundsensor", "NX A233")
            break

    tree.write(path, encoding="unicode", default_namespace=None, method="xml", xml_declaration=True)
    print(f"Reverted: removed {len(to_remove)} elements, A233 -> END_BUMPER. Panel should load (left part only).")


if __name__ == "__main__":
    main()
