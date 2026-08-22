#!/usr/bin/env python3
"""Reconcile the HART JMRI Dispatcher stations and their panel icons.

The working target defaults to ``tables/new_tables.xml``.  ``tables/tables.xml``
is a read-only snapshot and is explicitly rejected.  A normal run applies the
same reconciliation independently to ``jmri/layouts/hart/output/tables.xml``;
it never copies one complete configuration over the other.  Use ``--no-sync``
to skip the deployment bundle.  ``--check`` validates without writing.

This script deliberately leaves all existing sections, transits, and traininfo
untouched. Run Dispatcher Stage 1 and Stage 2 in PanelPro only when the
generated graph is absent or the audit reports it stale.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PANEL = ROOT / "tables" / "new_tables.xml"
READ_ONLY_PANEL = ROOT / "tables" / "tables.xml"
SYNC_PANEL = ROOT / "jmri" / "layouts" / "hart" / "output" / "tables.xml"

STATIONS = (
    "Main West",
    "West Main Ext",
    "McKees Rocks",
    "McKeesport",
    "South Yard East",
    "Main East",
    "East Main Ext",
    "Brick-Plane",
    "Engine House 1",
    "Engine House 2",
    "Engine House 3",
    "S-1",
    "S-2",
    "S-3",
    "S-4",
    "S-5",
    "Scale",
    "Barn",
    "West Yard 1",
    "West Yard 2",
    "K-1",
    "K-2",
)

INTERNAL_SENSOR_CLASS = "jmri.jmrix.internal.configurexml.InternalSensorManagerXml"
STOP_TOKEN = "stop"
# Progress is x-10 from MoveTo. Occupancy is MoveTo + (-10, +10) unless
# the station uses a left-right circuit row (engine house).
PAIR_DX = 10
OCCUPANCY_OFFSET = (-10, 10)
CIRCUIT_ICON_SIZE = 10
EH_ROW_STATIONS = frozenset(
    {"Engine House 1", "Engine House 2", "Engine House 3"}
)

# Progress icon position; the clickable MoveTo icon sits PAIR_DX to its right.
# Main West / Main East / Brick-Plane keep the progress lamp and pull MoveTo in.
# The other original five pull progress right to meet the existing MoveTo.
STATION_ICON_POSITIONS = {
    "Brick-Plane": (240, 293),
    "East Main Ext": (376, 390),
    "Main West": (943, 230),
    "Main East": (943, 520),
    "West Main Ext": (1416, 210),
    "South Yard East": (1416, 345),
    "McKees Rocks": (1706, 185),
    "McKeesport": (1706, 345),
    # Engine house: east/right of the 116 ladder.
    "Engine House 1": (668, 256),
    "Engine House 2": (668, 270),
    "Engine House 3": (668, 284),
    # South Yard body: replace the old Track 1–5 text labels.
    "S-1": (943, 293),
    "S-2": (943, 344),
    "S-3": (943, 391),
    "S-4": (943, 438),
    "S-5": (943, 480),
    # Scale (old T1) / Barn (old T6) left of the shortened house stubs.
    "Scale": (410, 266),
    "Barn": (490, 266),
    # West Yard body: replace Track 1 / Track 2 text at the west end.
    "West Yard 1": (103, 230),
    "West Yard 2": (105, 293),
    # Princess stubs: replace Track 1 / Track 2 east of 114 / 115.
    "K-1": (1730, 230),
    "K-2": (1730, 293),
}

STATION_OCCUPANCY = {
    "Brick-Plane": "Block 4-6",
    "East Main Ext": "Block 4-7",
    "Main West": "Block 2-1",
    "Main East": "Block 2-3",
    "West Main Ext": "Block 1-8",
    "South Yard East": "Block 1-7",
    "McKees Rocks": "Block 1-1",
    "McKeesport": "Block 1-2",
    "Engine House 1": "Block 13-5",
    "Engine House 2": "Block 13-6",
    "Engine House 3": "Block 13-7",
    "S-1": "Block 2-8",
    "S-2": "Block 2-7",
    "S-3": "Block 2-6",
    "S-4": "Block 2-5",
    "S-5": "Block 2-4",
    "Scale": "Block 4-8",
    "Barn": "Block 13-1",
    "West Yard 1": "Block 4-4",
    "West Yard 2": "Block 4-3",
    "K-1": "Block 1-4",
    "K-2": "Block 1-3",
}

# Loco marker is ~60px; size-10 bold fits about 8 characters.
STATION_DISPLAY_NAMES = {
    "Brick-Plane": "Brk-Pln",
    "East Main Ext": "E Main",
    "Main West": "Main W",
    "Main East": "Main E",
    "West Main Ext": "W Main",
    "South Yard East": "East",
    "McKees Rocks": "McK Rks",
    "McKeesport": "McKport",
    "Engine House 1": "EH 1",
    "Engine House 2": "EH 2",
    "Engine House 3": "EH 3",
    "S-1": "S-1",
    "S-2": "S-2",
    "S-3": "S-3",
    "S-4": "S-4",
    "S-5": "S-5",
    "Scale": "Scale",
    "Barn": "Barn",
    "West Yard 1": "W-1",
    "West Yard 2": "W-2",
    "K-1": "K-1",
    "K-2": "K-2",
}


@dataclass
class Changes:
    block_comments: int = 0
    sensors_created: int = 0
    icons_created: int = 0
    icons_repositioned: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.block_comments
            + self.sensors_created
            + self.icons_created
            + self.icons_repositioned
        )


def station_key(station: str) -> str:
    return station.replace(" ", "_")


def sensor_names(station: str) -> tuple[str, str]:
    key = station_key(station)
    return f"MoveTo{key}_stored", f"MoveInProgress{key}"


def cluster_positions(
    station: str,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Return progress, MoveTo, occupancy coordinates."""
    progress_pos = STATION_ICON_POSITIONS[station]
    move_to_pos = (progress_pos[0] + PAIR_DX, progress_pos[1])
    if station in EH_ROW_STATIONS:
        occ_pos = (
            move_to_pos[0] - PAIR_DX - CIRCUIT_ICON_SIZE,
            move_to_pos[1],
        )
    else:
        occ_pos = (
            move_to_pos[0] + OCCUPANCY_OFFSET[0],
            move_to_pos[1] + OCCUPANCY_OFFSET[1],
        )
    return progress_pos, move_to_pos, occ_pos


