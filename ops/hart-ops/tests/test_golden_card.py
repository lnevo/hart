#!/usr/bin/env python3
"""Tier C golden smoke — NW32800 roster + single-card generation."""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GOLDEN = ROOT / "tests/golden/NW32800.docx"
CAR_ID = "NW32800"


def assert_roster() -> None:
    merged = DATA / "HART_MergedCarRoster.xml"
    ops = DATA / "OperationsCarRoster.xml"
    for path in (merged, ops):
        if not path.is_file():
            raise AssertionError(f"missing {path.name} — run build_car_roster_sor.py")

    for path in (merged, ops):
        root = ET.parse(path).getroot()
        ids = {el.get("id") for el in root.findall("./cars/car")}
        if CAR_ID not in ids:
            raise AssertionError(f"{CAR_ID} not in {path.name}")

    meta = DATA / "image_metadata.csv"
    text = meta.read_text(encoding="utf-8")
    if CAR_ID not in text and "32800" not in text:
        raise AssertionError(f"{CAR_ID} not found in image_metadata.csv")


def assert_golden_docx() -> None:
    if not GOLDEN.is_file():
        raise AssertionError(f"missing golden docx: {GOLDEN}")

    script = ROOT / "card_pipeline/generate_single_card.py"
    out_dir = ROOT / "card_pipeline/output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "HART_Card_NW32800.docx"

    subprocess.run([sys.executable, str(script)], cwd=ROOT / "card_pipeline", check=True)
    if not out.is_file():
        raise AssertionError("generate_single_card.py did not produce output")

    if out.stat().st_size < 1000:
        raise AssertionError("generated docx suspiciously small")
    if GOLDEN.stat().st_size < 1000:
        raise AssertionError("golden docx suspiciously small")


def main() -> int:
    assert_roster()
    assert_golden_docx()
    print(f"OK golden smoke {CAR_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
