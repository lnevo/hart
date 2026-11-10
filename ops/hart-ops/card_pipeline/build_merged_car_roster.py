#!/usr/bin/env python3
"""Build a merged JMRI car roster from image_metadata.csv (primary) and legacy OperationsCarRoster.xml."""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from engine_lookup import is_locomotive_row
from roster_id import assign_freight_roster_id, manifest_car_id, road_code

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
DATA = BASE / "data"
SOURCE_ROSTER = DATA / "OperationsCarRoster.xml"
MANIFEST_CSV = DATA / "image_metadata.csv"
OUTPUT_ROSTER = DATA / "HART_MergedCarRoster.xml"

# Wrong roster ids mapped to the right ones (see apply_visual_review corrections).
ROSTER_TYPO_IDS = {
    "BO446063": "BO466063",
    "UTLX32638": "UTLX32642",
    "UTLX39084": "UTLX39042",
    "CO37700": "CO377700",
    "CO306585": "CO306607",
    "PRR474261": "PRR474563",
    "SHPX22425": "SHPX22329",
    "GATX31028": "GATX31090",
    "MSTL52763": "MSTL52673",
    "BO371604": "PRR371604",  # wrong road, not a misread number
}

JMRI_COLORS = [
    "Black",
    "Blue",
    "Brown",
    "Gray",
    "Yellow",
    "Green",
    "Orange",
    "Purple",
    "Red",
    "Silver",
    "Tuscan",
    "White",
]

# Typical JMRI weight by length (from existing HART roster).
LENGTH_WEIGHT: dict[str, tuple[str, str]] = {
    "34": ("3.3", "66"),
    "36": ("3.5", "32"),
    "40": ("3.8", "76"),
    "45": ("4.1", "82"),
    "50": ("4.4", "88"),
    "52": ("4.6", "92"),
    "53": ("4.7", "94"),
    "55": ("4.8", "96"),
    "67": ("5.6", "60"),
    "72": ("6.0", "64"),
    "80": ("6.5", "72"),
    "85": ("6.9", "76"),
    "90": ("7.2", "144"),
}

CAR_ATTR_ORDER = (
    "id",
    "roadName",
    "roadNumber",
    "type",
    "length",
    "color",
    "weight",
    "weightTons",
    "locationId",
    "secLocationId",
    "lastRouteId",
    "moves",
    "date",
    "selected",
    "caboose",
    "passenger",
    "lastLocationId",
    "lastTrackId",
    "lastTrain",
    "lastTrainId",
    "load",
    "nextDestId",
    "nextDestTrackId",
    "previousNextDestId",
    "previousNextDestTrackId",
    "rweDestId",
    "rwlDestId",
    "rwlDestTrackId",
)


def normalize_roster_type(car_type: str) -> str:
    t = car_type.strip()
    if t == "Coal":
        return "Hopper"
    return t


def normalize_color(color: str) -> str:
    c = color.strip()
    if not c:
        return ""
    if c in JMRI_COLORS:
        return c
    lower = c.lower()
    for name in JMRI_COLORS:
        if name.lower() in lower:
            return name
    return c


def default_weights(length: str) -> tuple[str, str]:
    return LENGTH_WEIGHT.get(length, ("3.8", "76"))


def car_sort_key(attrs: dict) -> tuple:
    road = attrs.get("roadName", "")
    number = attrs.get("roadNumber", "")
    num_match = re.search(r"\d+", number)
    num_val = int(num_match.group()) if num_match else 0
    return (road, num_val, number)


def attrs_from_element(el: ET.Element) -> dict[str, str]:
    attrs = dict(el.attrib)
    if "type" in attrs:
        attrs["type"] = normalize_roster_type(attrs["type"])
    return attrs


def format_car_line(attrs: dict[str, str]) -> str:
    parts: list[str] = []
    for key in CAR_ATTR_ORDER:
        if key in attrs:
            parts.append(f'{key}="{attrs[key]}"')
    for key, value in sorted(attrs.items()):
        if key not in CAR_ATTR_ORDER:
            parts.append(f'{key}="{value}"')
    return "    <car " + " ".join(parts) + " />"


def load_manifest_freight() -> list[dict]:
    rows = list(csv.DictReader(MANIFEST_CSV.open(newline="")))
    freight: list[dict] = []
    for row in rows:
        ctype = (row.get("car_type") or "").strip()
        if is_locomotive_row(row) or ctype in ("Locomotive", "Streetcar"):
            continue
        freight.append(row)
    return freight


def manifest_to_car(row: dict) -> dict[str, str] | None:
    rc = road_code(row)
    num = (row.get("road_number") or "").strip()
    if not rc or not num:
        return None

    cid = manifest_car_id(row)
    length = (row.get("roster_length_ft") or "").strip()
    weight = (row.get("roster_weight_oz") or "").strip()
    weight_tons = (row.get("roster_weight_tons") or "").strip()
    if not length:
        if weight_tons.isdigit() and int(weight_tons) >= 100:
            length = "90"
        else:
            length = "40"
    if not weight or not weight_tons:
        weight, weight_tons = default_weights(length)

    car_type = normalize_roster_type((row.get("car_type") or "Boxcar").strip() or "Boxcar")
    color = normalize_color(row.get("color") or "")

    attrs: dict[str, str] = {
        "id": cid,
        "roadName": rc,
        "roadNumber": num,
        "type": car_type,
        "length": length,
        "weight": weight,
        "weightTons": weight_tons,
        "moves": "0",
        "date": "",
        "selected": "false",
        "load": "E",
    }
    if color:
        attrs["color"] = color
    if car_type == "Caboose":
        attrs["caboose"] = "true"
    return attrs


