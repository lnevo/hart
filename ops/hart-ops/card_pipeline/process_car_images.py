#!/usr/bin/env python3
"""Batch-process light-box car photos for HART car cards.

For every PNG in ``Images/``:
  1. Detect and crop the full car (``crop_car_image.process_image``)
  2. Save card-ready PNGs to ``CarImages/{stem}.png``
  3. Save OCR zoom bands to ``OcrZoom/OCR_{stem}.png`` (easy to filter out)
  4. OCR stencilled markings from the original-resolution car band
  5. Match to ``OperationsCarRoster.xml`` when possible
  6. Flag duplicate cars (same roster id or same marks+number)
  7. Write ``image_metadata.csv``
"""

from __future__ import annotations

import csv
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytesseract
from PIL import Image, ImageFilter, ImageOps

from crop_car_image import detect_car_bbox, process_image
from car_paths import DATA, IMAGES_DIR, OCR_DIR, ROOT as BASE

CAR_IMAGES_DIR = BASE / "CarImages"
ROSTER_XML = DATA / "OperationsCarRoster.xml"
METADATA_CSV = DATA / "image_metadata.csv"

CSV_COLUMNS = [
    "source_image",
    "cropped_image",
    "ocr_zoom_image",
    "crop_status",
    "duplicate_of",
    "reporting_marks",
    "road_name",
    "road_number",
    "full_name",
    "car_type",
    "car_class",
    "color",
    "capy_lbs",
    "ld_lmt_lbs",
    "lt_wt_lbs",
    "built",
    "roster_id",
    "roster_road",
    "roster_length_ft",
    "roster_weight_oz",
    "roster_weight_tons",
    "ocr_text",
    "match_confidence",
    "notes",
    "out_of_service",
]

ROAD_ALIASES = {
    "NW": "NW",
    "N&W": "NW",
    "N W": "NW",
    "NOW": "NW",
    "NORFOLKANDWESTERN": "NW",
    "NORFOLKWESTERN": "NW",
    "KSMX": "KSMX",
    "KSM": "KSMX",
    "K S MX": "KSMX",
    "KS MX": "KSMX",
    "BO": "BO",
    "B&O": "BO",
    "B O": "BO",
    "BALTIMOREOHIO": "BO",
    "PRR": "PRR",
    "PENNSYLVANIA": "PRR",
    "NYC": "NYC",
    "NEWYORKCENTRAL": "NYC",
    "ATSF": "ATSF",
    "SANTAFE": "ATSF",
    "CBQ": "CBQ",
    "CB&Q": "CBQ",
    "BURLINGTON": "CBQ",
    "GN": "GN",
    "GREATNORTHERN": "GN",
    "MILW": "MILW",
    "MILWAUKEE": "MILW",
    "WP": "WP",
    "WESTERNPACIFIC": "WP",
    "WM": "WM",
    "WESTERNMARYLAND": "WM",
    "RDG": "RDG",
    "READING": "RDG",
    "EL": "EL",
    "ERIELACKAWANNA": "EL",
    "CO": "CO",
    "C&O": "CO",
    "CHESAPEAKEOHIO": "CO",
    "GATX": "GATX",
    "UTLX": "UTLX",
    "URTX": "URTX",
    "SHPX": "SHPX",
    "REX": "REX",
    "URR": "URR",
    "WLE": "WLE",
    "MSTL": "MSTL",
    "MOW": "MOW",
    "UNION": "UNION",
    "UN": "UNION",
}

WEIGHT_LABELS = re.compile(
    r"(CAPY|LD\s*LMT|LT\s*WT|LY\s*WT|LIGHT\s*WT|LOAD\s*LIMIT|CU\s*FT|CUFT|CAPACITY)\s*",
    re.I,
)

INVALID_MARKS = {
    "LT", "WT", "LTWT", "LYWT", "LD", "LMT", "LDLMT", "CAPY", "NEW", "BLT",
    "WI", "LR", "MJ", "LIKE", "LIGHT", "LOAD", "LRWT", "LY", "LO", "EXW", "EW",
}


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _is_weight_context(text: str, number: str) -> bool:
    for m in re.finditer(re.escape(number), text):
        start = max(0, m.start() - 35)
        snippet = text[start : m.end() + 5]
        if WEIGHT_LABELS.search(snippet):
            return True
    return False