def parse_xml(path: Path) -> ET.ElementTree:
    parser = ET.XMLParser(
        target=ET.TreeBuilder(insert_comments=True, insert_pis=True)
    )
    return ET.parse(path, parser=parser)


def bean_user_name(bean: ET.Element) -> str:
    return (bean.findtext("userName") or "").strip()


def is_full_block(block: ET.Element) -> bool:
    """Identify the real BlockManager row, not JMRI's leading summary copy."""
    return block.get("length") is not None


def comment_has_stop(text: str) -> bool:
    return any(part.strip() == STOP_TOKEN for part in text.split(";"))


def set_stop_token(block: ET.Element, wanted: bool) -> bool:
    comment = block.find("comment")
    original = comment.text if comment is not None and comment.text else ""
    parts = original.split(";") if original else []
    stop_parts = [
        part for part in parts if part.strip().casefold() == STOP_TOKEN
    ]
    canonical = len(stop_parts) == 1 and stop_parts[0].strip() == STOP_TOKEN
    if (wanted and canonical) or (not wanted and not stop_parts):
        return False

    kept = [part for part in parts if part.strip().casefold() != STOP_TOKEN]
    if wanted:
        preserved = ";".join(kept).strip(" ;")
        new_text = f"{preserved}; stop" if preserved else STOP_TOKEN
        if comment is None:
            comment = ET.Element("comment")
            user_name = block.find("userName")
            index = list(block).index(user_name) + 1 if user_name is not None else 0
            block.insert(index, comment)
        comment.text = new_text
        return True

    new_text = ";".join(kept).strip(" ;")
    if new_text:
        assert comment is not None
        comment.text = new_text
    elif comment is not None:
        block.remove(comment)
    return True


def reconcile_block_comments(root: ET.Element, changes: Changes) -> None:
    found: dict[str, list[ET.Element]] = {name: [] for name in STATIONS}
    for blocks in root.findall("blocks"):
        for block in blocks.findall("block"):
            if not is_full_block(block):
                continue
            name = bean_user_name(block)
            if name in found:
                found[name].append(block)
            wanted = name in found
            if set_stop_token(block, wanted):
                changes.block_comments += 1
                changes.details.append(
                    f"{'added' if wanted else 'removed'} stop token: {name}"
                )

    missing = [name for name, rows in found.items() if len(rows) != 1]
    if missing:
        counts = ", ".join(f"{name}={len(found[name])}" for name in missing)
        raise ValueError(f"expected one full block row per station ({counts})")


