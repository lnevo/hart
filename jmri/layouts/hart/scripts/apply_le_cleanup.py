#!/usr/bin/env python3
"""LE cleanup: MTT FB share, 114-McKeesport kink, zero-length K-2, hidden stub masts.

Writable source is tables/new_tables.xml. --sync-output also patches
jmri/layouts/hart/output/tables.xml and hart_prod.xml independently.
"""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT = ROOT / "tables/new_tables.xml"
OUTPUT_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
HART_PROD = ROOT / "jmri/layouts/hart/output/hart_prod.xml"

STUB_MASTS = [
    # systemName, userName, bumper ident, bound attr, icon x,y, degrees
    ("IF$vsm:AAR-1946:SL-1-low($1001)", "101LA", "EB70", "eastboundsignalmast", 40, 236, 90),
    ("IF$vsm:AAR-1946:SL-1-low($1002)", "101LB", "EB73", "eastboundsignalmast", 40, 299, 90),
    ("IF$vsm:AAR-1946:SL-1-low($1003)", "115RA", "EB71", "westboundsignalmast", 1740, 236, 270),
    ("IF$vsm:AAR-1946:SL-1-low($1004)", "114RA", "EB72", "westboundsignalmast", 1740, 299, 270),
    ("IF$vsm:AAR-1946:SL-1-low($1005)", "118L", "EB1", "eastboundsignalmast", 548, 250, 90),
    ("IF$vsm:AAR-1946:SL-1-low($1006)", "119LA", "EB2", "eastboundsignalmast", 548, 261, 90),
    ("IF$vsm:AAR-1946:SL-1-low($1007)", "119LB", "EB3", "eastboundsignalmast", 548, 273, 90),
    ("IF$vsm:AAR-1946:SL-1-low($1008)", "104L", "A53", "westboundsignalmast", 768, 350, 270),
    ("IF$vsm:AAR-1946:SL-1-low($1009)", "105L", "A46", "westboundsignalmast", 843, 397, 270),
    ("IF$vsm:AAR-1946:SL-1-low($1010)", "106L", "A41", "westboundsignalmast", 910, 444, 270),
    ("IF$vsm:AAR-1946:SL-1-low($1011)", "107L", "A12", "westboundsignalmast", 1050, 458, 270),
]

MTT_FB = {
    "MTT100": ("Switch 4-1 FB R", "Switch 4-1 FB N", "Switch 100"),
    "MTT113": ("Switch 1-1 FB R", "Switch 1-1 FB N", "Switch 113"),
    "MTT114": ("Switch 1-2 FB R", "Switch 1-2 FB N", "Switch 114"),
    "MTT115": ("Switch 1-3 FB R", "Switch 1-3 FB N", "Switch 115"),
}


def _le(root: ET.Element) -> ET.Element | None:
    for panel in root.findall("LayoutEditor"):
        name = (panel.get("name") or "").strip()
        if name in ("My Layout", "HART"):
            return panel
    return None


def patch_mtt(root: ET.Element) -> int:
    n = 0
    for turnout in root.iter("turnout"):
        sn = ""
        child = turnout.find("systemName")
        if child is not None and child.text:
            sn = child.text.strip()
        if sn not in MTT_FB:
            continue
        sensor1, sensor2, switch = MTT_FB[sn]
        if turnout.get("feedback") != "TWOSENSOR":
            turnout.set("feedback", "TWOSENSOR")
            n += 1
        if turnout.get("sensor1") != sensor1:
            turnout.set("sensor1", sensor1)
            n += 1
        if turnout.get("sensor2") != sensor2:
            turnout.set("sensor2", sensor2)
            n += 1
        comment = turnout.find("comment")
        want = f"OpenLCB alias of {switch}; same FB as MQTT hardware ({sensor2.split()[0]} {sensor2.split()[1]})"
        if comment is None:
            comment = ET.SubElement(turnout, "comment")
            comment.text = want
            n += 1
        elif comment.text != want:
            comment.text = want
            n += 1
    return n


