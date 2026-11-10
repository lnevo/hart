"""Staged intake: review sheet (stage 1) and repository records (stage 2).

    cars.py review [--batch NAME]    Crop and read new photos, flag problems, write a review sheet
    cars.py ai-notes BATCH FILE      Merge an AI reviewer's readings (JSON) into the sheet
    cars.py kind BATCH loco|car P..  Set the kind of photos (locomotive or car)
    cars.py approve BATCH            Approve the unflagged rows; flagged rows are approved by hand
    cars.py records BATCH            Write approved rows into the repository (cars and locos)

Decision: hart/wiki/decisions/ADR-018-staged-intake-workflow.md. Review writes only the
derived images and the batch folder ``ops/intake/<batch>/``: not the repository, STS or JMRI.
Every photo starts as a car (or a loco if the file name starts ``loco_`` or ``engine_``).
Phone photos keep their IMG_ names, so the kind is a decision on the sheet: likely locos are
flagged from the OCR text and the AI review, and ``cars.py kind`` switches a photo.
"""
from __future__ import annotations

import csv
import html
import os
import re
from datetime import date
from pathlib import Path

HART_ROOT = Path(__file__).resolve().parents[3]
BATCH_ROOT = Path(os.environ.get("HART_INTAKE_ROOT", HART_ROOT / "ops/intake"))

# Edge-response variance of the cropped image. Finished card images in the repository score
# 1,000-2,700; a Gaussian blur of radius 2 on one drops it to 450. A first guess: re-check it
# against the first real batch.
BLUR_THRESHOLD = 600.0

REVIEW_COLUMNS = [
    "photo",
    "kind",
    "image",
    "crop",
    "reporting_marks",
    "road_number",
    "car_type",
    "car_class",
    "color",
    "roster_length_ft",
    "capy_lbs",
    "ld_lmt_lbs",
    "lt_wt_lbs",
    "built",
    "full_name",
    "roster_id",
    "ocr_text",
    "crop_status",
    "blur",
    "ai_marks",
    "ai_number",
    "ai_type",
    "ai_note",
    "flags",
    "status",
    "note",
]
MANIFEST_COLUMNS = ["photo", "kind", "roster_id", "outcome", "reviewed", "recorded"]
LOCO_WORDS = re.compile(
    r"\b(EMD|ALCO|LOCOMOTIVE|DIESEL|HORSEPOWER|(?:GP|SD|SW|NW|RS|FA|FB|GE)\s?-?\d{1,2}[A-Z]?)\b", re.I)
LOCO_TYPES = ("locomotive", "diesel", "engine", "switcher", "electric", "steam")
KIND_FLAGS = ("maybe-loco", "ai-says-loco", "ai-says-car")
PENDING, APPROVED, REJECTED, RECORDED = "pending", "approved", "rejected", "recorded"


def batch_dir(name: str) -> Path:
    return BATCH_ROOT / name


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def blur_score(path: Path) -> float:
    """Edge-response variance of a downscaled grayscale copy. Higher is sharper."""
    import numpy as np
    from PIL import Image, ImageFilter

    image = Image.open(path).convert("L")
    image.thumbnail((1000, 1000))
    edges = np.asarray(image.filter(ImageFilter.FIND_EDGES), dtype="float64")
    return float(edges.var())


def flag_row(row: dict, known_roads: set[str], repo_rows: list[dict], find_car, seen: dict) -> list[str]:
    """The reasons a human should look at this photo before it is approved."""
    flags = []
    if row["crop_status"] not in ("ok", ""):
        flags.append(f"crop-{row['crop_status']}")
    if row["blur"] and float(row["blur"]) < BLUR_THRESHOLD:
        flags.append("blurry")
    if not row["reporting_marks"]:
        flags.append("no-marks")
    elif known_roads and row["reporting_marks"] not in known_roads:
        flags.append("road-not-in-fleet")
    if not row["road_number"]:
        flags.append("no-number")
    rid = row["roster_id"]
    if rid:
        if rid in seen:
            flags.append(f"same-id-as-{seen[rid]}")
        seen.setdefault(rid, row["photo"])
        existing = find_car(repo_rows, rid) if row["kind"] == "car" else None
        if existing is not None and existing.get("source_image"):
            flags.append("duplicate-has-photo")
    from private_name import contains_private_name

    if contains_private_name(row.get("full_name", "") + " " + row.get("ocr_text", "")):
        flags.append("private-name")
    if row["kind"] == "car" and (LOCO_WORDS.search(row.get("ocr_text", ""))
                                 or row.get("car_type", "").lower() in LOCO_TYPES):
        flags.append("maybe-loco")
    return flags


