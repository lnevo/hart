"""Stage 5: add new photographed cars and locomotives to the public rolling stock gallery.

    cars.py site            Show the entries that would be added to www/data/fleet-gallery.json
    cars.py site --apply    Add them

The gallery file in the hart repo is the only place the public Photos page reads
(www/js/fleet.js). Entries come from the repository, the same data the cards use, so the
caption matches the card. An entry whose text contains the private name is never added.
Deploy afterwards with www/scripts/deploy_hartrailroad.sh.
"""
from __future__ import annotations

from private_name import contains_private_name

import json
from pathlib import Path

HART_ROOT = Path(__file__).resolve().parents[3]
GALLERY = HART_ROOT / "www/data/fleet-gallery.json"
IMAGE_DIR = "../ops/car-cards/car-images/CarImagesFinal"
DEFAULT_ALBUM = "freight"


def album_for(type_name: str, known: dict[str, str]) -> str:
    """Locomotives go in locos; other types follow the album existing entries of that type use."""
    if type_name.lower() in ("locomotive", "diesel", "engine", "switcher", "electric"):
        return "locos"
    return known.get(type_name, DEFAULT_ALBUM)


def entry_for(record: dict, source_image: str, known: dict[str, str]) -> dict:
    kind = record["Type"]
    road, number = record["RoadName"], record["RoadNumber"]
    desc = record.get("Description", "")
    if desc.strip().lower().startswith(kind.strip().lower()):
        desc = desc.strip()[len(kind.strip()):].strip(" ·,-")  # drop a repeated type, keep the rest (e.g. 40')
    return {
        "album": album_for(kind, known),
        "src": f"{IMAGE_DIR}/{Path(source_image).stem}.png",
        "title": f"{road} {number}".strip(),
        "caption": " · ".join(x for x in (road, kind, desc) if x),
        "credit": "HART car roster",
        "road": road,
        "number": number,
        "type": kind,
    }


def missing_entries(candidates: list[tuple[dict, str]], data: dict) -> list[dict]:
    """Entries for photographed cars the gallery lacks. Never the private name."""
    have = {Path(i["src"]).stem for i in data["items"]}
    known = {}
    for item in data["items"]:
        known.setdefault(item.get("type", ""), item["album"])
    out = []
    for record, source_image in candidates:
        if not source_image or Path(source_image).stem in have:
            continue
        entry = entry_for(record, source_image, known)
        if contains_private_name(json.dumps(entry)):
            print(f"  skipped {entry['title']}: contains the private name")
            continue
        out.append(entry)
    return out


def add_entries(data: dict, entries: list[dict]) -> dict:
    data["items"].extend(entries)
    for album in data["albums"]:
        album["count"] = sum(1 for i in data["items"] if i["album"] == album["id"])
    return data


def cmd_site(args, ctx) -> int:
    import generate_all_cards as gen
    import locos

    rows, _ = ctx.read_rows()
    roster = gen.load_roster()
    _, engines = gen.load_engine_roster()
    candidates = []
    for row in rows:
        if row.get("source_image"):
            record, _image = gen.row_to_card(row, roster, engines)
            candidates.append((record, row["source_image"]))
    for loco in locos.read_locos():
        if loco.get("source_image"):
            card, engine = locos.card_row(loco)
            record, _image = gen.row_to_card(card, roster, {**engines, (loco["road_name"], loco["road_number"]): engine})
            candidates.append((record, loco["source_image"]))
    data = json.loads(GALLERY.read_text(encoding="utf-8"))
    entries = missing_entries(candidates, data)
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
