#!/usr/bin/env python3
"""Reconcile the HART JMRI Dispatcher stations and their panel icons.

The working target defaults to ``jmri/layouts/hart/output/tables.xml``.  ``tables/tables.xml``
is a read-only snapshot and is explicitly rejected.  A normal run applies the
same reconciliation independently to ``jmri/layouts/hart/output/tables.xml``;
it never copies one complete configuration over the other.  Use ``--no-sync``
to skip the deployment bundle.  ``--check`` validates without writing.

The main panel must be a generated one (build_layout_le.py --as-live; it holds
hartlib.tables.GENERATED_PANEL_MARKER). Each cluster icon stays where it stands: where the same
icon stands on the ``--reference`` panel (the copy taken before Stage 1, which deletes and
re-adds the cluster icons; run_panelpro_stage1.sh passes it), else where the panel's own one
copy stands, else (Progress and occupancy only) the usual offset from its MoveTo icon. A MoveTo
icon found on neither stops the run: there is no spot to give it.

This script deliberately leaves all existing sections, transits, and traininfo
untouched. Run Dispatcher Stage 1 and Stage 2 in PanelPro only when the
generated graph is absent or the audit reports it stale.
"""

from __future__ import annotations

import argparse
import copy
import os
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import parked, paths, tables  # noqa: E402

ROOT = paths.REPO_ROOT
DEFAULT_PANEL = paths.TABLES_XML
READ_ONLY_PANEL = ROOT / "tables" / "tables.xml"
SYNC_PANEL = paths.TABLES_XML

# Dispatcher stations: where trains start and end. Through tracks (mains,
# Brick-Plane, South Yard) stopped being stations on 2026-11-12 to cut the
# route count; trains still run over them.
STATIONS = (
    "Track K-1",
    "Track K-2",
    "Track East Lead",
    "Track EH-1",
    "Track EH-2",
    "Track EH-3",
    "Track Scale",
    "Track Barn",
    "Track W-1",
    "Track W-2",
    "Track McKees Rocks",
    "Track McKeesport",
)

# Former stations. reconcile removes their buttons, progress sensors and
# cluster lamps; the Stage 1 lamp on the track stays as an occupancy light.
RETIRED_STATION_OCCUPANCY = {
    "Track Main West": "BS Main West",
    "Track West Ext": "BS West Ext",
    "Track Main East": "BS Main East",
    "Track East Ext": "BS East Ext",
    "Track Brick-Plane": "BS Brick-Plane",
    "Track S-R": "BS S-R",
    "Track S-1": "BS S-1",
    "Track S-2": "BS S-2",
    "Track S-3": "BS S-3",
    "Track S-4": "BS S-4",
}
RETIRED_STATIONS = tuple(RETIRED_STATION_OCCUPANCY)

# Station cluster icons sit on level 12. The Stage 1 (CreateIcons) occupancy
# lamps on the track share the sensor at level 10 and are left alone.
CLUSTER_LEVEL = "12"
INTERNAL_SENSOR_CLASS = "jmri.jmrix.internal.configurexml.InternalSensorManagerXml"
STOP_TOKEN = "stop"
# Progress is x-10 from MoveTo. Occupancy is MoveTo + (-10, +10) unless
# the station uses a left-right circuit row (engine house).
PAIR_DX = 10
OCCUPANCY_OFFSET = (-10, 10)
CIRCUIT_ICON_SIZE = 10
EH_ROW_STATIONS = frozenset({"Track EH-1", "Track EH-2", "Track EH-3"})

# Occupancy sensor of each station block (public BS names, ADR-005). validate()
# fails if a block in tables.xml binds a different sensor.
STATION_OCCUPANCY = {
    "Track East Lead": "BS East Lead",
    "Track K-1": "BS K-1",
    "Track K-2": "BS K-2",
    "Track EH-1": "BS EH-1",
    "Track EH-2": "BS EH-2",
    "Track EH-3": "BS EH-3",
    "Track Scale": "BS Scale",
    "Track Barn": "BS Barn",
    "Track W-1": "BS W-1",
    "Track W-2": "BS W-2",
    "Track McKees Rocks": "BS Switch 39",
    "Track McKeesport": "BS Switch 37",
}

# Loco marker is ~60px; size-10 bold fits about 8 characters.
STATION_DISPLAY_NAMES = {
    "Track East Lead": "East End",
    "Track K-1": "Track K-1",
    "Track K-2": "Track K-2",
    "Track EH-1": "Track EH-1",
    "Track EH-2": "Track EH-2",
    "Track EH-3": "Track EH-3",
    "Track Scale": "Scale",
    "Track Barn": "Barn",
    "Track W-1": "Track W-1",
    "Track W-2": "Track W-2",
    "Track McKees Rocks": "McK Rks",
    "Track McKeesport": "McKport",
}