def internal_sensor_manager(root: ET.Element) -> ET.Element:
    managers = [
        manager
        for manager in root.findall("sensors")
        if manager.get("class") == INTERNAL_SENSOR_CLASS
    ]
    if len(managers) != 1:
        raise ValueError(
            f"expected one internal sensor manager, found {len(managers)}"
        )
    return managers[0]


def all_sensor_records(root: ET.Element) -> list[tuple[ET.Element, ET.Element, str, str]]:
    records: list[tuple[ET.Element, ET.Element, str, str]] = []
    for manager in root.findall("sensors"):
        for sensor in manager.findall("sensor"):
            records.append(
                (
                    manager,
                    sensor,
                    (sensor.findtext("systemName") or "").strip(),
                    bean_user_name(sensor),
                )
            )
    return records


def next_sensor_system_name(prefix: str, used: set[str]) -> str:
    number = 1
    while f"{prefix}{number}" in used:
        number += 1
    return f"{prefix}{number}"


def reconcile_sensors(root: ET.Element, changes: Changes) -> None:
    internal = internal_sensor_manager(root)
    records = all_sensor_records(root)
    used_system_names = {system for _, _, system, _ in records if system}
    by_user: dict[str, list[tuple[ET.Element, ET.Element, str]]] = {}
    for manager, sensor, system, user in records:
        if user:
            by_user.setdefault(user, []).append((manager, sensor, system))

    for station in STATIONS:
        move_to, in_progress = sensor_names(station)
        for user_name, prefix in (
            (move_to, "IS:DSMT:"),
            (in_progress, "IS:DSMP:"),
        ):
            existing = by_user.get(user_name, [])
            if len(existing) > 1:
                raise ValueError(f"duplicate sensor userName {user_name!r}")
            if existing:
                manager, _sensor, _system = existing[0]
                if manager is not internal:
                    raise ValueError(
                        f"{user_name!r} exists outside the internal sensor manager"
                    )
                continue

            system_name = next_sensor_system_name(prefix, used_system_names)
            sensor = ET.Element("sensor", {"inverted": "false"})
            ET.SubElement(sensor, "systemName").text = system_name
            ET.SubElement(sensor, "userName").text = user_name
            internal.append(sensor)
            used_system_names.add(system_name)
            by_user[user_name] = [(internal, sensor, system_name)]
            changes.sensors_created += 1
            changes.details.append(f"created sensor {system_name} / {user_name}")


def main_layout_editor(root: ET.Element) -> ET.Element:
    editors = root.findall("LayoutEditor")
    named = [editor for editor in editors if editor.get("name") == "My Layout"]
    candidates = named or [
        editor for editor in editors if editor.get("name") != "Dispatcher System"
    ]
    if len(candidates) != 1:
        raise ValueError(f"expected one main LayoutEditor, found {len(candidates)}")
    return candidates[0]


def icon_element(
    sensor_name: str,
    station: str,
    x: int,
    y: int,
    kind: str,
) -> ET.Element:
    attributes = {
        "sensor": sensor_name,
        "x": str(x),
        "y": str(y),
        "level": "12",
        "forcecontroloff": "false",
        "hidden": "no",
        "positionable": "true",
        "showtooltip": "true",
        "editable": "true",
        "momentary": "false",
        "icon": "yes",
        "class": "jmri.jmrit.display.configurexml.SensorIconXml",
    }
    display = STATION_DISPLAY_NAMES.get(station, station)
    if kind == "move_to":
        attributes.update(
            {
                "text": display,
                "size": "10",
                "style": "1",
                "red": "51",
                "green": "51",
                "blue": "51",
                "hasBackground": "no",
                "justification": "centre",
            }
        )
    icon = ET.Element("sensoricon", attributes)
    urls = (
        {
            "active": "program:resources/icons/markers/loco-green.gif",
            "inactive": "program:resources/icons/markers/loco-red.gif",
            "unknown": "program:resources/icons/markers/loco-gray.gif",
            "inconsistent": "program:resources/icons/markers/loco-yellow.gif",
        }
        if kind == "move_to"
        else {
            "active": "program:resources/icons/smallschematics/tracksegments/circuit-occupied.gif",
            "inactive": "program:resources/icons/smallschematics/tracksegments/circuit-empty.gif",
            "unknown": "program:resources/icons/smallschematics/tracksegments/circuit-error.gif",
            "inconsistent": "program:resources/icons/smallschematics/tracksegments/circuit-error.gif",
        }
    )
    for state, url in urls.items():
        state_element = ET.SubElement(
            icon, state, {"url": url, "degrees": "0", "scale": "1.0"}
        )
        ET.SubElement(state_element, "rotation").text = "0"
    ET.SubElement(icon, "iconmaps")
    if kind == "move_to":
        for tag, color in (
            ("activeText", ("255", "0", "0")),
            ("inactiveText", ("255", "255", "0")),
            ("unknownText", ("0", "0", "255")),
            ("inconsistentText", ("0", "0", "0")),
        ):
            ET.SubElement(
                icon,
                tag,
                {
                    "text": display,
                    "red": color[0],
                    "green": color[1],
                    "blue": color[2],
                },
            )
    return icon