LOCO_PREFIXES = ("loco_", "engine_")


def photo_kind(path: Path) -> str:
    return "loco" if path.name.lower().startswith(LOCO_PREFIXES) else "car"


def photos_to_review(images_dir: Path, repo_rows: list[dict], suffixes: set[str]) -> list[tuple[Path, str]]:
    """New photos in Images/. A converted copy of the same photo is not a second photo."""
    seen = {Path(r["source_image"]).stem for r in repo_rows if r.get("source_image")}
    found, listed = [], set()
    for p in sorted(images_dir.iterdir()) if images_dir.is_dir() else []:
        if p.is_file() and p.suffix.lower() in suffixes and p.stem not in seen | listed:
            found.append((p, photo_kind(p)))
            listed.add(p.stem)
    return found


EDIT_FIELDS = [
    ("reporting_marks", "marks"), ("road_number", "number"), ("car_type", "type"),
    ("car_class", "class"), ("color", "color"), ("roster_length_ft", "length ft"),
    ("capy_lbs", "capy lbs"), ("ld_lmt_lbs", "ld lmt"), ("lt_wt_lbs", "lt wt"),
    ("built", "built"), ("full_name", "full name"), ("note", "note"),
]

SHEET_SCRIPT = """
const COLS=%(cols)s, FIELDS=%(fields)s, ROWS=%(rows)s, KEY='intake-%(batch)s';
let saved={}; try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const csv=v=>/[",\\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;
function collect(){return ROWS.map((r,i)=>{const o={...r};
 document.querySelectorAll('[data-i="'+i+'"]').forEach(el=>o[el.dataset.f]=el.value);return o})}
function store(){const o={};collect().forEach((r,i)=>o[i]=r);
 try{localStorage.setItem(KEY,JSON.stringify(o))}catch(e){}}
document.querySelectorAll('[data-i]').forEach(el=>{
 const s=saved[el.dataset.i]; if(s&&s[el.dataset.f]!==undefined) el.value=s[el.dataset.f];
 el.addEventListener('input',()=>{store();tone(el.dataset.i)})});
function tone(i){const c=document.getElementById('c'+i), st=document.querySelector('[data-i="'+i+'"][data-f="status"]').value;
 c.className='c '+st}
ROWS.forEach((_,i)=>tone(i));
document.getElementById('dl').onclick=()=>{
 const rows=collect(), text=[COLS.join(',')].concat(rows.map(r=>COLS.map(c=>csv(r[c]||'')).join(','))).join('\\n')+'\\n';
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/csv'}));
 a.download='review.csv';a.click()};
"""


def contact_sheet(path: Path, rows: list[dict]) -> None:
    """The review page. Every field can be edited; Download writes review.csv back out."""
    import json

    import crop_picker

    picker_css, picker_html, picker_script, pick = crop_picker.page_parts(path.parent, rows)
    cells = []
    for i, r in enumerate(rows):
        flags = r["flags"].replace(";", " · ") or "ok"
        img = f'<img class=orig src="file://{html.escape(r["image"])}">' if r["image"] else ""
        crop = (f'<input type=hidden data-i="{i}" data-f="crop" value="{html.escape(r.get("crop", ""))}">'
                f'<span class=crop-set></span>')
        if r["photo"] in pick:
            crop += f'<br><button class=adj data-i="{i}">Adjust crop</button>'
        inputs = "".join(
            f'<label>{label}<input data-i="{i}" data-f="{key}" value="{html.escape(r[key])}"></label>'
            for key, label in EDIT_FIELDS
        )
        opts = "".join(
            f'<option{" selected" if r["status"] == v else ""}>{v}</option>'
            for v in (PENDING, APPROVED, "rejected")
        )
        cells.append(
            f'<div id="c{i}" class="c {html.escape(r["status"])}">{img}'
            f'<b>{html.escape(r["photo"])}</b> ({r["kind"]}) &rarr; {html.escape(r["roster_id"] or "?")}'
            f' blur {html.escape(r["blur"])}<br><i>{html.escape(flags)}</i>{crop}'
            f'<label>status<select data-i="{i}" data-f="status">{opts}</select></label>{inputs}</div>'
        )
    script = SHEET_SCRIPT % {
        "cols": json.dumps(REVIEW_COLUMNS), "fields": json.dumps([k for k, _ in EDIT_FIELDS]),
        "rows": json.dumps(rows).replace("</", "<\\/"), "batch": html.escape(path.parent.name),
    } + picker_script
    path.write_text(
        "<!doctype html><meta charset=utf-8><title>Intake review</title><style>"
        "body{font:14px sans-serif;margin:16px}.g{display:grid;gap:12px;"
        "grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}"
        ".c{border:3px solid #c93;padding:8px}.c.approved{border-color:#4a4}.c.rejected{border-color:#c33;opacity:.6}"
        "img{width:100%}label{display:flex;justify-content:space-between;gap:8px;margin-top:3px;font-size:12px}"
        "input,select{width:62%;font:inherit}#bar{position:sticky;top:0;background:#fff;padding:6px 0;margin-bottom:8px}"
        + picker_css + "</style>" + picker_html + "<div id=bar><button id=dl>Download review.csv</button> "
        "Edits are kept in this browser. Download, then run <code>bin/cars sheet-import "
        f"{html.escape(path.parent.name)} ~/Downloads/review.csv</code>.</div>"
        "<div class=g>" + "".join(cells) + f"</div><script>{script}</script>",
        encoding="utf-8",
    )


