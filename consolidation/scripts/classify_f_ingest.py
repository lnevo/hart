#!/usr/bin/env python3
"""Apply owner disposition rules to class-F manifest and build browse index.

Reads hart_root_inventory.csv, writes:
  sor/desktop/class_f_ingest_manifest.csv
  wiki/archive/F-ROOT-INDEX.md
  html/archive/f-root-index.html (re-wrapped by build_site.py)

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

BROWSE_CATEGORY_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("screenshots", "Screenshots", re.compile(r"^Screenshot ", re.I)),
    ("ebay_listings", "eBay / listing images", re.compile(r"^s-l\d|\.fp\.png$|^1VFNT", re.I)),
    ("social_downloads", "Social / web downloads", re.compile(r"_n\.jpg$", re.I)),
    ("iphone_photos", "iPhone photos (non-series)", re.compile(r"^IMG_\d", re.I)),
    ("reference_photos", "Reference photos", re.compile(r"^FZ2_", re.I)),
]

ARCHIVE_CATEGORY_LABELS = {
    "narrative": "HART narrative documents",
    "narrative_hart_branded": "HART-branded documents",
    "narrative_timetables": "Timetables & schedules",
    "narrative_safety": "Safety & orientation",
    "narrative_train_lists": "Train lists & routing",
    "narrative_other": "Other root documents",
    "reference": "Historical / design reference",
    "prototype": "Prototype & layout reference media",
}

SKIP_CATEGORY_LABELS = {
    "installer": "Installers & junk",
    "layout_photos": "Layout photo series",
    "wiring_drafts": "Wiring schematic drafts",
    "temp_files": "Office temp files",
    "review": "Unclassified — review",
}


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


def browse_category(name: str) -> str:
    for cat_id, _, pat in BROWSE_CATEGORY_RULES:
        if pat.search(name):
            return cat_id
    return "misc_media"


def browse_category_label(cat_id: str) -> str:
    for cid, label, _ in BROWSE_CATEGORY_RULES:
        if cid == cat_id:
            return label
    return "Other media"


def archive_category(name: str, bucket: str) -> str:
    if bucket == "F-reference":
        return "reference"
    if bucket == "F-narrative":
        return archive_narrative_subcategory(name)
    return "prototype"


def archive_narrative_subcategory(name: str) -> str:
    upper = name.upper()
    if re.search(r"TIMETABLE|Full_Timetable", name, re.I):
        return "narrative_timetables"
    if re.search(r"Safety|Orientation", name, re.I):
        return "narrative_safety"
    if re.search(r"Train_List|Train List", name, re.I):
        return "narrative_train_lists"
    if upper.startswith("HART_") or name.startswith("Hart Railroad"):
        return "narrative_hart_branded"
    return "narrative_other"


def skip_category(name: str, note: str) -> str:
    if name in SKIP_EXACT or name.endswith(".dmg"):
        return "installer"
    if name.startswith("~$"):
        return "temp_files"
    if "Wiring" in name or "wiring" in note.lower():
        return "wiring_drafts"
    if re.search(r"^IMG_894|^IMG_895|^IMG_897", name, re.I):
        return "layout_photos"
    if "layout photo" in note.lower():
        return "layout_photos"
    return "review"


def classify_row(name: str, size_bytes: str = "") -> dict[str, str]:
    bucket, disp, note = disposition(name)
    row = {
        "path": name,
        "bucket": bucket,
        "disposition": disp,
        "category": "",
        "notes": note,
        "size_bytes": size_bytes,
    }
    if disp == "browse":
        row["category"] = browse_category(name)
    elif disp == "archive":
        row["category"] = archive_category(name, bucket)
    elif disp in ("skip", "review"):
        row["category"] = skip_category(name, note)
    return row


def load_f_rows() -> list[dict]:
    rows = []
    for r in csv.DictReader(INVENTORY.open(newline="", encoding="utf-8")):
        if r.get("class") == "F":
            rows.append(r)
    return rows


def write_csv(rows: list[dict]) -> list[dict]:
    classified = []
    fieldnames = ["path", "bucket", "disposition", "category", "notes", "size_bytes"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            row = classify_row(r["path"], r.get("size_bytes", ""))
            w.writerow(row)
            classified.append(row)
    return classified


def _format_size(size_bytes: str) -> str:
    if not size_bytes or not str(size_bytes).isdigit():
        return ""
    n = int(size_bytes)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.0f} KB"
    return f"{n} B"


def write_md(rows: list[dict]) -> None:
    by_disp: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_disp[row["disposition"]].append(row)

    lines = [
        "# Desktop/HART class-F root index (2026-08-31)",
        "",
        "**Bench read-only.** Dispositions recorded by owner; no files moved.",
        "",
        "Browse HTML: [`html/archive/f-root-index.html`](../../html/archive/f-root-index.html)",
        "",
        "| Disposition | Meaning |",
        "|-------------|---------|",
        "| **browse** | Screenshots, downloads — categorized in portal |",
        "| **archive** | Narrative / reference — history project later |",
        "| **skip** | Installers, layout photo series, wiring drafts |",
        "",
    ]

    browse = sorted(by_disp.get("browse", []), key=lambda x: (x["category"], x["path"].lower()))
    if browse:
        lines.append(f"## Browse ({len(browse)})")
        lines.append("")
        current_cat = None
        for row in browse:
            if row["category"] != current_cat:
                current_cat = row["category"]
                lines.append(f"### {browse_category_label(current_cat)}")
                lines.append("")
            lines.append(f"- `{row['path']}`")
        lines.append("")

    archive = sorted(by_disp.get("archive", []), key=lambda x: (x["category"], x["path"].lower()))
    if archive:
        lines.append(f"## Archive ({len(archive)})")
        lines.append("")
        current_cat = None
        for row in archive:
            if row["category"] != current_cat:
                current_cat = row["category"]
                lines.append(f"### {ARCHIVE_CATEGORY_LABELS.get(current_cat, current_cat)}")
                lines.append("")
            lines.append(f"- `{row['path']}` — {row['bucket']}")
        lines.append("")

    skip_rows = sorted(
        [r for r in rows if r["disposition"] in ("skip", "review")],
        key=lambda x: (x["category"], x["path"].lower()),
    )
    if skip_rows:
        lines.append(f"## Skip ({len(skip_rows)})")
        lines.append("")
        current_cat = None
        for row in skip_rows:
            if row["category"] != current_cat:
                current_cat = row["category"]
                lines.append(f"### {SKIP_CATEGORY_LABELS.get(current_cat, current_cat)}")
                lines.append("")
            lines.append(f"- `{row['path']}`")
        lines.append("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def _table_rows(items: list[dict]) -> str:
    out = ["<table>", "<tr><th>File</th><th>Size</th><th>Notes</th></tr>"]
    for row in sorted(items, key=lambda x: x["path"].lower()):
        name = row["path"]
        file_url = html.escape(f"file://{DESKTOP}/{name}")
        size = html.escape(_format_size(row.get("size_bytes", "")))
        note = html.escape(row["notes"])
        out.append(
            f'<tr><td><a href="{file_url}">{html.escape(name)}</a></td>'
            f"<td>{size}</td><td>{note}</td></tr>"
        )
    out.append("</table>")
    return "\n".join(out)


def _category_sections(
    items: list[dict],
    label_fn,
    section_prefix: str,
    order: list[str],
) -> tuple[str, str]:
    """Return (toc_html, body_html) for categorized items."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in items:
        groups[row["category"]].append(row)

    toc_parts = []
    body_parts = []
    seen = set(order)
    ordered = [c for c in order if c in groups] + sorted(k for k in groups if k not in seen)

    for cat_id in ordered:
        group = groups[cat_id]
        if not group:
            continue
        label = label_fn(cat_id)
        anchor = f"{section_prefix}-{cat_id}"
        toc_parts.append(f'<a href="#{anchor}">{html.escape(label)} ({len(group)})</a>')
        body_parts.append(f'<h3 id="{anchor}">{html.escape(label)} ({len(group)})</h3>')
        body_parts.append(_table_rows(group))

    toc = (
        '<nav class="category-toc">' + " · ".join(toc_parts) + "</nav>"
        if toc_parts
        else ""
    )
    return toc, "\n".join(body_parts)


