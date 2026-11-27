#!/usr/bin/env python3
"""Check the public rolling-stock gallery against the car and loco masters (ADR-039, lane L6).

``www/data/fleet-gallery.json`` is a copy: ``bin/cars site --apply`` adds an entry for each photographed
car or loco from the card text, and the Photos page reads it (``www/js/fleet.js``). The masters are
``ops/hart-ops/data/image_metadata.csv`` (cars, ADR-013) and ``ops/hart-ops/data/locos.csv`` (locos). This
check reads all three and fails when the copy disagrees:

- each item names one master row: its photo is the row's ``source_image`` (the same file name, any
  extension), or, for a photo from elsewhere, its ``roster_id`` is a car or loco ``roster_id``;
- an item's ``number``, when it gives one, is that row's road number, and its ``type`` is the car row's
  ``car_type`` (``Locomotive`` for a loco that only the loco master has);
- ``Locomotive`` items are in the ``locos`` album and nothing else is; every item of one type is in one album;
- each album's ``count`` is the number of its items, and item ids are unique;
- each master row with a ``source_image`` is in the gallery, unless its text holds the private name, which
  ``bin/cars site`` never publishes.

Captions and road names are the card's wording (a relettered car shows the road it wears), so they are
not compared. It writes nothing: ``bin/cars site --apply`` adds what is missing.

    python3 tools/ops/check_fleet_gallery.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / "ops/hart-ops/card_pipeline"))
from private_name import contains_private_name  # noqa: E402  (the rule bin/cars site applies)

GALLERY = ROOT / "www/data/fleet-gallery.json"
CARS = ROOT / "ops/hart-ops/data/image_metadata.csv"
LOCOS = ROOT / "ops/hart-ops/data/locos.csv"
LOCO_TYPE = "Locomotive"
LOCO_ALBUM = "locos"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def stem(name: str) -> str:
    return Path(name).stem if name else ""


def _private(row: dict) -> bool:
    found: bool = contains_private_name(" ".join(str(v) for v in row.values()))
    return found


def check(gallery: dict, cars: list[dict], locos: list[dict]) -> list[str]:
    problems: list[str] = []
    for name, rows in (("car", cars), ("loco", locos)):
        for photo, n in sorted(Counter(stem(r["source_image"]) for r in rows if r.get("source_image")).items()):
            if n > 1:
                problems.append(f"{n} {name} rows share the photo {photo!r}; each photo is one row")
    car_by_photo = {stem(r["source_image"]): r for r in cars if r.get("source_image")}
    loco_by_photo = {stem(r["source_image"]): r for r in locos if r.get("source_image")}
    car_by_id = {r["roster_id"]: r for r in cars if r.get("roster_id")}
    loco_by_id = {r["roster_id"]: r for r in locos if r.get("roster_id")}
    items = gallery.get("items", [])
    shown: set[str] = set()
    type_albums: dict[str, set[str]] = {}

    for item in items:
        label = item.get("id") or item.get("title") or "?"
        photo = stem(item.get("src", ""))
        car, loco = car_by_photo.get(photo), loco_by_photo.get(photo)
        if car is None and loco is None and item.get("roster_id"):
            car, loco = car_by_id.get(item["roster_id"]), loco_by_id.get(item["roster_id"])
            if car is None and loco is None:
                problems.append(f"item {label}: roster_id {item['roster_id']!r} is in neither master")
                continue
        elif car is None and loco is None:
            problems.append(f"item {label}: its photo {photo!r} is no master row's source_image, and it names no roster_id")
            continue
        else:
            shown.add(photo)
            rids = {r["roster_id"] for r in (car, loco) if r and r.get("roster_id")}
            if item.get("roster_id") and item["roster_id"] not in rids:
                problems.append(f"item {label}: roster_id {item['roster_id']!r}; its photo's row has "
                                f"{' or '.join(sorted(rids)) or 'none'}")
        numbers = {r["road_number"] for r in (car, loco) if r}
        if item.get("number") and item["number"] not in numbers:
            problems.append(f"item {label}: number {item['number']!r}; the master has {' or '.join(sorted(numbers))}")
        want_type = car["car_type"] if car else LOCO_TYPE
        if item.get("type") != want_type:
            problems.append(f"item {label}: type {item.get('type')!r}; the master has {want_type!r}")
        if (item.get("type") == LOCO_TYPE) != (item.get("album") == LOCO_ALBUM):
            problems.append(f"item {label}: type {item.get('type')!r} in album {item.get('album')!r}; "
                            f"{LOCO_TYPE} goes in {LOCO_ALBUM!r} and nothing else does")
        type_albums.setdefault(item.get("type", ""), set()).add(item.get("album", ""))

    for kind, albums in sorted(type_albums.items()):
        if len(albums) > 1:
            problems.append(f"type {kind!r} is in several albums: {', '.join(sorted(albums))}")
    counts = Counter(i.get("album") for i in items)
    album_ids = set()
    for album in gallery.get("albums", []):
        album_ids.add(album.get("id"))
        if album.get("count") != counts.get(album.get("id"), 0):
            problems.append(f"album {album.get('id')!r} count is {album.get('count')}; it has {counts.get(album.get('id'), 0)} items")
    for album in sorted(set(counts) - album_ids, key=str):
        problems.append(f"album {album!r} has items but is not in albums")
    for item_id, n in sorted(Counter(i.get("id") for i in items).items(), key=lambda kv: str(kv[0])):
        if n > 1:
            problems.append(f"id {item_id!r} is given to {n} items")

    for name, by_photo in (("car", car_by_photo), ("loco", loco_by_photo)):
        for photo, row in sorted(by_photo.items()):
            if photo not in shown and not _private(row):
                problems.append(f"{name} row {row.get('roster_id') or photo} ({row['source_image']}) has a photo but no "
                                f"gallery item (bin/cars site --apply adds it)")
    return problems


def main() -> int:
    gallery = json.loads(GALLERY.read_text(encoding="utf-8"))
    problems = check(gallery, read_csv(CARS), read_csv(LOCOS))
    for p in problems:
        print(f"check_fleet_gallery: {p}", file=sys.stderr)
    if problems:
        print(f"check_fleet_gallery: {len(problems)} difference(s) between {GALLERY.relative_to(ROOT)} and the masters",
              file=sys.stderr)
        return 1
    albums = ", ".join(f"{a['id']} {a['count']}" for a in gallery.get("albums", []))
    print(f"check_fleet_gallery: ok ({len(gallery.get('items', []))} items: {albums})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
