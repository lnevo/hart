#!/usr/bin/env python3
"""Apply the reviewed HART Layout Editor visual standard.

This script changes display geometry only.  It deliberately does not touch
track connectivity, turnout ports, block assignments, signal-mast bindings,
SML, CTC data, or hardware bean names.

The writable source is ``jmri/layouts/hart/output/tables.xml``.  ``--sync-output`` has had
no effect since ADR-008.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

ROOT = paths.REPO_ROOT
DEFAULT_PANEL = paths.TABLES_XML

# Keep this list in sync with jmri/layouts/hart/scripts/add_digicon_le_signal_icons.py.
# Horizontal masts follow the North American right-hand placement convention:
# east-facing (90 degrees) below the rail, west-facing (270) above it.
SIGNAL_PLACEMENTS: dict[str, tuple[int, int, int]] = {
    "Mast 2L": (378, 222, 270),
    "Mast 4RA": (185, 258, 90),
    "Mast 4RB": (185, 321, 90),
    "Mast 6LA": (366, 290, 270),
    "Mast 6LB": (366, 338, 270),
    # 117 east homes sit just east of the diamond, not out on 116 / engine house.
    "Mast 8RA": (445, 327, 90),
    "Mast 8LB": (552, 290, 270),
    "Mast 8RB": (445, 374, 90),
    "Mast 8LA": (529, 341, 270),
    "Mast 24RA": (1095, 263, 90),
    "Mast 24L": (1248, 218, 270),
    "Mast 24RB": (1095, 326, 90),
    "Mast 34L": (1392, 289, 270),
    "Mast 32R": (1265, 349, 60),
    "Mast 34R": (1320, 348, 60),
    "Mast 40LB": (1640, 170, 225),
    "Mast 36RA": (1465, 264, 90),
    "Mast 36RB": (1465, 325, 90),
    "Mast 38LB": (1654, 340, 310),
    "Mast 2035": (1848, 245, 0),
    "Mast 2036": (1816, 291, 180),
    "Mast 40LA": (1665, 222, 270),
    "Mast 38LA": (1665, 285, 270),
}

SIGNAL_ICON_SCALE = "1.0"
REDUNDANT_OCCUPANCY_SENSOR = re.compile(r"Block \d+-\d+")
# Dispatcher System Stage 1 occupancy dots on OS / plant blocks.
# Same circuit-occupied.gif set as CreateIcons.addOccupancyIconsAndLabels.
# Shared occupancy (body + hidden throats, or OS + stub) gets one circuit dot.
# Keep the body / points icon; drop the extras CreateIcons stacks on the same sensor.
# South Yard: one column mid-yard, centred on each track (y 315 / 366 / 413 /
# 460 / 502), below the track-name labels at x 953. Used for both the Stage 1
# lamp placement and the dedupe keep spot.
LAMP_COLUMN_X = 985  # mid-yard column shared by the South Yard and the mains
SOUTH_YARD_LAMPS = {
    "BS S-R": (LAMP_COLUMN_X, 310),
    "BS S-1": (LAMP_COLUMN_X, 361),
    "BS S-2": (LAMP_COLUMN_X, 408),
    "BS S-3": (LAMP_COLUMN_X, 455),
    "BS S-4": (LAMP_COLUMN_X, 497),
}
# Sensors that can get more than one Stage 1 lamp; one is kept, at its target.
SHARED_OCCUPANCY_KEEP = (
    *SOUTH_YARD_LAMPS,
    "BS Switch 37 / BS McKeesport",
    "BS Switch 39 / BS McKees Rocks",
)
# Switch OS lamps that must exist. Where they go comes from stage1_lamp_targets().
OS_OCCUPANCY_ICONS = (
    "BS Switch 3",
    "BS Switch 1",
    "BS Switch 5",
    "BS Switch 13",
    "BS Switch 15",
    "BS Switch 17",
    "BS Switch 19",
    "BS Switch 21",
    "BS Switch 25",
    "BS Switch 27",
    "BS Switch 23a",
    "BS Switch 29",
    "BS Switch 31",
    "BS Switch 33",
    "BS Switch 11",
    "BS Switch 7",
    "BS Switch 9",
    "BS Switch 35b",
    "BS Switch 35a",
)
# Stage 1 (CreateIcons) occupancy lamps go where they belong: a switch's OS
# lamp centred in its turnout circle, a track's lamp centred on the track
# (owner, 2026-11-13). Positions are the top-left of the 10x10 circuit GIF.
# The level-12 lamps in the Dispatcher station clusters belong to
# reconcile_dispatcher_stations.py and are left alone.
# Engine house: one lamp just east of each bumper (x=573), centred vertically
# on its spur (y 266 / 277 / 289), clear of the Switch 9 and 11 circles.
CLUSTER_LAMP_LEVEL = "12"
# Fixed spots that win over the computed ones (owner-approved 2026-11-12/13).
# Every other Stage 1 lamp is placed by stage1_lamp_targets(): a switch's OS
# lamp centred in its turnout circle, a track's lamp centred on the track.
STAGE1_LAMP_PLACEMENTS = {
    # Mains in the South Yard lamp column (x 985), on their own track (owner,
    # 2026-11-13): Main West along the top (y 252), Main East along the
    # bottom (y 550).
    "BS Main West": (LAMP_COLUMN_X, 247),
    "BS Main East": (LAMP_COLUMN_X, 545),
    # West Yard: at the bumper end of each spur (x 55), like the engine house.
    "BS W-1": (58, 247),
    "BS W-2": (58, 310),
    "BS EH-1": (576, 261),
    "BS EH-2": (576, 272),
    "BS EH-3": (576, 284),
    **SOUTH_YARD_LAMPS,
}
REMOVED_LABELS = {
    "OS East Lead",
    "OS Main East",
    "OS Main West",
    "Track East Lead",
    "Track Main East",
    "Track Main West",
}

# ADR-002 visible hierarchy.
LABEL_STYLE: dict[str, tuple[str, str]] = {
    "Neville Island": ("28", "1"),
    "Brick": ("16", "1"),
    "Plane": ("16", "1"),
    "Barn": ("16", "1"),
    "East End": ("16", "1"),
    "Princess": ("16", "1"),
    "West Yard": ("16", "0"),
    "South Yard": ("16", "0"),
    "Industries": ("16", "0"),
}

# South Yard track names. The Dispatcher station buttons carried them until
# South Yard stopped being stations (2026-11-12); plain labels sit in the same
# spots, in the buttons' size-10 bold grey text.
TRACK_NAME_LABELS: dict[str, tuple[int, int]] = {
    "Track S-R": (953, 293),
    "Track S-1": (953, 344),
    "Track S-2": (953, 391),
    "Track S-3": (953, 438),
    "Track S-4": (953, 480),
}


def _track_name_label(text: str, x: int, y: int) -> ET.Element:
    label = ET.Element("positionablelabel")
    for attr, value in (
        ("x", str(x)), ("y", str(y)), ("level", "4"), ("forcecontroloff", "false"),
        ("hidden", "no"), ("positionable", "true"), ("showtooltip", "true"),
        ("editable", "false"), ("text", text), ("size", "10"), ("style", "1"),
        ("red", "51"), ("green", "51"), ("blue", "51"), ("hasBackground", "no"),
        ("justification", "left"),
        ("class", "jmri.jmrit.display.configurexml.PositionableLabelXml"),
    ):
        label.set(attr, value)
    return label


def ensure_track_name_labels(le: ET.Element, *, check: bool) -> tuple[int, list[str]]:
    changes = 0
    errors: list[str] = []
    labels = [l for l in le.findall("positionablelabel")]
    for text, (x, y) in TRACK_NAME_LABELS.items():
        found = [l for l in labels if (l.get("text") or "").strip() == text]
        if len(found) == 1 and _same_number(found[0].get("x"), x) and _same_number(found[0].get("y"), y):
            continue
        if check:
            errors.append(f"track name label {text!r}: {len(found)} found, expected one at ({x}, {y})")
            continue
        for extra in found:
            le.remove(extra)
        first = next((i for i, c in enumerate(le) if c.tag == "positionablelabel"), len(le))
        le.insert(first, _track_name_label(text, x, y))
        changes += 1
    return changes, errors


LABEL_PLACEMENTS: dict[str, tuple[tuple[int, int], ...]] = {
    "116": ((572, 270),),
    "Barn": ((464, 430),),
    "Princess": ((1510, 170),),
    "114": ((1570, 340),),
    "115": ((1570, 220),),
    "Track 1": ((103, 230), (943, 293), (1730, 230)),
    "Track 2": ((105, 293), (943, 344), (1730, 293)),
}

TURNOUT_GEOMETRY = {
    "TOR36": {
        "xcen": "1602.5",
        "xa": "1586.0",
        "xb": "1619.0",
        "xc": "1612.0999755859375",
        "xd": "1586.0",
    },
}

ANCHOR_POSITIONS = {
    "A55": (1639, 315),
    "A62": (1623, 334),
}

EXPECTED_TURNOUT_DEFAULTS = {
    "mainlinetrackwidth": "4",
    "sidetrackwidth": "2",
    "turnoutcirclesize": "3",
    "turnoutbx": "30.0",
    "turnoutcx": "30.0",
    "turnoutwid": "15.0",
    "xoverlong": "45.0",
    "xoverhwid": "15.0",
    "xovershort": "15.0",
    "xscale": "1.0",
    "yscale": "1.0",
}


def _panel_score(le: ET.Element) -> tuple[int, int]:
    """Prefer the railroad LayoutEditor and never the command panel."""
    geometry = len(le.findall("tracksegment")) + len(le.findall("layoutturnout"))
    named = 1 if le.get("name") in {"HART Railroad", "HART", "My Layout"} else 0
    return named, geometry


def find_layout_editor(root: ET.Element) -> ET.Element:
    editors = list(root.findall("LayoutEditor"))
    candidates = [le for le in editors if len(le.findall("tracksegment")) >= 90]
    if len(candidates) != 1:
        details = [(le.get("name"), len(le.findall("tracksegment"))) for le in editors]
        raise ValueError(f"expected one HART geometry panel, found {details}")
    return max(candidates, key=_panel_score)


# Layout Editor draws tracks at level 3. Labels at 4 sit on top. Level 0 is
# behind the panel background, so BlockContentsIcon text never shows.
BCI_LEVEL = "4"
BCI_COLOR = ("0", "0", "0")
BCI_DROP_FONT_ATTRS = ("fontFamily", "fontname")
# Stage 1 (CreateIcons) puts the engine-house train names on Switch 9 and 11,
# where they overlap the OS Switch 9 / 11 labels. Each sits on its spur's
# Dispatcher button row instead, at x 794 clear of the station buttons.
BCI_PLACEMENTS = {
    "Track EH-1": (794, 256),
    "Track EH-2": (794, 270),
    "Track EH-3": (794, 284),
}


def ensure_block_contents_visible(le: ET.Element, *, check: bool) -> tuple[int, list[str]]:
    """Put block-value labels on the label layer with default Dialog/black text."""
    changes = 0
    errors: list[str] = []
    for icon in le.findall("BlockContentsIcon"):
        name = icon.get("blockcontents") or "?"
        if icon.get("level") != BCI_LEVEL:
            if check:
                errors.append(
                    f"BlockContentsIcon {name!r} level={icon.get('level')!r}, "
                    f"expected {BCI_LEVEL}"
                )
            else:
                icon.set("level", BCI_LEVEL)
                changes += 1
        for attr, value in zip(("red", "green", "blue"), BCI_COLOR, strict=True):
            if icon.get(attr) == value:
                continue
            if check:
                errors.append(
                    f"BlockContentsIcon {name!r} {attr}={icon.get(attr)!r}, "
                    f"expected {value!r}"
                )
            else:
                icon.set(attr, value)
                changes += 1
        for attr in BCI_DROP_FONT_ATTRS:
            if attr not in icon.attrib:
                continue
            if check:
                errors.append(f"BlockContentsIcon {name!r} still has {attr}")
            else:
                del icon.attrib[attr]
                changes += 1
        if name in BCI_PLACEMENTS:
            x, y = BCI_PLACEMENTS[name]
            if not (_same_number(icon.get("x"), x) and _same_number(icon.get("y"), y)):
                if check:
                    errors.append(
                        f"BlockContentsIcon {name!r} at ({icon.get('x')}, {icon.get('y')}), "
                        f"expected ({x}, {y})"
                    )
                else:
                    icon.set("x", str(x))
                    icon.set("y", str(y))
                    changes += 1
    return changes, errors


def _same_number(stored: str | None, wanted: int) -> bool:
    try:
        return float(stored or "") == float(wanted)
    except ValueError:
        return False


def _set_xy(el: ET.Element, x: int, y: int) -> bool:
    changed = el.get("x") != str(x) or el.get("y") != str(y)
    el.set("x", str(x))
    el.set("y", str(y))
    return changed


def _circuit_occupancy_icon(sensor: str, x: int, y: int) -> ET.Element:
    icon = ET.Element(
        "sensoricon",
        {
            "sensor": sensor,
            "x": str(x),
            "y": str(y),
            "level": "10",
            "forcecontroloff": "false",
            "hidden": "no",
            "positionable": "true",
            "showtooltip": "true",
            "editable": "true",
            "momentary": "false",
            "icon": "yes",
            "class": "jmri.jmrit.display.configurexml.SensorIconXml",
        },
    )
    for state, url in (
        ("active", "program:resources/icons/smallschematics/tracksegments/circuit-occupied.gif"),
        ("inactive", "program:resources/icons/smallschematics/tracksegments/circuit-empty.gif"),
        ("unknown", "program:resources/icons/smallschematics/tracksegments/circuit-error.gif"),
        ("inconsistent", "program:resources/icons/smallschematics/tracksegments/circuit-error.gif"),
    ):
        child = ET.SubElement(icon, state, {"url": url, "degrees": "0", "scale": "1.0"})
        ET.SubElement(child, "rotation").text = "0"
    ET.SubElement(icon, "iconmaps")
    return icon


def _os_icon_insert_index(le: ET.Element, x: int, y: int) -> int:
    """Place the circuit dot immediately before its OS BlockContentsIcon."""
    children = list(le)
    label_x, label_y = str(x), str(y - 30)
    for idx, child in enumerate(children):
        if (
            child.tag == "BlockContentsIcon"
            and child.get("x") == label_x
            and child.get("y") == label_y
        ):
            return idx
    for idx, child in enumerate(children):
        if child.tag == "layoutturnout":
            return idx
    return len(children)


def ensure_os_occupancy_icons(
    le: ET.Element, *, check: bool, targets: dict[str, tuple[int, int]]
) -> tuple[int, list[str]]:
    """Keep Dispatcher System OS occupancy dots on HART Railroad, at their targets."""
    changes = 0
    errors: list[str] = []
    existing = {
        (icon.get("sensor") or "").strip()
        for icon in le.findall("sensoricon")
        if (icon.get("sensor") or "").strip() in OS_OCCUPANCY_ICONS
    }
    missing = [name for name in OS_OCCUPANCY_ICONS if name not in existing]
    if check:
        for name in missing:
            errors.append(f"missing OS occupancy icon {name!r}")
        return 0, errors
    for name in missing:
        if name not in targets:
            errors.append(f"no target for missing OS occupancy icon {name!r}")
            continue
        x, y = targets[name]
        le.insert(_os_icon_insert_index(le, x, y), _circuit_occupancy_icon(name, x, y))
        changes += 1
    return changes, errors


LAMP_SIZE = 10  # circuit-*.gif is 10x10; x/y is its top-left corner


def _segment_ends(le: ET.Element) -> list[tuple[str, tuple[float, float], tuple[float, float], bool, str]]:
    """(block, end1, end2, curved, ident) for each track segment."""
    points = {
        pt.get("ident"): (float(pt.get("x")), float(pt.get("y")))
        for pt in le.findall("positionablepoint")
    }
    turnouts = {to.get("ident"): to for to in le.findall("layoutturnout")}

    def end(name: str | None, kind: str | None) -> tuple[float, float] | None:
        if name in points:
            return points[name]
        to = turnouts.get(name or "")
        if to is None:
            return None
        leg = {"TURNOUT_A": "a", "TURNOUT_B": "b", "TURNOUT_C": "c", "TURNOUT_D": "d"}.get(kind or "")
        if leg and to.get(f"x{leg}") is not None:
            return float(to.get(f"x{leg}")), float(to.get(f"y{leg}"))
        return float(to.get("xcen")), float(to.get("ycen"))

    out = []
    for ts in le.findall("tracksegment"):
        a = end(ts.get("connect1name"), ts.get("type1"))
        b = end(ts.get("connect2name"), ts.get("type2"))
        if a is None or b is None:
            continue
        if ts.get("hidden") == "yes":
            continue
        curved = "yes" in (ts.get("arc"), ts.get("bezier"), ts.get("circle"))
        out.append((ts.get("blockname") or "", a, b, curved, ts.get("ident") or ""))
    return out


def stage1_lamp_targets(root: ET.Element, le: ET.Element) -> dict[str, tuple[int, int]]:
    """Where each Stage 1 occupancy lamp belongs, from the panel geometry.

    A sensor whose block is a switch's OS block goes in the centre of that
    turnout circle. Otherwise it goes in the middle of the longest straight
    segment of its track, leaving out hidden throat blocks that share it.
    """
    blocks_by_sensor: dict[str, list[str]] = {}
    throats: set[str] = set()
    for blocks in root.findall("blocks"):
        for block in blocks.findall("block"):
            sensor = (block.findtext("occupancysensor") or "").strip()
            name = (block.findtext("userName") or "").strip()
            if not sensor or not name:
                continue
            blocks_by_sensor.setdefault(sensor, []).append(name)
    # A hidden throat shares its station's detector and is named after it
    # ("Track S-1 West", "Track East Lead East"); no reliance on comments,
    # which Stage 1 drops.
    for names in blocks_by_sensor.values():
        for name in names:
            if any(name != other and name.startswith(other + " ") for other in names):
                throats.add(name)
    turnout_by_block: dict[str, ET.Element] = {}
    # Only a turnout's own block makes an OS block; per-leg blocks are track.
    for to in le.findall("layoutturnout"):
        if to.get("blockname"):
            turnout_by_block.setdefault(to.get("blockname"), to)
    segments = _segment_ends(le)
    half = LAMP_SIZE / 2
    targets: dict[str, tuple[int, int]] = {}
    for sensor, names in blocks_by_sensor.items():
        os_blocks = [n for n in names if n in turnout_by_block]
        if os_blocks:
            to = turnout_by_block[os_blocks[0]]
            cx, cy = float(to.get("xcen")), float(to.get("ycen"))
        else:
            # Straight track of the block itself first; a track drawn only as
            # curves (K-1's loop) falls back to its straight throat stub, since
            # a curve's chord midpoint can sit off the drawn track.
            mains = [n for n in names if n not in throats] or names
            main_pieces = [seg for seg in segments if seg[0] in mains]
            all_pieces = [seg for seg in segments if seg[0] in names]
            if not all_pieces:
                continue
            straight = (
                [seg for seg in main_pieces if not seg[3]]
                or [seg for seg in all_pieces if not seg[3]]
                or main_pieces
                or all_pieces
            )
            _b, a, b, _c, _i = max(
                straight, key=lambda seg: ((seg[1][0] - seg[2][0]) ** 2 + (seg[1][1] - seg[2][1]) ** 2, seg[4])
            )
            cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        targets[sensor] = (round(cx - half), round(cy - half))
    targets.update(STAGE1_LAMP_PLACEMENTS)
    return targets


def _is_circuit_lamp(icon: ET.Element) -> bool:
    active = icon.find("active")
    # A bare test icon has no state children; treat it as a lamp.
    return active is None or "circuit-" in (active.get("url") or "")


def place_stage1_lamps(
    le: ET.Element, *, check: bool, targets: dict[str, tuple[int, int]]
) -> tuple[int, list[str]]:
    """Put each Stage 1 occupancy lamp on its target, one lamp per sensor.

    A copy already on the target is the one kept; any other Stage 1 copy of
    the same sensor is removed, so copies never stack on one spot.
    """
    changes = 0
    errors: list[str] = []
    by_sensor: dict[str, list[ET.Element]] = {}
    for icon in le.findall("sensoricon"):
        name = (icon.get("sensor") or "").strip()
        if name in targets and icon.get("level") != CLUSTER_LAMP_LEVEL and _is_circuit_lamp(icon):
            by_sensor.setdefault(name, []).append(icon)
    for name, icons in by_sensor.items():
        x, y = targets[name]
        on_spot = [i for i in icons if _same_number(i.get("x"), x) and _same_number(i.get("y"), y)]
        keep = on_spot[0] if on_spot else icons[0]
        for extra in icons:
            if extra is keep:
                continue
            if check:
                errors.append(f"{name}: more than one Stage 1 lamp")
            else:
                le.remove(extra)
                changes += 1
        if keep in on_spot:
            continue
        if check:
            errors.append(f"{name} at ({keep.get('x')}, {keep.get('y')}), expected ({x}, {y})")
        else:
            _set_xy(keep, x, y)
            changes += 1
    return changes, errors


def dedupe_shared_occupancy_icons(
    le: ET.Element, *, check: bool, targets: dict[str, tuple[int, int]]
) -> tuple[int, list[str]]:
    """Keep one Stage 1 lamp per shared occupancy sensor, the one at its target."""
    changes = 0
    errors: list[str] = []
    by_name: dict[str, list[ET.Element]] = {}
    for icon in le.findall("sensoricon"):
        name = (icon.get("sensor") or "").strip()
        # The level-12 cluster lamp shares the sensor and belongs to
        # reconcile_dispatcher_stations.py; only Stage 1 copies count here.
        if name in SHARED_OCCUPANCY_KEEP and name in targets and icon.get("level") != CLUSTER_LAMP_LEVEL:
            by_name.setdefault(name, []).append(icon)
    for name, icons in by_name.items():
        keep_x, keep_y = targets[name]
        keepers = [i for i in icons if _same_number(i.get("x"), keep_x) and _same_number(i.get("y"), keep_y)]
        extras = [i for i in icons if i not in keepers[:1]] if keepers else icons[1:]
        if check:
            if extras:
                errors.append(
                    f"duplicate occupancy icon {name!r} count={len(icons)}, "
                    f"expected 1 at {keep_x},{keep_y}"
                )
            continue
        for icon in extras:
            le.remove(icon)
            changes += 1
    return changes, errors

def apply_visual_standard(path: Path, *, check: bool = False) -> tuple[int, list[str]]:
    doc = tables.load(path)
    root = doc.root
    le = find_layout_editor(root)
    changes = 0
    errors: list[str] = []

    track_n, track_errors = ensure_track_name_labels(le, check=check)
    changes += track_n
    errors.extend(f"{path.name}: {e}" for e in track_errors)

    for attr, expected in EXPECTED_TURNOUT_DEFAULTS.items():
        actual = le.get(attr)
        if actual != expected:
            if check:
                errors.append(f"{path.name}: LayoutEditor {attr}={actual!r}, expected {expected!r}")
            else:
                le.set(attr, expected)
                changes += 1

    for ident, expected_attrs in TURNOUT_GEOMETRY.items():
        rows = [
            turnout
            for turnout in le.findall("layoutturnout")
            if turnout.get("ident") == ident
        ]
        if len(rows) != 1:
            errors.append(
                f"{path.name}: layoutturnout {ident!r} count={len(rows)}, expected 1"
            )
            continue
        turnout = rows[0]
        for attr, value in expected_attrs.items():
            if turnout.get(attr) == value:
                continue
            if check:
                errors.append(
                    f"{path.name}: {ident} {attr}={turnout.get(attr)!r}, "
                    f"expected {value!r}"
                )
            else:
                turnout.set(attr, value)
                changes += 1

    for ident, (x, y) in ANCHOR_POSITIONS.items():
        rows = [
            point
            for point in le.findall("positionablepoint")
            if point.get("ident") == ident
        ]
        if len(rows) != 1:
            errors.append(
                f"{path.name}: positionablepoint {ident!r} count={len(rows)}, expected 1"
            )
            continue
        point = rows[0]
        # JMRI stores anchors as floats ("1639.0"); compare the numbers.
        if _same_number(point.get("x"), x) and _same_number(point.get("y"), y):
            continue
        if check:
            errors.append(
                f"{path.name}: {ident} at ({point.get('x')}, {point.get('y')}), "
                f"expected ({x}, {y})"
            )
        else:
            _set_xy(point, x, y)
            changes += 1

    icons: dict[str, ET.Element] = {}
    for icon in le.findall("signalmasticon"):
        name = icon.get("signalmast") or ""
        if name in SIGNAL_PLACEMENTS:
            if name in icons:
                errors.append(f"{path.name}: duplicate signalmasticon {name!r}")
            icons[name] = icon

    missing = sorted(set(SIGNAL_PLACEMENTS) - set(icons))
    extra = sorted(set(icons) - set(SIGNAL_PLACEMENTS))
    if missing:
        errors.append(f"{path.name}: missing signal icons: {', '.join(missing)}")
    if extra:
        errors.append(f"{path.name}: unexpected managed signal icons: {', '.join(extra)}")

    for name, (x, y, degrees) in SIGNAL_PLACEMENTS.items():
        icon = icons.get(name)
        if icon is None:
            continue
        expected = {
            "x": str(x),
            "y": str(y),
            "degrees": str(degrees),
            "scale": SIGNAL_ICON_SCALE,
        }
        for attr, value in expected.items():
            if icon.get(attr) == value:
                continue
            if check:
                errors.append(
                    f"{path.name}: {name} {attr}={icon.get(attr)!r}, expected {value!r}"
                )
            else:
                icon.set(attr, value)
                changes += 1

    bci_changes, bci_errors = ensure_block_contents_visible(le, check=check)
    changes += bci_changes
    errors.extend(bci_errors)

    targets = stage1_lamp_targets(root, le)
    os_added, os_errors = ensure_os_occupancy_icons(le, check=check, targets=targets)
    changes += os_added
    errors.extend(os_errors)

    shared_n, shared_errors = dedupe_shared_occupancy_icons(le, check=check, targets=targets)
    changes += shared_n
    errors.extend(shared_errors)

    # Layout Editor track coloring already provides occupancy indication
    # for leftover Block n-n sensors. Keep Dispatcher System OS occupancy
    # dots; omit other duplicate occupancy icons from the monitor.
    for icon in list(le.findall("sensoricon")):
        name = (icon.get("sensor") or "").strip()
        if not REDUNDANT_OCCUPANCY_SENSOR.fullmatch(name):
            continue
        if name in OS_OCCUPANCY_ICONS:
            continue
        if check:
            errors.append(f"{path.name}: redundant occupancy icon {name!r}")
        else:
            le.remove(icon)
            changes += 1

    for label in list(le.findall("positionablelabel")):
        text = (label.get("text") or "").strip()
        if text in REMOVED_LABELS:
            if check:
                errors.append(f"{path.name}: removed label remains: {text!r}")
            else:
                le.remove(label)
                changes += 1
            continue
        if re.fullmatch(r"SIG (Brick|Plane|East End|Princess) [WE]", text):
            if check:
                errors.append(f"{path.name}: stale signal placeholder {text!r}")
            else:
                le.remove(label)
                changes += 1
            continue
        if text in LABEL_STYLE:
            size, style = LABEL_STYLE[text]
            for attr, value in (("size", size), ("style", style)):
                if label.get(attr) == value:
                    continue
                if check:
                    errors.append(
                        f"{path.name}: label {text!r} {attr}={label.get(attr)!r}, "
                        f"expected {value!r}"
                    )
                else:
                    label.set(attr, value)
                    changes += 1
        if re.fullmatch(r"1(?:0[0-9]|1[0-9])", text):
            for attr, value in (("size", "13"), ("style", "1")):
                if label.get(attr) == value:
                    continue
                if check:
                    errors.append(
                        f"{path.name}: equipment label {text} {attr}={label.get(attr)!r}, "
                        f"expected {value!r}"
                    )
                else:
                    label.set(attr, value)
                    changes += 1

    for text, positions in LABEL_PLACEMENTS.items():
        labels = sorted(
            [
                label
                for label in le.findall("positionablelabel")
                if (label.get("text") or "").strip() == text
            ],
            key=lambda label: (
                int(label.get("x", "0")),
                int(label.get("y", "0")),
            ),
        )
        if not labels:
            continue
        if len(labels) != len(positions):
            errors.append(
                f"{path.name}: label {text!r} count={len(labels)}, "
                f"expected {len(positions)}"
            )
            continue
        for label, (x, y) in zip(labels, positions):
            if label.get("x") == str(x) and label.get("y") == str(y):
                continue
            if check:
                errors.append(
                    f"{path.name}: label {text!r} at "
                    f"({label.get('x')}, {label.get('y')}), expected ({x}, {y})"
                )
            else:
                _set_xy(label, x, y)
                changes += 1

    if check:
        return changes, errors
    doc.save(path)
    return changes, errors


def apply_overlap_cleanup(path: Path, *, check: bool = False) -> tuple[int, list[str]]:
    """Shrink-LE companion: keep Pi mast nudges, hide virtuals, put Stage 1 lamps on their targets.

    Does not add OS Block n-n icons or restripe station occupancy.
    """
    doc = tables.load(path)
    le = find_layout_editor(doc.root)
    changes = 0
    errors: list[str] = []

    for icon in le.findall("signalmasticon"):
        name = (icon.get("signalmast") or "").strip()
        if name in SIGNAL_PLACEMENTS:
            x, y, degrees = SIGNAL_PLACEMENTS[name]
            expected = {
                "x": str(x),
                "y": str(y),
                "degrees": str(degrees),
                "hidden": "no",
            }
        else:
            expected = {"hidden": "yes"}
        for attr, value in expected.items():
            if icon.get(attr) == value:
                continue
            if check:
                errors.append(
                    f"{path.name}: {name} {attr}={icon.get(attr)!r}, expected {value!r}"
                )
            else:
                icon.set(attr, value)
                changes += 1

    # Placing also removes extra copies, so no separate dedupe pass is needed.
    lamp_n, lamp_errors = place_stage1_lamps(
        le, check=check, targets=stage1_lamp_targets(doc.root, le)
    )
    changes += lamp_n
    errors.extend(f"{path.name}: {e}" for e in lamp_errors)

    if check:
        return changes, errors
    doc.save(path)
    return changes, errors


def apply_block_labels_only(path: Path, *, check: bool) -> tuple[int, list[str]]:
    """Lift BlockContentsIcons to level 4 and put Stage 1 lamps on their targets.

    A Stage 1 Store resets both, so the deploy and Stage 1 wrapper run this.
    """
    doc = tables.load(path)
    le = find_layout_editor(doc.root)
    changes, errors = ensure_block_contents_visible(le, check=check)
    lamp_n, lamp_errors = place_stage1_lamps(
        le, check=check, targets=stage1_lamp_targets(doc.root, le)
    )
    changes += lamp_n
    errors.extend(f"{path.name}: {e}" for e in lamp_errors)
    if check or not changes:
        return changes, errors
    doc.save(path)
    return changes, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument(
        "--sync-output",
        action="store_true",
        help="No effect since ADR-008; kept for existing callers",
    )
    ap.add_argument("--check", action="store_true", help="Validate without writing")
    ap.add_argument(
        "--block-labels-only",
        action="store_true",
        help="Only restore BlockContentsIcon level/color and Stage 1 lamp spots (safe after Stage 1 Store).",
    )
    ap.add_argument(
        "--overlap-cleanup",
        action="store_true",
        help="Pi mast nudges, hide virtuals, drop shared occupancy duplicates only.",
    )
    args = ap.parse_args()

    panels = [args.panel.resolve()]

    if args.overlap_cleanup:
        apply_fn = apply_overlap_cleanup
    elif args.block_labels_only:
        apply_fn = apply_block_labels_only
    else:
        apply_fn = apply_visual_standard
    all_errors: list[str] = []
    for path in panels:
        if not path.is_file():
            all_errors.append(f"missing {path}")
            continue
        try:
            changes, errors = apply_fn(path, check=args.check)
        except RuntimeError as exc:  # hartlib save refuses while PanelPro or CATS is open
            all_errors.append(f"{path}: not changed: {exc}")
            continue
        all_errors.extend(errors)
        verb = "checked" if args.check else "updated"
        print(f"{verb} {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {changes} changes")

    if all_errors:
        print("FAIL")
        for error in all_errors:
            print(f"  - {error}")
        return 1
    print("PASS HART Layout Editor visual standard" if args.check else "Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
