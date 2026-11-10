"""Engine roster helpers for locomotive card descriptions."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
ENGINE_ROSTER_XML = BASE / "data" / "OperationsEngineRoster.xml"

ROAD_DISPLAY = {
    "NW": "N&W",
    "BO": "B&O",
    "PRR": "PRR",
    "NYC": "NYC",
    "ATSF": "ATSF",
    "CBQ": "CB&Q",
    "GN": "GN",
    "MILW": "MILW",
    "WP": "WP",
    "WM": "WM",
    "RDG": "RDG",
    "EL": "EL",
    "CO": "C&O",
    "KSMX": "KSMX",
    "GATX": "GATX",
    "UTLX": "UTLX",
    "URTX": "URTX",
    "SHPX": "SHPX",
    "REX": "REX",
    "URR": "URR",
    "WLE": "WLE",
    "MSTL": "MSTL",
    "MOW": "MOW",
    "CSX": "CSX",
    "CWRY": "Ohio Central",
}

ENGINE_ROAD_ALIASES = {
    "OC": "CWRY",
    "OHIO CENTRAL": "CWRY",
    "B&O": "BO",
    "C&O": "CO",
    "CR": "CR",
    "CONRAIL": "CR",
    "CSX": "CSX",
}

# Model -> manufacturer (EMD, GE, ALCO, etc.)
MODEL_MANUFACTURER: dict[str, str] = {
    "GP20": "EMD",
    "GP30": "EMD",
    "GP35": "EMD",
    "GP38": "EMD",
    "GP40": "EMD",
    "GP40-2": "EMD",
    "SW1200": "EMD",
    "SW1500": "EMD",
    "SW8": "EMD",
    "NW2": "EMD",
    "NW2 Phase V": "EMD",
    "F3": "EMD",
    "F7": "EMD",
    "F7A": "EMD",
    "F7B": "EMD",
    "F9": "EMD",
    "FT": "EMD",
    "SD26": "EMD",
    "SD45": "EMD",
    "E8": "EMD",
    "U30B": "GE",
    "U28B": "GE",
    "B23-7": "GE",
    "ES44AH": "GE",
    "AS-16": "ALCO",
    "RS1": "ALCO",
    "RS2": "ALCO",
    "RS3": "ALCO",
    "RS11": "ALCO",
    "RS18": "ALCO",
    "RS27": "ALCO",
    "RSD4": "ALCO",
    "P-7": "EMD",
}

# Locomotives not in OperationsEngineRoster.xml
MANUAL_ENGINES: dict[tuple[str, str], dict] = {
    ("CR", "1993"): {
        "engine_roster_id": "",
        "model": "B23-7",
        "length_ft": "61",
        "manufacturer": "GE",
    },
}


def manufacturer_for_model(model: str) -> str:
    model = model.strip()
    if not model:
        return ""
    if model in MODEL_MANUFACTURER:
        return MODEL_MANUFACTURER[model]
    upper = model.upper()
    for key, mfr in MODEL_MANUFACTURER.items():
        if key.upper() in upper or upper in key.upper():
            return mfr
    if model.startswith(("GP", "SW", "NW", "F", "SD", "E")):
        return "EMD"
    if model.startswith(("U", "B23", "ES", "C", "AC")):
        return "GE"
    return ""


def load_engine_roster() -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    root = ET.parse(ENGINE_ROSTER_XML).getroot()
    by_id: dict[str, dict] = {}
    by_key: dict[tuple[str, str], dict] = {}
    for el in root.findall("./engines/engine"):
        rid = el.get("id", "")
        road = el.get("roadName", "")
        num = el.get("roadNumber", "")
        model = el.get("model", "")
        rec = {
            "engine_roster_id": rid,
            "roster_road": road,
            "road_number": num,
            "engine_type": el.get("type", ""),
            "model": model,
            "length_ft": el.get("length", ""),
            "manufacturer": manufacturer_for_model(model),
        }
        by_id[rid] = rec
        by_key[(road, num)] = rec
    return by_id, by_key


def match_engine(row: dict, by_key: dict[tuple[str, str], dict]) -> dict | None:
    marks = (row.get("reporting_marks") or row.get("road_name") or "").strip()
    number = (row.get("road_number") or "").strip()
    if not number:
        return None
    norm_marks = re.sub(r"[^A-Z0-9&]", "", marks.upper())
    candidates = [norm_marks, marks.upper()]
    alias = ENGINE_ROAD_ALIASES.get(marks.upper()) or ENGINE_ROAD_ALIASES.get(norm_marks)
    if alias:
        candidates.append(alias)
    for road in candidates:
        hit = by_key.get((road, number))
        if hit:
            return hit
        manual = MANUAL_ENGINES.get((road, number))
        if manual:
            return manual
    return MANUAL_ENGINES.get((norm_marks, number)) or MANUAL_ENGINES.get((marks.upper(), number))


def is_locomotive_row(row: dict) -> bool:
    ctype = (row.get("car_type") or "").strip().lower()
    return ctype in ("locomotive", "diesel", "engine", "switcher", "electric")


def build_locomotive_description(engine: dict | None, row: dict | None = None) -> str:
    if engine:
        mfr = engine.get("manufacturer") or manufacturer_for_model(engine.get("model", ""))
        model = engine.get("model", "")
        length = engine.get("length_ft", "")
    elif row:
        mfr = ""
        model = ""
        length = row.get("roster_length_ft", "")
        notes = row.get("notes", "")
        m = re.search(r"\b(GP\d+|SW\d+|B23-7|ES44AH|NW2|U\d+B)\b", notes, re.I)
        if m:
            model = m.group(1).upper() if m.group(1).upper().startswith("B") else m.group(1)
            if model.lower() == "gp-38":
                model = "GP38"
            mfr = manufacturer_for_model(model)
    else:
        return ""

    parts: list[str] = []
    if mfr:
        parts.append(mfr)
    if model:
        parts.append(model)
    if length:
        parts.append(f"{length}'")
    return " · ".join(parts)
