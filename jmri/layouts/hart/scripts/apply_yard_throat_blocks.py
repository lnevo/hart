#!/usr/bin/env python3
"""Split South Yard S-1…S-5 into station body + hidden throat blocks.

Dispatcher System needs a signal mast *beyond* each stopping block. The yard
body tracks were one block from frog to frog, so Discover could not see a
mast at A53/A46/…. Each turnout C/B leg becomes a short throat that *shares
the body occupancy sensor* (same pattern as K-1 / OS 115). The existing
anchors become real block boundaries; virtual masts move there.

Throat block comments must not contain the substring "stop" — CreateGraph
uses ``if "stop" in comment.lower()``. Use "not a station".

S-1 is only two segments, so F46-S-0 is split at a new A81 just east of TOR14.

Writable source is tables/new_tables.xml. --sync-output also patches
output/tables.xml and hart_prod.xml. Idempotent.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT = ROOT / "tables/new_tables.xml"
OUTPUT_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
HART_PROD = ROOT / "jmri/layouts/hart/output/hart_prod.xml"

# Turnout-leg segments that become throats (already short).
THROAT_SEGMENTS = [
    # ident, new block userName, occupancy sensor, station plate
    ("T-EL-TOL15", "S-2 West", "Block 2-7", "S-2"),
    ("T-ER-TOR7", "S-2 East", "Block 2-7", "S-2"),
    ("T-EL-TOL17", "S-3 West", "Block 2-6", "S-3"),
    ("T-ER-TOR9", "S-3 East", "Block 2-6", "S-3"),
    ("T-EL-TOL19", "S-4 West", "Block 2-5", "S-4"),
    ("T-ER-TOR11", "S-4 East", "Block 2-5", "S-4"),
    ("T-ER-TOL19", "S-5 West", "Block 2-4", "S-5"),
    ("T-EL-TOR11", "S-5 East", "Block 2-4", "S-5"),
    ("T-EL-TOR32", "S-1 East", "Block 2-8", "S-1"),
    # T3 is the west throat of Switch 7, not a Scale station block. Putting
    # it in OS Switch 7 makes A45 a real Scale|Switch 7 boundary so 26L can
    # Discover 8LC. A extra "Scale East" block hid 8LC behind Switch 7.
    ("T3", "OS Switch 7", "BS Scale", "Track Scale"),
]

# After throats exist, bind virtuals on the new boundaries (not turnout legs).
BOUNDARY_MASTS = [
    # ident, attr, systemName, userName, icon x, y, degrees
    ("A53", "westboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1008)", "Mast 18L", 768, 350, 270),
    ("A61", "eastboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1012)", "Mast 18R", 1148, 350, 90),
    ("A46", "westboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1009)", "Mast 20L", 843, 397, 270),
    ("A36", "eastboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1013)", "Mast 20R", 1148, 397, 90),
    ("A41", "westboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1010)", "Mast 22L", 910, 444, 270),
    ("A39", "eastboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1014)", "Mast 22R", 1148, 444, 90),
    ("A15", "westboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1011)", "Mast 26L", 910, 474, 270),
    ("A12", "eastboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1015)", "Mast 26R", 1148, 474, 90),
    ("A81", "westboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1016)", "Mast 16L", 720, 300, 270),
    ("A37", "eastboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1017)", "Mast 32L", 1145, 300, 90),
    ("A45", "westboundsignalmast", "IF$vsm:AAR-1946:SL-1-low($1018)", "Mast 8LC", 382, 305, 270),
]

TURNOUT_MAST_TAGS = ("signalAMast", "signalBMast", "signalCMast", "signalDMast")
YARD_VIRTUALS = {row[3] for row in BOUNDARY_MASTS}

# Engine House exits. Bumper 12L/10LA/10LB are arrival dests only; without a
# mast at EH-n | Switch 9/11, getBeansInPath(EH→yard) is empty or picks
# 32L (S-1 East) and Stage 1 never builds EH→S-1/S-4/S-R.
EH_EXIT_MASTS = [
    # turnout, tag, sysname, uname, icon x, y, degrees
    ("TO11", "signalBMast", "IF$vsm:AAR-1946:SL-1-low($1020)", "Mast 11L", 620, 270, 270),
    ("TO10", "signalCMast", "IF$vsm:AAR-1946:SL-1-low($1021)", "Mast 9LA", 598, 268, 270),
    ("TO10", "signalBMast", "IF$vsm:AAR-1946:SL-1-low($1022)", "Mast 9LB", 596, 280, 270),
]


def _le(root: ET.Element) -> ET.Element | None:
    for panel in root.findall("LayoutEditor"):
        name = (panel.get("name") or "").strip()
        if name in ("HART Railroad", "My Layout", "HART"):
            return panel
    return None


def _user_names(root: ET.Element) -> set[str]:
    names = set()
    blocks = root.find("blocks")
    if blocks is None:
        return names
    for block in blocks.findall("block"):
        un = (block.findtext("userName") or "").strip()
        if un:
            names.add(un)
    return names


def _next_ib_auto(root: ET.Element) -> int:
    n = 0
    blocks = root.find("blocks")
    if blocks is None:
        return 52
    for block in blocks.findall("block"):
        sn = (block.findtext("systemName") or block.get("systemName") or "")
        if sn.startswith("IB:AUTO:"):
            n = max(n, int(sn.split(":")[-1]))
    return n + 1


def _next_ilb(root: ET.Element) -> int:
    n = 0
    lbs = root.find("layoutblocks")
    if lbs is None:
        return 78
    for block in lbs.findall("layoutblock"):
        sn = (block.findtext("systemName") or block.get("systemName") or "")
        if sn.startswith("ILB"):
            try:
                n = max(n, int(sn[3:]))
            except ValueError:
                pass
    return n + 1


def _ensure_virtual_mast(
    masts: ET.Element, existing: set[str], sysname: str, uname: str
) -> int:
    if sysname in existing:
        return 0
    el = ET.SubElement(masts, "virtualsignalmast")
    el.set("class", "jmri.implementation.configurexml.VirtualSignalMastXml")
    ET.SubElement(el, "systemName").text = sysname
    ET.SubElement(el, "userName").text = uname
    unlit = ET.SubElement(el, "unlit")
    unlit.set("allowed", "yes")
    existing.add(sysname)
    return 1


def _ensure_turnout_mast(to: ET.Element, tag: str, uname: str) -> int:
    for child in to:
        if child.tag == tag and (child.text or "").strip() == uname:
            return 0
    el = ET.Element(tag)
    el.text = uname
    to.append(el)
    return 1


def _ensure_hidden_icon(le: ET.Element, uname: str, x: int, y: int, deg: int) -> int:
    for ic in le.findall("signalmasticon"):
        if ic.get("signalmast") == uname and ic.get("hidden") == "yes":
            return 0
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
    ic.set("class", "jmri.jmrit.display.configurexml.SignalMastIconXml")
    first_to = next((c for c in list(le) if c.tag == "layoutturnout"), None)
    if first_to is not None:
        le.insert(list(le).index(first_to), ic)
    else:
        le.append(ic)
    return 1


def _add_block_beans(
    root: ET.Element,
    ib: str,
    ilb: str,
    uname: str,
    sensor: str,
    station: str,
    *,
    panel_style: bool = False,
) -> None:
    blocks = root.find("blocks")
    lbs = root.find("layoutblocks")
    if blocks is None or lbs is None:
        raise SystemExit("missing blocks/layoutblocks")
    comment = (
        f"Hidden {station} throat (same detector as {station}); "
        f"occupancy {sensor}; not a station"
    )
    stub = ET.Element("block")
    stub.set("systemName", ib)
    ET.SubElement(stub, "systemName").text = ib
    ET.SubElement(stub, "userName").text = uname
    full = ET.Element("block")
    full.set("systemName", ib)
    full.set("length", "400.0")
    full.set("curve", "0")
    ET.SubElement(full, "systemName").text = ib
    ET.SubElement(full, "userName").text = uname
    ET.SubElement(full, "comment").text = comment
    ET.SubElement(full, "permissive").text = "no"
    ET.SubElement(full, "occupancysensor").text = sensor

    stubs = [
        b
        for b in list(blocks)
        if b.tag == "block" and b.get("length") is None and b.find("occupancysensor") is None
    ]
    # tables.xml keeps JMRI's stub+full pair. hart_prod.xml is a panel
    # and only has one <block> per userName — adding both fails phase02.
    if not panel_style:
        if stubs:
            last_stub = stubs[-1]
            idx = list(blocks).index(last_stub)
            blocks.insert(idx + 1, stub)
        else:
            blocks.append(stub)
    blocks.append(full)

    lb = ET.SubElement(lbs, "layoutblock")
    lb.set("systemName", ilb)
    lb.set("occupancysensor", sensor)
    lb.set("occupiedsense", "2")
    lb.set("trackcolor", "gray")
    lb.set("occupiedcolor", "red")
    lb.set("extracolor", "white")
    ET.SubElement(lb, "systemName").text = ilb
    ET.SubElement(lb, "userName").text = uname


def _split_s1_west(le: ET.Element) -> int:
    """Insert A81 and a short S-1 West segment east of TOR14."""
    n = 0
    if any(pt.get("ident") == "A81" for pt in le.findall("positionablepoint")):
        # Still force the west-throat blockname if a previous run created A81.
        for ts in le.findall("tracksegment"):
            if ts.get("ident") == "F46-W-0" and ts.get("blockname") != "S-1 West":
                ts.set("blockname", "S-1 West")
                n += 1
        return n
    f46 = None
    tor14 = None
    for ts in le.findall("tracksegment"):
        if ts.get("ident") == "F46-S-0":
            f46 = ts
    for to in le.findall("layoutturnout"):
        if to.get("ident") == "TOR14":
            tor14 = to
    if f46 is None or tor14 is None:
        return 0
    a81 = ET.Element("positionablepoint")
    a81.set("ident", "A81")
    a81.set("type", "ANCHOR")
    a81.set("x", "720.0")
    a81.set("y", "315.0")
    a81.set("connect1name", "F46-W-0")
    a81.set("connect2name", "F46-S-0")
    a81.set(
        "class",
        "jmri.jmrit.display.layoutEditor.configurexml.PositionablePointXml",
    )
    le.insert(list(le).index(f46), a81)
    west = ET.Element("tracksegment")
    west.set("ident", "F46-W-0")
    west.set("blockname", "S-1 West")
    west.set("connect1name", "TOR14")
    west.set("type1", "TURNOUT_B")
    west.set("connect2name", "A81")
    west.set("type2", "POS_POINT")
    west.set("dashed", "no")
    west.set("mainline", "no")
    west.set("hidden", "no")
    west.set(
        "class",
        "jmri.jmrit.display.layoutEditor.configurexml.TrackSegmentXml",
    )
    le.insert(list(le).index(f46), west)
    f46.set("connect2name", "A81")
    f46.set("type2", "POS_POINT")
    if tor14.get("connectbname") == "F46-S-0":
        tor14.set("connectbname", "F46-W-0")
    n += 3
    return n


def _clear_turnout_virtuals(le: ET.Element) -> int:
    n = 0
    for to in le.findall("layoutturnout"):
        for child in list(to):
            if child.tag in TURNOUT_MAST_TAGS and (child.text or "").strip() in YARD_VIRTUALS:
                to.remove(child)
                n += 1
    return n


def _remove_orphan_scale_east(root: ET.Element) -> int:
    """Drop Track Scale East. T3 is OS Switch 7; no segment uses this block."""
    n = 0
    for parent_tag in ("blocks", "layoutblocks"):
        parent = root.find(parent_tag)
        if parent is None:
            continue
        child_tag = "block" if parent_tag == "blocks" else "layoutblock"
        for child in list(parent):
            if child.tag != child_tag:
                continue
            un = (child.findtext("userName") or "").strip()
            if un == "Track Scale East":
                parent.remove(child)
                n += 1
    return n


def apply_scale_east(path: Path) -> int:
    """T3 in OS Switch 7; 8LC west / 8RA east on A45; no Scale East block."""
    tree = ET.parse(path)
    root = tree.getroot()
    le = _le(root)
    if le is None:
        print(f"{path}: no Layout Editor")
        return 0
    n = _remove_orphan_scale_east(root)
    segs = {ts.get("ident"): ts for ts in le.findall("tracksegment")}
    t3 = segs.get("T3")
    if t3 is not None and t3.get("blockname") != "OS Switch 7":
        t3.set("blockname", "OS Switch 7")
        n += 1
    masts = root.find("signalmasts")
    existing = set()
    if masts is not None:
        existing = {
            (el.findtext("systemName") or "").strip()
            for el in list(masts)
            if el.tag in ("signalmast", "virtualsignalmast")
        }
        n += _ensure_virtual_mast(
            masts,
            existing,
            "IF$vsm:AAR-1946:SL-1-low($1018)",
            "Mast 8LC",
        )
    n += _ensure_hidden_icon(le, "Mast 8LC", 382, 305, 270)
    points = {pt.get("ident"): pt for pt in le.findall("positionablepoint")}
    pt = points.get("A45")
    if pt is not None:
        if pt.get("westboundsignalmast") != "Mast 8LC":
            pt.set("westboundsignalmast", "Mast 8LC")
            n += 1
        if pt.get("eastboundsignalmast") != "Mast 8RA":
            pt.set("eastboundsignalmast", "Mast 8RA")
            n += 1
    for to in le.findall("layoutturnout"):
        if to.get("ident") != "TO117":
            continue
        for child in list(to):
            if child.tag == "signalAMast" and (child.text or "").strip() == "Mast 8RA":
                to.remove(child)
                n += 1
        break
    # Switch 13 (TO1) had no mast on the Barn leg. Discover then jumped
    # 8RA → 26L through Barn; get_last(26L, Track Barn) returned 8RA.
    if masts is not None:
        n += _ensure_virtual_mast(
            masts,
            existing,
            "IF$vsm:AAR-1946:SL-1-low($1019)",
            "Mast 13R",
        )
    n += _ensure_hidden_icon(le, "Mast 13R", 620, 305, 90)
    turnouts = {to.get("ident"): to for to in le.findall("layoutturnout")}
    to1 = turnouts.get("TO1")
    if to1 is not None:
        n += _ensure_turnout_mast(to1, "signalBMast", "Mast 13R")
    n += _ensure_eh_exits(le, masts, existing, turnouts)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return n


def _ensure_eh_exits(
    le: ET.Element,
    masts: ET.Element | None,
    existing: set[str],
    turnouts: dict[str, ET.Element],
) -> int:
    n = 0
    for ident, tag, sysname, uname, x, y, deg in EH_EXIT_MASTS:
        if masts is not None:
            n += _ensure_virtual_mast(masts, existing, sysname, uname)
        n += _ensure_hidden_icon(le, uname, x, y, deg)
        to = turnouts.get(ident)
        if to is not None:
            n += _ensure_turnout_mast(to, tag, uname)
    return n


def apply(path: Path) -> int:
    tree = ET.parse(path)
    root = tree.getroot()
    le = _le(root)
    if le is None:
        print(f"{path}: no Layout Editor")
        return 0
    n = 0
    names = _user_names(root)
    ib_n = _next_ib_auto(root)
    ilb_n = _next_ilb(root)

    wanted = [(seg, uname, sensor, station) for seg, uname, sensor, station in THROAT_SEGMENTS]
    wanted.append(("F46-W-0", "S-1 West", "Block 2-8", "S-1"))
    for _seg, uname, sensor, station in wanted:
        if uname in names:
            continue
        ib = f"IB:AUTO:{ib_n:04d}"
        ilb = f"ILB{ilb_n}"
        _add_block_beans(
            root,
            ib,
            ilb,
            uname,
            sensor,
            station,
            panel_style=path.name == "hart_prod.xml",
        )
        names.add(uname)
        ib_n += 1
        ilb_n += 1
        n += 1

    n += _split_s1_west(le)

    segs = {ts.get("ident"): ts for ts in le.findall("tracksegment")}
    for ident, uname, _sensor, _station in THROAT_SEGMENTS:
        ts = segs.get(ident)
        if ts is None:
            continue
        if ts.get("blockname") != uname:
            ts.set("blockname", uname)
            n += 1
    west = segs.get("F46-W-0")
    if west is not None and west.get("blockname") != "S-1 West":
        west.set("blockname", "S-1 West")
        n += 1

    n += _clear_turnout_virtuals(le)

    masts = root.find("signalmasts")
    existing = set()
    if masts is not None:
        existing = {
            (el.findtext("systemName") or "").strip()
            for el in list(masts)
            if el.tag in ("signalmast", "virtualsignalmast")
        }
    points = {pt.get("ident"): pt for pt in le.findall("positionablepoint")}
    for ident, attr, sysname, uname, x, y, deg in BOUNDARY_MASTS:
        if masts is not None:
            n += _ensure_virtual_mast(masts, existing, sysname, uname)
        n += _ensure_hidden_icon(le, uname, x, y, deg)
        pt = points.get(ident)
        if pt is None:
            continue
        if pt.get(attr) != uname:
            pt.set(attr, uname)
            n += 1
        other = (
            "eastboundsignalmast"
            if attr == "westboundsignalmast"
            else "westboundsignalmast"
        )
        # A45 keeps both: 8LC westbound (Scale) and 8RA eastbound (Switch 7).
        if ident == "A45":
            continue
        if pt.get(other):
            del pt.attrib[other]
            n += 1

    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT)
    ap.add_argument("--sync-output", action="store_true")
    ap.add_argument(
        "--scale-east-only",
        action="store_true",
        help="Only fix Scale/Switch 7 (T3=OS Switch 7, 8LC/8RA on A45). Do not rewrite yard throats.",
    )
    args = ap.parse_args()
    paths = [args.panel.resolve()]
    if args.sync_output:
        paths.extend([OUTPUT_TABLES, HART_PROD])
    fn = apply_scale_east if args.scale_east_only else apply
    for path in paths:
        if not path.is_file():
            print(f"missing {path}")
            continue
        n = fn(path)
        print(f"{path}: {n} edits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
