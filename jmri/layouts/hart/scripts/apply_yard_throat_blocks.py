#!/usr/bin/env python3
"""Split South Yard Track S-R and S-1…S-4 into station body + hidden throat blocks.

Dispatcher System needs a signal mast *beyond* each stopping block. The yard
body tracks were one block from frog to frog, so Discover could not see a
mast at A53/A46/…. Each turnout C/B leg becomes a short throat that *shares
the body occupancy sensor* (same pattern as K-1 / OS 115). The existing
anchors become real block boundaries; virtual masts move there.

Throat block comments must not contain the substring "stop" — CreateGraph
uses ``if "stop" in comment.lower()``. Use "not a station".

Track S-R is only two segments, so F46-S-0 is split at a new A81 just east of
TOR14 (Track S-R West).

The default run also places the Switch 7, Mast 14R, engine-house exit and
Brick-Plane masts (--scale-east-only does just that part). It parses once and
writes only when something changed, so a run that stops on an old mast name
leaves the file untouched.

Writable source is jmri/layouts/hart/output/tables.xml. --sync-output has had no
effect since ADR-008. Idempotent.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT = ROOT / "jmri/layouts/hart/output/tables.xml"
OUTPUT_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"

# Turnout-leg segments that become throats (already short).
# Public names (ADR-005). Before 2026-08-21 these were S-2 West … S-1 East on
# occupancy Block 2-n; public_name_map.csv keeps those as historical aliases.
S_R_WEST = "Track S-R West"
THROAT_SEGMENTS = [
    # ident, block userName, occupancy sensor, station, hardware block
    ("T-EL-TOL15", "Track S-1 West", "BS S-1", "Track S-1", "Block 2-7"),
    ("T-ER-TOR7", "Track S-1 East", "BS S-1", "Track S-1", "Block 2-7"),
    ("T-EL-TOL17", "Track S-2 West", "BS S-2", "Track S-2", "Block 2-6"),
    ("T-ER-TOR9", "Track S-2 East", "BS S-2", "Track S-2", "Block 2-6"),
    ("T-EL-TOL19", "Track S-3 West", "BS S-3", "Track S-3", "Block 2-5"),
    ("T-ER-TOR11", "Track S-3 East", "BS S-3", "Track S-3", "Block 2-5"),
    ("T-ER-TOL19", "Track S-4 West", "BS S-4", "Track S-4", "Block 2-4"),
    ("T-EL-TOR11", "Track S-4 East", "BS S-4", "Track S-4", "Block 2-4"),
    ("T-EL-TOR32", "Track S-R East", "BS S-R", "Track S-R", "Block 2-8"),
    # Made by _split_s1_west.
    ("F46-W-0", S_R_WEST, "BS S-R", "Track S-R", "Block 2-8"),
]
# T3 (west throat of Switch 7, in OS Switch 7) is set by _scale_east_edits.

# After throats exist, bind virtuals on the new boundaries (not turnout legs).
BOUNDARY_MASTS = [
    # ident, attr, systemName, userName, icon x, y, degrees
    ("A53", "westboundsignalmast", "IF$vsm:basic:one-low($1008)", "Mast 18L", 768, 350, 270),
    ("A61", "eastboundsignalmast", "IF$vsm:basic:one-low($1012)", "Mast 18R", 1148, 350, 90),
    ("A46", "westboundsignalmast", "IF$vsm:basic:one-low($1009)", "Mast 20L", 843, 397, 270),
    ("A36", "eastboundsignalmast", "IF$vsm:basic:one-low($1013)", "Mast 20R", 1148, 397, 90),
    ("A41", "westboundsignalmast", "IF$vsm:basic:one-low($1010)", "Mast 22L", 910, 444, 270),
    ("A39", "eastboundsignalmast", "IF$vsm:basic:one-low($1014)", "Mast 22R", 1148, 444, 90),
    ("A15", "westboundsignalmast", "IF$vsm:basic:one-low($1011)", "Mast 26L", 910, 474, 270),
    ("A12", "eastboundsignalmast", "IF$vsm:basic:one-low($1015)", "Mast 26R", 1148, 474, 90),
    ("A81", "westboundsignalmast", "IF$vsm:basic:one-low($1016)", "Mast 16L", 720, 300, 270),
    ("A37", "eastboundsignalmast", "IF$vsm:basic:one-low($1017)", "Mast 32L", 1145, 300, 90),
    ("A45", "westboundsignalmast", "IF$vsm:basic:one-low($1018)", "Mast 8LC", 382, 305, 270),
]

TURNOUT_MAST_TAGS = ("signalAMast", "signalBMast", "signalCMast", "signalDMast")
YARD_VIRTUALS = {row[3] for row in BOUNDARY_MASTS}

# Engine House exits. Bumper 12L/10LA/10LB are arrival dests only; without a
# mast at EH-n | Switch 9/11, getBeansInPath(EH→yard) is empty or picks
# 32L (S-1 East) and Stage 1 never builds EH→S-1/S-4/S-R.
EH_EXIT_MASTS = [
    # turnout, tag, sysname, uname, icon x, y, degrees (90: R is eastbound, ADR-005)
    ("TO11", "signalBMast", "IF$vsm:basic:one-low($1020)", "Mast 12R", 620, 270, 90),
    ("TO10", "signalCMast", "IF$vsm:basic:one-low($1021)", "Mast 10RA", 598, 268, 90),
    ("TO10", "signalBMast", "IF$vsm:basic:one-low($1022)", "Mast 10RB", 596, 280, 90),
]

# Track Brick-Plane (Block 4-6) had no mast at either end, so it sat inside the
# sections 2L→8RA/8RB and 6LA/6LB→24RA: runs into Brick-Plane went past it and
# runs to East Main Ext / Main West reused Brick-Plane's transits (2026-11-10).
# Hidden virtuals on the Brick-Plane legs of Switch 1 and Switch 5 make it a
# station with a mast at each end. Name: signal = switch + 1, opposite letter.
BRICK_PLANE_MASTS = [
    # turnout, tag, sysname, uname, icon x, y, degrees, comment
    ("TOL3", "signalCMast", "IF$vsm:basic:one-low($1023)", "Mast 2R", 294, 271, 90, "Brick | Switch 1"),
    ("TOL42", "signalAMast", "IF$vsm:basic:one-low($1024)", "Mast 6R", 295, 374, 90, "Plane | Switch 5"),
]

# Rear masts for start blocks that sat inside a through section (2026-11-12).
# A train starting in Track East Lead (westbound) or Track K-1 (eastbound) had
# no mast behind it, so Stage 1 picked the first section holding the block by
# system-name sort and flipped whenever mast names changed. The short stub
# between each anchor and its switch becomes a hidden throat block sharing the
# station's detector (the South Yard pattern), so the anchor is a real
# boundary and takes a hidden virtual for the station's leaving direction.
# The switch-leg masts (36RB, 40LB) stay where they are.
# An anchor's eastbound slot protects the block on its connect1 side (as A45).
REAR_MASTS = [
    {
        "anchor": "A56",
        "segment": "T-I-TOL2",
        "throat": "Track East Lead East",
        "sensor": "BS East Lead",
        "station": "Track East Lead",
        "hardware": "Block 1-7 / M2S106",
        "virtual": ("IF$vsm:basic:one-low($1025)", "Mast 36L", "westbound", 1449, 300, 270, "Princess | Switch 35"),
    },
    {
        "anchor": "A1",
        "segment": "T-EL-TOL29",
        "throat": "Track K-1 West",
        "sensor": "BS K-1",
        "station": "Track K-1",
        "hardware": "Block 1-1 / M2S100",
        "virtual": ("IF$vsm:basic:one-low($1026)", "Mast 40RB", "eastbound", 1627, 236, 90, "Princess | Switch 39"),
    },
]


def _set_point_attr(pt: ET.Element, attr: str, value: str) -> int:
    if pt.get(attr) == value:
        return 0
    cls = pt.attrib.pop("class", None)
    pt.set(attr, value)
    if cls is not None:
        pt.set("class", cls)  # JMRI writes class last
    return 1


def _ensure_rear_masts(
    root: ET.Element, le: ET.Element, masts: ET.Element | None, existing: set[str]
) -> int:
    n = 0
    names = _user_names(root)
    segs = {ts.get("ident"): ts for ts in le.findall("tracksegment")}
    points = {pt.get("ident"): pt for pt in le.findall("positionablepoint")}
    for row in REAR_MASTS:
        seg, pt = segs.get(row["segment"]), points.get(row["anchor"])
        if seg is None or pt is None:
            raise ValueError(f"rear mast at {row['anchor']}: panel element missing")
        if row["throat"] not in names:
            _add_block_beans(
                root,
                f"IB:AUTO:{_next_ib_auto(root):04d}",
                f"ILB{_next_ilb(root)}",
                row["throat"],
                row["sensor"],
                row["station"],
                row["hardware"],
            )
            names.add(row["throat"])
            n += 1
        if seg.get("blockname") != row["throat"]:
            seg.set("blockname", row["throat"])
            n += 1
        sysname, uname, vdir, x, y, deg, comment = row["virtual"]
        n += _set_point_attr(pt, f"{vdir}signalmast", uname)
        if masts is not None:
            n += _ensure_virtual_mast(masts, existing, sysname, uname, comment)
        n += _ensure_hidden_icon(le, uname, x, y, deg)
    return n


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


def _insert_tidy(parent: ET.Element, index: int, el: ET.Element) -> None:
    """Insert keeping JMRI's one-element-per-line indentation."""
    kids = list(parent)
    if index >= len(kids):
        if kids:
            el.tail = kids[-1].tail
            kids[-1].tail = kids[-2].tail if len(kids) > 1 else parent.text
        else:
            el.tail = parent.tail
        parent.append(el)
        return
    el.tail = kids[index - 1].tail if index > 0 else parent.text
    parent.insert(index, el)