def patch_kink(le: ET.Element) -> int:
    n = 0
    a62 = None
    for pt in le.findall("positionablepoint"):
        if pt.get("ident") == "A62":
            a62 = pt
            break
    if a62 is None:
        return 0
    x0, y0 = float(a62.get("x", "0")), float(a62.get("y", "0"))
    # Turnout C → A62 heading ~46.3°. Place last bezier CP on that ray.
    dist = 24.9
    heading = math.radians(46.3)
    nx = round(x0 + dist * math.cos(heading), 1)
    ny = round(y0 + dist * math.sin(heading), 1)
    for seg in le.findall("tracksegment"):
        if seg.get("ident") != "F60-S-0":
            continue
        cps = seg.find("controlpoints")
        if cps is None:
            continue
        for cp in cps.findall("controlpoint"):
            if cp.get("index") == "1":
                if cp.get("x") != str(nx) or cp.get("y") != str(ny):
                    cp.set("x", str(nx))
                    cp.set("y", str(ny))
                    n += 1
    return n


def patch_zero_length_k2(le: ET.Element) -> int:
    n = 0
    f5 = None
    a57 = None
    a55 = None
    f57 = None
    for seg in le.findall("tracksegment"):
        if seg.get("ident") == "F5-S-0":
            f5 = seg
        if seg.get("ident") == "F57-S-0":
            f57 = seg
    for pt in le.findall("positionablepoint"):
        if pt.get("ident") == "A57":
            a57 = pt
        if pt.get("ident") == "A55":
            a55 = pt
    if f5 is None:
        return 0
    if f57 is not None and f57.get("connect2name") == "A57":
        f57.set("connect2name", "A55")
        n += 1
    if a55 is not None and a55.get("connect1name") == "F5-S-0":
        a55.set("connect1name", "F57-S-0")
        n += 1
    le.remove(f5)
    n += 1
    if a57 is not None:
        le.remove(a57)
        n += 1
    return n


def patch_stub_masts(root: ET.Element, le: ET.Element) -> int:
    n = 0
    masts = root.find("signalmasts")
    if masts is None:
        return 0
    existing = {
        (el.findtext("systemName") or "").strip()
        for el in masts.findall("signalmast")
    }
    for sysname, uname, _ident, _attr, x, y, deg in STUB_MASTS:
        if sysname in existing:
            continue
        el = ET.SubElement(masts, "signalmast")
        el.set("class", "jmri.implementation.configurexml.VirtualSignalMastXml")
        sn = ET.SubElement(el, "systemName")
        sn.text = sysname
        un = ET.SubElement(el, "userName")
        un.text = uname
        unlit = ET.SubElement(el, "unlit")
        unlit.set("allowed", "yes")
        n += 1
        existing.add(sysname)
        icons = [
            ic
            for ic in le.findall("signalmasticon")
            if ic.get("signalmast") == uname and ic.get("hidden") == "yes"
        ]
        if not icons:
            ic = ET.Element("signalmasticon")
            ic.set("signalmast", uname)
            ic.set("x", str(x))
            ic.set("y", str(y))
            ic.set("level", "9")
            ic.set("forcecontroloff", "false")
            ic.set("hidden", "yes")
            ic.set("positionable", "true")
            ic.set("showtooltip", "true")
            ic.set("editable", "false")
            ic.set("degrees", str(deg))
            ic.set("clickmode", "0")
            ic.set("litmode", "false")
            ic.set("scale", "1.0")
            ic.set("imageset", "default")
            ic.set(
                "class",
                "jmri.jmrit.display.configurexml.SignalMastIconXml",
            )
            # Park next to other LE mast icons.
            first_to = None
            for child in list(le):
                if child.tag == "layoutturnout":
                    first_to = child
                    break
            if first_to is not None:
                idx = list(le).index(first_to)
                le.insert(idx, ic)
            else:
                le.append(ic)
            n += 1
        for pt in le.findall("positionablepoint"):
            if pt.get("ident") != _ident:
                continue
            if pt.get(_attr) != uname:
                pt.set(_attr, uname)
                n += 1
    return n


def apply(path: Path) -> int:
    tree = ET.parse(path)
    root = tree.getroot()
    n = patch_mtt(root)
    le = _le(root)
    if le is not None:
        n += patch_kink(le)
        n += patch_zero_length_k2(le)
        n += patch_stub_masts(root, le)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT)
    ap.add_argument("--sync-output", action="store_true")
    args = ap.parse_args()
    paths = [args.panel.resolve()]
    if args.sync_output:
        paths.extend([OUTPUT_TABLES, HART_PROD])
    for path in paths:
        if not path.is_file():
            print(f"missing {path}")
            continue
        n = apply(path)
        print(f"{path}: {n} edits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
