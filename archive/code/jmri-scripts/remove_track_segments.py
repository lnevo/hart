#!/usr/bin/env python3
"""
Remove track segments from a LayoutEditor panel and fix anchor connections.

Usage:
  python3 remove_track_segments.py panel.xml segment1 [segment2 ...]
  python3 remove_track_segments.py panel.xml --list exclude_segments.txt
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag or ""
    return tag.split("}", 1)[-1] if "}" in tag else tag.lower()


def _find_layout(root: ET.Element) -> ET.Element | None:
    layout = root.find(".//LayoutEditor")
    if layout is None:
        layout = root.find(".//{*}LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if elem.tag and "LayoutEditor" in elem.tag:
                return elem
    return layout


def load_idents(path: str) -> list[str]:
    idents: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                idents.append(line)
    return idents


def remove_segments(layout: ET.Element, remove: set[str]) -> tuple[int, int]:
    """Returns (segments_removed, anchors_patched)."""
    removed = 0
    for seg in list(layout):
        if _local_tag(seg) != "tracksegment":
            continue
        ident = seg.get("ident")
        if ident in remove:
            layout.remove(seg)
            removed += 1

    patched = 0
    for pt in layout:
        if _local_tag(pt) != "positionablepoint":
            continue
        c1 = pt.get("connect1name") or ""
        c2 = pt.get("connect2name") or ""
        if c1 in remove:
            if c2 in remove:
                pt.attrib.pop("connect1name", None)
                pt.attrib.pop("connect2name", None)
            elif c2:
                pt.set("connect1name", c2)
                del pt.attrib["connect2name"]
            else:
                del pt.attrib["connect1name"]
            patched += 1
        elif c2 in remove:
            del pt.attrib["connect2name"]
            patched += 1
    return removed, patched


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove layout track segments and fix anchors.")
    ap.add_argument("panel", help="Panel XML path")
    ap.add_argument("segments", nargs="*", help="Segment idents to remove")
    ap.add_argument("--list", help="Text file with one segment ident per line")
    ap.add_argument("-o", "--output", help="Output path (default: overwrite panel)")
    args = ap.parse_args()

    remove = set(args.segments)
    if args.list:
        remove.update(load_idents(args.list))
    if not remove:
        print("No segments specified.", file=sys.stderr)
        sys.exit(1)

    tree = ET.parse(args.panel)
    layout = _find_layout(tree.getroot())
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {args.panel}")

    n_seg, n_pt = remove_segments(layout, remove)
    out = args.output or args.panel
    ET.indent(tree, space="  ", level=0)
    with open(out, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)

    print(f"Wrote {out}")
    print(f"  Removed {n_seg} segment(s): {', '.join(sorted(remove))}")
    print(f"  Patched {n_pt} anchor point(s)")


if __name__ == "__main__":
    main()
