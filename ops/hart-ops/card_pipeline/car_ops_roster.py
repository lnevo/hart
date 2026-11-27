"""The Operations Pro car roster (OperationsCarRoster.xml): read its cars, add cars, set fields and flags.

Every write goes through ``write_ops``, which keeps the stylesheet and DOCTYPE lines ElementTree drops.
Cars already in the roster keep their session state (location, moves); only the named attributes change.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

import car_repo  # noqa: F401  (sets HART_CAR_CARDS_ROOT before car_paths loads)
from car_paths import CardPipelineError
from car_records import FieldDiff
from hartlib import operations


def roster_part(root: ET.Element, tag: str, path: Path) -> ET.Element:
    """The ``<cars>`` (or other) section of a roster, or a named error when the file has none."""
    part = root.find(tag)
    if part is None:
        raise CardPipelineError(f"{path} has no <{tag}> section")
    return part


def add_to_sections(root: ET.Element, car: ET.Element) -> None:
    for section, tag, value in (
        ("roads", "road", car.get("roadName")),
        ("types", "type", car.get("type")),
        ("colors", "color", car.get("color")),
    ):
        parent = root.find(section)
        if parent is None or not value:
            continue
        if not any(e.get("name") == value for e in parent):
            ET.SubElement(parent, tag, {"name": value})


def write_ops(tree: ET.ElementTree[ET.Element], live_path: Path) -> None:
    """Write the merged roster, keeping the stylesheet and DOCTYPE lines ElementTree drops."""
    text = live_path.read_text(encoding="utf-8")
    header = text[: text.index("<operations-config")]
    body = ET.tostring(tree.getroot(), encoding="unicode")
    live_path.write_text(header + body + "\n", encoding="utf-8")


def ops_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return set(operations.ids(operations.cars(path)))


def ops_out_of_service(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        c.get("id", "") for c in operations.cars(path) if c.get("outOfService") == "true"
    }


def ops_car_attrs(path: Path) -> dict[str, dict[str, str]]:
    return {c.get("id", ""): dict(c.attrib) for c in operations.cars(path)}


def merge_ops(
    live_path: Path,
    wanted: Iterable[str],
    source_path: Path,
    out_of_service: set[str] | None = None,
) -> list[str]:
    """Add cars from the merged roster at ``source_path`` to the Operations Pro roster, leaving every other car alone.

    When out_of_service is given, every car's flag is set to match it.
    """
    tree = ET.parse(live_path)
    root = tree.getroot()
    cars_el = roster_part(root, "cars", live_path)
    have = {c.get("id") for c in cars_el.findall("car")}
    source = {c.get("id"): c for c in operations.cars(source_path)}
    added = []
    for roster_id in wanted:
        if roster_id in have:
            continue
        if roster_id not in source:
            raise CardPipelineError(f"{roster_id} is missing from {source_path.name}")
        car = source[roster_id]
        cars_el.append(car)
        added.append(roster_id)
        add_to_sections(root, car)
    if out_of_service is not None:
        for car in cars_el.findall("car"):
            if car.get("id") in out_of_service:
                car.set("outOfService", "true")
            else:
                car.attrib.pop("outOfService", None)
    write_ops(tree, live_path)
    return added


def update_ops_fields(path: Path, diffs: list[FieldDiff]) -> int:
    """Set only the differing attributes on existing cars, through the writer merge_ops uses."""
    tree = ET.parse(path)
    by_id = {c.get("id"): c for c in tree.getroot().findall("./cars/car")}
    for cid, attr, want, _have in diffs:
        by_id[cid].set(attr, want)
    write_ops(tree, path)
    return len(diffs)
