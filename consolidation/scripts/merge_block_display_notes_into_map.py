#!/usr/bin/env python3
"""Draft: merge block_display notes into public_name_map (D2b prep).

Writes consolidation/sor/names/public_name_map_merged.csv — not live map.
Match key: block_display public_user_name == map proposed column.
Prefer canonical row where current == proposed.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "jmri/layouts/hart/data/public_name_map.csv"
LEGACY = ROOT / "jmri/layouts/hart/data/block_display_names.csv"
OUT = ROOT / "consolidation/sor/names/public_name_map_merged.csv"


def _pick_row_index(rows: list[dict[str, str]], proposed: str) -> int | None:
    matches = [i for i, r in enumerate(rows) if (r.get("proposed") or "").strip() == proposed]
    if not matches:
        return None
    for i in matches:
        if (rows[i].get("current") or "").strip() == proposed:
            return i
    return matches[0]


def _merge_note(existing: str, incoming: str) -> str:
    existing = (existing or "").strip()
    incoming = (incoming or "").strip()
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming in existing:
        return existing
    return f"{existing}; {incoming}"


def main() -> int:
    if not MAP.is_file():
        print(f"missing map: {MAP}", file=sys.stderr)
        return 1
    if not LEGACY.is_file():
        print(f"missing legacy: {LEGACY}", file=sys.stderr)
        return 1

    with MAP.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    notes_by_public: dict[str, str] = {}
    with LEGACY.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pub = (row.get("public_user_name") or "").strip()
            note = (row.get("notes") or "").strip()
            if pub and note:
                notes_by_public[pub] = note

    merged = 0
    unmatched: list[str] = []
    for pub, note in sorted(notes_by_public.items()):
        idx = _pick_row_index(rows, pub)
        if idx is None:
            unmatched.append(pub)
            continue
        before = (rows[idx].get("notes") or "").strip()
        after = _merge_note(before, note)
        if after != before:
            rows[idx]["notes"] = after
            merged += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"legacy notes rows: {len(notes_by_public)}")
    print(f"map rows updated: {merged}")
    print(f"unmatched public names: {len(unmatched)}")
    if unmatched:
        for name in unmatched:
            print(f"  - {name}")
    print(f"wrote: {OUT.relative_to(ROOT)}")
    return 1 if unmatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
