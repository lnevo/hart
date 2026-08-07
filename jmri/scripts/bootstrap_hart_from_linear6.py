#!/usr/bin/env python3
"""Bootstrap jmri/layouts/hart from linear6 panel.

- Freeze linear6 baseline (connectivity + positions)
- Copy to hart authoritative / output panels
- Apply block display-name contract (ADR-002)
- Remove unreferenced internal sensors (keep ISCLOCKRUNNING) (ADR-003)

Does not modify live linear6.xml or tables/tables.xml.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

JMRI_ROOT = Path(__file__).resolve().parents[1]
LINEAR6 = JMRI_ROOT / "layouts" / "linear6" / "linear6.xml"
HART = JMRI_ROOT / "layouts" / "hart"
BASELINE = HART / "reference" / "linear6_baseline.xml"
DISPLAY_CSV = HART / "data" / "block_display_names.csv"
PURGE_REPORT = HART / "data" / "sensor_purge_report.txt"

KEEP_SENSORS = {"ISCLOCKRUNNING"}


def load_display_map(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cur = (row.get("current_user_name") or "").strip()
            pub = (row.get("public_user_name") or "").strip()
            if cur and pub and cur != pub:
                out[cur] = pub
    return out


def referenced_sensor_names(root: ET.Element) -> set[str]:
    names: set[str] = set()
    for el in root.iter():
        for attr, val in el.attrib.items():
            if "sensor" in attr.lower() and val:
                names.add(val.strip())
        tag = el.tag.lower()
        if "sensor" in tag and el.text and el.text.strip():
            if tag in {
                "occupancysensor",
                "sensor1",
                "sensor2",
                "sensor",
                "eastboundsensor",
                "westboundsensor",
                "sensora",
                "sensorb",
                "sensorc",
                "sensord",
            } or tag.endswith("sensor"):
                names.add(el.text.strip())
    return names


def sensor_system_name(el: ET.Element) -> str:
    return (el.get("systemName") or el.findtext("systemName") or "").strip()


def sensor_user_name(el: ET.Element) -> str:
    return (el.findtext("userName") or el.get("userName") or "").strip()


def purge_unused_internal_sensors(root: ET.Element) -> list[str]:
    refs = referenced_sensor_names(root)
    removed: list[str] = []
    # JMRI may nest sensors under one or more <sensors> managers
    for sensors_parent in root.findall("sensors"):
        for el in list(sensors_parent.findall("sensor")):
            sn = sensor_system_name(el)
            un = sensor_user_name(el)
            if not sn:
                continue
            if sn in KEEP_SENSORS or sn.startswith("ISC"):
                continue
            # Only purge internal IS/ISIS leftovers, never MQTT M2S*
            if not sn.startswith("IS"):
                continue
            if sn in refs or un in refs:
                continue
            sensors_parent.remove(el)
            removed.append(f"{sn}\t{un}")
    return removed


def rename_blocks(root: ET.Element, mapping: dict[str, str]) -> int:
    n = 0
    for b in root.iter("block"):
        un_el = b.find("userName")
        if un_el is None or not (un_el.text or "").strip():
            continue
        cur = un_el.text.strip()
        if cur in mapping:
            un_el.text = mapping[cur]
            n += 1
    for lb in root.iter("layoutblock"):
        # userName element or attributes used by JMRI variants
        un_el = lb.find("userName")
        if un_el is not None and (un_el.text or "").strip() in mapping:
            un_el.text = mapping[un_el.text.strip()]
            n += 1
        for attr in ("username", "userName"):
            if lb.get(attr) in mapping:
                lb.set(attr, mapping[lb.get(attr)])
                n += 1
    # LayoutEditor blockname attributes on segments/turnouts
    for el in root.iter():
        bn = el.get("blockname")
        if bn in mapping:
            el.set("blockname", mapping[bn])
            n += 1
        for attr in ("blockname2", "blockname3", "blockname4"):
            if el.get(attr) in mapping:
                el.set(attr, mapping[el.get(attr)])
                n += 1
    return n


def write_xml(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source",
        type=Path,
        default=LINEAR6,
        help="Source panel XML (default: linear6.xml)",
    )
    ap.add_argument(
        "--skip-rename",
        action="store_true",
        help="Do not apply block_display_names.csv",
    )
    ap.add_argument(
        "--skip-purge",
        action="store_true",
        help="Do not remove unused internal sensors",
    )
    args = ap.parse_args()

    src = args.source.resolve()
    if not src.is_file():
        raise SystemExit(f"Source panel not found: {src}")

    HART.mkdir(parents=True, exist_ok=True)
    for sub in (
        "anyrail",
        "authoritative",
        "data",
        "output",
        "working",
        "reference",
        "dispatcher",
    ):
        (HART / sub).mkdir(parents=True, exist_ok=True)

    shutil.copy2(src, BASELINE)
    shutil.copy2(src, HART / "anyrail" / "hart.xml")

    tree = ET.parse(src)
    root = tree.getroot()

    renamed = 0
    if not args.skip_rename:
        mapping = load_display_map(DISPLAY_CSV)
        renamed = rename_blocks(root, mapping)

    removed: list[str] = []
    if not args.skip_purge:
        removed = purge_unused_internal_sensors(root)

    out_blocked = HART / "output" / "hart_blocked.xml"
    out_prod = HART / "output" / "hart_prod.xml"
    auth = HART / "authoritative" / "hart.xml"
    write_xml(root, out_blocked)
    shutil.copy2(out_blocked, out_prod)
    shutil.copy2(out_blocked, auth)

    PURGE_REPORT.write_text(
        "Unused internal sensors removed from hart panel\n"
        f"source: {src}\n"
        f"block renames applied: {renamed}\n"
        f"sensors removed: {len(removed)}\n\n"
        + "\n".join(removed)
        + ("\n" if removed else ""),
        encoding="utf-8",
    )

    print(f"Baseline: {BASELINE}")
    print(f"Output:   {out_blocked}")
    print(f"Prod:     {out_prod}")
    print(f"Renames:  {renamed}")
    print(f"Purged:   {len(removed)} internal sensors → {PURGE_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