@dataclass
class Changes:
    block_comments: int = 0
    sensors_created: int = 0
    icons_created: int = 0
    icons_repositioned: int = 0
    retired: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.block_comments
            + self.sensors_created
            + self.icons_created
            + self.icons_repositioned
            + self.retired
        )


def station_key(station: str) -> str:
    return station.replace(" ", "_")


def sensor_names(station: str) -> tuple[str, str]:
    key = station_key(station)
    return f"MoveTo{key}_stored", f"MoveInProgress{key}"


def cluster_positions(
    station: str, move_to: tuple[int, int],
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Return progress, MoveTo, occupancy coordinates around the MoveTo icon at `move_to`."""
    move_to_pos = move_to
    progress_pos = (move_to[0] - PAIR_DX, move_to[1])
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


def main_panel(root: ET.Element) -> ET.Element:
    """The generated main panel of the tables (hartlib.tables.require_generated_panel)."""
    return tables.require_generated_panel(root, "the tables")


def station_display(station: str) -> str:
    """The MoveTo button's text: STATION_DISPLAY_NAMES without a leading "Track " (owner, 2026-11-16: "EH-1" fits
    the loco marker; the sensor and block names keep it)."""
    return tables.without_track_word(STATION_DISPLAY_NAMES.get(station, station))


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
        "level": CLUSTER_LEVEL,
        # Only the MoveTo button takes a click. The occupancy and move-in-progress lamps show state: a click would
        # set the block occupied or a move in progress (owner, 2026-11-15).
        "forcecontroloff": "false" if kind == "move_to" else "true",
        "hidden": "no",
        "positionable": "true",
        "showtooltip": "true",
        # Occupancy lamps are display only; the MoveTo button is clicked.
        "editable": "false" if kind == "occupancy" else "true",
        "momentary": "false",
        "icon": "yes",
        "class": "jmri.jmrit.display.configurexml.SensorIconXml",
    }
    if kind == "move_to":
        display = station_display(station)
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


def retire_stations(root: ET.Element, changes: Changes) -> None:
    """Drop a former station's MoveTo button, progress sensor and cluster lamp."""
    names = {name for station in RETIRED_STATIONS for name in sensor_names(station)}
    lamps = set(RETIRED_STATION_OCCUPANCY.values())
    internal = internal_sensor_manager(root)
    for sensor in list(internal.findall("sensor")):
        if bean_user_name(sensor) in names:
            internal.remove(sensor)
            changes.retired += 1
            changes.details.append(f"removed sensor {bean_user_name(sensor)}")
    editor = main_panel(root)
    for icon in list(editor.findall("sensoricon")):
        name = icon.get("sensor") or ""
        if name in names or (name in lamps and icon.get("level") == CLUSTER_LEVEL):
            editor.remove(icon)
            changes.retired += 1
            changes.details.append(f"removed icon {name}")


def is_stage1_lamp(icon: ET.Element) -> bool:
    """A station occupancy icon that is not the cluster one: Stage 1's track lamp."""
    occupancy_names = set(STATION_OCCUPANCY.values())
    return (icon.get("sensor") or "") in occupancy_names and icon.get("level") != CLUSTER_LEVEL


def xy(element: ET.Element) -> tuple[int, int] | None:
    try:
        return int(float(element.get("x", ""))), int(float(element.get("y", "")))
    except ValueError:
        return None


def cluster_icons(editor: ET.Element | None) -> dict[str, list[ET.Element]]:
    """{sensor: its station cluster icons} on a panel (Stage 1 track lamps left out)."""
    out: dict[str, list[ET.Element]] = {}
    for element in (editor.findall("sensoricon") if editor is not None else ()):
        if not is_stage1_lamp(element):
            out.setdefault(element.get("sensor") or "", []).append(element)
    return out


def generated_positions(
    editor: ET.Element, reference: ET.Element | None
) -> dict[str, tuple[tuple[int, int], tuple[int, int], tuple[int, int]]]:
    """{station: (progress, MoveTo, occupancy)} on a generated panel, from the panels themselves (module docstring)."""
    sources = [cluster_icons(reference)] if reference is not None else []
    sources.append(cluster_icons(editor))

    def spot(name: str) -> tuple[int, int] | None:
        """The one copy on the reference panel, else the one copy on the panel itself."""
        for icons in sources:
            rows = icons.get(name, [])
            if len(rows) == 1:
                return xy(rows[0])
        return None

    out = {}
    for station in STATIONS:
        move_to_name, progress_name = sensor_names(station)
        move_to = spot(move_to_name)
        if move_to is None:
            where = "the --reference panel or the panel" if reference is not None else "the panel"
            raise ValueError(f"generated panel: {station}: no single {move_to_name} icon on {where}, so its "
                             "cluster has no position (run with --reference <tables before Stage 1>)")
        derived = cluster_positions(station, move_to)
        out[station] = (spot(progress_name) or derived[0], move_to,
                        spot(STATION_OCCUPANCY[station]) or derived[2])
    return out


