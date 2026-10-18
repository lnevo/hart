#!/usr/bin/env python3
"""Build ops-portal content JSON + curated media from consolidation sources.

Legacy: briefing.json, gallery.json and the other data files are hand-edited now,
and this regenerates older content over them. Dry run by default (lists what it
would write); --force writes.

  python3 consolidation/ops-portal/scripts/legacy/build_ops_content.py [--f-root DIR] [--force]

--f-root (or HART_F_ROOT) is the Desktop/HART folder; the default is its
external/desktop-data/f-root mirror.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

CONS = Path(__file__).resolve().parents[3]
PORTAL = CONS / "ops-portal"
DATA = PORTAL / "data"
MEDIA = PORTAL / "assets" / "media"

HART_OPS = CONS / "external" / "hart-ops"
DESKTOP = CONS / "external" / "desktop-data"
STS_DATA = CONS / "external" / "sts-docker-data"
F_ROOT = Path(os.environ.get("HART_F_ROOT") or DESKTOP / "f-root")
WRITE = False  # --force


def _copy(src: Path, dest_name: str) -> str | None:
    if not src.is_file():
        print(f"  skip missing: {src}")
        return None
    dest = MEDIA / dest_name
    if not WRITE:
        print(f"  would copy {src.name} → assets/media/{dest_name} ({src.stat().st_size // 1024} KB)")
        return f"assets/media/{dest_name}"
    MEDIA.mkdir(parents=True, exist_ok=True)
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
        "pub": "HB-01 · Revision B",
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
                        "From 1899 until January 31, 1994, the Pittsburgh & Ohio Valley "
                        "Railway switched the island's furnaces, coke ovens, and "
                        "interchange. HART Railroad's Pittsburgh & Chartiers Valley "
                        "Division is its successor: we handle the interchange between CSX "
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
                "label": "Pittsburgh & Ohio Valley Railway history",
                "href": "../library/pittsburgh-ohio-valley-railway.html",
            },
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
    # Factual About page: what the layout is, its prototype, its aims, and where it stands.
    # History lives in the Articles and the Briefing; link to them rather than retelling.
    return {
        "title": "About HART",
        "lede": (
            "HART Railroad is an HO scale model railroad of Neville Island, the industrial "
            "island in the Ohio River just downstream of Pittsburgh. The places, industries, "
            "and connecting railroads are real. HART itself, and its Pittsburgh & Chartiers "
            "Valley Division, are our own."
        ),
        "sections": [
            {
                "heading": "What HART is",
                "paragraphs": [
                    "From 1899 until January 31, 1994, the Pittsburgh & Ohio Valley Railway "
                    "switched the island's furnaces, coke ovens, and interchange. HART is "
                    "modeled as its successor: the railroad that takes over that job once the "
                    "P&OV is gone.",
                    "HART handles the interchange between CSX and the Pittsburgh & Ohio "
                    "Central (POHC) and switches the industries on the island. South Yard is "
                    "where the two connections meet and where most of the sorting gets done.",
                ],
                "links": [
                    {"label": "Pittsburgh & Ohio Valley Railway history", "href": "library/pittsburgh-ohio-valley-railway.html"},
                    {"label": "New operator briefing", "href": "briefing/index.html"},
                ],
            },
            {
                "heading": "Prototype target",
                "paragraphs": [
                    "The island between 1994, when the P&OV shut down, and January 2016, when "
                    "Shenango Coke Works made its last coke.",
                ],
                "bullets": [
                    "CSX local D749 works the island from Demmler and McKeesport.",
                    "The POHC comes over from Scully Yard and McKees Rocks, often waiting for "
                    "D749 to clear the trestle over the Ohio.",
                    "Customers: Aristech Plastics, A. Stucki Company, Calgon Carbon, "
                    "Ferrellgas, Kosmos Cement, and Shenango Coke Works.",
                    "Signals are Chessie / early CSX searchlights: 13 two-head searchlights "
                    "and 10 dwarfs.",
                    "Not prototype: HART and the P&CV Division are invented, and Route 23, a "
                    "PCC streetcar crossing the island, is a liberty.",
                ],
                "links": [
                    {"label": "Industries", "href": "industries/index.html"},
                    {"label": "Neville Island coke, cement, and chemical history", "href": "library/neville-island-coke-cement-chemical-history.html"},
                    {"label": "Railroads of the Chartiers Valley", "href": "library/chartiers-valley-railroads.html"},
                ],
            },
            {
                "heading": "Aims",
                "bullets": [
                    "Operations that feel like a real railroad, not a pile of car cards.",
                    "Shipper-driven traffic: shippers create demand, the railroad fills it "
                    "with cars, and the paperwork follows the move. Traffic and waybills come "
                    "from STS, the Shipper-driven Traffic Simulator.",
                    "A track scale at South Yard. Coke hoppers from Shenango are weighed "
                    "mid-move, and cars that are overloaded or out of balance go back for a "
                    "reload, the practice AAR General Information Bulletin No. 5 describes.",
                    "A dispatcher running Digicon-style CTC with working signals in the "
                    "aisle.",
                    "Repeatable sessions: each session is saved as a recipe, so it can be "
                    "rerun, tuned, or handed to someone else.",
                    "A small roster where every car earns its keep.",
                ],
                "links": [
                    {"label": "Setting up car movement with STS", "href": "library/sts-operations-article.html"},
                    {"label": "Dispatcher guides", "href": "guides/index.html"},
                ],
            },
            {
                "heading": "Where the layout stands (October 2026)",
                "bullets": [
                    "Operating sessions have started. Session #2 was the first run with STS "
                    "traffic, car cards, and waybills.",
                    "Control runs on JMRI, with turnouts and occupancy detection reported "
                    "over MQTT.",
                    "CATS provides the Digicon CTC and ABS panels. JMRI Signal Mast Logic "
                    "sets the aspects, and LCOS drives the LED searchlights. Signal rules are "
                    "still being tuned.",
                    "The Neville Island helix is under construction.",
                ],
                "links": [
                    {"label": "Layout Explorer", "href": "layout/index.html"},
                    {"label": "Helix build", "href": "helix/index.html"},
                    {"label": "Official publications", "href": "docs/index.html"},
                ],
            },
        ],
        "more_title": "Read more",
        "more": [
            {"label": "Operator briefing", "href": "briefing/index.html", "blurb": "Island history, jobs on the board, destination colors, and the track scale."},
            {"label": "Industries", "href": "industries/index.html", "blurb": "The six customers, their commodities, and logos."},
            {"label": "Articles", "href": "articles/index.html", "blurb": "P&OV, Pittsburgh Coke & Chemical, POHC-line plants, and Chartiers Valley railroads."},
            {"label": "Voices of the P&OV", "href": "library/voices-of-the-pov.html", "blurb": "The crews and clerks of the railroad HART succeeds."},
            {"label": "Photos", "href": "photos/index.html", "blurb": "The island, maps, the layout, and control panels."},
            {"label": "Rolling stock", "href": "fleet/index.html", "blurb": "Car fleet and published power."},
        ],
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
            "On HART, plastic resins and monomers arrive by covered hopper and tank car; "
            "the prototype island plant made plasticizers for flexible PVC. "
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

    # Waybill keys keep the STS spelling; show the companies' real names.
    display_names = {"A Stucki Co": "A. Stucki Company", "Ferrel Gas": "Ferrellgas"}

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
                "name": display_names.get(name, name),
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
            "The customers and commodities that make the railroad work."
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


# Car-note fragments that are roster bookkeeping, not something a visitor should read.
_INTERNAL_NOTE_PREFIXES = ("final_ref=", "engine_roster_id=", "replacement photo for", "not in ")


def public_car_note(notes: str) -> str:
    kept: list[str] = []
    for part in (p.strip() for p in notes.split(";")):
        if not part or part.lower().startswith(_INTERNAL_NOTE_PREFIXES):
            continue
        if any(part.lower() in k.lower() for k in kept):
            continue
        kept.append(part)
    return "; ".join(kept)


# STS stores each car's photo as <cars.Id>.jpg; this backup's Ids match "Rolling Stock photos".
STS_CARS_DUMP = STS_DATA / "backups" / "hart_session_mid4"
_STS_ROAD_MARKS = {"BO": "B&O", "CO": "C&O", "NW": "N&W", "CBQ": "CB&Q"}


def _sts_rows(dump: str, table: str) -> list[list[str]]:
    prefix = f"insert into `{table}` values("
    return [
        next(csv.reader([line[len(prefix) : line.rindex(")")]], escapechar="\\"))
        for line in dump.splitlines()
        if line.startswith(prefix)
    ]


def _display_marks(sts_marks: str) -> str:
    """BO8300 → B&O 8300, GATX31090 → GATX 31090, COST1 → C&O ST1."""
    for short, road in sorted(_STS_ROAD_MARKS.items(), key=lambda kv: -len(kv[0])):
        if sts_marks.startswith(short):
            return f"{road} {sts_marks[len(short):]}"
    m = re.match(r"([A-Z]+)(\d.*)", sts_marks)
    return f"{m.group(1)} {m.group(2)}" if m else sts_marks


def sts_aisle_cars() -> dict[str, tuple[str, str]]:
    """Map aisle photo stem (STS car Id) → (title, caption) from the STS roster."""
    if not STS_CARS_DUMP.is_file():
        return {}
    meta_by_roster: dict[str, dict] = {}
    meta = HART_OPS / "data" / "image_metadata.csv"
    if meta.is_file():
        with meta.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                meta_by_roster.setdefault((row.get("roster_id") or "").strip(), row)
    out: dict[str, tuple[str, str]] = {}
    for row in _sts_rows(STS_CARS_DUMP.read_text(encoding="utf-8"), "cars"):
        car_id, sts_marks, remarks = row[0], row[1], row[7].strip()
        m = meta_by_roster.get(sts_marks, {})
        title = _display_marks(sts_marks)
        road = (m.get("road_name") or "").strip() or title.split(" ")[0]
        # One description per car; skip reviewer remarks like "check road number in OCR zoom".
        note = next(
            (n for n in public_car_note(m.get("notes") or "").split("; ") if not re.search(r"(?i)\bocr\b|\bcheck\b", n)),
            "",
        )
        out[car_id] = (title, " · ".join(p for p in (road, remarks, note) if p))
    return out


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
        "HART publications",
    )
    add(
        "power",
        media.get("loco_pohc"),
        "POHC 2091",
        "Pittsburgh & Ohio Central unit — the other side of the island interchange.",
        "HART publications",
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
        "station_map_barn.png": (
            "Barn",
            "Switch 7 / 9 / 11 / 13 — Engine House and the Barn crossover.",
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
                note = public_car_note(notes)
                title = f"{marks} {num}".strip() or (note.split(";")[0] if note else ctype) or "Roster car"
                caption_parts = [p for p in (road, ctype, note) if p]
                caption = " · ".join(caption_parts) if caption_parts else ctype or "Roster car"
                add(
                    "fleet",
                    f"../external/desktop-data/car-images/CarImagesFinal/{img.name}",
                    title,
                    caption,
                    "HART car roster",
                )

    rs = STS_DATA / "Rolling Stock photos"
    if rs.is_dir():
        aisle_cars = sts_aisle_cars()
        for img in sorted(
            rs.glob("*.jpg"),
            key=lambda p: int(p.stem) if p.stem.isdigit() else 9999,
        ):
            title, caption = aisle_cars.get(img.stem, ("HART car", "Rolling stock on the HART layout."))
            add(
                "aisle",
                f"../external/sts-docker-data/Rolling Stock photos/{img.name}",
                title,
                caption,
                "HART aisle photos",
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
    path = DATA / name
    if not WRITE:
        print(f"  would write {path.relative_to(CONS)} ({len(json.dumps(payload)) // 1024} KB)")
        return
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(CONS)} ({path.stat().st_size // 1024} KB)")


def main() -> None:
    global F_ROOT, WRITE
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--f-root", type=Path, default=F_ROOT, help="Desktop/HART folder (default %(default)s)")
    parser.add_argument("--force", action="store_true", help="write the files (default: dry run)")
    args = parser.parse_args()
    F_ROOT, WRITE = args.f_root, args.force
    print(f"portal: {PORTAL}" + ("" if WRITE else " (dry run; --force to write)"))
    media = build_media()
    write_json("briefing.json", build_briefing())
    write_json("about.json", build_about())
    write_json("industries.json", build_industries())
    write_json("invites.json", build_invites())
    gallery = build_gallery(media)
    write_json("gallery.json", gallery)
    print(
        "done — gallery" if WRITE else "dry run — gallery",
        {a["id"]: a["count"] for a in gallery["albums"]},
        f"total={len(gallery['items'])}",
    )


if __name__ == "__main__":
    main()
