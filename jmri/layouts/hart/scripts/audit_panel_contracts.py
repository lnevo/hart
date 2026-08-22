#!/usr/bin/env python3
"""Read-only audit of the HART panel contracts across stored XML sources."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCES = (
    ("working", REPO_ROOT / "tables" / "new_tables.xml"),
    ("deployment", REPO_ROOT / "jmri" / "layouts" / "hart" / "output" / "tables.xml"),
    ("standalone", REPO_ROOT / "jmri" / "layouts" / "hart" / "output" / "hart_prod.xml"),
)
BOUNDARIES = REPO_ROOT / "cats" / "data" / "le_signal_boundaries.csv"
TRAININFO = REPO_ROOT / "jmri" / "layouts" / "hart" / "dispatcher" / "traininfo"
PANEL_NAMES = {"HART", "My Layout"}
STATION_COMMENTS = {
    "South Yard East": "South Yard lead east of 110/112 toward Princess; occupancy Block 1-7 / M2S106; stop",
    "East Main Ext": "Main east of Plane toward Barn; occupancy Block 4-7 / M2S406; stop",
    "Main East": "Main east of East End; occupancy Block 2-3 / M2S202; stop",
    "Main West": "Main west of Brick toward East End; occupancy Block 2-1 / M2S200; stop",
    "Brick-Plane": "Main West between Brick and Plane; occupancy Block 4-6 / M2S405; stop",
    "McKees Rocks": "Princess balloon, McKees Rocks; occupancy Block 1-1 / M2S100; stop",
    "McKeesport": "Princess balloon, McKeesport; occupancy Block 1-2 / M2S101; stop",
    "West Main Ext": "Main West stub west of 111; occupancy Block 1-8 / M2S107; stop",
    "Engine House 1": "Top house track; occupancy Block 13-5 / M2S1304; stop",
    "Engine House 2": "Middle house track; occupancy Block 13-6 / M2S1305; stop",
    "Engine House 3": "Bottom house track; occupancy Block 13-7 / M2S1306; stop",
    "South Yard 1": "Run-through east of 103; occupancy Block 2-8 / M2S207; stop",
    "South Yard 2": "South Yard body; occupancy Block 2-7 / M2S206; stop",
    "South Yard 3": "South Yard body; occupancy Block 2-6 / M2S205; stop",
    "South Yard 4": "South Yard body; occupancy Block 2-5 / M2S204; stop",
    "South Yard 5": "South Yard body; occupancy Block 2-4 / M2S203; stop",
    "Scale": "Plane diverging lead to Barn; occupancy Block 4-8 / M2S407; stop",
    "Barn": "Lead 117 to 116; occupancy Block 13-1 / M2S1300; stop",
    "West Yard 1": "Brick yard W-1; access Switch 101 only; occupancy Block 4-4 / M2S403; stop",
    "West Yard 2": "Brick yard W-2; access Switch 101 only; occupancy Block 4-3 / M2S402; stop",
    "K-1": "Princess stub east of Switch 115; shares Block 1-4 with OS 115; occupancy Block 1-4 / M2S103; stop",
    "K-2": "Princess stub east of Switch 114; shares Block 1-3 with OS 114; occupancy Block 1-3 / M2S102; stop",
}


def text(element: ET.Element | None, child: str) -> str:
    if element is None:
        return ""
    value = element.findtext(child)
    return value.strip() if value else ""


def attr_or_child(element: ET.Element, name: str) -> str:
    return (element.get(name) or text(element, name)).strip()


def sensor_key(block_name: str) -> str:
    return block_name.replace(" ", "_")


@dataclass(frozen=True)
class Boundary:
    kind: str
    ident: str
    slot: str
    mast: str

    @property
    def binding_name(self) -> str:
        if self.kind == "turnout":
            return f"signal{self.slot.upper()}Mast"
        return f"{self.slot.lower()}boundsignalmast"


@dataclass
class Audit:
    label: str
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def load_boundaries(path: Path) -> list[Boundary]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    boundaries = [
        Boundary(
            kind=row["kind"].strip(),
            ident=row["ident"].strip(),
            slot=row["slot"].strip(),
            mast=row["mast_user_name"].strip(),
        )
        for row in rows
    ]
    if len(boundaries) != 23 or len({item.mast for item in boundaries}) != 23:
        raise ValueError(f"{path}: expected 23 unique boundary mast names")
    return boundaries


def select_panel(root: ET.Element, audit: Audit) -> ET.Element | None:
    candidates = [
        panel
        for panel in root.iter("LayoutEditor")
        if (panel.get("name") or "").strip() in PANEL_NAMES
    ]
    if len(candidates) != 1:
        names = [(panel.get("name") or "<unnamed>") for panel in root.iter("LayoutEditor")]
        audit.error(
            "expected exactly one LayoutEditor named HART or My Layout; "
            f"found {len(candidates)} (all panels: {names or ['<none>']})"
        )
        return None
    audit.facts["panel"] = candidates[0].get("name", "")
    return candidates[0]


def audit_masts(root: ET.Element, expected: set[str], audit: Audit) -> None:
    masts = root.find("signalmasts")
    names: set[str] = set()
    cats_virtual: list[str] = []
    if masts is not None:
        for mast in masts.findall("signalmast"):
            name = text(mast, "userName")
            system_name = text(mast, "systemName")
            normalized = (system_name + " " + name).upper()
            if "IF$VSM:CATS" in normalized or "CATS1" in normalized or "CATS2" in normalized:
                cats_virtual.append(f"{name or '<unnamed>'} [{system_name or '<no system name>'}]")
            if (system_name or "").startswith("IF$vsm:AAR-1946:"):
                continue
            if name:
                names.add(name)
    missing = sorted(expected - names)
    extra = sorted(names - expected)
    if missing or extra or len(names) != 23:
        audit.error(
            f"signal mast names are not the exact expected 23; "
            f"missing={missing or 'none'}, extra={extra or 'none'}, count={len(names)}"
        )
    if cats_virtual:
        audit.error(f"CATS runtime virtual masts stored in file: {cats_virtual}")
    audit.facts["masts"] = tuple(sorted(names))
    audit.facts["cats_virtual"] = tuple(sorted(cats_virtual))


def audit_bindings(
    panel: ET.Element | None, boundaries: list[Boundary], audit: Audit
) -> None:
    actual: dict[tuple[str, str, str], str] = {}
    if panel is None:
        audit.facts["bindings"] = ()
        return
    by_key: dict[tuple[str, str], list[ET.Element]] = {}
    for element in panel.iter():
        ident = element.get("ident")
        if ident and element.tag in {"layoutturnout", "positionablepoint"}:
            kind = "turnout" if element.tag == "layoutturnout" else "anchor"
            by_key.setdefault((kind, ident), []).append(element)
    for boundary in boundaries:
        elements = by_key.get((boundary.kind, boundary.ident), [])
        if len(elements) != 1:
            audit.error(
                f"boundary {boundary.kind} {boundary.ident} expected once in selected panel, "
                f"found {len(elements)}"
            )
            continue
        value = attr_or_child(elements[0], boundary.binding_name)
        actual[(boundary.kind, boundary.ident, boundary.slot)] = value
        if value != boundary.mast:
            audit.error(
                f"boundary {boundary.kind} {boundary.ident} slot {boundary.slot}: "
                f"expected {boundary.mast!r}, found {value or '<unbound>'!r}"
            )
    audit.facts["bindings"] = tuple(
        sorted((*key, value) for key, value in actual.items())
    )


def audit_sml(root: ET.Element, audit: Audit, *, required: bool) -> None:
    destinations: list[tuple[str, str, str]] = []
    for logic in root.findall("./signalmastlogics/signalmastlogic"):
        source = attr_or_child(logic, "sourceSignalMast") or logic.get("source", "")
        for destination in logic.findall("destinationMast"):
            target = (
                attr_or_child(destination, "destinationSignalMast")
                or destination.get("destination", "")
            )
            use_le = text(destination, "useLayoutEditor").lower()
            destinations.append((source, target, use_le))
    auto = sum(use_le == "yes" for _, _, use_le in destinations)
    manual = sum(use_le == "no" for _, _, use_le in destinations)
    unknown = len(destinations) - auto - manual
    if (len(destinations), auto, manual, unknown) != (41, 39, 2, 0):
        message = (
            "stored SML destinations expected total=41, useLayoutEditor=yes=39, "
            f"manual=2; found total={len(destinations)}, yes={auto}, "
            f"manual={manual}, unspecified/other={unknown}"
        )
        (audit.error if required else audit.warn)(message)
    audit.facts["sml"] = tuple(sorted(destinations))


def block_definitions(root: ET.Element) -> dict[str, list[str]]:
    definitions: dict[str, list[str]] = {}
    for block in root.findall("./blocks/block"):
        name = text(block, "userName")
        if name:
            definitions.setdefault(name, []).append(text(block, "comment"))
    return definitions


def audit_stations(
    root: ET.Element, panel: ET.Element | None, audit: Audit, *, required: bool
) -> None:
    problem = audit.error if required else audit.warn
    definitions = block_definitions(root)
    station_names = {
        name
        for name, comments in definitions.items()
        if any(comment == "stop" or comment.endswith("; stop") for comment in comments)
    }
    expected_names = set(STATION_COMMENTS)
    if station_names != expected_names:
        problem(
            "Dispatcher station block names differ; "
            f"missing={sorted(expected_names - station_names) or 'none'}, "
            f"extra={sorted(station_names - expected_names) or 'none'}"
        )
    station_snapshot: list[tuple[str, str]] = []
    for name, expected_comment in STATION_COMMENTS.items():
        comments = definitions.get(name, [])
        if expected_comment not in comments:
            problem(
                f"Dispatcher station {name!r}: expected block comment "
                f"{expected_comment!r}, found {comments or ['<missing block>']}"
            )
        station_snapshot.append((name, expected_comment if expected_comment in comments else ""))

    sensors: list[str] = []
    for sensor in root.findall("./sensors/sensor"):
        name = text(sensor, "userName")
        if name.startswith("MoveTo") or name.startswith("MoveInProgress"):
            sensors.append(name)
    sensor_set = set(sensors)
    expected_sensors: set[str] = set()
    expected_icons: set[str] = set()
    for name in STATION_COMMENTS:
        key = sensor_key(name)
        expected_sensors.update(
            {f"MoveTo{key}_stored", f"MoveInProgress{key}"}
        )
        expected_icons.update(
            {f"MoveTo{key}_stored", f"MoveInProgress{key}"}
        )
    if sensor_set != expected_sensors or len(sensors) != len(expected_sensors):
        problem(
            "Dispatcher station sensor pairs differ; "
            f"missing={sorted(expected_sensors - sensor_set) or 'none'}, "
            f"extra={sorted(sensor_set - expected_sensors) or 'none'}, "
            f"duplicates={sorted(name for name in sensor_set if sensors.count(name) > 1) or 'none'}"
        )

    icon_sensors: list[str] = []
    if panel is not None:
        for icon in panel.iter("sensoricon"):
            name = (icon.get("sensor") or "").strip()
            if name.startswith("MoveTo") or name.startswith("MoveInProgress"):
                icon_sensors.append(name)
    icon_set = set(icon_sensors)
    if icon_set != expected_icons or len(icon_sensors) != len(expected_icons):
        problem(
            "Dispatcher station sensor icons are not exactly one paired icon per station; "
            f"missing={sorted(expected_icons - icon_set) or 'none'}, "
            f"extra={sorted(icon_set - expected_icons) or 'none'}, "
            f"duplicates={sorted(name for name in icon_set if icon_sensors.count(name) > 1) or 'none'}"
        )
    audit.facts["stations"] = tuple(sorted(station_snapshot))
    audit.facts["station_sensors"] = tuple(sorted(sensor_set))
    audit.facts["station_icons"] = tuple(sorted(icon_set))


def audit_placeholders(panel: ET.Element | None, audit: Audit) -> None:
    placeholders: list[str] = []
    redundant_occupancy_icons: list[str] = []
    if panel is not None:
        for label in panel.iter("positionablelabel"):
            value = (label.get("text") or text(label, "text")).strip()
            if value.upper().startswith("SIG"):
                placeholders.append(value)
        station_occupancy = {
            "Block 4-6",
            "Block 4-7",
            "Block 2-1",
            "Block 2-3",
            "Block 1-8",
            "Block 1-7",
            "Block 1-1",
            "Block 1-2",
            "Block 13-5",
            "Block 13-6",
            "Block 13-7",
            "Block 2-8",
            "Block 2-7",
            "Block 2-6",
            "Block 2-5",
            "Block 2-4",
            "Block 4-8",
            "Block 13-1",
            "Block 4-4",
            "Block 4-3",
            "Block 1-4",
            "Block 1-3",
        }
        for icon in panel.iter("sensoricon"):
            name = (icon.get("sensor") or "").strip()
            if re.fullmatch(r"Block \d+-\d+", name) and name not in station_occupancy:
                redundant_occupancy_icons.append(name)
    if placeholders:
        audit.warn(f"stale SIG placeholder labels remain: {sorted(placeholders)}")
    if redundant_occupancy_icons:
        audit.warn(
            "redundant block-occupancy sensor icons remain on Layout Editor: "
            f"{sorted(redundant_occupancy_icons)}"
        )
    audit.facts["sig_placeholders"] = tuple(sorted(placeholders))
    audit.facts["occupancy_sensor_icons"] = tuple(
        sorted(redundant_occupancy_icons)
    )


def audit_generated_dispatcher(root: ET.Element, audit: Audit) -> None:
    ctc_bundle = (
        len(root.findall("ctcdata")),
        len(root.findall("paneleditor")),
        len(root.findall("LayoutEditor")),
    )
    if ctc_bundle != (1, 1, 2):
        audit.error(
            "deployment bundle expected ctcdata=1, paneleditor=1, "
            f"LayoutEditor=2; found {ctc_bundle}"
        )
    sections = len(root.findall("./sections/section"))
    transits = len(root.findall("./transits/transit"))
    if (sections, transits) != (41, 175):
        audit.error(
            f"generated Dispatcher graph expected 41 sections / 175 transits, "
            f"found {sections} / {transits}"
        )
    files = sorted(TRAININFO.glob("*.xml"))
    bad_detection: list[str] = []
    for path in files:
        try:
            train_root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            audit.error(f"invalid traininfo {path.name}: {exc}")
            continue
        values = [
            element.get("traindetection")
            for element in train_root.iter()
            if element.get("traindetection")
        ]
        if values != ["TRAINDETECTION_HEADANDTAIL"]:
            bad_detection.append(path.name)
    if len(files) != 394:
        audit.error(f"expected 394 generated traininfo files, found {len(files)}")
    if bad_detection:
        audit.error(
            "traininfo not HEAD_AND_TAIL: "
            + ", ".join(bad_detection[:8])
            + (" ..." if len(bad_detection) > 8 else "")
        )
    audit.facts["dispatcher_generated"] = (
        *ctc_bundle,
        sections,
        transits,
        len(files),
    )


def audit_source(
    label: str, path: Path, boundaries: list[Boundary], expected_masts: set[str]
) -> Audit:
    audit = Audit(label=label, path=path)
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        audit.error(f"cannot parse source: {exc}")
        return audit
    panel = select_panel(root, audit)
    full_config = label != "standalone"
    audit_masts(root, expected_masts, audit)
    audit_bindings(panel, boundaries, audit)
    if full_config:
        audit_sml(root, audit, required=True)
        audit_stations(root, panel, audit, required=True)
        if label == "deployment":
            audit_generated_dispatcher(root, audit)
    else:
        # hart_prod.xml is intentionally a standalone monitor artifact, not a
        # complete JMRI configuration. Audit only its visual/topology contract.
        audit.facts["sml"] = ()
        audit.facts["stations"] = ()
        audit.facts["station_sensors"] = ()
        audit.facts["station_icons"] = ()
    audit_placeholders(panel, audit)
    return audit


def concise_delta(reference: object, current: object) -> str:
    if isinstance(reference, tuple) and isinstance(current, tuple):
        reference_set = set(reference)
        current_set = set(current)
        removed = sorted(reference_set - current_set)
        added = sorted(current_set - reference_set)
        return f"missing={short_items(removed)}, extra={short_items(added)}"
    return f"expected={reference!r}, found={current!r}"


def short_items(items: list[object], limit: int = 8) -> object:
    if not items:
        return "none"
    if len(items) <= limit:
        return items
    return f"{items[:limit]} ... (+{len(items) - limit} more)"


def report_drift(audits: list[Audit]) -> list[str]:
    if not audits:
        return []
    reference = next((item for item in audits if item.label == "deployment"), audits[0])
    drift: list[str] = []
    full_sections = (
        "masts",
        "bindings",
        "sml",
        "stations",
        "station_sensors",
        "station_icons",
        "cats_virtual",
        "sig_placeholders",
    )
    visual_sections = ("masts", "bindings", "cats_virtual", "sig_placeholders")
    for audit in audits:
        if audit is reference:
            continue
        sections = visual_sections if audit.label == "standalone" else full_sections
        for section in sections:
            expected = reference.facts.get(section)
            actual = audit.facts.get(section)
            if expected != actual:
                drift.append(
                    f"{audit.label} differs from {reference.label} in {section}: "
                    f"{concise_delta(expected, actual)}"
                )
    return drift


def print_messages(prefix: str, messages: Iterable[str]) -> None:
    for message in messages:
        print(f"  {prefix}: {message}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit HART panel contracts without modifying XML/configuration files."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail when warnings or semantic source drift are present",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        boundaries = load_boundaries(BOUNDARIES)
    except (OSError, KeyError, ValueError) as exc:
        print(f"ERROR: cannot load boundary contract: {exc}")
        return 1
    expected_masts = {item.mast for item in boundaries}
    audits = [
        audit_source(label, path, boundaries, expected_masts)
        for label, path in DEFAULT_SOURCES
    ]
    for audit in audits:
        panel = audit.facts.get("panel", "<not selected>")
        print(
            f"{audit.label}: {audit.path.relative_to(REPO_ROOT)} "
            f"(panel={panel}, errors={len(audit.errors)}, warnings={len(audit.warnings)})"
        )
        print_messages("ERROR", audit.errors)
        print_messages("WARN", audit.warnings)

    drift = report_drift(audits)
    print(f"source drift: {len(drift)} difference(s)")
    print_messages("DRIFT", drift)

    errors = sum(len(audit.errors) for audit in audits)
    warnings = sum(len(audit.warnings) for audit in audits)
    failed = errors > 0 or (args.strict and (warnings > 0 or bool(drift)))
    mode = "strict" if args.strict else "default"
    print(
        f"RESULT: {'FAIL' if failed else 'PASS'} ({mode}; "
        f"hard errors={errors}, warnings={warnings}, drift={len(drift)})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
