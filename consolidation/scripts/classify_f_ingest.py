#!/usr/bin/env python3
"""Apply owner disposition rules to class-F manifest and build browse index.

Reads hart_root_inventory.csv, writes:
  sor/desktop/class_f_ingest_manifest.csv
  wiki/archive/F-ROOT-INDEX.md
  html/archive/f-root-index.html (via build_site or standalone)

Does not read or modify ~/Desktop/HART files beyond path metadata in CSV.
"""
from __future__ import annotations

import csv
import html
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONSOL = ROOT / "consolidation"
INVENTORY = CONSOL / "sor/desktop/hart_root_inventory.csv"
OUT_CSV = CONSOL / "sor/desktop/class_f_ingest_manifest.csv"
OUT_MD = CONSOL / "wiki/archive/F-ROOT-INDEX.md"
OUT_HTML = CONSOL / "html/archive/f-root-index.html"
DESKTOP = Path.home() / "Desktop/HART"

SKIP_EXACT = frozenset({"Coke_Ovens.dmg", "Thumbs.db"})
SKIP_PREFIXES = ("~$",)
SKIP_PATTERNS = [
    re.compile(r"^IMG_894\d", re.I),
    re.compile(r"^IMG_895\d", re.I),
    re.compile(r"^IMG_897[56]", re.I),
    re.compile(r"^Wiring[_ ]Schematic", re.I),
    re.compile(r"^~\\$Wiring", re.I),
]
BROWSE_PATTERNS = [
    re.compile(r"^Screenshot ", re.I),
    re.compile(r"^IMG_\d", re.I),
    re.compile(r"^s-l\d", re.I),
    re.compile(r"_n\.jpg$", re.I),
    re.compile(r"\.webp$", re.I),
    re.compile(r"^2022-10-16.*Google Maps", re.I),
    re.compile(r"^2022-10-16.*USGS", re.I),
    re.compile(r"^1VFNT", re.I),
    re.compile(r"\.fp\.png$", re.I),
    re.compile(r"^FZ2_", re.I),
    re.compile(r"^flannery-16-nov", re.I),
]
REFERENCE_PATTERNS = [
    re.compile(r"Google Maps|USGS|topo|seabass", re.I),
    re.compile(r"PRR_|P&LE|RAILROAD\.NET|Kirwan|jmri_ops|SP op|Neville Island Industrial", re.I),
    re.compile(r"Lee Nevo Design", re.I),
    re.compile(r"1956-07-07", re.I),
]
ARCHIVE_MEDIA_KEEP = [
    re.compile(r"beck|flannery|bkPA|Chartiers|Freight_Flow|Neville Trackplan|trolley|sewickley|Shenango", re.I),
    re.compile(r"ammonium|pit\.|ptry_head|lcn-connection|HART_Coal|J_B_Higbee", re.I),
]


def disposition(name: str) -> tuple[str, str, str]:
    """Return bucket, disposition, note."""
    if name in SKIP_EXACT or any(name.startswith(p) for p in SKIP_PREFIXES):
        return "F-skip", "skip", "owner: skip installer/junk"

    for pat in SKIP_PATTERNS:
        if pat.search(name):
            return "F-skip", "skip", "owner: layout photo / wiring draft — skip"

    if name.upper().startswith("HART_") or name.startswith("Hart Railroad"):
        return "F-narrative", "archive", "owner: older HART narrative — archive for history consolidation"

    for pat in REFERENCE_PATTERNS:
        if pat.search(name):
            return "F-reference", "archive", "historical / design reference — keep in archive"

    for pat in ARCHIVE_MEDIA_KEEP:
        if pat.search(name):
            return "F-media", "archive", "prototype / layout reference — keep in archive"

    for pat in BROWSE_PATTERNS:
        if pat.search(name):
            return "F-media", "browse", "sort in consolidation portal — candidate download/screenshot"

    lower = name.lower()
    if lower.endswith((".docx", ".pdf", ".pptx", ".xlsx", ".xls")):
        return "F-narrative", "archive", "root document — archive"

    if lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return "F-media", "browse", "root media — review in browse index"

    return "F-skip", "review", "unclassified — human review"