def reconcile_icons(root: ET.Element, changes: Changes, reference: ET.Element | None = None) -> None:
    editor = main_panel(root)
    if reference is not None:
        tables.require_generated(reference, "--reference")
    positions = generated_positions(editor, reference)
    expected_names = {
        sensor_name
        for station in STATIONS
        for sensor_name in (*sensor_names(station), STATION_OCCUPANCY[station])
    }
    existing: dict[str, list[ET.Element]] = {name: [] for name in expected_names}
    for element in editor.findall("sensoricon"):
        name = element.get("sensor") or ""
        if is_stage1_lamp(element):
            continue
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
        progress_pos, move_to_pos, occ_pos = positions[station]
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
            if len(rows) == 1:
                # The cluster icon the panel has (as JMRI stored it: its own attribute order, fonts, editable
                # flag): kept as it is, only moved to its spot when it stands elsewhere, so a run after Stage 1
                # changes nothing (idempotent, owner 2026-11-16)
                kept = copy.deepcopy(rows[0])
                kept.tail = None
                moved = xy(rows[0]) != expected_positions[name]
                if moved:
                    kept.set("x", str(expected_positions[name][0]))
                    kept.set("y", str(expected_positions[name][1]))
                retext = False
                if name == move_to_name:        # its text as station_display gives it ("K-1", not "Track K-1")
                    display = station_display(station)
                    for e in [kept] + [c for c in kept if c.tag.endswith("Text")]:
                        if e.get("text") is not None and e.get("text") != display:
                            e.set("text", display)
                            retext = True
                if moved or retext:
                    changes.icons_repositioned += 1
                    changes.details.append(f"reconciled icon {name}")
                expected_icons[name] = kept
            elif not rows:
                changes.icons_created += 1
                changes.details.append(f"created icon {name}")
            else:                               # copies: one new icon at the spot replaces them all
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


def reconcile(tree: ET.ElementTree, reference: ET.Element | None = None) -> Changes:
    """`reference`: the main panel of the tables before Stage 1 (a generated panel only)."""
    changes = Changes()
    root = tree.getroot()
    reconcile_block_comments(root, changes)
    reconcile_sensors(root, changes)
    retire_stations(root, changes)
    reconcile_icons(root, changes, reference)
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

    # A block may store its sensor by system name (a GUI edit); accept either.
    user_by_system = {
        (sensor.findtext("systemName") or "").strip(): bean_user_name(sensor)
        for sensor in root.iter("sensor")
    }
    wrong_sensor = []
    for block in full_blocks:
        station = bean_user_name(block)
        bound = (block.findtext("occupancysensor") or "").strip()
        if station not in STATION_OCCUPANCY or not bound:
            continue
        if user_by_system.get(bound, bound) != STATION_OCCUPANCY[station]:
            wrong_sensor.append(f"{station}: {bound}")
    if wrong_sensor:
        raise ValueError(
            f"station blocks bind other occupancy sensors than STATION_OCCUPANCY: {wrong_sensor}"
        )

    editor = main_panel(root)
    icon_names = [
        icon.get("sensor") or ""
        for icon in editor.findall("sensoricon")
        if not is_stage1_lamp(icon)
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
        help="working XML (default: jmri/layouts/hart/output/tables.xml)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate a reconciled in-memory copy; never write or sync",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        help="a generated panel's tables before Stage 1 (run_panelpro_stage1.sh): station clusters go "
        "back where they stood in it",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="do not independently reconcile hart/output/tables.xml",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.check:
        paths.exit_if_overridden(Path(__file__).name)
    try:
        panel = safe_panel_path(args.panel)
        tree = parse_xml(panel)         # parsed once: the parked test below and the reconcile read the same tree
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if "dispatcher" in parked.parked_in(tree.getroot()):
        # parked (hartlib.parked): tables without the Dispatcher System hold no station to reconcile
        print("SKIPPED: the Dispatcher System is parked (hartlib.parked.PARKED); its stations are in "
              f"{paths.rel(parked.PARKED_XML)}")
        return 0
    try:
        reference = None
        if args.reference:
            reference = tables.require_generated_panel(parse_xml(args.reference).getroot(),
                                                       f"--reference {args.reference}")
        changes = reconcile(tree, reference)
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
            if "dispatcher" in parked.parked_in(sync_tree.getroot()):
                print(f"SKIPPED deployment {SYNC_PANEL}: the Dispatcher System is parked there")
                sync_changes = None
            else:
                sync_changes = reconcile(sync_tree, reference)
            if sync_changes is None:
                pass
            elif sync_changes.total:
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