def _remove_tidy(parent: ET.Element, el: ET.Element) -> None:
    kids = list(parent)
    i = kids.index(el)
    if i == len(kids) - 1 and i > 0:
        kids[i - 1].tail = el.tail
    parent.remove(el)


def _ensure_virtual_mast(
    masts: ET.Element, existing: set[str], sysname: str, uname: str, comment: str | None = None
) -> int:
    if sysname in existing:
        for mast in masts:
            if (mast.findtext("systemName") or "").strip() != sysname:
                continue
            found = (mast.findtext("userName") or "").strip()
            if found != uname:
                # A tables.xml from before a rename: adding the new name beside
                # the old one would give a turnout two masts in one slot.
                raise ValueError(
                    f"{sysname} is named {found!r}, expected {uname!r}; "
                    "rename it in tables.xml before running this script"
                )
        return 0
    el = ET.Element("virtualsignalmast")
    el.set("class", "jmri.implementation.configurexml.VirtualSignalMastXml")
    inner = (list(masts)[-1].text if len(masts) else None) or "\n      "
    for tag, text in (("systemName", sysname), ("userName", uname), ("comment", comment)):
        if text:
            ET.SubElement(el, tag).text = text
    ET.SubElement(el, "unlit").set("allowed", "yes")
    el.text = inner
    kids = list(el)
    for kid in kids[:-1]:
        kid.tail = inner
    kids[-1].tail = inner[:-2] if inner.endswith("  ") else inner
    _insert_tidy(masts, len(masts), el)
    existing.add(sysname)
    return 1