def write_html(rows: list[dict]) -> None:
    browse = [r for r in rows if r["disposition"] == "browse"]
    archive = [r for r in rows if r["disposition"] == "archive"]
    skip_rows = [r for r in rows if r["disposition"] in ("skip", "review")]

    browse_order = [c[0] for c in BROWSE_CATEGORY_RULES] + ["misc_media"]
    archive_order = [
        "narrative_hart_branded",
        "narrative_timetables",
        "narrative_safety",
        "narrative_train_lists",
        "narrative_other",
        "reference",
        "prototype",
    ]
    skip_order = ["installer", "layout_photos", "wiring_drafts", "temp_files", "review"]

    browse_toc, browse_body = _category_sections(
        browse, browse_category_label, "browse", browse_order
    )
    archive_toc, archive_body = _category_sections(
        archive, lambda c: ARCHIVE_CATEGORY_LABELS.get(c, c), "archive", archive_order
    )
    skip_toc, skip_body = _category_sections(
        skip_rows, lambda c: SKIP_CATEGORY_LABELS.get(c, c), "skip", skip_order
    )

    parts = [
        "<h1>Desktop/HART root files (class F)</h1>",
        "<p>Local <code>file://</code> links open files on this Mac. Nothing copied; bench read-only.</p>",
    ]
    if browse:
        parts.extend(
            [
                f'<h2 id="browse">Browse ({len(browse)})</h2>',
                browse_toc,
                browse_body,
            ]
        )
    if archive:
        parts.extend(
            [
                f'<h2 id="archive">Archive ({len(archive)})</h2>',
                archive_toc,
                archive_body,
            ]
        )
    if skip_rows:
        parts.extend(
            [
                f'<h2 id="skip">Skip ({len(skip_rows)})</h2>',
                skip_toc,
                skip_body,
            ]
        )

    body = "\n".join(parts)
    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><title>Class F root browse — HART Consolidation</title>
