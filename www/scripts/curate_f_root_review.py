#!/usr/bin/env python3
"""Generate F-root preview thumbnails and optional GPT vision curation."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from f_root_common import (  # noqa: E402
    CATEGORY_IDS,
    CATEGORY_LABELS,
    ROOT,
    CURATION_JSON,
    FROOT,
    MANIFEST,
    PREVIEW_DIR,
    format_size,
    media_kind,
    pretty_title,
)
from f_root_preview import extract_text, generate_all_previews, generate_preview, preview_rel_url  # noqa: E402

DEFAULT_MODEL = "gpt-5.4-mini"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def load_api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    candidates = [
        ROOT / ".env.local",
        ROOT / "tools/env/hart.env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "OPENAI_API_KEY":
                return value.strip().strip('"').strip("'")
    return None


def load_manifest_rows() -> list[dict]:
    rows = []
    with MANIFEST.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows


def load_curation() -> dict:
    if not CURATION_JSON.is_file():
        return {"version": 1, "model": None, "items": {}}
    data = json.loads(CURATION_JSON.read_text(encoding="utf-8"))
    data.setdefault("items", {})
    return data


def save_curation(data: dict) -> None:
    CURATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    CURATION_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_prompt(row: dict, excerpt: str) -> str:
    cats = "\n".join(f"- {cid}: {label}" for cid, label in CATEGORY_LABELS.items())
    return (
        "You curate files from the HART model railroad archive (Neville Island, PA).\n"
        "Return JSON only with keys: summary, suggestedCategory, suggestedAction, confidence, tags.\n"
        "- summary: 1-2 plain sentences describing what this file IS (visible content or document purpose).\n"
        "- suggestedCategory: one category id from the list below.\n"
        "- suggestedAction: delete | archive | review\n"
        "  delete = junk, duplicate, temp, installer, wiring draft, or layout photo series\n"
        "  archive = keep for railroad history / ops reference\n"
        "  review = uncertain, needs human eyes\n"
        "- confidence: high | medium | low\n"
        "- tags: up to 5 short strings (topics, locations, railroad names)\n\n"
        f"Categories:\n{cats}\n\n"
        f"Filename: {row['path']}\n"
        f"Auto category: {row.get('category', '')}\n"
        f"Auto disposition: {row.get('disposition', '')}\n"
        f"Auto notes: {row.get('notes', '')}\n"
        f"Size: {format_size(row.get('size_bytes', ''))}\n"
        f"Text excerpt: {excerpt or '(none — use the preview image)'}\n"
    )


def _response_text(body: dict) -> str:
    chunks: list[str] = []
    for item in body.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    chunks.append(part.get("text") or "")
    if chunks:
        return "\n".join(chunks).strip()
    # Chat Completions fallback shape
    try:
        return body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return ""


def gpt_curate(
    *,
    api_key: str,
    model: str,
    row: dict,
    preview_file: Path | None,
    excerpt: str,
) -> dict:
    user_parts: list[dict] = [
        {"type": "input_text", "text": build_prompt(row, excerpt)},
    ]
    if preview_file and preview_file.is_file():
        b64 = base64.standard_b64encode(preview_file.read_bytes()).decode("ascii")
        user_parts.append(
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}
        )

    payload = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": "Respond with valid JSON only. No markdown fences."}],
            },
            {"role": "user", "content": user_parts},
        ],
        "max_output_tokens": 400,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as err:
            last_err = err
            if err.code == 429 and attempt < 4:
                time.sleep(2 ** attempt + 1)
                continue
            raise
    else:
        raise last_err  # type: ignore[misc]
    text = _response_text(body)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if parsed.get("suggestedCategory") not in CATEGORY_IDS:
        parsed["suggestedCategory"] = row.get("category") or "review"
    if parsed.get("suggestedAction") not in {"delete", "archive", "review"}:
        parsed["suggestedAction"] = "review"
    parsed["confidence"] = parsed.get("confidence") or "medium"
    parsed["tags"] = parsed.get("tags") or []
    parsed["summary"] = parsed.get("summary") or pretty_title(row["path"])
    parsed["curatedAt"] = datetime.now(timezone.utc).isoformat()
    parsed["model"] = model
    if excerpt:
        parsed["excerpt"] = excerpt[:500]
    return parsed


def local_curate(row: dict, excerpt: str) -> dict:
    path = row["path"]
    cat = row.get("category") or "review"
    disp = row.get("disposition") or "review"
    action_map = {"skip": "delete", "archive": "archive", "browse": "review", "review": "review"}
    blob = f"{path} {excerpt} {row.get('notes', '')}".lower()

    if excerpt and len(excerpt.strip()) > 50:
        summary = re.sub(r"\s+", " ", excerpt.strip())
        if len(summary) > 220:
            summary = summary[:220].rsplit(" ", 1)[0] + "…"
    else:
        label = CATEGORY_LABELS.get(cat, cat.replace("_", " "))
        summary = f"{label}: {pretty_title(path)}"

    tags: list[str] = []
    for token in (
        "HART",
        "PRR",
        "P&LE",
        "Neville",
        "Chartiers",
        "Shenango",
        "JMRI",
        "eBay",
        "timetable",
        "safety",
        "wiring",
    ):
        if token.lower() in blob:
            tags.append(token)

    return {
        "summary": summary,
        "suggestedCategory": cat,
        "suggestedAction": action_map.get(disp, "review"),
        "confidence": "medium" if excerpt else "low",
        "tags": tags[:5],
        "curatedAt": datetime.now(timezone.utc).isoformat(),
        "model": "local",
        "excerpt": excerpt[:500] if excerpt else "",
    }


def run_local(rows: list[dict], *, force: bool) -> None:
    data = load_curation()
    data["model"] = "local"
    items = data["items"]
    updated = 0
    for row in rows:
        rel = row["path"]
        existing = items.get(rel)
        if existing and not force:
            if existing.get("model") and existing.get("model") != "local":
                continue
            if existing.get("model") == "local":
                continue
        excerpt = extract_text(rel)
        items[rel] = local_curate(row, excerpt)
        updated += 1
    save_curation(data)
    print(f"  {updated} local summaries written")


def generate_previews(rows: list[dict], force: bool) -> tuple[int, int]:
    paths = [row["path"] for row in rows]
    return generate_all_previews(paths, force=force)


def gpt_priority(row: dict, cached: dict | None) -> int:
    """Higher score = needs GPT vision/summary more."""
    score = 0
    cat = row.get("category") or ""
    disp = row.get("disposition") or ""
    path = row["path"]
    media = media_kind(path)

    if media in {"image", "pdf"}:
        score += 8
    if cat in {"ebay_listings", "screenshots", "misc_media", "reference_photos", "social_downloads", "iphone_photos"}:
        score += 10
    if disp == "browse":
        score += 4
    if cached:
        if cached.get("model") == "local" and not cached.get("excerpt"):
            score += 12
        if cached.get("confidence") == "low":
            score += 6
        summary = cached.get("summary") or ""
        if summary.startswith(
            ("Screenshots:", "Other media:", "eBay", "Reference photos:", "Social", "Other root documents:")
        ):
            score += 8
    if not cached or cached.get("model") == "local":
        score += 2
    if cached and cached.get("model", "").startswith("gpt-"):
        return -1
    return score


def run_gpt(
    rows: list[dict],
    *,
    api_key: str,
    model: str,
    force: bool,
    limit: int | None,
    prioritize: bool = True,
) -> None:
    data = load_curation()
    data["model"] = model
    items = data["items"]

    todo = rows
    if prioritize:
        todo = sorted(
            rows,
            key=lambda r: gpt_priority(r, items.get(r["path"])),
            reverse=True,
        )
        todo = [r for r in todo if gpt_priority(r, items.get(r["path"])) >= 0]

    if limit is not None:
        todo = todo[:limit]

    for i, row in enumerate(todo, start=1):
        rel = row["path"]
        cached = items.get(rel)
        if cached and cached.get("model", "").startswith("gpt-") and not force:
            print(f"  skip (gpt cached) {rel}")
            continue
        excerpt = extract_text(rel)
        preview = generate_preview(rel)
        print(f"  [{i}/{len(todo)}] curating {rel}...")
        try:
            curated = gpt_curate(
                api_key=api_key,
                model=model,
                row=row,
                preview_file=preview,
                excerpt=excerpt,
            )
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError) as err:
            print(f"    FAILED: {err}", file=sys.stderr)
            continue
        items[rel] = curated
        save_curation(data)
        time.sleep(1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="F-root preview + GPT curation pipeline")
    parser.add_argument("--previews", action="store_true", help="Generate preview thumbnails")
    parser.add_argument("--gpt", action="store_true", help="Run GPT vision curation (needs OPENAI_API_KEY)")
    parser.add_argument("--force-previews", action="store_true", help="Regenerate all preview JPGs")
    parser.add_argument("--local", action="store_true", help="Local text-based curation (no API key)")
    parser.add_argument("--force-gpt", action="store_true", help="Re-curate items already GPT-cached")
    parser.add_argument("--force-local", action="store_true", help="Overwrite GPT cache with local summaries")
    parser.add_argument("--no-prioritize", action="store_true", help="Process manifest order, not vision-first")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model (default: {DEFAULT_MODEL})")
    parser.add_argument("--limit", type=int, default=None, help="Limit GPT calls (for testing)")
    parser.add_argument("--merge", action="store_true", help="Rebuild f-root-review.json after run")
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print("Missing manifest www/review-data/class_f_ingest_manifest.csv; its generator is retired", file=sys.stderr)
        return 1

    rows = load_manifest_rows()
    if not args.previews and not args.gpt and not args.local and not args.merge:
        args.previews = True
        args.merge = True

    if args.previews:
        ok, missing = generate_previews(rows, force=args.force_previews)
        print(f"Previews: {ok} generated, {missing} skipped/missing → {PREVIEW_DIR.relative_to(ROOT)}")

    if args.gpt:
        api_key = load_api_key()
        if not api_key:
            print("OPENAI_API_KEY not set (.env.local or tools/env/hart.env)", file=sys.stderr)
            return 1
        run_gpt(
            rows,
            api_key=api_key,
            model=args.model,
            force=args.force_gpt,
            limit=args.limit,
            prioritize=not args.no_prioritize,
        )
        print(f"Curation cache → {CURATION_JSON.relative_to(ROOT)}")

    if args.local:
        run_local(rows, force=args.force_local)
        print(f"Local curation → {CURATION_JSON.relative_to(ROOT)}")

    if args.merge or args.previews or args.gpt or args.local:
        merge_script = SCRIPT_DIR / "build_f_root_review.py"
        import subprocess

        subprocess.run([sys.executable, str(merge_script)], check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