def cmd_review(args, ctx) -> int:
    """Stage 1. ``ctx`` is the cars module: it supplies the photo processing and repository."""
    rows, _ = ctx.read_rows()
    photos = photos_to_review(ctx.IMAGES_DIR, rows, ctx.IMAGE_SUFFIXES)
    if not photos:
        print(f"No new photos in {ctx.IMAGES_DIR}")
        return 0
    name = args.batch or date.today().isoformat()
    out = batch_dir(name)
    if (out / "review.csv").exists():
        raise SystemExit(f"Batch {name} already exists. Use --batch with another name.")
    out.mkdir(parents=True, exist_ok=True)
    from process_car_images import load_roster

    known_roads = {c["roster_road"] for c in load_roster()} | {c["reporting_marks"] for c in rows}
    known_roads.discard("")
    review, seen = [], {}
    for photo, kind in photos:
        print(f"{photo.name} ({kind})")
        final = ctx.FINAL_DIR / f"{photo.stem}.png"
        row = {c: "" for c in REVIEW_COLUMNS}
        row.update(photo=photo.name, kind=kind, image=str(final), status=PENDING)
        try:
            fields = ctx.process_photo(ctx.to_png(photo))
        except (Exception, SystemExit) as err:  # one bad photo must not stop the batch
            row.update(image="", flags="process-failed", note=str(err)[:200])
            print(f"  failed: {row['note']}")
            review.append(row)
            continue
        row.update({k: v for k, v in fields.items() if k in row})
        row["blur"] = f"{blur_score(final):.0f}" if final.is_file() else ""
        row["roster_id"] = ctx.guess_roster_id(row, kind)
        row["flags"] = ";".join(flag_row(row, known_roads, rows, ctx.find_car, seen))
        review.append(row)
    write_csv(out / "review.csv", REVIEW_COLUMNS, review)
    import crop_picker

    crop_picker.prepare(out, review, ctx)
    contact_sheet(out / "review.html", review)
    flagged = sum(1 for r in review if r["flags"])
    print(f"\n{len(review)} photos, {flagged} flagged. Sheet: {out / 'review.html'}")
    print(f"Fix flagged rows in {out / 'review.csv'} (set status to approved), then:")
    print(f"  cars.py approve {name}")
    return 0


def norm(text: str) -> str:
    return "".join(ch for ch in text.upper() if ch.isalnum())


def apply_ai_notes(rows: list[dict], notes: dict) -> list[str]:
    """Merge an AI reviewer's readings. A reading that differs from the OCR flags the row.

    ``notes`` maps photo name to {"marks", "number", "type", "note"}. The AI only
    suggests: it never changes the OCR fields or the status.
    """
    unknown = [p for p in notes if p not in {r["photo"] for r in rows}]
    for r in rows:
        n = notes.get(r["photo"])
        if n is None:
            continue
        r["ai_marks"], r["ai_number"] = n.get("marks", ""), str(n.get("number", ""))
        r["ai_type"], r["ai_note"] = n.get("type", ""), n.get("note", "") or "reviewed"
        flags = [f for f in r["flags"].split(";") if f and f not in ("ai-disagrees", "ai-says-loco", "ai-says-car")]
        ai_loco = r["ai_type"].lower() in LOCO_TYPES
        if ai_loco and r["kind"] == "car":
            flags.append("ai-says-loco")
        elif r["ai_type"] and not ai_loco and r["kind"] == "loco":
            flags.append("ai-says-car")
        if (norm(r["ai_marks"]) != norm(r["reporting_marks"])
                or norm(r["ai_number"]) != norm(r["road_number"])):
            flags.append("ai-disagrees")
        r["flags"] = ";".join(flags)
    return unknown