def _ensure_turnout_mast(to: ET.Element, tag: str, uname: str) -> int:
    for child in to:
        if child.tag != tag:
            continue
        found = (child.text or "").strip()
        if found == uname:
            return 0
        # One mast per slot. A different name here is usually a tables.xml
        # from before a rename; adding a second slot would break Discover.
        raise ValueError(
            f"{to.get('ident')} {tag} holds {found!r}, expected {uname!r}; "
            "rename it in tables.xml before running this script"
        )
    el = ET.Element(tag)
    el.text = uname
    # Mast slots come before the NX sensor slots, as JMRI stores them.
    kids = list(to)
    first_sensor = next((i for i, c in enumerate(kids) if c.tag.startswith("sensor")), None)
    if first_sensor is None:
        to.append(el)
    else:
        to.insert(first_sensor, el)
    return 1


def _ensure_hidden_icon(le: ET.Element, uname: str, x: int, y: int, deg: int) -> int:
    for ic in le.findall("signalmasticon"):
        if ic.get("signalmast") == uname and ic.get("hidden") == "yes":
            # Position may be nudged by other scripts; the direction is ours.
            if ic.get("degrees") == str(deg):
                return 0
            ic.set("degrees", str(deg))
            return 1
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
    _insert_tidy(le, list(le).index(first_to) if first_to is not None else len(le), ic)
    return 1


