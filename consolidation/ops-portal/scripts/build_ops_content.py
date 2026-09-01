#!/usr/bin/env python3
"""Build ops-portal content JSON + curated media from consolidation sources.

  python3 consolidation/ops-portal/scripts/build_ops_content.py
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

CONS = Path(__file__).resolve().parents[2]
PORTAL = CONS / "ops-portal"
DATA = PORTAL / "data"
MEDIA = PORTAL / "assets" / "media"

HART_OPS = CONS / "external" / "hart-ops"
DESKTOP = CONS / "external" / "desktop-data"
STS_DATA = CONS / "external" / "sts-docker-data"
F_ROOT = Path("/Users/lnevo/Desktop/HART")


def _copy(src: Path, dest_name: str) -> str | None:
    if not src.is_file():
        print(f"  skip missing: {src}")
        return None
    MEDIA.mkdir(parents=True, exist_ok=True)
    dest = MEDIA / dest_name
    shutil.copy2(src, dest)
    print(f"  media {dest_name} ({dest.stat().st_size // 1024} KB)")
    return f"assets/media/{dest_name}"


def build_media() -> dict[str, str]:
    print("media…")
    out: dict[str, str] = {}
    pairs = [
        (
            HART_OPS / "docs" / "published" / "nevilel_island_birdseye view.jpg",
            "birdseye-neville-island.jpg",
            "birdseye",
        ),
        (
            F_ROOT / "Freight_Flow_Map_HART_Railroad_Final.png",
            "freight-flow-map.png",
            "freight_flow",
        ),
        (F_ROOT / "HART_Coal_Types.png", "coal-types.png", "coal_types"),
        (F_ROOT / "Logo.png", "hart-logo.png", "logo"),
        (
            F_ROOT / "J_B_Higbee_Glass__Postcard02B.webp",
            "higbee-glass-postcard.webp",
            "postcard",
        ),
        (
            HART_OPS / "publications" / "assets" / "CR_1993.png",
            "loco-cr-1993.png",
            "loco_cr",
        ),
        (
            HART_OPS / "publications" / "assets" / "POHC_2091.png",
            "loco-pohc-2091.png",
            "loco_pohc",
        ),
        (
            PORTAL / "assets" / "layout" / "dispatcher_panel_neville_island.png",
            "dispatcher-panel.png",
            "dispatcher",
        ),
    ]
    for src, name, key in pairs:
        rel = _copy(src, name)
        if rel:
            out[key] = rel
    return out


def build_briefing() -> dict:
    return {
        "title": "New Operator Primer",
        "pub": "HB-01 · Revision A",
        "lede": (
            "If this is your first Neville Island session, this primer gives you "
            "the story behind the railroad and a feel for how a session runs. "
            "You do not need to memorize it."
        ),
        "sections": [
            {
                "id": "island",
                "heading": "Neville Island",
                "paragraphs": [
                    (
                        "Nestled between Pittsburgh and the Chartiers Valley in the Ohio "
                        "River lies a five-mile strip of land. Originally called Montour's "
                        "Island and later Long Island, it was renamed Neville Island in "
                        "honor of Revolutionary War General John Neville. It was once "
                        'farmland renowned as the "Market Basket of Pittsburgh," which '
                        "all changed at the turn of the century."
                    ),
                    (
                        "Bridges and an electric street railway opened easy access to the "
                        "mainland. American Steel & Wire began the island's first mill in "
                        "1900. During World War I the government took land for a munitions "
                        "plant. After Pearl Harbor, the Dravo Corporation built ships for "
                        "the Navy—and that sealed the island's industrial future."
                    ),
                    (
                        "Today the 1,200-acre township is a mix of heavy industry, "
                        "logistics, and a small residential community. Manufacturing and "
                        "chemical plants still work here, alongside cleanup and redevelopment."
                    ),
                ],
            },
            {
                "id": "railroad",
                "heading": "The Railroad Today",
                "paragraphs": [
                    (
                        "HART Railroad's Pittsburgh & Chartiers Valley Division sits in "
                        "the middle of that story. We handle the interchange between CSX "
                        "and the Pittsburgh & Ohio Central, and we switch the industries "
                        "on the island."
                    ),
                    (
                        "Cars arrive from Demmler / McKeesport on one side and from "
                        "Scully / McKees Rocks on the other. South Yard is where those "
                        "moves meet—and where most of the sorting gets done."
                    ),
                    (
                        "On the real railroad, CSX's D749 works the island toward Demmler, "
                        "and the POHC comes over from McKees Rocks—often waiting for D749 "
                        "to clear the trestle over the Ohio. There is scrap, steel, "
                        "chemicals, and fuel for the airport. Our session compresses that "
                        "into a few overlapping jobs that all share South Yard."
                    ),
                ],
                "industries": [
                    "Aristech Plastics",
                    "A. Stucki Company",
                    "Calgon Carbon",
                    "Ferrellgas",
                    "Kosmos Cement",
                    "Shenango Coke Works",
                ],
            },
            {
                "id": "jobs",
                "heading": "Jobs on the Board",
                "intro": (
                    "Here is the usual crew board for a full session. Exact "
                    "assignments are confirmed in the invitation and again at the briefing."
                ),
                "jobs": [
                    {
                        "code": "D749",
                        "name": "CSX Neville Island Switcher",
                        "blurb": (
                            "The CSX local that comes over from Demmler / McKeesport. It drops "
                            "its inbound cars at South Yard, visits the engine terminal, then "
                            "picks up the outbound block and heads back."
                        ),
                    },
                    {
                        "code": "NVL",
                        "name": "Neville Island Turn",
                        "blurb": (
                            "The Pittsburgh & Ohio Central local from Scully Yard. It swaps "
                            "cars at South Yard, switches the island industries, then takes "
                            "the return cut back toward McKees Rocks."
                        ),
                    },
                    {
                        "code": "CK1",
                        "name": "Coke Transfer",
                        "blurb": (
                            "Works Shenango Coke Works—the pickup, the weigh, and the sort. "
                            "Also calibrates the track scale at the start of the session. "
                            "The Yardmaster assigns the engine."
                        ),
                    },
                    {
                        "code": "Yardmaster",
                        "name": "South Yard",
                        "blurb": (
                            "Keeps South Yard organized. Builds cuts by color, hands work to "
                            "each train, and keeps D749, NVL, and CK1 from stepping on each other."
                        ),
                    },
                    {
                        "code": "Dispatcher",
                        "name": "Neville Island Ops",
                        "blurb": (
                            "Gives clearance and keeps freight out of the streetcar's way. "
                            "When things get busy, Route 23 and the main trains come first."
                        ),
                    },
                    {
                        "code": "Route 23",
                        "name": "Streetcar",
                        "blurb": (
                            "A refurbished PCC car running local passenger service across the "
                            "island. Freight holds until the streetcar clears."
                        ),
                    },
                ],
            },
            {
                "id": "colors",
                "heading": "Destination Colors",
                "intro": (
                    "We sort cars by color. Each color is a place—an industry or an "
                    "interchange. The same colors show up on switch lists, car cards, "
                    "and the yard sheets."
                ),
                "blocks": [
                    {"color": "BLUE", "hex": "#0000CD", "text": "#fff", "dest": "Demmler Yard; McKeesport", "train": "D749"},
                    {"color": "YELLOW", "hex": "#FFFF00", "text": "#000", "dest": "Aristech Plastics", "train": "NVL"},
                    {"color": "GREEN", "hex": "#008000", "text": "#fff", "dest": "A. Stucki Co.", "train": "NVL"},
                    {"color": "PURPLE", "hex": "#800080", "text": "#fff", "dest": "Calgon Carbon", "train": "NVL"},
                    {"color": "RED", "hex": "#FF0000", "text": "#fff", "dest": "Ferrellgas", "train": "NVL"},
                    {"color": "PINK", "hex": "#FFC0CB", "text": "#000", "dest": "Kosmos Cement", "train": "NVL"},
                    {"color": "BLACK", "hex": "#000000", "text": "#fff", "dest": "Shenango Coke Works", "train": "CK1"},
                    {"color": "ORANGE", "hex": "#FFA500", "text": "#000", "dest": "Scully Yard; McKees Rocks", "train": "NVL return"},
                ],
            },
            {
                "id": "scale",
                "heading": "The Track Scale",
                "paragraphs": [
                    (
                        "Shenango loads a lot of coke, and not every hopper comes out "
                        "perfectly. Before those cars leave the island, we weigh them on "
                        "the scale at South Yard. Cars that check out continue on their "
                        "way. Cars that are too heavy or out of balance go back for a reload."
                    ),
                    (
                        "Someone—usually CK1—calibrates the scale before the first weigh "
                        "of the session. Without that, the readings start to drift."
                    ),
                ],
            },
        ],
        "links": [
            {
                "label": "Pittsburgh & Ohio Central overview",
                "href": "https://www.lundsten.dk/railfan_pa/poc/index.html",
            },
            {
                "label": "Neville Island operations notes",
                "href": "https://railroad.net/post1592461.html#p1592461",
            },
            {
                "label": "Proper balancing of hopper cars (CSX / AAR)",
                "href": "https://www.csx.com/index.cfm/library/files/customers/leads/proper-balancing-of-hopper-cars/",
            },
        ],
    }


def build_about() -> dict:
    story = (
        "In the steel-shadowed corners of Pittsburgh, where the smoke of industry once "
        "crowned the skyline and the Ohio River cut a glinting scar through the city's "
        "heart, a quiet revolution took place. It didn't roar like the iron beasts it "
        "ushered in. It whispered, rumbling through the railyards and slipping past "
        "forgotten sidings. It was the birth of HART Railroad.\n\n"
        "In the winter of 1975, a group of visionaries stood on the cracked pavement of "
        "McKees Rocks, a crossroads of history and decay. Industry was retreating. The "
        "great Baltimore & Ohio was withdrawing from its Wheeling Division, and "
        "communities like Bridgeville, Houston, and Neville Island watched their steel "
        "and coal lifelines shrivel. But these people saw something more: a second chance.\n\n"
        "HART Industries was born that year—not a corporation of steel and cement, but of "
        "hope and grit. Led by former railroaders, local investors, and civic leaders, "
        "they sought to lease the aging corridor. Their pitch? Preserve the legacy. "
        "Restore local service. Reawaken the rails.\n\n"
        "Fortune favored the bold. In 1976, the federal government passed the Rail "
        "Revitalization and Regulatory Reform Act, offering financial lifelines for rail "
        "preservation. HART Industries moved quickly. With grant in hand and blueprints "
        "rolled underarm, they courted the Chessie System, the proud but cautious steward "
        "of the B&O.\n\n"
        "And then came the moment—February 1977, at the 150th birthday celebration of the "
        "B&O, held in the grand halls of the Baltimore & Ohio Railroad Museum. Amid "
        "speeches, steam whistles, and antique engines dressed in garland, the deal was "
        "announced. By April 1, 1977, HART Railroad was official. A fifty-year lease. "
        "Renewal guaranteed. A handshake across history.\n\n"
        "The work began in earnest. Scully Yard was scrubbed and rebuilt. Old depots in "
        "Carnegie and Washington saw fresh paint and warm coal stoves. Rails long buried "
        "under weeds rang once more beneath the wheels of NW2s and GP30s. HART revived "
        "the river interchange at McKees Rocks, floating cars across the water like "
        "whispers of the past.\n\n"
        "Freight ran again: chemical cars to Neville, steel coils from Pittsburgh, coal "
        "drags grinding south with RF-16s grumbling at dusk. Tank cars, hoppers, "
        "gondolas—all part of the symphony. And through it all, the passenger service "
        "never died.\n\n"
        "They called it the Pittsburgh-Wheeling Limited, a daily run with varnished "
        "coaches and silverware in the dining car. But hearts truly stirred when the "
        "Royal Blue Excursion steamed to life, pulled by the resurrected P-7 "
        '"President Washington." A living monument, cloaked in smoke and memory.\n\n'
        "Even now, as decades fold into the past, the HART Railroad carries more than "
        "freight. It hauls pride, tradition, and the collective heartbeat of a region. "
        "Each mile of rail, each whistle echoing off the river, tells a story—not just "
        "of commerce, but of community.\n\n"
        "This is not just a railroad.\n"
        "It is a legacy that rides the rails."
    )
    return {
        "title": "About HART",
        "story_title": "Rails Through Time",
        "story": story,
        "narrative_title": "Operational narrative",
        "narrative_bullets": [
            "Privately held regional railroad operated by HART Industries, headquartered in McKees Rocks.",
            "Leases the former B&O Wheeling Division from CSX; Neville Island to Washington, PA, with rights toward Wheeling, WV.",
            "Formed to preserve local freight, heritage passenger service, and industrial lifelines in the Ohio River Valley.",
            "50-year Chessie lease announced at the B&O's 150th birthday (1977); river float revived at McKees Rocks.",
            "Core freight: Neville chemicals and plastics, Pittsburgh steel, Bridgeville/Houston quarry traffic, seasonal coal and coke.",
        ],
        "sts_title": "Building operations (STS)",
        "sts_excerpt": (
            "My layout is the HART Railroad, Pittsburgh & Chartiers Valley Division — a "
            "Pittsburgh-area shortline centered on Neville Island. It interchanges with CSX "
            "and POHC and works mainland staging and yards at Scully, Demmler, McKees Rocks, "
            "and McKeesport. On the island are the industries crews switch — Aristech Plastics, "
            "Calgon Carbon, A Stucki Co, Ferrel Gas, and Kosmos Cement — plus South Yard for "
            "classification and interchange. Nearby, Shenango Coke Works loads coke for steel "
            "customers such as U.S. Steel. The goal was simple: operations that feel like a "
            "real railroad, not a pile of car cards."
        ),
        "sts_note": (
            "From the July 2026 article on setting up car movement with the "
            "Shipper-driven Traffic Simulator — track scale, session recipes, and traffic balance."
        ),
    }


def build_industries() -> dict:
    wb_path = HART_OPS / "data" / "HART_Spot_Waybills.csv"
    by_ind: dict[str, list] = defaultdict(list)
    if wb_path.is_file():
        with wb_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                by_ind[row.get("industry") or "Unknown"].append(row)

    blurbs = {
        "Aristech Plastics": (
            "Plastic resins and monomers arrive by covered hopper and tank car. "
            "Yellow block on the color board — worked by the Neville Island Turn."
        ),
        "A Stucki Co": (
            "Railway springs, machined parts, and steel for the island's railroad supplier. "
            "Green destination."
        ),
        "Calgon Carbon": (
            "Activated carbon, coal, and process chemicals. Purple block — a busy spot for NVL."
        ),
        "Ferrel Gas": (
            "LPG in and out on tank cars. Red destination on the crew sheets."
        ),
        "Kosmos Cement": (
            "Cement and aggregate. Pink block — covered hoppers and bulk moves."
        ),
        "INTERCHANGE": (
            "Off-island shippers and receivers that feed the CSX and POHC connections — "
            "the reason cars keep arriving at South Yard."
        ),
    }

    # Prefer root operator_logos/*.png (verified present)
    logo_files = {
        "Aristech Plastics": HART_OPS / "operator_logos" / "aristech.png",
        "A Stucki Co": HART_OPS / "operator_logos" / "stucki.png",
        "Calgon Carbon": HART_OPS / "operator_logos" / "calgon.png",
        "Ferrel Gas": HART_OPS / "operator_logos" / "ferrellgas.png",
        "Kosmos Cement": HART_OPS / "operator_logos" / "kosmos.png",
        "Shenango Coke Works": HART_OPS / "operator_logos" / "shenango.png",
        "INTERCHANGE": HART_OPS / "operator_logos" / "hart.png",
    }

    def logo_rel(path: Path | None) -> str | None:
        if path is None or not path.is_file():
            return None
        return f"../external/hart-ops/{path.relative_to(HART_OPS).as_posix()}"

    # Waybill industry keys may differ slightly — map aliases
    key_map = {
        "Aristech Plastics": ["Aristech Plastics", "Aristech"],
        "A Stucki Co": ["A Stucki Co", "A. Stucki Co", "Stucki"],
        "Calgon Carbon": ["Calgon Carbon", "Calgon"],
        "Ferrel Gas": ["Ferrel Gas", "Ferrellgas", "Ferrelgas"],
        "Kosmos Cement": ["Kosmos Cement", "Kosmos"],
        "INTERCHANGE": ["INTERCHANGE", "Interchange"],
    }

    def rows_for(name: str) -> list:
        keys = key_map.get(name, [name])
        out: list = []
        for k in keys:
            out.extend(by_ind.get(k, []))
        return out

    industries = []
    for name in [
        "Aristech Plastics",
        "A Stucki Co",
        "Calgon Carbon",
        "Ferrel Gas",
        "Kosmos Cement",
    ]:
        rows = rows_for(name)
        commodities = sorted(
            {
                r.get("commodity") or ""
                for r in rows
                if r.get("commodity") and r.get("commodity") != "EMPTY"
            }
        )
        industries.append(
            {
                "name": name,
                "blurb": blurbs.get(name, ""),
                "commodities": commodities,
                "waybill_count": len(rows),
                "logo": logo_rel(logo_files.get(name)),
            }
        )

    industries.append(
        {
            "name": "Shenango Coke Works",
            "blurb": (
                "Coke for steel customers. Black destination — CK1 works the pickup, "
                "the weigh, and the reload when hoppers fail the scale."
            ),
            "commodities": ["Coke"],
            "waybill_count": 0,
            "logo": logo_rel(logo_files.get("Shenango Coke Works")),
        }
    )
    rows = rows_for("INTERCHANGE")
    industries.append(
        {
            "name": "Interchange",
            "blurb": blurbs["INTERCHANGE"],
            "commodities": sorted(
                {
                    r.get("commodity") or ""
                    for r in rows
                    if r.get("commodity") and r.get("commodity") != "EMPTY"
                }
            ),
            "waybill_count": len(rows),
            "logo": logo_rel(logo_files.get("INTERCHANGE")),
        }
    )

    return {
        "title": "Industries on Neville Island",
        "lede": (
            "The customers and commodities that make the railroad work. "
            "Waybill counts come from the consolidation spot-waybill seed."
        ),
        "industries": industries,
    }


def build_invites() -> dict:
    return {
        "title": "Session invitations",
        "lede": (
            "These are the introductions sent to new and returning operators — "
            "the place narrative, jobs, and the tone of a Neville Island night."
        ),
        "sessions": [
            {
                "id": "session-1",
                "title": "Neville Island Operating Session",
                "when": "Session #1 · doors 6:30 · trains 7–10",
                "body": [
                    (
                        "Nestled between Pittsburgh and the Chartiers Valley in the Ohio "
                        "River lies a 5-mile long strip of land. Originally called Montour's "
                        "Island and later Long Island, it was renamed Neville Island in honor "
                        "of Revolutionary War General John Neville. It was once farmland "
                        'renowned as the "Market Basket of Pittsburgh," which all changed '
                        "at the turn of the century."
                    ),
                    (
                        "We'll be focusing on the Neville Island turn (NVL), classification "
                        "work in South Yard receiving/sending from Duff Jct, while also "
                        "working the POV interchange with CSX. We'll also be running the "
                        "newly acquired streetcar service for the island recreating the "
                        "Coraopolis–Sewickley route."
                    ),
                ],
                "jobs": ["NVL (local freight)", "Streetcar service", "Yardmaster", "Dispatcher"],
            },
            {
                "id": "session-2",
                "title": "Neville Island Operating Session #2",
                "when": "Session #2 · CSX inspectors gave the green light",
                "body": [
                    (
                        "CSX local D749 works out of Neville Island, heading east towards "
                        "Demmler Yard. POHC works out of McKees Rocks around noon, heading "
                        "to Neville Island. Often, they wait for D749 to clear the trestle "
                        "over the Ohio River, and clearance from the CSX dispatcher."
                    ),
                    (
                        "There are a number of industries dealing with scrap metal and metal "
                        "fabrication. Visitors should be wary of the truck traffic — dump "
                        "trucks and 18 wheelers — and no trespassing signs."
                    ),
                ],
                "jobs": ["Dispatcher", "Yardmaster", "The Local", "Streetcar / Extras"],
            },
            {
                "id": "session-815",
                "title": "Neville Island Operating Session — 8/15",
                "when": "Day session · briefing mid-morning · trains until the work (or lunch) is done",
                "body": [
                    (
                        "Today, the HART Railroad manages the interchange between CSX and "
                        "POHC and servicing the local industries. After much local demand, "
                        "we've refurbished a classic PCC Streetcar to provide much needed "
                        "commuter service."
                    ),
                    (
                        "The coke works is constantly sending imbalanced or overloaded "
                        "hoppers, so we'll be weighing the outgoing coke shipment. Our track "
                        "scale was recently serviced so it will require calibrating. CSX "
                        "train D749 will be swapping blocks on its way down to McKeesport "
                        "and back, while the POHC NVL train comes in to switch out the local "
                        "industries before heading back to McKees Rocks."
                    ),
                ],
                "jobs": ["D749", "NVL", "CK1 / scale", "Yardmaster", "Dispatcher", "Route 23"],
            },
        ],
    }


def build_gallery(media: dict[str, str]) -> dict:
    items: list[dict] = []

    def add(album: str, src: str | None, title: str, caption: str, credit: str = "") -> None:
        if not src:
            return
        items.append(
            {
                "album": album,
                "src": src,
                "title": title,
                "caption": caption,
                "credit": credit,
            }
        )

    add(
        "place",
        media.get("birdseye"),
        "Neville Island from above",
        "The five-mile strip in the Ohio River — heavy industry, logistics, and a tight residential community.",
        "Published ops photo",
    )
    add(
        "place",
        media.get("freight_flow"),
        "Freight flow on HART",
        "How traffic moves between island industries, South Yard, and the CSX / POHC connections.",
        "HART freight-flow map",
    )
    add(
        "place",
        media.get("coal_types"),
        "Coal and coke on the railroad",
        "Commodity story behind Shenango and the scale job.",
        "HART publications",
    )
    add(
        "place",
        media.get("postcard"),
        "J.B. Higbee Glass postcard",
        "Prototype flavor from the Pittsburgh glass era — the industrial DNA of the island.",
        "Archive postcard",
    )
    add(
        "place",
        media.get("logo"),
        "HART mark",
        "House brand for publications and operator sheets.",
        "HART",
    )
    add(
        "power",
        media.get("loco_cr"),
        "CR 1993",
        "Conrail power on the roster art used in crew publications.",
        "hart-ops publications",
    )
    add(
        "power",
        media.get("loco_pohc"),
        "POHC 2091",
        "Pittsburgh & Ohio Central unit — the other side of the island interchange.",
        "hart-ops publications",
    )
    add(
        "maps",
        media.get("dispatcher"),
        "Dispatcher panel — Neville Island",
        "Compact dispatcher art for the island plant.",
        "Station / dispatcher publications",
    )

    map_captions = {
        "station_map_subdivision.png": (
            "Subdivision overview",
            "Neville Island subdivision — the big picture for new operators.",
        ),
        "station_map_west_yard.png": (
            "West Yard",
            "West end of the plant — approach and classification context.",
        ),
        "station_map_south_yard.png": (
            "South Yard",
            "Where CSX and POHC meet the island jobs. Color blocking starts here.",
        ),
        "station_map_east_end.png": (
            "East End",
            "East end of Neville Island — industries and leads.",
        ),
        "station_map_shenango.png": (
            "Shenango",
            "Shenango Coke Works and the scale story.",
        ),
        "station_map_shenango_rotated.png": (
            "Shenango (rotated sheet)",
            "Alternate orientation of the Shenango station map for the desk.",
        ),
        "station_map_diagram_only.png": (
            "Track diagram",
            "Clean diagram without the publication chrome.",
        ),
        "station_map_subdivision_tt23_panel.png": (
            "Route 23 panel",
            "Streetcar / TT-23 context on the subdivision.",
        ),
    }
    maps_dir = PORTAL / "assets" / "maps"
    for fname, (title, cap) in map_captions.items():
        if (maps_dir / fname).is_file():
            add("maps", f"assets/maps/{fname}", title, cap, "Station maps SM-series")

    meta = HART_OPS / "data" / "image_metadata.csv"
    car_dir = DESKTOP / "car-images" / "CarImagesFinal"
    if meta.is_file() and car_dir.is_dir():
        with meta.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                # Prefer final car-side image name from notes or source
                notes = row.get("notes") or ""
                src_name = row.get("source_image") or ""
                if "CarImagesFinal/" in notes:
                    src_name = notes.split("CarImagesFinal/", 1)[-1].split(";")[0].strip()
                img = car_dir / src_name
                if not img.is_file():
                    continue
                marks = (row.get("reporting_marks") or "").strip()
                num = (row.get("road_number") or "").strip()
                ctype = (row.get("car_type") or "").strip()
                road = (row.get("road_name") or "").strip()
                note = notes
                if ";" in note:
                    note = note.split(";", 1)[-1].strip()
                title = f"{marks} {num}".strip() or src_name
                caption_parts = [p for p in (road, ctype, note) if p]
                caption = " · ".join(caption_parts) if caption_parts else ctype or "Roster car"
                add(
                    "fleet",
                    f"../external/desktop-data/car-images/CarImagesFinal/{img.name}",
                    title,
                    caption,
                    "CarImagesFinal + image_metadata.csv",
                )

    rs = STS_DATA / "Rolling Stock photos"
    if rs.is_dir():
        for img in sorted(
            rs.glob("*.jpg"),
            key=lambda p: int(p.stem) if p.stem.isdigit() else 9999,
        ):
            add(
                "aisle",
                f"../external/sts-docker-data/Rolling Stock photos/{img.name}",
                f"Roster photo {img.stem}",
                "Photographed rolling stock from the HART fleet — browsable aisle set.",
                "STS docker data / Rolling Stock photos",
            )

    albums = [
        {"id": "place", "label": "Place & story"},
        {"id": "maps", "label": "Station maps"},
        {"id": "fleet", "label": "Car fleet"},
        {"id": "aisle", "label": "Aisle photos"},
        {"id": "power", "label": "Power"},
    ]
    counts: dict[str, int] = defaultdict(int)
    for it in items:
        counts[it["album"]] += 1
    for a in albums:
        a["count"] = counts[a["id"]]

    return {
        "title": "Photo gallery",
        "lede": (
            "Browse by album. Open any image for the caption — place, maps, car fleet, "
            "aisle photos, and power."
        ),
        "albums": albums,
        "items": items,
    }


def write_json(name: str, payload: object) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(CONS)} ({path.stat().st_size // 1024} KB)")


def main() -> None:
    print(f"portal: {PORTAL}")
    media = build_media()
    write_json("briefing.json", build_briefing())
    write_json("about.json", build_about())
    write_json("industries.json", build_industries())
    write_json("invites.json", build_invites())
    gallery = build_gallery(media)
    write_json("gallery.json", gallery)
    print(
        "done — gallery",
        {a["id"]: a["count"] for a in gallery["albums"]},
        f"total={len(gallery['items'])}",
    )


if __name__ == "__main__":
    main()
