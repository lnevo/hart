#!/usr/bin/env python3
"""Remove Entry/Exit (NX) table entries and layout-boundary sensor hooks from a JMRI panel/tables XML."""
import re
import sys
import xml.etree.ElementTree as ET

SCRIPT_DIR = __file__.rsplit("/", 1)[0]


def _local_tag(elem):
    tag = elem.tag or ""
    return tag.split("}")[-1].lower() if tag else ""


def _sensor_username(sensor_elem):
    for un in sensor_elem.iter():
        if _local_tag(un) != "username":
            continue
        if un.text:
            return un.text.strip()
    return ""


def _is_nx_sensor_name(name):
    if not name:
        return False
    u = name.strip()
    return u.startswith("NX ") or u.upper().startswith("NX ")


def _strip_nx_from_comment(text):
    if not text or "NX " not in text and not re.search(r"\bNX\s", text):
        return text
    # Drop comma/dot-separated phrases that are NX sensor names
    chunks = re.split(r"[,;]\s*|\.\s+", text)
    kept = []
    for c in chunks:
        c = c.strip()
        if not c:
            continue
        if c.startswith("NX ") or re.match(r"^NX\s", c):
            continue
        kept.append(c)
    return ". ".join(kept) if kept else ""


def strip_nx(tree):
    root = tree.getroot()
    # Root-level entry/exit
    for child in list(root):
        t = _local_tag(child)
        if "entryexitpairs" in t:
            root.remove(child)
            continue
        if t == "layoutblocks":
            child.set("blockrouting", "no")

    # Sensors: drop NX userName entries
    for parent in root.iter():
        if _local_tag(parent) != "sensors":
            continue
        for ch in list(parent):
            if _local_tag(ch) != "sensor":
                continue
            if _is_nx_sensor_name(_sensor_username(ch)):
                parent.remove(ch)

    # Remove NX boundary lists from <comment> on remaining sensors (e.g. Block Sensor 1…)
    for parent in root.iter():
        if _local_tag(parent) != "sensors":
            continue
        for ch in parent:
            if _local_tag(ch) != "sensor":
                continue
            for sub in list(ch):
                if _local_tag(sub) != "comment":
                    continue
                text = (sub.text or "").strip()
                if not text:
                    ch.remove(sub)
                    continue
                if "NX " not in text and not re.search(r"\bNX\s", text):
                    continue
                new_t = _strip_nx_from_comment(text)
                if new_t:
                    sub.text = new_t
                else:
                    ch.remove(sub)

    layout = root.find(".//LayoutEditor")
    if layout is None:
        layout = root.find(".//{*}LayoutEditor")
    if layout is None:
        for elem in root.iter():
            if elem.tag and "LayoutEditor" in elem.tag:
                layout = elem
                break
    if layout is not None:
        for elem in layout.iter():
            t = _local_tag(elem)
            if "positionablepoint" in t:
                for attr in ("eastboundsensor", "westboundsensor"):
                    if elem.get(attr):
                        del elem.attrib[attr]
            if "layoutturnout" in t or "layoutslip" in t or "layoutxing" in t:
                for sub in list(elem):
                    st = _local_tag(sub)
                    if st in ("sensora", "sensorb", "sensorc", "sensord"):
                        elem.remove(sub)

    # Block comments mentioning NX only
    for blk in root.iter():
        if _local_tag(blk) != "block":
            continue
        com = None
        for c in blk:
            if _local_tag(c) == "comment":
                com = c
                break
        if com is not None and com.text:
            new_t = _strip_nx_from_comment(com.text)
            if new_t:
                com.text = new_t
            else:
                blk.remove(com)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else f"{SCRIPT_DIR}/tables.xml"
    dst = sys.argv[2] if len(sys.argv) > 2 else f"{SCRIPT_DIR}/new_tables.xml"
    tree = ET.parse(src)
    strip_nx(tree)
    ET.indent(tree, space="  ", level=0)
    with open(dst, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<?xml-stylesheet href="/xml/XSLT/panelfile-5-5-5.xsl" type="text/xsl"?>\n')
        tree.write(f, encoding="unicode", default_namespace=None, xml_declaration=False)


if __name__ == "__main__":
    main()
