#!/usr/bin/env python3
"""Expand photo galleries, split rolling stock, and index articles + official docs."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

CONS = Path(__file__).resolve().parents[2]
PORTAL = CONS / "ops-portal"
DATA = PORTAL / "data"
FROOT = CONS / "external" / "desktop-data" / "f-root"
DJ = CONS / "external" / "desktop-data" / "dj-trains"
DOCS_HTML = PORTAL / "docs" / "html"
LIBRARY = PORTAL / "library"

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Skip UI chrome / giant plans that dominate the place gallery
SKIP_PLACE = {
    "Logo.png",
    "Neville Trackplan Clean.png",
    "Neville Trackplan Clean copy.png",
    "Freight_Flow_Map_HART_Railroad_Final.png",
    "HART_Coal_Types.png",
}

PLACE_PRIORITY = [
    "1VFNT00010012.jpg",
    "IMG_4633.png",
    "IMG_5437.jpeg",
    "Shenango1.webp",
    "PRC waiting to return to Coraopolis.jpg",
    "FZ2_758.jpg",
    "FZ2_758-1.jpg",
    "ChartiersTrackScheme.jpg",
    "sewickley streetcar.jpg",
    "sewickley_loop.jpg",
    "trolley_sewickley_bridge.jpg",
    "flannery-16-nov-1940.jpg",
    "flannery_bolts_em1.jpg",
    "flannery_em-1.jpg",
    "allegheny_ludlam.png",
    "ammonium sulphate.png",
    "beckPAdiagram.jpg",
    "beckPAmaners.jpg",
    "beckPAoroszi.jpg",
    "bkPAmaners.jpg",
    "bkPAsalamon1.jpg",
    "bkPAsalamon2.jpg",
    "bkPAunknown.jpg",
    "J_B_Higbee_Glass__Postcard02B.webp",
    "pit.gif",
    "ptry_head.gif",
    "lcn-connection-diagram.webp",
]


def pretty_title(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if stem.upper().startswith("IMG_"):
        return stem.replace("_", " ")
    if stem.lower().startswith("screenshot"):
        return "Layout / ops capture"
    return stem[:80]


def write_json(name: str, payload: object) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(CONS)} ({len(json.dumps(payload))} chars)")


def load_gallery() -> dict:
    return json.loads((DATA / "gallery.json").read_text(encoding="utf-8"))


def build_place_items() -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    # Curated media already copied into portal assets
    curated = [
        (
            "assets/media/birdseye-neville-island.jpg",
            "Neville Island from above",
            "The five-mile strip in the Ohio River — heavy industry, logistics, and a tight community.",
            "Published ops photo",
        ),
        (
            "assets/media/freight-flow-map.png",
            "Freight flow on HART",
            "How traffic moves between island industries, South Yard, and the CSX / POHC connections.",
            "HART freight-flow map",
        ),
        (
            "assets/media/coal-types.png",
            "Coal and coke on the railroad",
            "Commodity story behind Shenango and the scale job.",
            "HART publications",
        ),
        (
            "assets/media/higbee-glass-postcard.webp",
            "J.B. Higbee Glass postcard",
            "Prototype flavor from the Pittsburgh glass era.",
            "Archive postcard",
        ),
        (
            "assets/media/hart-logo.png",
            "HART mark",
            "House brand for publications and operator sheets.",
            "HART",
        ),
    ]
    for src, title, cap, credit in curated:
        if (PORTAL / src).is_file():
            items.append(
                {
                    "album": "place",
                    "src": src,
                    "title": title,
                    "caption": cap,
                    "credit": credit,
                }
            )
            seen.add(Path(src).name.lower())

    # Priority archive photos from Desktop/HART root (mirrored in f-root)
    for name in PLACE_PRIORITY:
        p = FROOT / name
        if not p.is_file():
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "album": "place",
                "src": f"../external/desktop-data/f-root/{name}",
                "title": pretty_title(name),
                "caption": "From the HART Desktop archive (mirrored in consolidation).",
                "credit": "Desktop/HART → consolidation/external/desktop-data/f-root",
            }
        )

    # Remaining f-root photos (layout shots, prototype, maps) — skip duplicates & huge plans
    for p in sorted(FROOT.iterdir(), key=lambda x: x.name.lower()):
        if p.suffix.lower() not in IMG_EXT:
            continue
        if p.name in SKIP_PLACE:
            continue
        key = p.name.lower()
        if key in seen:
            continue
        # Skip tiny decorative gifs already handled; include the rest
        album = "archive"
        if p.name.lower().startswith("screenshot"):
            album = "archive"
        elif p.name.startswith("IMG_") or p.name.startswith("FZ2"):
            album = "layout"
        elif any(
            t in p.name.lower()
            for t in ("map", "usgs", "google", "diagram", "scheme", "trackplan")
        ):
            album = "maps"
        elif any(
            t in p.name.lower()
            for t in (
                "sewickley",
                "flannery",
                "beck",
                "bkpa",
                "postcard",
                "streetcar",
                "trolley",
                "shenango",
                "coal",
                "ludlam",
                "ammonium",
                "higbee",
                "prc",
            )
        ):
            album = "place"
        else:
            album = "archive"
        seen.add(key)
        items.append(
            {
                "album": album,
                "src": f"../external/desktop-data/f-root/{p.name}",
                "title": pretty_title(p.name),
                "caption": "From the HART Desktop archive (mirrored in consolidation).",
                "credit": "Desktop/HART → consolidation/external/desktop-data/f-root",
            }
        )

    # DJ Trains ops / layout captures (newly mirrored)
    if DJ.is_dir():
        for p in sorted(DJ.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMG_EXT:
                continue
            rel = p.relative_to(DJ).as_posix()
            items.append(
                {
                    "album": "layout",
                    "src": f"../external/desktop-data/dj-trains/{rel}",
                    "title": pretty_title(p.name),
                    "caption": "DJ Trains / layout capture from the Desktop HART folder.",
                    "credit": "Desktop/HART/DJ Trains",
                }
            )

    # Station maps already in portal
    maps_dir = PORTAL / "assets" / "maps"
    map_captions = {
        "station_map_subdivision.png": (
            "Subdivision overview",
            "Neville Island subdivision — the big picture for new operators.",
        ),
        "station_map_west_yard.png": ("West Yard", "West end of the plant."),
        "station_map_south_yard.png": (
            "South Yard",
            "Where CSX and POHC meet the island jobs.",
        ),
        "station_map_east_end.png": ("East End", "East end industries and leads."),
        "station_map_shenango.png": ("Shenango", "Shenango Coke Works and the scale story."),
        "station_map_shenango_rotated.png": (
            "Shenango (rotated)",
            "Alternate orientation for the desk.",
        ),
        "station_map_diagram_only.png": ("Track diagram", "Clean diagram without chrome."),
        "station_map_subdivision_tt23_panel.png": (
            "Route 23 panel",
            "Streetcar / TT-23 context on the subdivision.",
        ),
    }
    for fname, (title, cap) in map_captions.items():
        if (maps_dir / fname).is_file():
            items.append(
                {
                    "album": "maps",
                    "src": f"assets/maps/{fname}",
                    "title": title,
                    "caption": cap,
                    "credit": "Station maps SM-series",
                }
            )

    dispatcher = PORTAL / "assets" / "media" / "dispatcher-panel.png"
    if dispatcher.is_file():
        items.append(
            {
                "album": "maps",
                "src": "assets/media/dispatcher-panel.png",
                "title": "Dispatcher panel — Neville Island",
                "caption": "Compact dispatcher art for the island plant.",
                "credit": "Station / dispatcher publications",
            }
        )

    # Current control panels (user-provided Aug 2026)
    panels = [
        (
            "assets/panels/digicon-ctc.png",
            "Digicon CTC",
            "Current Digicon schematic — HART Railroad / Neville Island Operations.",
        ),
        (
            "assets/panels/classic-ctc.png",
            "Classic CTC machine",
            "Current classic CTC panel with switches and signal levers.",
        ),
        (
            "assets/panels/neville-island-le.png",
            "Neville Island LE panel",
            "Current Layout Editor / Neville Island panel with SW labels.",
        ),
    ]
    for src, title, cap in panels:
        if (PORTAL / src).is_file():
            items.append(
                {
                    "album": "panels",
                    "src": src,
                    "title": title,
                    "caption": cap,
                    "credit": "Live panels · Aug 2026",
                }
            )

    return items


def album_counts(items: list[dict], order: list[tuple[str, str]]) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for it in items:
        counts[it["album"]] += 1
    albums = []
    for aid, label in order:
        if counts[aid]:
            albums.append({"id": aid, "label": label, "count": counts[aid]})
    return albums


def split_fleet(old: dict) -> tuple[dict, dict]:
    fleet_items = [it for it in old.get("items", []) if it.get("album") in ("fleet", "aisle", "power")]
    # Remap power into rolling-stock gallery
    for it in fleet_items:
        if it["album"] == "power":
            it = dict(it)
    place_items = build_place_items()

    photo = {
        "title": "Photo gallery",
        "lede": (
            "Place, prototype, layout captures, station maps, and current control panels. "
            "Rolling stock lives in its own gallery."
        ),
        "albums": album_counts(
            place_items,
            [
                ("place", "Place & story"),
                ("layout", "Layout & aisle"),
                ("maps", "Maps & diagrams"),
                ("panels", "Control panels"),
                ("archive", "Archive"),
            ],
        ),
        "items": place_items,
    }

    # Rebuild fleet items from existing gallery (preserve metadata) + power
    stock_items = []
    for it in old.get("items", []):
        if it.get("album") in ("fleet", "aisle", "power"):
            stock_items.append(it)
    # Ensure power locos present even if old gallery lacked them
    for src, title, cap in [
        (
            "assets/media/loco-cr-1993.png",
            "CR 1993",
            "Conrail power on the roster art used in crew publications.",
        ),
        (
            "assets/media/loco-pohc-2091.png",
            "POHC 2091",
            "Pittsburgh & Ohio Central unit — island interchange power.",
        ),
    ]:
        if (PORTAL / src).is_file() and not any(i.get("src") == src for i in stock_items):
            stock_items.append(
                {
                    "album": "power",
                    "src": src,
                    "title": title,
                    "caption": cap,
                    "credit": "hart-ops publications",
                }
            )

    fleet = {
        "title": "Rolling stock gallery",
        "lede": (
            "Car fleet sides from CarImagesFinal, aisle roster photos, and published power art. "
            "Separate from the place / layout photo gallery."
        ),
        "albums": album_counts(
            stock_items,
            [
                ("fleet", "Car fleet"),
                ("aisle", "Aisle photos"),
                ("power", "Power"),
            ],
        ),
        "items": stock_items,
    }
    return photo, fleet


def build_publications() -> dict:
    catalog = [
        {
            "id": "primer",
            "title": "New Operator Primer (HB-01)",
            "kind": "Official publication",
            "html": "docs/html/Neville_Island_New_Operator_Primer.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_New_Operator_Primer.docx",
            "blurb": "Primary briefing document for operators new to Neville Island.",
        },
        {
            "id": "scale-ops",
            "title": "Scale Operating Instructions",
            "kind": "Official publication",
            "html": "docs/html/HART Railroad Scale Operating Instructions.html",
            "source": "../external/hart-ops/docs/published/HART Railroad Scale Operating Instructions.docx",
            "blurb": "How the scale job works on HART.",
        },
        {
            "id": "ym-seq",
            "title": "Yardmaster Sequence",
            "kind": "Official publication",
            "html": "docs/html/Neville_Island_Yardmaster_Sequence.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Yardmaster_Sequence.docx",
            "blurb": "Yardmaster flow for South Yard and the island plant.",
        },
        {
            "id": "ds-list",
            "title": "Dispatcher Train List",
            "kind": "Official publication",
            "html": "docs/html/Neville_Island_Dispatcher_Train_List.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Dispatcher_Train_List.docx",
            "blurb": "Dispatcher-facing train list for Neville Island sessions.",
        },
        {
            "id": "crew-d749",
            "title": "Crew sheet — D749",
            "kind": "Crew sheet",
            "html": "docs/html/Neville_Island_Crew_D749.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Crew_D749.docx",
            "blurb": "Published crew sheet for D749.",
        },
        {
            "id": "crew-nvl",
            "title": "Crew sheet — NVL",
            "kind": "Crew sheet",
            "html": "docs/html/Neville_Island_Crew_NVL.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Crew_NVL.docx",
            "blurb": "Published crew sheet for NVL.",
        },
        {
            "id": "crew-ck1",
            "title": "Crew sheet — CK1",
            "kind": "Crew sheet",
            "html": "docs/html/Neville_Island_Crew_CK1.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Crew_CK1.docx",
            "blurb": "Published crew sheet for CK1.",
        },
        {
            "id": "op-sheet",
            "title": "Operator Sheet",
            "kind": "Official publication",
            "html": "docs/html/HART_Operator_Sheet.html",
            "source": "../external/hart-ops/docs/published/HART_Operator_Sheet.docx",
            "blurb": "General HART operator sheet.",
        },
        {
            "id": "standards",
            "title": "Publication Standards v1.0",
            "kind": "Standards",
            "html": "docs/html/HART_Railroad_Publication_Standards_v1.0.html",
            "source": "../external/hart-ops/docs/published/HART_Railroad_Publication_Standards_v1.0.docx",
            "blurb": "How official HART publications are authored and branded.",
        },
        {
            "id": "sm-sub",
            "title": "Station Map — Subdivision",
            "kind": "Station map",
            "html": "docs/html/Neville_Island_Station_Map.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Station_Map.docx",
            "blurb": "Official subdivision station map publication.",
        },
        {
            "id": "sm-ee",
            "title": "Station Map — East End",
            "kind": "Station map",
            "html": "docs/html/Neville_Island_Station_Map_East_End.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Station_Map_East_End.docx",
            "blurb": "East End station map publication.",
        },
        {
            "id": "sm-sh",
            "title": "Station Map — Shenango",
            "kind": "Station map",
            "html": "docs/html/Neville_Island_Station_Map_Shenango.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Station_Map_Shenango.docx",
            "blurb": "Shenango station map publication.",
        },
        {
            "id": "sm-sy",
            "title": "Station Map — South Yard",
            "kind": "Station map",
            "html": "docs/html/Neville_Island_Station_Map_South_Yard.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Station_Map_South_Yard.docx",
            "blurb": "South Yard station map publication.",
        },
        {
            "id": "sm-wy",
            "title": "Station Map — West Yard",
            "kind": "Station map",
            "html": "docs/html/Neville_Island_Station_Map_West_Yard.html",
            "source": "../external/hart-ops/docs/published/Neville_Island_Station_Map_West_Yard.docx",
            "blurb": "West Yard station map publication.",
        },
        {
            "id": "strr",
            "title": "STRR Speed Match / Measure Table SOP Rev2",
            "kind": "SOP (PDF)",
            "html": "",
            "pdf": "docs/STRR Speed Match-Measure Table SOP Rev2.pdf",
            "source": "../external/hart-ops/docs/published/STRR Speed Match-Measure Table SOP Rev2.pdf",
            "blurb": "Speed match / measure table standard operating procedure.",
        },
    ]
    docs = []
    for row in catalog:
        html_rel = row.get("html") or ""
        pdf_rel = row.get("pdf") or ""
        ok = False
        if html_rel and (PORTAL / html_rel).is_file():
            ok = True
        if pdf_rel and (PORTAL / pdf_rel).is_file():
            ok = True
        if not ok:
            # still list with source link into consolidation external
            src = row.get("source") or ""
            if src.startswith("../") and (CONS / src.replace("../", "", 1)).is_file():
                ok = True
        if ok:
            docs.append(row)
    return {
        "title": "Official publications",
        "lede": (
            "Documents produced by the HART publication pipeline "
            "(hart-ops/docs/published). These are the official operator-facing sheets."
        ),
        "items": docs,
    }


def build_articles() -> dict:
    articles = [
        {
            "id": "rails-through-time",
            "title": "Rails Through Time",
            "kind": "Narrative",
            "href": "library/rails-through-time.html",
            "blurb": "Long-form HART railroad narrative — updated edition.",
        },
        {
            "id": "short-story",
            "title": "HART Railroad short story",
            "kind": "Story",
            "href": "library/short-story.html",
            "blurb": "Short fiction set on the railroad.",
        },
        {
            "id": "sts-ops",
            "title": "STS operations article",
            "kind": "Article",
            "href": "library/sts-operations-article.html",
            "blurb": "How HART uses STS for car forwarding and operations.",
        },
        {
            "id": "history",
            "title": "Updated railroad history",
            "kind": "History notes",
            "href": "library/updated-history.txt",
            "blurb": "Working history notes for the railroad story.",
        },
    ]
    items = []
    for a in articles:
        if (PORTAL / a["href"]).is_file():
            items.append(a)
    return {
        "title": "Articles & stories",
        "lede": "Narratives, history notes, and operations writing from the HART archive.",
        "items": items,
    }


def build_panels() -> dict:
    return {
        "title": "Control panels",
        "lede": (
            "Current live panels (Aug 2026). Digicon CTC, classic CTC machine, and the "
            "Neville Island Layout Editor panel. Use these as the visual source of truth — "
            "the LE device map below is for switch/signal lookup and may show imperfect "
            "crossover geometry on SW-7, SW-23, and SW-35."
        ),
        "panels": [
            {
                "id": "digicon",
                "label": "Digicon CTC",
                "src": "assets/panels/digicon-ctc.png",
                "caption": "HART Railroad · Neville Island Operations · P&CV Division · CTC Digicon",
            },
            {
                "id": "classic",
                "label": "Classic CTC",
                "src": "assets/panels/classic-ctc.png",
                "caption": "Classic CTC board with switch and signal levers",
            },
            {
                "id": "le",
                "label": "Neville Island LE",
                "src": "assets/panels/neville-island-le.png",
                "caption": "Layout Editor panel with SW labels (including SW-7 / SW-23 / SW-35)",
            },
        ],
    }


def main() -> None:
    old = load_gallery()
    photo, fleet = split_fleet(old)
    write_json("gallery.json", photo)
    write_json("fleet-gallery.json", fleet)
    write_json("publications.json", build_publications())
    write_json("articles.json", build_articles())
    write_json("panels.json", build_panels())
    print(
        "photos",
        {a["id"]: a["count"] for a in photo["albums"]},
        "total",
        len(photo["items"]),
    )
    print(
        "fleet",
        {a["id"]: a["count"] for a in fleet["albums"]},
        "total",
        len(fleet["items"]),
    )


if __name__ == "__main__":
    main()