def _valid_marks(marks: str) -> bool:
    mk = _norm(marks)
    return bool(mk) and mk not in INVALID_MARKS and not any(
        bad in mk for bad in ("LTWT", "LDLMT", "LIGHT", "LOAD")
    )


def load_roster() -> list[dict]:
    root = ET.parse(ROSTER_XML).getroot()
    cars = []
    for el in root.findall("./cars/car"):
        cars.append(
            {
                "roster_id": el.get("id", ""),
                "roster_road": el.get("roadName", ""),
                "road_number": el.get("roadNumber", ""),
                "car_type": el.get("type", ""),
                "roster_length_ft": el.get("length", ""),
                "roster_weight_oz": el.get("weight", ""),
                "roster_weight_tons": el.get("weightTons", ""),
            }
        )
    return cars


def _source_images() -> list[Path]:
    return sorted(IMAGES_DIR.glob("*.png"))


def _ocr_band(img: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[str, Image.Image]:
    """OCR the car-side band; return text and the upscaled OCR zoom image."""
    x0, y0, x1, y1 = bbox
    W, H = img.size
    pad_x = int(0.06 * (x1 - x0))
    pad_y = int(0.10 * (y1 - y0))
    rx0 = max(0, x0 - pad_x)
    ry0 = max(0, y0 - pad_y)
    rx1 = min(W, x1 + pad_x)
    ry1 = min(H, y1 + pad_y)
    band = img.crop((rx0, ry0, rx1, ry1))
    band = ImageOps.grayscale(band)
    band = band.point(lambda p: 255 if p > 175 else (0 if p < 110 else p))
    zoom = band.resize((band.width * 3, band.height * 3), Image.LANCZOS)

    # Reporting marks sit on the left third — OCR that band separately too.
    split = max(1, int(band.width * 0.42))
    left = band.crop((0, 0, split, band.height))
    left_zoom = left.resize((left.width * 4, left.height * 4), Image.LANCZOS)
    left_text = pytesseract.image_to_string(left_zoom, config="--psm 6")

    text = pytesseract.image_to_string(zoom, config="--psm 6")
    text = f"{left_text} {text}"
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text, zoom


def _ocr_mask(window: Image.Image, scale: float) -> str:
    """Read stencilled lettering as solid black on white, from its colour not its tone.

    Gold-on-silver lettering has almost no brightness contrast, so plain OCR reads
    noise. The red-minus-blue difference isolates it cleanly.
    """
    a = np.asarray(window.convert("RGB")).astype(int)
    diff = a[..., 0] - a[..., 2]
    thr = max(15.0, float(np.percentile(diff, 97)) * scale)
    img = Image.fromarray(np.where(diff > thr, 0, 255).astype("uint8"))
    img = img.filter(ImageFilter.MedianFilter(3))
    img = ImageOps.expand(img.resize((img.width * 2, img.height * 2)), border=30, fill=255)
    return pytesseract.image_to_string(img, config="--psm 6")


def _digits(text: str) -> str:
    table = str.maketrans("OQDIlSB", "0001158")
    return re.sub(r"\D", "", text.upper().translate(table))


def ocr_lettering(crop: Image.Image) -> dict:
    """Read reporting marks, road number and weights from a finished car crop.

    Looks at the left-centre of the car side, where the big lettering sits on the
    cars this was tuned on. Returns only what it read; an empty dict means no luck.
    """
    W, H = crop.size
    out: dict[str, str] = {}
    window = crop.crop((int(W * 0.15), int(H * 0.24), int(W * 0.42), int(H * 0.62)))
    for scale in (0.45, 0.35, 0.28):
        lines = [ln.strip() for ln in _ocr_mask(window, scale).upper().split("\n") if ln.strip()]
        for i, line in enumerate(lines[:-1]):
            marks = re.sub(r"[^A-Z]", "", line)
            number = _digits(lines[i + 1])
            if 3 <= len(marks) <= 5 and len(number) >= 4:
                out.update(reporting_marks=marks, road_number=number, ocr_text=" ".join(lines))
                break
        if out:
            break
    blue = ImageOps.autocontrast(crop.convert("RGB").split()[2], cutoff=1)
    wt = blue.crop((int(W * 0.22), int(H * 0.60), int(W * 0.42), int(H * 0.84)))
    wt = wt.resize((wt.width * 3, wt.height * 3), Image.LANCZOS)
    text = pytesseract.image_to_string(wt, config="--psm 6").upper()
    m = re.search(r"LD\s*LMT\D{0,6}(\d{6})", text)
    if m:
        out["ld_lmt_lbs"] = m.group(1)
    m = re.search(r"(?:LT|LIGHT)\s*WT\D{0,6}(\d{5})", text)
    if m:
        out["lt_wt_lbs"] = m.group(1)
    return out



def _parse_markings(text: str) -> dict:
    out: dict[str, str] = {}
    m = re.search(r"CAPY\s*([0-9,]+)", text)
    if m:
        out["capy_lbs"] = m.group(1).replace(",", "")
    m = re.search(r"LD\s*LMT\s*([0-9,]+)", text)
    if m:
        out["ld_lmt_lbs"] = m.group(1).replace(",", "")
    m = re.search(r"(?:LT|LIGHT)\s*WT\s*([0-9,]+)", text)
    if m:
        out["lt_wt_lbs"] = m.group(1).replace(",", "")
    for pat in (r"NEW\s*([0-9-]+)", r"BLT\s*([0-9-]+)", r"BUILT\s*([0-9-]+)"):
        m = re.search(pat, text)
        if m:
            out["built"] = m.group(1)
            break
    m = re.search(r"\b(LO|XM|GB|HT|F3|HTS)\b", text)
    if m:
        out["car_class"] = m.group(1)
    if "SCALE TEST" in text:
        out["car_type"] = "Scale Test Car"
    return out


def _find_in_road_context(
    text: str,
    roster: list[dict],
    road_code: str,
    display_marks: str,
    context_pat: str,
) -> tuple[str, str]:
    if not re.search(context_pat, text, re.I):
        return "", ""
    for car in sorted(
        [c for c in roster if c["roster_road"] == road_code],
        key=lambda c: len(c["road_number"]),
        reverse=True,
    ):
        num = car["road_number"]
        if not num or len(num) < 4:
            continue
        if _is_weight_context(text, num):
            continue
        if re.search(rf"(?<![0-9]){re.escape(num)}(?![0-9])", text):
            return display_marks, num
        if len(num) >= 5 and _norm(num) in _norm(text):
            return display_marks, num
    return "", ""


def _find_road_mark(text: str, roster: list[dict]) -> tuple[str, str]:
    compact = _norm(text)

    m = re.search(r"N\s*[&]?\s*W\s*(\d{4,6})", text)
    if m:
        return "N&W", m.group(1)
    m = re.search(r"K\s*S\s*M\s*X?\s*(\d{2,4})", text)
    if m:
        return "KSMX", m.group(1)
    m = re.search(r"KSMX\s*(\d{2,4})", text)
    if m:
        return "KSMX", m.group(1)

    for road_code, marks, pat in (
        ("BO", "B&O", r"BALTIMORE|B\s*&?\s*O"),
        ("PRR", "PRR", r"PENNSY|PEN\s*NSY|PRR"),
        ("SHPX", "SHPX", r"SHPX|SHIPPERS\s*CAR"),
        ("CO", "C&O", r"CHESAPEAKE|C\s*&?\s*O|CONRAIL"),
        ("CBQ", "CBQ", r"BURLING|CBQ|C\s*B\s*&?\s*Q"),
    ):
        found = _find_in_road_context(text, roster, road_code, marks, pat)
        if found[1]:
            return found

    for car in sorted(roster, key=lambda c: len(c["road_number"]), reverse=True):
        num = _norm(car["road_number"])
        if not num:
            continue
        road = car["roster_road"]
        for mark in (road, "N&W" if road == "NW" else road, "B&O" if road == "BO" else road):
            if _norm(f"{mark}{num}") in compact:
                return mark, car["road_number"]

    patterns = [
        r"\b(UN\s*ION|UNION|PENNSYLVANIA(?:\s*LINES)?)\s+(\d{3}\s*\d{3}|\d{4,6})\b",
        r"\b([A-Z]{1,4})\s+([A-Z]{1,2})\s+(\d{2,6})\b",
        r"\b([A-Z&]{2,6})\s+(\d{2,6})\b",
        r"\b([A-Z&]{2,4})\s+(\d{3})\s+(\d{3})\b",  # B&O 600 409
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        if pat.startswith(r"\b(UN"):
            return "UNION", m.group(2).replace(" ", "")
        if len(m.groups()) == 3 and m.group(3).isdigit() and len(m.group(2)) == 3:
            marks = f"{m.group(1)} {m.group(2)}"
            if not _valid_marks(marks):
                continue
            return marks, f"{m.group(2)}{m.group(3)}"
        if len(m.groups()) == 3:
            marks = f"{m.group(1)} {m.group(2)}"
            if not _valid_marks(marks):
                continue
            return marks, m.group(3)
        marks = m.group(1)
        if not _valid_marks(marks):
            continue
        return marks, m.group(2)
    return "", ""


def _excluded_numbers(parsed: dict) -> set[str]:
    return {
        v
        for v in (
            parsed.get("capy_lbs", ""),
            parsed.get("ld_lmt_lbs", ""),
            parsed.get("lt_wt_lbs", ""),
        )
        if v
    }


def _match_roster(
    text: str, roster: list[dict], marks: str, number: str, parsed: dict
) -> tuple[dict | None, str]:
    if number:
        if _is_weight_context(text, number):
            number = ""
        else:
            hits = [c for c in roster if c["road_number"] == number]
            if len(hits) == 1:
                return hits[0], "road_number"
            if len(hits) > 1 and marks and _valid_marks(marks):
                mk = _norm(marks)
                alias = ROAD_ALIASES.get(mk) or ROAD_ALIASES.get(mk.replace("AND", ""))
                if alias:
                    for c in hits:
                        if c["roster_road"] == alias:
                            return c, "road_number+marks"
                return hits[0], "road_number_ambiguous"

    excluded = _excluded_numbers(parsed)
    text_compact = _norm(text)
    for car in sorted(roster, key=lambda c: len(c["road_number"]), reverse=True):
        num = car["road_number"]
        if not num or num in excluded or len(num) < 4:
            continue
        if _is_weight_context(text, num):
            continue
        if re.search(rf"(?<![0-9]){re.escape(num)}(?![0-9])", text):
            return car, "road_number_in_text"
        if len(num) >= 5 and _norm(num) in text_compact:
            return car, "road_number_in_text"
    return None, "none"


def _analysis_notes(ocr_text: str, marks: str, number: str) -> str:
    notes: list[str] = []
    if "NOW" in ocr_text and "32500" in ocr_text:
        notes.append("OCR likely misread N&W 32800 as NOW 32500")
    if "NORFOLK" in ocr_text and "WESTERN" in ocr_text and not marks:
        notes.append("Norfolk & Western car — verify road number in OCR zoom")
    if re.search(r"UN\s*ION", ocr_text):
        notes.append("Union hopper — check road number in OCR zoom")
    if "KOSMOS" in ocr_text or "KSMX" in ocr_text:
        notes.append("Kosmos cement hopper")
    if "SCALE TEST" in ocr_text:
        notes.append("C&O scale test car ST-1")
    if marks and number and not notes:
        return ""
    return "; ".join(notes)


def _identity_key(row: dict) -> str:
    if row.get("roster_id") and row.get("match_confidence") != "none":
        return f"roster:{row['roster_id']}"
    marks = row.get("reporting_marks", "").strip()
    number = row.get("road_number", "").strip()
    if marks and number and len(number) >= 5 and _valid_marks(marks):
        alias = ROAD_ALIASES.get(_norm(marks), _norm(marks))
        return f"marks:{alias}:{number}"
    return ""


def process_all() -> list[dict]:
    roster = load_roster()
    CAR_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen: dict[str, str] = {}

    for src in _source_images():
        rel_source = src.name
        img = Image.open(src).convert("RGB")
        bbox = detect_car_bbox(img)
        ocr_text, ocr_zoom = _ocr_band(img, bbox)
        parsed = _parse_markings(ocr_text)
        marks, number = _find_road_mark(ocr_text, roster)
        roster_row, confidence = _match_roster(ocr_text, roster, marks, number, parsed)

        cropped_name = f"{src.stem}.png"
        ocr_name = f"OCR_{src.stem}.png"
        crop_path = CAR_IMAGES_DIR / cropped_name
        ocr_path = OCR_DIR / ocr_name
        meta = process_image(src, crop_path)
        ocr_zoom.save(ocr_path)

        row = {
            "source_image": rel_source,
            "cropped_image": f"CarImages/{cropped_name}",
            "ocr_zoom_image": f"OcrZoom/{ocr_name}",
            "crop_status": meta["crop_status"],
            "duplicate_of": "",
            "reporting_marks": marks,
            "road_name": marks,
            "road_number": number,
            "full_name": "",
            "car_type": parsed.get("car_type", ""),
            "car_class": parsed.get("car_class", ""),
            "color": "",
            "capy_lbs": parsed.get("capy_lbs", ""),
            "ld_lmt_lbs": parsed.get("ld_lmt_lbs", ""),
            "lt_wt_lbs": parsed.get("lt_wt_lbs", ""),
            "built": parsed.get("built", ""),
            "roster_id": "",
            "roster_road": "",
            "roster_length_ft": "",
            "roster_weight_oz": "",
            "roster_weight_tons": "",
            "ocr_text": ocr_text[:400].replace("\n", " "),
            "match_confidence": confidence,
            "notes": _analysis_notes(ocr_text, marks, number),
        }
        if roster_row:
            row.update(
                {
                    "road_number": roster_row["road_number"] or number,
                    "car_type": roster_row["car_type"] or row["car_type"],
                    "roster_id": roster_row["roster_id"],
                    "roster_road": roster_row["roster_road"],
                    "roster_length_ft": roster_row["roster_length_ft"],
                    "roster_weight_oz": roster_row["roster_weight_oz"],
                    "roster_weight_tons": roster_row["roster_weight_tons"],
                }
            )

        key = _identity_key(row)
        if key:
            if key in seen:
                row["duplicate_of"] = seen[key]
                extra = "duplicate photo of same car"
                row["notes"] = f"{row['notes']}; {extra}".strip("; ")
            else:
                seen[key] = rel_source

        rows.append(row)
        dup = f" DUP->{row['duplicate_of']}" if row["duplicate_of"] else ""
        tag = row["roster_id"] or number or "?"
        print(
            f"{rel_source} -> {cropped_name}  "
            f"[{row['crop_status']}] [{confidence}] {tag}{dup}"
        )

    return rows


def write_csv(rows: list[dict]) -> None:
    with METADATA_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in CSV_COLUMNS})
    matched = sum(1 for r in rows if r.get("roster_id"))
    dups = sum(1 for r in rows if r.get("duplicate_of"))
    review = sum(1 for r in rows if r.get("crop_status") == "review")
    print(f"\nWrote {METADATA_CSV}  ({len(rows)} rows)")
    print(f"  {matched} roster matches · {dups} duplicates · {review} crop review")
    print(f"  OCR zooms:   {OCR_DIR}/  (filter with OCR_ prefix)")


def main() -> None:
    if not ROSTER_XML.exists():
        raise FileNotFoundError(ROSTER_XML)
    if "--rebuild-repository" not in os.sys.argv:
        raise SystemExit(
            "This rewrites image_metadata.csv from Images/ and loses every other car. "
            "Use cars.py intake. Pass --rebuild-repository only to start over."
        )
    rows = process_all()
    write_csv(rows)


if __name__ == "__main__":
    main()