def cmd_ai_notes(args, _ctx) -> int:
    import json

    path = batch_dir(args.batch) / "review.csv"
    rows = read_csv(path)
    unknown = apply_ai_notes(rows, json.loads(Path(args.file).read_text(encoding="utf-8")))
    if unknown:
        raise SystemExit(f"Not in the batch: {' '.join(unknown)}")
    write_csv(path, REVIEW_COLUMNS, rows)
    contact_sheet(batch_dir(args.batch) / "review.html", rows)
    disagree = [r["photo"] for r in rows if "ai-disagrees" in r["flags"]]
    print(f"AI notes merged. Disagrees with OCR: {' '.join(disagree) or 'none'}")
    return 0


def cmd_kind(args, ctx) -> int:
    """Set the kind of photos. The roster id is worked out again; kind flags are cleared."""
    path = batch_dir(args.batch) / "review.csv"
    rows = read_csv(path)
    known = {r["photo"] for r in rows}
    unknown = [p for p in args.photos if p not in known]
    if unknown:
        raise SystemExit(f"Not in the batch: {' '.join(unknown)}")
    for r in rows:
        if r["photo"] in args.photos and r["status"] == PENDING:
            r["kind"] = args.kind
            r["roster_id"] = ctx.guess_roster_id(r, args.kind)
            r["flags"] = ";".join(f for f in r["flags"].split(";") if f and f not in KIND_FLAGS)
    import crop_picker

    if (path.parent / crop_picker.DATA_FILE).is_file():  # the picker shows a loco as taken
        crop_picker.prepare(path.parent, rows, ctx)
    write_csv(path, REVIEW_COLUMNS, rows)
    contact_sheet(batch_dir(args.batch) / "review.html", rows)
    print(f"Set {len(args.photos)} photos to {args.kind}.")
    return 0


def cmd_approve(args, _ctx) -> int:
    path = batch_dir(args.batch) / "review.csv"
    rows = read_csv(path)
    unreviewed = [r["photo"] for r in rows if r["status"] == PENDING and not r["ai_note"]]
    if unreviewed and not args.no_ai:
        raise SystemExit(f"{len(unreviewed)} photos have no AI review yet ({' '.join(unreviewed)}). "
                         "Run the AI review (wiki/pipelines/intake-stages.md) or pass --no-ai.")
    count = 0
    for r in rows:
        if r["status"] == PENDING and not r["flags"]:
            r["status"] = APPROVED
            count += 1
    write_csv(path, REVIEW_COLUMNS, rows)
    left = [r["photo"] for r in rows if r["status"] == PENDING]
    print(f"Approved {count} unflagged photos.")
    if left:
        print(f"Still pending ({len(left)}): set status to approved or rejected in {path}")
        print("  " + " ".join(left))
    return 0


def cmd_records(args, ctx) -> int:
    """Stage 2. Writes approved rows into the repository and the batch manifest."""
    out = batch_dir(args.batch)
    review = read_csv(out / "review.csv")
    manifest_path = out / "manifest.csv"
    manifest = read_csv(manifest_path) if manifest_path.is_file() else []
    todo = [r for r in review if r["status"] == APPROVED]
    waiting = [r["photo"] for r in review if r["status"] == PENDING]
    if waiting and not args.allow_pending:
        raise SystemExit(f"{len(waiting)} photos are still pending: {' '.join(waiting)}")
    rows, columns = ctx.read_rows()
    queue = ctx.read_queue()
    for r in todo:
        if r["kind"] == "loco":
            outcome = ctx.record_loco(r, args.dry_run)
        else:
            outcome = ctx.record_car(r, rows, columns, queue, args.dry_run)
        print(f"  {r['photo']}: {outcome}")
        if not args.dry_run:
            r["status"] = RECORDED
            manifest.append(
                {
                    "photo": r["photo"],
                    "kind": r["kind"],
                    "roster_id": r["roster_id"],
                    "outcome": outcome,
                    "reviewed": "owner",
                    "recorded": date.today().isoformat(),
                }
            )
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0
    ctx.write_rows(rows, columns)
    ctx.write_queue(queue)
    write_csv(out / "review.csv", REVIEW_COLUMNS, review)
    write_csv(manifest_path, MANIFEST_COLUMNS, manifest)
    print(f"Recorded {len(todo)}. Manifest: {manifest_path}. Review the diff, then commit.")
    return 0


