"""Stage 5: add new photographed cars and locomotives to the public rolling stock gallery.

    cars.py site            Show the entries that would be added to www/data/fleet-gallery.json
    cars.py site --apply    Add them

The gallery file in the hart repo is the only place the public Photos page reads
(www/js/fleet.js). Entries come from the repository, the same data the cards use, so the
caption matches the card. An entry whose text contains the private name is never added.
tools/ops/check_fleet_gallery.py (a check.sh step) holds the file to the car and loco masters.
Deploy afterwards with www/scripts/deploy_hartrailroad.sh.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, TypedDict

import hartlib_path
from card_template_records import CardRecord
from car_records import IntakeContext
from car_repo import as_fields
from private_name import contains_private_name

hartlib_path.ensure_on_path()
from hartlib import paths  # noqa: E402

HART_ROOT = paths.REPO_ROOT
GALLERY = HART_ROOT / "www/data/fleet-gallery.json"
IMAGE_DIR = "../ops/car-cards/car-images/CarImagesFinal"
DEFAULT_ALBUM = "freight"
LOCO_TYPES = ("locomotive", "diesel", "engine", "switcher", "electric")


class GalleryItem(TypedDict, total=False):
    """One photo of fleet-gallery.json. Entries this module adds carry every key."""

    id: str
    album: str
    src: str
    title: str
    caption: str
    credit: str
    road: str
    number: str
    type: str


class GalleryAlbum(TypedDict, total=False):
    id: str
    count: int


class Gallery(TypedDict, total=False):
    """fleet-gallery.json: its albums and items, and any other keys, kept as they are."""

    albums: list[GalleryAlbum]
    items: list[GalleryItem]


class Candidate(NamedTuple):
    """A photographed car or locomotive: the card fields it prints and its photo's file name."""

    record: CardRecord
    source_image: str


def album_for(type_name: str, known: Mapping[str, str]) -> str:
    """Locomotives go in locos; other types follow the album existing entries of that type use."""
    if type_name.lower() in LOCO_TYPES:
        return "locos"
    return known.get(type_name, DEFAULT_ALBUM)


def fleet_id(title: str) -> str:
    """Stable id for the photos page link (photos/#rolling-stock/<id>) and site search: the title as a slug."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def entry_for(record: CardRecord, source_image: str, known: Mapping[str, str]) -> GalleryItem:
    kind = record["Type"]
    road, number = record["RoadName"], record["RoadNumber"]
    desc = record.get("Description", "")
    if desc.strip().lower().startswith(kind.strip().lower()):
        desc = desc.strip()[len(kind.strip()):].strip(" ·,-")  # drop a repeated type, keep the rest (e.g. 40')
    title = f"{road} {number}".strip()
    return {
        "id": fleet_id(title),
        "album": album_for(kind, known),
        "src": f"{IMAGE_DIR}/{Path(source_image).stem}.png",
        "title": title,
        "caption": " · ".join(x for x in (road, kind, desc) if x),
        "credit": "HART car roster",
        "road": road,
        "number": number,
        "type": kind,
    }


def missing_entries(candidates: Sequence[tuple[CardRecord, str]], data: Gallery) -> list[GalleryItem]:
    """Entries for photographed cars the gallery lacks. Never the private name."""
    have = {Path(i["src"]).stem for i in data["items"]}
    known: dict[str, str] = {}
    for item in data["items"]:
        known.setdefault(item.get("type", ""), item["album"])
    taken = {i.get("id") for i in data["items"]}
    out = []
    for record, source_image in candidates:
        if not source_image or Path(source_image).stem in have:
            continue
        entry = entry_for(record, source_image, known)
        if contains_private_name(json.dumps(entry)):
            print(f"  skipped {entry['title']}: contains the private name")
            continue
        base, n = entry["id"], 2
        while entry["id"] in taken:  # a second photo of the same car gets csx-2738-2, and so on
            entry["id"], n = f"{base}-{n}", n + 1
        taken.add(entry["id"])
        out.append(entry)
    return out


def add_entries(data: Gallery, entries: list[GalleryItem]) -> Gallery:
    data["items"].extend(entries)
    for album in data["albums"]:
        album["count"] = sum(1 for i in data["items"] if i["album"] == album["id"])
    return data


def candidates(ctx: IntakeContext) -> list[Candidate]:
    """Every photographed car of the repository, then every photographed locomotive."""
    import generate_all_cards as gen
    import locos

    rows, _ = ctx.read_rows()
    roster = gen.load_roster()
    _, engines = gen.load_engine_roster()
    out = []
    for row in rows:
        if row.get("source_image"):
            record, _image = gen.row_to_card(as_fields(row), roster, engines)
            out.append(Candidate(record, row["source_image"]))
    for loco in locos.read_locos():
        if loco.get("source_image"):
            card, engine = locos.card_row(loco)
            record, _image = gen.row_to_card(card, roster, {**engines, (loco["road_name"], loco["road_number"]): engine})
            out.append(Candidate(record, loco["source_image"]))
    return out


def cmd_site(args: argparse.Namespace, ctx: IntakeContext) -> int:
    found = candidates(ctx)
    data: Gallery = json.loads(GALLERY.read_text(encoding="utf-8"))
    entries = missing_entries(found, data)
    if not entries:
        print("The public gallery already has every photographed car and locomotive.")
        return 0
    for e in entries:
        print(f"  {e['album']:<8} {e['caption']}")
    if not args.apply:
        print(f"{len(entries)} to add. Run again with --apply.")
        return 0
    GALLERY.write_text(json.dumps(add_entries(data, entries), indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"Added {len(entries)} to {GALLERY}. Commit it in the hart repo, then run www/scripts/deploy_hartrailroad.sh.")
    return 0
