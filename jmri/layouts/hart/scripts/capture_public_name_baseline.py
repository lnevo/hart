#!/usr/bin/env python3
"""Read-only baseline capture for public-name rename regression checks.

Writes live userNames / bindings from tables.xml (and the live CATS CTC
hold panel when present). Re-run before a rename pass so `current` in
public_name_map.csv can be diffed against this snapshot.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TABLES = REPO_ROOT / "jmri" / "layouts" / "hart" / "output" / "tables.xml"
DEFAULT_OUT = REPO_ROOT / "jmri" / "layouts" / "hart" / "data" / "baselines"
CATS_MASTER_CANDIDATES = (
    REPO_ROOT / "cats" / "panels" / "HART_Master_CTC_hold.xml",
    REPO_ROOT / "cats" / "panels" / "HART_Master_ABS_hold.xml",
    REPO_ROOT / "cats" / "panels" / "HART_Master.xml",
    REPO_ROOT / "cats" / "panels" / "HART_Master_ABS.xml",
)

TURNOUT_MAST_SLOTS = ("signalAMast", "signalBMast", "signalCMast", "signalDMast")
POINT_MAST_ATTRS = ("eastboundsignalmast", "westboundsignalmast")


def text(element: ET.Element | None, child: str) -> str:
    if element is None:
        return ""
    value = element.findtext(child)
    return value.strip() if value else ""


def attr_or_child(element: ET.Element, name: str) -> str:
    return (element.get(name) or text(element, name)).strip()


def child_text(element: ET.Element) -> str:
    parts = [chunk.strip() for chunk in element.itertext() if chunk.strip()]
    return parts[0] if parts else ""


def join_signals(parent: ET.Element | None) -> str:
    if parent is None:
        return ""
    signals = [text(signal, ".") or (signal.text or "").strip() for signal in parent.findall("signal")]
    signals = [signal for signal in signals if signal]
    return "|".join(signals)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows, key=lambda row: tuple(row.get(field, "") for field in fieldnames))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted_rows)
    return len(sorted_rows)


def capture_hardware_identity(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for sensor in root.iter("sensor"):
        user_name = text(sensor, "userName")
        if user_name.startswith("Block") or ("Switch" in user_name and " FB" in user_name):
            rows.append(
                {
                    "layer": "sensor",
                    "systemName": text(sensor, "systemName"),
                    "userName": user_name,
                }
            )

    for turnout in root.iter("turnout"):
        system_name = text(turnout, "systemName")
        user_name = text(turnout, "userName")
        if system_name.startswith("M2T") or user_name.startswith("Switch "):
            rows.append(
                {
                    "layer": "turnout",
                    "systemName": system_name,
                    "userName": user_name,
                }
            )

    for signalhead in root.iter("signalhead"):
        system_name = text(signalhead, "systemName")
        if system_name.startswith("IH"):
            rows.append(
                {
                    "layer": "signalhead",
                    "systemName": system_name,
                    "userName": text(signalhead, "userName"),
                }
            )

    for tag in ("signalmast", "virtualsignalmast"):
        for signalmast in root.iter(tag):
            rows.append(
                {
                    "layer": "signalmast",
                    "systemName": text(signalmast, "systemName"),
                    "userName": text(signalmast, "userName"),
                }
            )

    blocks_by_name: dict[str, dict[str, str]] = {}
    for block in root.iter("block"):
        system_name = attr_or_child(block, "systemName")
        if not system_name.startswith("IB"):
            continue
        user_name = text(block, "userName")
        occupancy = text(block, "occupancysensor")
        if occupancy and user_name:
            combined = f"{user_name}|{occupancy}"
        elif occupancy:
            combined = occupancy
        else:
            combined = user_name
        blocks_by_name[system_name] = {
            "layer": "block",
            "systemName": system_name,
            "userName": combined,
        }
    rows.extend(blocks_by_name.values())
    return rows


def capture_sml_pairs(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for logic in root.iter("signalmastlogic"):
        source = logic.get("source", "").strip()
        for destination in logic.findall("destinationMast"):
            rows.append(
                {
                    "source": source,
                    "destination": destination.get("destination", "").strip(),
                    "associatedSection": text(destination, "associatedSection"),
                }
            )
    return rows


def capture_sml_sections(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in root.iter("section"):
        if section.get("creationtype") != "signalmastlogic":
            continue
        user_name = section.get("userName", "").strip()
        if user_name:
            rows.append({"sectionUserName": user_name})
    return rows


def capture_ctc_sidi(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for column in root.iter("ctcCodeButtonData"):
        column_number = text(column, "GUIColumnNumber")
        if not column_number:
            continue
        rows.append(
            {
                "column": column_number,
                "turnout": text(column, "SWDI_ExternalTurnout"),
                "ltr": join_signals(column.find("SIDI_LeftRightTrafficSignals")),
                "rtl": join_signals(column.find("SIDI_RightLeftTrafficSignals")),
            }
        )
    return rows


def capture_ctc_trl(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for column in root.iter("ctcCodeButtonData"):
        column_number = text(column, "GUIColumnNumber")
        if not column_number:
            continue
        for direction, tag in (("LEFT", "TRL_LeftRules"), ("RIGHT", "TRL_RightRules")):
            rules_parent = column.find(tag)
            if rules_parent is None:
                continue
            for rule in rules_parent.findall("TRL_TrafficLockingRule"):
                dest = text(rule, "DestinationSignalOrComment")
                sensors = join_signals(rule.find("OccupancyExternalSensors"))
                if not dest and not sensors:
                    continue
                rows.append(
                    {
                        "column": column_number,
                        "direction": direction,
                        "dest": dest,
                        "occupancySensors": sensors,
                    }
                )
    return rows


def capture_le_mast_bindings(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for turnout in root.iter("layoutturnout"):
        ident = turnout.get("ident", "").strip()
        if not ident:
            continue
        for slot_tag in TURNOUT_MAST_SLOTS:
            mast = text(turnout, slot_tag)
            if mast:
                rows.append(
                    {
                        "kind": "turnout",
                        "ident": ident,
                        "slot": slot_tag.replace("signal", "").replace("Mast", ""),
                        "mast": mast,
                    }
                )

    for point in root.iter("positionablepoint"):
        ident = point.get("ident", "").strip()
        if not ident:
            continue
        for attr in POINT_MAST_ATTRS:
            mast = point.get(attr, "").strip()
            if mast:
                slot = attr.replace("boundsignalmast", "")
                rows.append(
                    {
                        "kind": "point",
                        "ident": ident,
                        "slot": slot,
                        "mast": mast,
                    }
                )
    return rows


def capture_block_sensors(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for layoutblock in root.iter("layoutblock"):
        occupancy = layoutblock.get("occupancysensor", "").strip()
        if not occupancy:
            continue
        user_name = attr_or_child(layoutblock, "userName")
        rows.append({"blockUserName": user_name, "occupancySensor": occupancy})
    return rows


def find_cats_master() -> Path | None:
    for path in CATS_MASTER_CANDIDATES:
        if path.is_file():
            return path
    return None


def capture_cats_bindings(cats_path: Path) -> list[dict[str, str]]:
    root = ET.parse(cats_path).getroot()
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for edge in root.iter("SEC_EDGE"):
        block = edge.find("BLOCK")
        if block is None:
            continue
        block_name = block.get("NAME", "").strip()
        if not block_name:
            continue

        occupied = block.find("OCCUPIEDSPEC")
        iospec = occupied.find("IOSPEC") if occupied is not None else None
        sensor_user_name = iospec.get("USER_NAME", "").strip() if iospec is not None else ""
        prefix = iospec.get("JMRIPREFIX", "").strip() if iospec is not None else ""
        decaddr = iospec.get("DECADDR", "").strip() if iospec is not None else ""
        mqtt_addr = f"{prefix}{decaddr}" if prefix and decaddr else ""

        secsignal = ""
        signal_elem = edge.find("SECSIGNAL")
        if signal_elem is not None:
            secsignal = child_text(signal_elem)

        if not sensor_user_name and not mqtt_addr:
            continue

        key = (block_name, sensor_user_name, mqtt_addr, secsignal)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "blockName": block_name,
                "sensorUserName": sensor_user_name,
                "mqttAddr": mqtt_addr,
                "secsignal": secsignal,
            }
        )
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_counts(path: Path, tables_path: Path, counts: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"tables.xml sha256={sha256_file(tables_path)}",
        f"tables.xml path={tables_path}",
        "",
    ]
    for name in sorted(counts):
        lines.append(f"{name}={counts[name]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", type=Path, default=DEFAULT_TABLES, help="JMRI tables.xml path")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory for baselines")
    args = parser.parse_args()

    if not args.tables.is_file():
        print(f"tables.xml not found: {args.tables}", file=sys.stderr)
        return 1

    root = ET.parse(args.tables).getroot()
    counts: dict[str, int] = {}

    captures = (
        ("hardware_identity.csv", ["layer", "systemName", "userName"], capture_hardware_identity(root)),
        ("sml_pairs.csv", ["source", "destination", "associatedSection"], capture_sml_pairs(root)),
        ("sml_sections.csv", ["sectionUserName"], capture_sml_sections(root)),
        ("ctc_sidi.csv", ["column", "turnout", "ltr", "rtl"], capture_ctc_sidi(root)),
        ("ctc_trl.csv", ["column", "direction", "dest", "occupancySensors"], capture_ctc_trl(root)),
        ("le_mast_bindings.csv", ["kind", "ident", "slot", "mast"], capture_le_mast_bindings(root)),
        ("block_sensors.csv", ["blockUserName", "occupancySensor"], capture_block_sensors(root)),
    )

    written: list[tuple[str, int]] = []
    for filename, fieldnames, rows in captures:
        out_path = args.out / filename
        count = write_csv(out_path, fieldnames, rows)
        counts[filename] = count
        written.append((str(out_path), count))

    cats_master = find_cats_master()
    if cats_master is not None:
        cats_rows = capture_cats_bindings(cats_master)
        cats_path = args.out / "cats_bindings.csv"
        cats_count = write_csv(
            cats_path,
            ["blockName", "sensorUserName", "mqttAddr", "secsignal"],
            cats_rows,
        )
        counts["cats_bindings.csv"] = cats_count
        written.append((str(cats_path), cats_count))
    else:
        counts["cats_bindings.csv"] = 0

    counts_path = args.out / "counts.txt"
    write_counts(counts_path, args.tables, counts)
    written.append((str(counts_path), None))

    print(f"Wrote baselines to {args.out}")
    if cats_master is not None:
        print(f"CATS source: {cats_master}")
    else:
        print("CATS source: not found (skipped cats_bindings.csv)")
    for path, count in written:
        if count is None:
            print(f"  {path}: (metadata)")
        else:
            print(f"  {path}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