def _add_block_beans(
    root: ET.Element,
    ib: str,
    ilb: str,
    uname: str,
    sensor: str,
    station: str,
    hardware: str,
) -> None:
    blocks = root.find("blocks")
    lbs = root.find("layoutblocks")
    if blocks is None or lbs is None:
        raise SystemExit("missing blocks/layoutblocks")
    comment = (
        f"Hidden {station} throat (same detector as {station}); "
        f"occupancy {hardware}; not a station"
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
    # tables.xml keeps JMRI's stub+full pair.
    for el in (stub, full):
        ET.indent(el, space="  ", level=2)
    _insert_tidy(blocks, list(blocks).index(stubs[-1]) + 1 if stubs else len(blocks), stub)
    _insert_tidy(blocks, len(blocks), full)

    lb = ET.Element("layoutblock")
    lb.set("systemName", ilb)
    lb.set("occupancysensor", sensor)
    lb.set("occupiedsense", "2")
    lb.set("trackcolor", "gray")
    lb.set("occupiedcolor", "red")
    lb.set("extracolor", "white")
    ET.SubElement(lb, "systemName").text = ilb
    ET.SubElement(lb, "userName").text = uname
    ET.indent(lb, space="  ", level=2)
    _insert_tidy(lbs, len(lbs), lb)


def _split_s1_west(le: ET.Element) -> int:
    """Insert A81 and a short Track S-R West segment east of TOR14."""
    n = 0
    if any(pt.get("ident") == "A81" for pt in le.findall("positionablepoint")):
        # Still force the west-throat blockname if a previous run created A81.
        for ts in le.findall("tracksegment"):
            if ts.get("ident") == "F46-W-0" and ts.get("blockname") != S_R_WEST:
                ts.set("blockname", S_R_WEST)
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
    west.set("blockname", S_R_WEST)
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
    n = _scale_east_edits(root, le)
    if n:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return n


def _scale_east_edits(root: ET.Element, le: ET.Element) -> int:
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
            "IF$vsm:basic:one-low($1018)",
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
            "IF$vsm:basic:one-low($1019)",
            "Mast 14R",
        )
    n += _ensure_hidden_icon(le, "Mast 14R", 620, 305, 90)
    turnouts = {to.get("ident"): to for to in le.findall("layoutturnout")}
    to1 = turnouts.get("TO1")
    if to1 is not None:
        n += _ensure_turnout_mast(to1, "signalBMast", "Mast 14R")
    n += _ensure_eh_exits(le, masts, existing, turnouts)
    n += _ensure_rear_masts(root, le, masts, existing)
    return n


def _ensure_eh_exits(
    le: ET.Element,
    masts: ET.Element | None,
    existing: set[str],
    turnouts: dict[str, ET.Element],
) -> int:
    n = 0
    rows = [row + (None,) for row in EH_EXIT_MASTS] + list(BRICK_PLANE_MASTS)
    for ident, tag, sysname, uname, x, y, deg, comment in rows:
        if masts is not None:
            n += _ensure_virtual_mast(masts, existing, sysname, uname, comment)
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

    for _seg, uname, sensor, station, hardware in THROAT_SEGMENTS:
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
            hardware,
        )
        names.add(uname)
        ib_n += 1
        ilb_n += 1
        n += 1

    n += _split_s1_west(le)

    segs = {ts.get("ident"): ts for ts in le.findall("tracksegment")}
    for ident, uname, _sensor, _station, _hardware in THROAT_SEGMENTS:
        ts = segs.get(ident)
        if ts is None:
            continue
        if ts.get("blockname") != uname:
            ts.set("blockname", uname)
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

    # Scale/Switch 7, Mast 14R, the engine-house exits and Brick-Plane ends.
    n += _scale_east_edits(root, le)
    if n:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT)
    ap.add_argument("--sync-output", action="store_true")
    ap.add_argument(
        "--scale-east-only",
        action="store_true",
        help="Only the Scale/Switch 7, Mast 14R, engine-house exit, Brick-Plane and East Lead / K-1 rear masts; skip the South Yard throats.",
    )
    args = ap.parse_args()
    paths = [args.panel.resolve()]
    fn = apply_scale_east if args.scale_east_only else apply
    for path in paths:
        if not path.is_file():
            print(f"missing {path}")
            continue
        try:
            n = fn(path)
        except ValueError as exc:
            print(f"{path}: not changed: {exc}")
            return 1
        print(f"{path}: {n} edits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
