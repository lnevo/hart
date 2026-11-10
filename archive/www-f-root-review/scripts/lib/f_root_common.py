"""Shared F-root review paths and taxonomy."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "www/review-data/class_f_ingest_manifest.csv"
FROOT = ROOT / "media/hart-research"
PREVIEW_DIR = ROOT / "www/assets/f-root-previews"
REVIEW_JSON = ROOT / "www/data/f-root-review.json"
CURATION_JSON = ROOT / "www/data/f-root-curation.json"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PDF_EXT = {".pdf"}
DOC_EXT = {".docx", ".xlsx", ".xls", ".pptx", ".ppt", ".doc"}

CATEGORY_LABELS = {
    "screenshots": "Screenshots",
    "ebay_listings": "eBay / listing images",
    "social_downloads": "Social / web downloads",
    "iphone_photos": "iPhone photos",
    "reference_photos": "Reference photos",
    "misc_media": "Other media",
    "narrative_hart_branded": "HART-branded documents",
    "narrative_timetables": "Timetables & schedules",
    "narrative_safety": "Safety & orientation",
    "narrative_train_lists": "Train lists & routing",
    "narrative_other": "Other root documents",
    "reference": "Historical / design reference",
    "prototype": "Prototype & layout reference",
    "installer": "Installers & junk",
    "layout_photos": "Layout photo series",
    "wiring_drafts": "Wiring schematic drafts",
    "temp_files": "Office temp files",
    "review": "Unclassified — review",
}

CATEGORY_IDS = frozenset(CATEGORY_LABELS)


def pretty_title(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if stem.upper().startswith("IMG_"):
        return stem.replace("_", " ")
    if stem.lower().startswith("screenshot"):
        return "Layout / ops capture"
    return stem[:96]


def media_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in PDF_EXT:
        return "pdf"
    if ext in DOC_EXT:
        return "document"
    if ext == ".dmg":
        return "installer"
    return "other"


def format_size(size_bytes: str) -> str:
    if not size_bytes or not str(size_bytes).isdigit():
        return ""
    n = int(size_bytes)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.0f} KB"
    return f"{n} B"
