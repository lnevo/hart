#!/usr/bin/env python3
"""Apply the reviewed HART Layout Editor visual standard.

This script changes display geometry only.  It deliberately does not touch
track connectivity, turnout ports, block assignments, signal-mast bindings,
SML, CTC data, or hardware bean names.

The writable source is ``tables/new_tables.xml``.  Use ``--sync-output`` to
apply the same visual edits independently to the deployment bundle and the
standalone monitor panel; the files are never copied over one another.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PANEL = ROOT / "tables/new_tables.xml"
OUTPUT_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
STANDALONE_PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"

# Keep this list in sync with cats/scripts/add_digicon_le_signal_icons.py.
# Horizontal masts follow the North American right-hand placement convention:
# east-facing (90 degrees) below the rail, west-facing (270) above it.
SIGNAL_PLACEMENTS: dict[str, tuple[int, int, int]] = {
    "100L": (378, 222, 270),
    "101RA": (185, 258, 90),
    "101RB": (185, 321, 90),
    "102LA": (360, 297, 270),
    "102LB": (365, 345, 270),
    # 117 east homes sit just east of the diamond, not out on 116 / engine house.
    "117RA": (435, 321, 90),
    "117LB": (534, 297, 270),
    "117RB": (425, 368, 90),
    "117LA": (534, 344, 270),
    "111RA": (1095, 258, 90),
    "111L": (1225, 222, 270),
    "111RB": (1135, 321, 90),
    "112L": (1392, 285, 270),
    "110R": (1248, 350, 60),
    "112R": (1320, 348, 60),
    "115LB": (1608, 185, 225),
    "113RA": (1465, 258, 90),
    "113RB": (1465, 321, 90),
    "114LB": (1628, 322, 310),
    "115R": (1810, 276, 180),
    "114R": (1855, 276, 0),
    "115LA": (1665, 239, 270),
    "114LA": (1665, 302, 270),
}

SIGNAL_ICON_SCALE = "1.0"
REDUNDANT_OCCUPANCY_SENSOR = re.compile(r"Block \d+-\d+")
REMOVED_LABELS = {"South Yard East", "Main East", "Main West"}

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
    named = 1 if le.get("name") in {"HART", "My Layout"} else 0
    return named, geometry


def find_layout_editor(root: ET.Element) -> ET.Element:
    editors = list(root.findall("LayoutEditor"))
    candidates = [le for le in editors if len(le.findall("tracksegment")) >= 90]
    if len(candidates) != 1:
        details = [(le.get("name"), len(le.findall("tracksegment"))) for le in editors]
        raise ValueError(f"expected one HART geometry panel, found {details}")
    return max(candidates, key=_panel_score)


def _set_xy(el: ET.Element, x: int, y: int) -> bool:
    changed = el.get("x") != str(x) or el.get("y") != str(y)
    el.set("x", str(x))
    el.set("y", str(y))
    return changed


def apply_visual_standard(path: Path, *, check: bool = False) -> tuple[int, list[str]]:
    tree = ET.parse(path)
    root = tree.getroot()
    le = find_layout_editor(root)
    changes = 0
    errors: list[str] = []

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
        if point.get("x") == str(x) and point.get("y") == str(y):
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

    # Layout Editor track coloring already provides occupancy indication.
    # Retain the sensor beans for Dispatcher/CTC logic, but omit their
    # duplicate dots from the geographic monitor.
    for icon in list(le.findall("sensoricon")):
        name = (icon.get("sensor") or "").strip()
        if not REDUNDANT_OCCUPANCY_SENSOR.fullmatch(name):
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
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return changes, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument(
        "--sync-output",
        action="store_true",
        help="Also patch output/tables.xml and output/hart_prod.xml independently",
    )
    ap.add_argument("--check", action="store_true", help="Validate without writing")
    args = ap.parse_args()

    paths = [args.panel.resolve()]
    if args.sync_output and args.panel.resolve() == DEFAULT_PANEL.resolve():
        paths.extend([OUTPUT_TABLES, STANDALONE_PANEL])

    all_errors: list[str] = []
    for path in paths:
        if not path.is_file():
            all_errors.append(f"missing {path}")
            continue
        changes, errors = apply_visual_standard(path, check=args.check)
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
