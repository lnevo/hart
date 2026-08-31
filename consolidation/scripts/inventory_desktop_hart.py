#!/usr/bin/env python3
"""Read-only inventory of ~/Desktop/HART root files (P3 prep).

Writes:
  consolidation/sor/desktop/hart_root_inventory.csv
  consolidation/audits/desktop-inventory.md

Does not modify Desktop files.
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = Path.home() / "Desktop" / "HART"
OUT_CSV = ROOT / "consolidation/sor/desktop/hart_root_inventory.csv"
OUT_MD = ROOT / "consolidation/audits/desktop-inventory.md"

# Known operational subtrees (class C when entry is a directory)
SUBTREES = frozenset(
    {
        "Car Cards",
        "Industries",
        "Wiring Documentation",
        "DJ Trains",
    }
)

# Basenames that match Car Cards/docs published outputs (class D)
CARDS_DOCS = Path.home() / "Desktop/HART/Car Cards/docs"


def file_hash(path: Path, limit_mb: int = 50) -> str:
    if path.stat().st_size > limit_mb * 1024 * 1024:
        return "skipped_large"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def published_basenames() -> set[str]:
    if not CARDS_DOCS.is_dir():
        return set()
    return {p.name for p in CARDS_DOCS.iterdir() if p.is_file()}


def classify_root_file(path: Path, pub_names: set[str], hash_index: dict[str, str]) -> tuple[str, str]:
    name = path.name
    if name.startswith("."):
        return "skip", "dotfile"

    if name in pub_names:
        return "D", "basename matches Car Cards/docs published output"

    suffix = path.suffix.lower()
    if suffix in {".dmg", ".iso"}:
        return "F", "large installer image — archive candidate"

    h = file_hash(path)
    if h != "skipped_large" and h in hash_index:
        return "E", f"sha256 prefix matches Car Cards/{hash_index[h]}"

    lower = name.lower()
    if lower.startswith("hart_") or lower.startswith("hart "):
        if suffix in {".docx", ".pdf", ".xlsx", ".pptx"}:
            return "F", "root narrative/ops doc — review vs Car Cards publications pipeline"
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return "F", "root media — archive or move to publications/assets"
    if suffix in {".docx", ".pdf", ".xlsx", ".pptx"}:
        return "F", "root document — archive taxonomy pending"

    return "F", "unclassified root file"


def build_cards_hash_index(cards_root: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    if not cards_root.is_dir():
        return index
    for path in cards_root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.stat().st_size > 50 * 1024 * 1024:
            continue
        try:
            digest = file_hash(path)
        except OSError:
            continue
        if digest != "skipped_large":
            index.setdefault(digest, str(path.relative_to(cards_root)))
    return index


def summarize_dir(path: Path) -> tuple[int, int]:
    files = 0
    total = 0
    for root, _dirs, names in os.walk(path):
        for n in names:
            if n.startswith("."):
                continue
            p = Path(root) / n
            try:
                total += p.stat().st_size
                files += 1
            except OSError:
                pass
    return files, total


def main() -> int:
    if not DESKTOP.is_dir():
        print(f"MISSING: {DESKTOP}", file=sys.stderr)
        return 2

    pub_names = published_basenames()
    cards_root = DESKTOP / "Car Cards"
    hash_index = build_cards_hash_index(cards_root)

    rows: list[dict[str, str]] = []

    for entry in sorted(DESKTOP.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            if entry.name in SUBTREES:
                fc, sz = summarize_dir(entry)
                rows.append(
                    {
                        "path": entry.name + "/",
                        "kind": "dir",
                        "class": "C",
                        "size_bytes": str(sz),
                        "file_count": str(fc),
                        "notes": "operational subtree — future hart-ops or sibling repo",
                    }
                )
            else:
                fc, sz = summarize_dir(entry)
                rows.append(
                    {
                        "path": entry.name + "/",
                        "kind": "dir",
                        "class": "F",
                        "size_bytes": str(sz),
                        "file_count": str(fc),
                        "notes": "unexpected subdirectory",
                    }
                )
            continue

        if not entry.is_file():
            continue

        cls, note = classify_root_file(entry, pub_names, hash_index)
        if cls == "skip":
            continue
        rows.append(
            {
                "path": entry.name,
                "kind": "file",
                "class": cls,
                "size_bytes": str(entry.stat().st_size),
                "file_count": "",
                "notes": note,
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["path", "kind", "class", "size_bytes", "file_count", "notes"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    by_class: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_class.setdefault(r["class"], []).append(r)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Audit — Desktop/HART root inventory",
        "",
        f"**Date:** {ts}  ",
        f"**Script:** `consolidation/scripts/inventory_desktop_hart.py`  ",
        f"**CSV:** [`sor/desktop/hart_root_inventory.csv`](../sor/desktop/hart_root_inventory.csv)",
        "",
        "## Taxonomy (consolidation draft)",
        "",
        "| Class | Meaning |",
        "|-------|---------|",
        "| **C** | Operational subtree (Car Cards, Industries, Wiring, …) |",
        "| **D** | Root file basename matches `Car Cards/docs/` published output (duplicate) |",
        "| **E** | Root file content hash matches file under Car Cards |",
        "| **F** | Archive / review candidate at Desktop root |",
        "",
        "**Deferred (P4):** ingest F → `hart/docs/archive/`; slim Desktop to README + links.",
        "",
        "## Summary",
        "",
    ]
    for cls in ("C", "D", "E", "F"):
        items = by_class.get(cls, [])
        lines.append(f"- **{cls}:** {len(items)} entries")

    lines.extend(["", "## Class C — subtrees", ""])
    for r in by_class.get("C", []):
        mb = int(r["size_bytes"]) / (1024 * 1024)
        lines.append(f"- `{r['path']}` — {r['file_count']} files, {mb:.1f} MB")

    for label, cls in (("D — duplicates of Car Cards/docs", "D"), ("E — hash dup of Car Cards", "E")):
        items = by_class.get(cls, [])
        if not items:
            continue
        lines.extend(["", f"## Class {label}", ""])
        for r in items[:25]:
            lines.append(f"- `{r['path']}` — {r['notes']}")
        if len(items) > 25:
            lines.append(f"- … and {len(items) - 25} more (see CSV)")

    lines.extend(["", "## Class F — sample (first 20)", ""])
    for r in by_class.get("F", [])[:20]:
        if r["kind"] == "dir":
            lines.append(f"- `{r['path']}` — {r['notes']}")
        else:
            lines.append(f"- `{r['path']}` — {r['notes']}")

    lines.extend(
        [
            "",
            "## Decision not needed yet",
            "",
            "Ingest policy for class F root files waits on **hart-ops** repo creation (P3).",
            "",
        ]
    )

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Desktop: {DESKTOP}")
    print(f"entries: {len(rows)}")
    for cls in ("C", "D", "E", "F"):
        print(f"  class {cls}: {len(by_class.get(cls, []))}")
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