def build_color_lookup(freight: list[dict]) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    by_id: dict[str, str] = {}
    by_key: dict[tuple[str, str], str] = {}
    for row in freight:
        color = normalize_color(row.get("color") or "")
        if not color:
            continue
        cid = manifest_car_id(row)
        if cid:
            by_id[cid] = color
        rc = road_code(row)
        num = (row.get("road_number") or "").strip()
        if rc and num:
            by_key[(rc, num)] = color
    return by_id, by_key


def merge_roster() -> tuple[dict[str, dict[str, str]], list[str]]:
    """Build roster metadata-first, then merge legacy ops-only cars (passenger/caboose)."""
    freight = load_manifest_freight()
    by_id_color, by_key_color = build_color_lookup(freight)
    skipped: list[str] = []
    cars: dict[str, dict[str, str]] = {}

    for row in freight:
        new_car = manifest_to_car(row)
        if new_car is None:
            skipped.append(row.get("source_image", "?"))
            continue
        cars[new_car["id"]] = new_car

    for cid, attrs in cars.items():
        if "color" in attrs:
            continue
        color = by_id_color.get(cid) or by_key_color.get(
            (attrs.get("roadName", ""), attrs.get("roadNumber", "")), ""
        )
        if color:
            attrs["color"] = color

    if SOURCE_ROSTER.is_file():
        root = ET.parse(SOURCE_ROSTER).getroot()
        for el in root.findall("./cars/car"):
            attrs = attrs_from_element(el)
            cid = attrs["id"]
            if cid in ROSTER_TYPO_IDS:
                continue
            if cid not in cars:
                cars[cid] = attrs
            else:
                if "color" not in cars[cid] and attrs.get("color"):
                    cars[cid]["color"] = attrs["color"]
                for flag in ("caboose", "passenger"):
                    if flag in attrs and flag not in cars[cid]:
                        cars[cid][flag] = attrs[flag]

    for cid in list(cars):
        if cid in ROSTER_TYPO_IDS:
            del cars[cid]

    return cars, skipped


def collect_sections(cars: dict[str, dict[str, str]], source_root: ET.Element) -> dict:
    roads = sorted({a["roadName"] for a in cars.values() if a.get("roadName")})
    types = sorted({a["type"] for a in cars.values() if a.get("type")})
    lengths = sorted(
        {a["length"] for a in cars.values() if a.get("length")},
        key=lambda x: int(x) if x.isdigit() else 0,
    )
    colors_used = sorted({a["color"] for a in cars.values() if a.get("color")})
    colors = sorted(set(JMRI_COLORS) | set(colors_used))
    return {
        "roads": roads,
        "types": types,
        "colors": colors,
        "lengths": lengths,
    }


def write_roster(cars: dict[str, dict[str, str]], skipped: list[str]) -> None:
    source_root = ET.parse(SOURCE_ROSTER).getroot()
    sections = collect_sections(cars, source_root)
    sorted_cars = [cars[cid] for cid in sorted(cars, key=lambda i: car_sort_key(cars[i]))]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?xml-stylesheet href="/xml/XSLT/operations-cars.xsl" type="text/xsl"?>',
        '<!DOCTYPE operations-config SYSTEM "/xml/DTD/operations-cars.dtd">',
        "<operations-config>",
        f"  <!--Merged HART car roster — {len(sorted_cars)} cars — "
        f"{datetime.now():%a %b %d %H:%M:%S %Y}-->",
        "  <roads>",
    ]
    for road in sections["roads"]:
        lines.append(f'    <road name="{road}" />')
    lines.append("  </roads>")
    lines.append("  <types>")
    for ctype in sections["types"]:
        lines.append(f'    <type name="{ctype}" />')
    lines.append("  </types>")
    lines.append("  <colors>")
    for color in sections["colors"]:
        lines.append(f'    <color name="{color}" />')
    lines.append("  </colors>")
    lines.append("  <lengths>")
    for length in sections["lengths"]:
        lines.append(f'    <length value="{length}" />')
    lines.append("  </lengths>")
    lines.append('  <owners>')
    lines.append('    <owner name="" />')
    lines.append("  </owners>")
    lines.append("  <loads>")
    lines.append('    <defaults empty="E" load="L" />')
    lines.append("  </loads>")
    lines.append("  <newKernels />")
    lines.append("  <options />")
    lines.append("  <cars>")
    for attrs in sorted_cars:
        lines.append(format_car_line(attrs))
    lines.append("  </cars>")
    lines.append("</operations-config>")
    lines.append("")

    OUTPUT_ROSTER.write_text("\n".join(lines), encoding="utf-8")

    with_color = sum(1 for a in sorted_cars if a.get("color"))
    print(f"Wrote {OUTPUT_ROSTER.name}: {len(sorted_cars)} cars ({with_color} with color)")
    if skipped:
        print(f"Skipped {len(skipped)} manifest row(s) without road/number: {', '.join(skipped)}")


def main() -> None:
    cars, skipped = merge_roster()
    write_roster(cars, skipped)


if __name__ == "__main__":
    main()