def load_f_rows() -> list[dict]:
    rows = []
    for r in csv.DictReader(INVENTORY.open(newline="")):
        if r.get("class") == "F":
            rows.append(r)
    return rows


def write_csv(rows: list[dict]) -> None:
    fieldnames = ["path", "bucket", "disposition", "notes", "size_bytes"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            name = r["path"]
            bucket, disp, note = disposition(name)
            w.writerow(
                {
                    "path": name,
                    "bucket": bucket,
                    "disposition": disp,
                    "notes": note,
                    "size_bytes": r.get("size_bytes", ""),
                }
            )


def write_md(rows: list[dict]) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        name = r["path"]
        bucket, disp, note = disposition(name)
        key = disp if disp in ("browse", "archive", "skip") else "review"
        groups[key].append({"path": name, "bucket": bucket, "note": note, "size": r.get("size_bytes", "")})

    lines = [
        "# Desktop/HART class-F root index (2026-08-31)",
        "",
        "**Bench read-only.** Dispositions recorded by owner; no files moved.",
        "",
        "| Disposition | Meaning |",
        "|-------------|---------|",
        "| **skip** | Never ingest (`Coke_Ovens.dmg`, `Thumbs.db`, layout photo series) |",
        "| **browse** | Sort via [F-root browse HTML](../../html/archive/f-root-index.html) |",
        "| **archive** | Keep for future `docs/archive/` when history project runs |",
        "",
    ]
    for key in ("browse", "archive", "skip"):
        items = sorted(groups.get(key, []), key=lambda x: x["path"].lower())
        if not items:
            continue
        lines.append(f"## {key.title()} ({len(items)})")
        lines.append("")
        for it in items[:200]:
            lines.append(f"- `{it['path']}` — {it['bucket']}: {it['note']}")
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def write_html(rows: list[dict]) -> None:
    browse = []
    archive = []
    skip = []
    for r in rows:
        name = r["path"]
        bucket, disp, note = disposition(name)
        entry = (name, bucket, note, r.get("size_bytes", ""))
        if disp == "browse":
            browse.append(entry)
        elif disp == "skip":
            skip.append(entry)
        else:
            archive.append(entry)

    def section(title: str, items: list[tuple]) -> str:
        if not items:
            return ""
        out = [f"<h2>{html.escape(title)} ({len(items)})</h2>", "<table>", "<tr><th>File</th><th>Bucket</th><th>Notes</th></tr>"]
        for name, bucket, note, _ in sorted(items):
            file_url = html.escape(f"file://{DESKTOP}/{name}")
            out.append(
                f"<tr><td><a href=\"{file_url}\">{html.escape(name)}</a></td>"
                f"<td>{html.escape(bucket)}</td><td>{html.escape(note)}</td></tr>"
            )
        out.append("</table>")
        return "\n".join(out)

    body = "\n".join(
        [
            section("Browse — screenshots & downloads", browse),
            section("Archive — narrative & reference (later history project)", archive),
            section("Skip", skip),
        ]
    )
    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><title>Class F root browse — HART Consolidation</title>
<link rel="stylesheet" href="../style.css">
</head><body>
<nav class="sidebar"><a class="brand" href="../../index.html">HART Consolidation</a>
<a href="index.html">Archive taxonomy</a>
<a href="f-root-index.html">F-root browse</a>
</nav>
<main class="content">
<h1>Desktop/HART root files (class F)</h1>
<p>Local <code>file://</code> links open files on this Mac. Nothing copied; bench read-only.</p>
{body}
</main></body></html>"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(page, encoding="utf-8")


def main() -> int:
    if not INVENTORY.is_file():
        print("Run inventory_desktop_hart.py first", file=sys.stderr)
        return 1
    rows = load_f_rows()
    write_csv(rows)
    write_md(rows)
    write_html(rows)
    counts = defaultdict(int)
    for r in rows:
        counts[disposition(r["path"])[1]] += 1
    print(f"Wrote {len(rows)} rows → {OUT_CSV.name}")
    print("Dispositions:", dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
