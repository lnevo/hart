#!/usr/bin/env python3
"""Remove the 5 layout turnouts and their stub segments/points added by add_five_turnout_stubs.py."""
import os
import sys
import xml.etree.ElementTree as ET

JMRI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JMRI_ROOT)
from layout_paths import layout_paths

_DEFAULT_PANEL = os.path.join(layout_paths()["working"], "new_panel.xml")

REMOVE_TURNOUTS = {"TOR35232", "TOR35228", "TOR35230", "TOR35284", "TOR35283"}
REMOVE_SEGMENTS = {"T-I-TOR35283", "T-EL-TOR35284", "T-ER-TOR35230", "T-ER-TOR35228", "T-ER-TOR35232"}
REMOVE_POINTS = {"CUT-TOR35232", "CUT-TOR35228", "CUT-TOR35230", "CUT-TOR35284", "CUT-TOR35283"}


def find_layout(root):
    for e in root.iter():
        if e.tag and "LayoutEditor" in (e.tag or ""):
            return e
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PANEL
    tree = ET.parse(path)
    root = tree.getroot()
    layout = find_layout(root)
    if layout is None:
        print("LayoutEditor not found")
        sys.exit(1)

    removed_t, removed_s, removed_p = 0, 0, 0
    for child in list(layout):
        tag = (child.tag or "").strip().lower()
        ident = child.get("ident") or ""
        if "layoutturnout" in tag and ident in REMOVE_TURNOUTS:
            layout.remove(child)
            removed_t += 1
        elif tag == "tracksegment" and ident in REMOVE_SEGMENTS:
            layout.remove(child)
            removed_s += 1
        elif "positionablepoint" in tag and ident in REMOVE_POINTS:
            layout.remove(child)
            removed_p += 1

    tree.write(path, encoding="unicode", default_namespace=None, method="xml", xml_declaration=True)
    print(f"Removed {removed_t} layout turnouts, {removed_s} segments, {removed_p} points. Panel should load again.")


if __name__ == "__main__":
    main()