DETAIL_FIELDS = ["car_type", "car_class", "color", "roster_length_ft", "capy_lbs",
                 "ld_lmt_lbs", "lt_wt_lbs", "built", "full_name"]


def refresh_rows(rows: list[dict], ctx, only_pending: bool = True) -> None:
    """Work out roster ids and flags again after rows were edited."""
    from process_car_images import load_roster

    repo_rows, _ = ctx.read_rows()
    known_roads = {c["roster_road"] for c in load_roster()} | {c["reporting_marks"] for c in repo_rows}
    known_roads.discard("")
    seen: dict = {}
    lengths = [len(r["road_number"]) for r in rows if r["road_number"]]
    usual = max(set(lengths), key=lengths.count) if lengths else 0
    for r in rows:
        if only_pending and r["status"] != PENDING:
            continue
        r["roster_id"] = ctx.guess_roster_id(r, r["kind"] or "car")
        flags = [f for f in flag_row(r, known_roads, repo_rows, ctx.find_car, seen)
                 if not f.startswith("ai-") or f in r["flags"]]
        if r["road_number"] and len(r["road_number"]) != usual and lengths.count(usual) > len(rows) / 2:
            flags.append("number-length")  # most of the batch has the same digit count
        r["flags"] = ";".join(flags)


def best_row(rows: list[dict]) -> dict:
    """The row with the most detail filled in; ties go to the sharper photo."""
    return max(rows, key=lambda r: (sum(bool(r[f]) for f in DETAIL_FIELDS), float(r["blur"] or 0)))


def cmd_fill(args, ctx) -> int:
    """Set fields on every row, then fill each row's empty details from the best row."""
    path = batch_dir(args.batch) / "review.csv"
    rows = read_csv(path)
    for pair in args.set or []:
        key, _, value = pair.partition("=")
        if key not in REVIEW_COLUMNS:
            raise SystemExit(f"Unknown column {key}")
        for r in rows:
            r[key] = value
    best = best_row([r for r in rows if r["kind"] == "car"] or rows)
    filled = 0
    for r in rows:
        for f in DETAIL_FIELDS:
            if not r[f] and best[f]:
                r[f], filled = best[f], filled + 1
            elif r[f] and best[f] and r[f] != best[f] and f != "full_name":
                print(f"  {r['photo']} {f} reads {r[f]}, best row {best['photo']} has {best[f]}")
    refresh_rows(rows, ctx)
    write_csv(path, REVIEW_COLUMNS, rows)
    contact_sheet(batch_dir(args.batch) / "review.html", rows)
    print(f"Best row {best['photo']}. Filled {filled} empty details.")
    return 0


def cmd_sheet_import(args, ctx) -> int:
    """Take the review.csv downloaded from the review page and make it the batch's sheet."""
    new = read_csv(Path(args.file).expanduser())
    path = batch_dir(args.batch) / "review.csv"
    old = read_csv(path)
    if [r["photo"] for r in new] != [r["photo"] for r in old]:
        raise SystemExit("The downloaded sheet is not for this batch (photos differ).")
    for r in new:
        if r["status"] not in (PENDING, APPROVED, "rejected"):
            raise SystemExit(f"{r['photo']}: status must be pending, approved or rejected.")
    import crop_picker

    for r, before in zip(new, old):  # a crop picked on the page re-cuts the card image
        r["crop"] = r.get("crop", "")
        if r["crop"] and r["crop"] != before.get("crop", ""):
            print(f"  {r['photo']}: new crop {r['crop']} -> {crop_picker.apply(r, ctx)}")
    refresh_rows(new, ctx, only_pending=False)  # you may have edited approved rows too
    write_csv(path, REVIEW_COLUMNS, new)
    contact_sheet(batch_dir(args.batch) / "review.html", new)
    print(f"Imported {len(new)} rows. Approved: {sum(r['status'] == APPROVED for r in new)}.")
    return 0
