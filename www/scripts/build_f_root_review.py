#!/usr/bin/env python3
"""Build F-root review gallery JSON from class-F ingest manifest + curation."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from f_root_common import (  # noqa: E402
    CATEGORY_LABELS,
    CURATION_JSON,
    FROOT,
    IMAGE_EXT,
    MANIFEST,
    PDF_EXT,
    REVIEW_JSON,
    format_size,
    media_kind,
    pretty_title,
)
from f_root_preview import preview_path, preview_rel_url  # noqa: E402


def load_curation_items() -> dict[str, dict]:
    if not CURATION_JSON.is_file():
        return {}
    data = json.loads(CURATION_JSON.read_text(encoding="utf-8"))
    return data.get("items") or {}


def build_item(row: dict, curated: dict | None) -> dict:
    path = row["path"]
    ext = Path(path).suffix.lower()
    mirrored = (FROOT / path).is_file()
    src = None
    if mirrored and ext in IMAGE_EXT | PDF_EXT:
        src = f"../external/desktop-data/f-root/{path}"

    preview_src = None
    if preview_path(path).is_file():
        preview_src = preview_rel_url(path)

    cat = row.get("category") or "review"
    notes = row.get("notes") or ""
    title = pretty_title(path)
    caption = notes

    item = {
        "id": path,
        "path": path,
        "title": title,
        "caption": caption,
        "category": cat,
        "categoryLabel": CATEGORY_LABELS.get(cat, cat.replace("_", " ").title()),
        "disposition": row.get("disposition") or "review",
        "bucket": row.get("bucket") or "",
        "size": format_size(row.get("size_bytes") or ""),
        "media": media_kind(path),
        "src": src,
        "previewSrc": preview_src,
        "mirrored": mirrored,
    }

    if curated:
        summary = curated.get("summary") or ""
        if summary:
            item["summary"] = summary
            item["caption"] = summary
            if curated.get("confidence") == "high" and len(summary) > 8:
                item["title"] = summary.split(".")[0][:96]
        if curated.get("suggestedCategory") in CATEGORY_LABELS:
            item["suggestedCategory"] = curated["suggestedCategory"]
            item["suggestedCategoryLabel"] = CATEGORY_LABELS[curated["suggestedCategory"]]
        if curated.get("suggestedAction") in {"delete", "archive", "review"}:
            item["suggestedAction"] = curated["suggestedAction"]
        if curated.get("tags"):
            item["tags"] = curated["tags"]
        if curated.get("excerpt"):
            item["excerpt"] = curated["excerpt"]
        if curated.get("confidence"):
            item["confidence"] = curated["confidence"]

    return item


def main() -> int:
    if not MANIFEST.is_file():
        print(f"Missing manifest: {MANIFEST}", file=sys.stderr)
        print("Missing www/review-data/class_f_ingest_manifest.csv", file=sys.stderr)
        return 1

    curated_map = load_curation_items()
    items = []
    cat_counts: dict[str, int] = defaultdict(int)
    disp_counts: dict[str, int] = defaultdict(int)
    curated_count = 0
    preview_count = 0

    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            curated = curated_map.get(row["path"])
            item = build_item(row, curated)
            items.append(item)
            cat_counts[item["category"]] += 1
            disp_counts[item["disposition"]] += 1
            if curated:
                curated_count += 1
            if item.get("previewSrc"):
                preview_count += 1

    items.sort(key=lambda x: (x["category"], x["path"].lower()))

    categories = [
        {"id": cid, "label": CATEGORY_LABELS.get(cid, cid), "count": n}
        for cid, n in sorted(cat_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    lede = (
        f"{len(items)} Desktop/HART class-F files — mark delete, archive, or review; "
        "edit caption and category. Decisions append to sor/desktop/f_root_review_log.jsonl."
    )
    if preview_count:
        lede += f" {preview_count} preview thumbnails."
    if curated_count:
        lede += f" {curated_count} GPT-curated summaries."

    payload = {
        "title": "F-root document review",
        "lede": lede,
        "categories": categories,
        "dispositions": [
            {"id": d, "label": d.title(), "count": disp_counts.get(d, 0)}
            for d in ("browse", "archive", "skip", "review")
            if disp_counts.get(d)
        ],
        "actionOptions": [
            {"id": "delete", "label": "Delete"},
            {"id": "archive", "label": "Archive"},
            {"id": "review", "label": "Review"},
        ],
        "items": items,
    }

    REVIEW_JSON.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(items)} items → {REVIEW_JSON.name}"
        f" ({preview_count} previews, {curated_count} curated)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