<link rel="stylesheet" href="../style.css">
<style>
.category-toc {{ margin: 0.75rem 0 1.25rem; padding: 0.75rem 1rem; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); line-height: 1.8; }}
.category-toc a {{ margin-right: 0.25rem; }}
h2 {{ margin-top: 2.5rem; }}
h3 {{ margin-top: 1.5rem; color: var(--text); }}
</style>
</head><body>
<nav class="sidebar"><a class="brand" href="../../index.html">HART Consolidation</a>
<a href="index.html">Archive taxonomy</a>
<a href="f-root-index.html">F-root browse</a>
</nav>
<main class="content">
{body}
</main></body></html>"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(page, encoding="utf-8")


def main() -> int:
    if not INVENTORY.is_file():
        print("Run inventory_desktop_hart.py first", file=sys.stderr)
        return 1
    rows = load_f_rows()
    classified = write_csv(rows)
    write_md(classified)
    write_html(classified)

    disp_counts: dict[str, int] = defaultdict(int)
    cat_counts: dict[str, int] = defaultdict(int)
    for row in classified:
        disp_counts[row["disposition"]] += 1
        if row["disposition"] == "browse":
            cat_counts[row["category"]] += 1

    print(f"Wrote {len(classified)} rows → {OUT_CSV.name}")
    print("Dispositions:", dict(disp_counts))
    if cat_counts:
        print("Browse categories:", dict(sorted(cat_counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