def xy(element: ET.Element) -> tuple[int, int] | None:
    try:
        return int(float(element.get("x", ""))), int(float(element.get("y", "")))
    except ValueError:
        return None


def reconcile_icons(root: ET.Element, changes: Changes) -> None:
    editor = main_layout_editor(root)
    expected_names = {
        sensor_name
        for station in STATIONS
        for sensor_name in (*sensor_names(station), STATION_OCCUPANCY[station])
    }
    existing: dict[str, list[ET.Element]] = {name: [] for name in expected_names}
    for element in editor.findall("sensoricon"):
        name = element.get("sensor") or ""
        if name in existing:
            existing[name].append(element)

    anchors: dict[str, list[ET.Element]] = {station: [] for station in STATIONS}
    for element in editor.findall("BlockContentsIcon"):
        name = element.get("blockcontents") or ""
        if name in anchors:
            anchors[name].append(element)
    bad_anchors = [name for name, rows in anchors.items() if not rows]
    if bad_anchors:
        raise ValueError(
            "expected at least one BlockContentsIcon per station "
            f"({', '.join(bad_anchors)})"
        )

    children = list(editor)
    managed_elements = {
        id(element)
        for elements in existing.values()
        for element in elements
    }
    insertion_index = min(
        (i for i, element in enumerate(children) if id(element) in managed_elements),
        default=max(
            (
                i + 1
                for i, element in enumerate(children)
                if element.tag == "BlockContentsIcon"
            ),
            default=len(children),
        ),
    )
    new_icons: list[ET.Element] = []
    for station in STATIONS:
        anchor = xy(anchors[station][0])
        if anchor is None:
            raise ValueError(f"BlockContentsIcon for {station!r} has invalid x/y")
        progress_pos, move_to_pos, occ_pos = cluster_positions(station)
        move_to_name, progress_name = sensor_names(station)
        occ_name = STATION_OCCUPANCY[station]
        expected_positions = {
            move_to_name: move_to_pos,
            progress_name: progress_pos,
            occ_name: occ_pos,
        }
        expected_icons = {
            move_to_name: icon_element(
                move_to_name, station, move_to_pos[0], move_to_pos[1], "move_to"
            ),
            progress_name: icon_element(
                progress_name, station, progress_pos[0], progress_pos[1], "progress"
            ),
            occ_name: icon_element(
                occ_name, station, occ_pos[0], occ_pos[1], "occupancy"
            ),
        }
        for name in (move_to_name, progress_name, occ_name):
            rows = existing[name]
            if not rows:
                changes.icons_created += 1
                changes.details.append(f"created icon {name}")
            elif (
                len(rows) != 1
                or xy(rows[0]) != expected_positions[name]
                or element_signature(rows[0])
                != element_signature(expected_icons[name])
            ):
                changes.icons_repositioned += 1
                changes.details.append(f"reconciled icon {name}")
        new_icons.append(expected_icons[move_to_name])
        new_icons.append(expected_icons[progress_name])
        new_icons.append(expected_icons[occ_name])

    for element in children:
        if id(element) in managed_elements:
            editor.remove(element)
    for offset, element in enumerate(new_icons):
        editor.insert(insertion_index + offset, element)


def element_signature(element: ET.Element) -> bytes:
    """Compare icon structure while ignoring indentation-only tail whitespace."""
    clone = copy_element_without_tails(element)
    return ET.tostring(clone, encoding="utf-8")


def copy_element_without_tails(element: ET.Element) -> ET.Element:
    clone = ET.Element(element.tag, dict(element.attrib))
    clone.text = (
        element.text
        if element.text is not None and element.text.strip()
        else None
    )
    for child in element:
        clone.append(copy_element_without_tails(child))
    return clone


