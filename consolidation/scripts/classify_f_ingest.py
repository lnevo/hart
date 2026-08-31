#!/usr/bin/env python3
"""Classify class-F Desktop root files for archive ingest manifest (read-only scan).

Reads consolidation/sor/desktop/hart_root_inventory.csv and writes
consolidation/sor/desktop/class_f_ingest_manifest.csv with ingest buckets.

Does not copy files or modify Desktop/HART (D12 bench freeze).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "consolidation/sor/desktop/hart_root_inventory.csv"
OUT = ROOT / "consolidation/sor/desktop/class_f_ingest_manifest.csv"

SKIP_EXTENSIONS = frozenset({".dmg", ".pkg", ".exe", ".iso", ".app"})
DOC_EXTENSIONS = frozenset({".docx", ".pdf", ".pptx", ".xlsx", ".xls", ".txt", ".md"})
MEDIA_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".tif", ".tiff"})
REFERENCE_NAME_RE = re.compile(
    r"google\s*maps|usgs|topo|topographic|seabass|historical",
    re.I,
)


def classify_row(row: dict) -> tuple[str, str, str]:
    """Return bucket, action, notes."""
    inv_class = (row.get("class") or "").strip()
    name = (row.get("path") or row.get("name") or "").strip()
    notes = (row.get("notes") or "").strip()
    path_lower = name.lower()

    if inv_class in {"C", "D", "E", "skip"}:
        return "F-skip", "skip", f"class {inv_class}: {notes}"

    suffix = Path(name).suffix.lower()

    if suffix in SKIP_EXTENSIONS:
        return "F-skip", "skip", "installer or disk image"

    if inv_class == "D":
        return "F-skip", "skip", "duplicate of Car Cards/docs published output"

    if inv_class == "E":
        return "F-skip", "skip", "hash duplicate under Car Cards"

    if REFERENCE_NAME_RE.search(name) or REFERENCE_NAME_RE.search(notes):
        return "F-reference", "review", notes or "reference capture"

    if suffix in MEDIA_EXTENSIONS:
        if name.lower().startswith("img_") or re.search(r"\d{3,}", name):
            return "F-media", "review", notes or "root media — verify not duplicate"
        return "F-media", "approve", notes or "root media"

    if suffix in DOC_EXTENSIONS:
        return "F-narrative", "approve", notes or "root document"

    if suffix in {".html", ".htm", ".csv"}:
        return "F-narrative", "review", notes or "structured doc"

    return "F-skip", "review", notes or "unclassified — human review"


def main() -> int:
    if not INVENTORY.is_file():
        print(f"Missing inventory: {INVENTORY}", file=sys.stderr)
        print("Run: python3 consolidation/scripts/inventory_desktop_hart.py", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(INVENTORY.open(newline="")))
    f_rows = [r for r in rows if (r.get("class") or "").strip() == "F"]
    if not f_rows:
        f_rows = [r for r in rows if (r.get("class") or "").strip() not in {"C"}]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "inventory_class", "bucket", "action", "notes", "inventory_notes"]
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        counts: dict[str, int] = {}
        for row in f_rows:
            bucket, action, note = classify_row(row)
            counts[bucket] = counts.get(bucket, 0) + 1
            writer.writerow(
                {
                    "name": row.get("path") or row.get("name", ""),
                    "inventory_class": row.get("class", ""),
                    "bucket": bucket,
                    "action": action,
                    "notes": note,
                    "inventory_notes": row.get("notes", ""),
                }
            )

    print(f"Wrote {OUT.name}: {len(f_rows)} rows")
    for bucket in sorted(counts):
        print(f"  {bucket}: {counts[bucket]}")
    review = sum(1 for r in f_rows if classify_row(r)[1] == "review")
    print(f"  human review: {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