def reconcile(tree: ET.ElementTree) -> Changes:
    changes = Changes()
    root = tree.getroot()
    reconcile_block_comments(root, changes)
    reconcile_sensors(root, changes)
    reconcile_icons(root, changes)
    validate(root)
    return changes


def validate(root: ET.Element) -> None:
    full_blocks = [
        block
        for blocks in root.findall("blocks")
        for block in blocks.findall("block")
        if is_full_block(block)
    ]
    station_rows = {
        bean_user_name(block)
        for block in full_blocks
        if comment_has_stop(block.findtext("comment") or "")
    }
    if station_rows != set(STATIONS):
        raise ValueError(
            "full block stop-token set differs from intended stations: "
            f"{sorted(station_rows)}"
        )

    internal = internal_sensor_manager(root)
    internal_users = [bean_user_name(sensor) for sensor in internal.findall("sensor")]
    expected_sensors = [
        name for station in STATIONS for name in sensor_names(station)
    ]
    expected_icons = expected_sensors + [
        STATION_OCCUPANCY[station] for station in STATIONS
    ]
    bad_sensors = [
        name for name in expected_sensors if internal_users.count(name) != 1
    ]
    if bad_sensors:
        raise ValueError(f"missing or duplicate internal sensors: {bad_sensors}")

    editor = main_layout_editor(root)
    icon_names = [
        icon.get("sensor") or "" for icon in editor.findall("sensoricon")
    ]
    bad_icons = [name for name in expected_icons if icon_names.count(name) != 1]
    if bad_icons:
        raise ValueError(f"missing or duplicate station icons: {bad_icons}")

    positions = [
        xy(icon)
        for icon in editor.findall("sensoricon")
        if (icon.get("sensor") or "") in expected_icons
    ]
    if len(positions) != len(set(positions)):
        raise ValueError("station icon coordinate collision")


def write_atomic(tree: ET.ElementTree, destination: Path) -> None:
    ET.indent(tree, space="  ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        tree.write(
            temporary,
            encoding="UTF-8",
            xml_declaration=True,
            short_empty_elements=True,
        )
        if destination.exists():
            os.chmod(temporary, stat.S_IMODE(destination.stat().st_mode))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def safe_panel_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == READ_ONLY_PANEL.resolve():
        raise ValueError(f"refusing read-only source snapshot: {resolved}")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile HART Dispatcher station comments, internal "
            "sensors, and paired LayoutEditor icons."
        ),
        epilog=(
            "Run JMRI Dispatcher Stage 1 and Stage 2 in PanelPro only if the "
            "generated sections/transits/traininfo are absent or stale."
        ),
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=DEFAULT_PANEL,
        help="working XML (default: tables/new_tables.xml)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate a reconciled in-memory copy; never write or sync",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="do not independently reconcile hart/output/tables.xml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        panel = safe_panel_path(args.panel)
        tree = parse_xml(panel)
        changes = reconcile(tree)
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.check:
        if changes.total:
            print(
                f"CHECK FAILED: {panel} needs {changes.total} reconciliation change(s)"
            )
            for detail in changes.details:
                print(f"  - {detail}")
            return 1
        print(f"CHECK OK: {panel}")
        return 0

    if changes.total:
        write_atomic(tree, panel)
        print(f"Wrote {changes.total} reconciliation change(s) -> {panel}")
    else:
        print(f"Already reconciled: {panel}")

    if not args.no_sync and panel == DEFAULT_PANEL.resolve():
        try:
            sync_tree = parse_xml(SYNC_PANEL)
            sync_changes = reconcile(sync_tree)
            if sync_changes.total:
                write_atomic(sync_tree, SYNC_PANEL)
                print(
                    f"Reconciled deployment independently "
                    f"({sync_changes.total} change(s)) -> {SYNC_PANEL}"
                )
            else:
                print(f"Deployment already reconciled: {SYNC_PANEL}")
        except (OSError, ET.ParseError, ValueError) as error:
            print(f"ERROR: deployment reconciliation failed: {error}", file=sys.stderr)
            return 2
    elif not args.no_sync and panel != DEFAULT_PANEL.resolve():
        print("Custom --panel was not synced")

    print(
        "Existing generated Dispatcher graph was preserved. Run Stage 1 and "
        "Stage 2 in PanelPro only if audit_panel_contracts.py reports it stale."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
