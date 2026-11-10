#!/usr/bin/env python3
"""Generate HART spot waybill cards from spot_assignments.csv.

CSV columns: Industry, Spot #, Usage, Cars Applicable

Rules:
  - Skip Off Spot and Storage usages.
  - Combine spots with the same industry, usage, and car-type list.
  - Normalize hopper variants (Loaded/Empty/Coal Hopper) to ``Hopper``.
  - Every spot group gets INBOUND and OUTBOUND waybills (one design per
    car type per direction). Load is ``EMPTY`` or a commodity.
  - Three cards per direction for loaded moves and for inbound ``EMPTY`` on load
    tracks (via matches that spot's outbound customer routing). Outbound ``EMPTY`` cards
    are consolidated — one generic empty per spot not already covered by an
    inbound-empty load track.
  - Two additional pages of CSX ↔ NS interchange cards (POHC / through
    traffic). Header reads INTERCHANGE — not individual industry names.
"""

from __future__ import annotations

import csv
import os
import random
import re
import shutil
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table

import generate_card_template as g

BASE = g.BASE
DATA = g.DATA
OUTPUT_DIR = g.OUTPUT_DIR
SPOT_CSV = DATA / "spot_assignments.csv"
OUTPUT = OUTPUT_DIR / "HART_Spot_Waybills.docx"
WAYBILL_CSV = DATA / "HART_Spot_Waybills.csv"
CARDS_PER_PAGE = len(g.CARD_SLOTS)
CARDS_PER_DIRECTION = 3
INTERCHANGE_PAGES = 2
EMPTY = "EMPTY"
PROCESS_CHEMICALS = "Process Chemicals"
GENERAL_FREIGHT = "General Freight"

# Per-card names that summarize to Process Chemicals in the lower table.
_PROCESS_CHEMICAL_DETAILS = frozenset(
    {
        "Phosphoric Acid",
        "Caustic Soda",
        "Hydrochloric Acid",
        "Styrene Monomer",
        "Methyl Methacrylate",
        "Ethyl Acrylate",
        "Phosphor Compounds",
        "Argon",
        "Industrial Gases",
    }
)

# Outbound empty return yards — one destination per industry; totals balance 8 POHC / 8 CSX.
OUTBOUND_EMPTY_RETURN: dict[str, dict[str, str]] = {
    "Aristech Plastics": {"RouteTo": "Scully Yard", "RouteChain": "POHC"},
    "Calgon Carbon": {"RouteTo": "Scully Yard", "RouteChain": "POHC"},
    "A Stucki Co": {"RouteTo": "Demmler Yard", "RouteChain": "CSX"},
    "Ferrel Gas": {"RouteTo": "Demmler Yard", "RouteChain": "CSX"},
    "Kosmos Cement": {"RouteTo": "Demmler Yard", "RouteChain": "CSX"},
}

SKIP_USAGES = frozenset({"off spot", "storage"})

INDUSTRY_ORDER = {
    "Aristech Plastics": 0,
    "A Stucki Co": 1,
    "Calgon Carbon": 2,
    "Ferrel Gas": 3,
    "Kosmos Cement": 4,
}

# Per spot usage: loads plus named suppliers/customers from the HART routing matrix.
# Unload spots: loaded in, empty out. Load/shipping spots: empty in, loaded out.
SPOT_WAYBILL: dict[tuple[str, str], dict] = {
    ("Calgon Carbon", "Coal Unload"): {
        "inbound_load": "Coal",
        "outbound_load": EMPTY,
        "suppliers": [
            "Consol Energy (Pittsburgh, PA)",
            "R&P Coal (Brady Twp, PA)",
            {"name": "Hillman Coal (Canton Twp, PA)", "entry": "POHC"},
        ],
        "customers": [],
    },
    ("Calgon Carbon", "Carbon Load"): {
        "inbound_load": EMPTY,
        "outbound_load": "Activated Carbon",
        "suppliers": [],
        "customers": [
            {"name": "Univar (Salem, MA)", "via": "NS"},
            {"name": "Houghton Chemical (Allston, MA)", "via": "CSX"},
            {"name": "Calgon Corp (Columbus, OH)", "via": "CSX"},
        ],
    },
    ("Calgon Carbon", "Chemical Unload"): {
        "inbound_load": "Process Chemicals",
        "outbound_load": EMPTY,
        "suppliers": [
            {
                "name": "Dow Chemical (Midland, MI)",
                "entry": "CSX",
                "commodity": "Phosphoric Acid",
            },
            {
                "name": "Houghton Chemical (Allston, MA)",
                "entry": "POHC",
                "commodity": "Caustic Soda",
            },
            {
                "name": "General Chemical (Parsippany, NJ)",
                "entry": "POHC",
                "commodity": "Hydrochloric Acid",
            },
        ],
        "customers": [],
    },
    ("Kosmos Cement", "Cement Unload"): {
        "inbound_load": "Cement",
        "outbound_load": EMPTY,
        "suppliers": [
            {"name": "Kosmos Cement (Canton, OH)", "entry": "POHC"},
            {"name": "Lehigh Cement (Mitchell, IN)", "entry": "POHC"},
            "Medusa Cement (Charlevoix, MI)",
        ],
        "customers": [],
    },
    ("Kosmos Cement", "Aggregate Unload"): {
        "inbound_load": "Aggregate",
        "outbound_load": EMPTY,
        "suppliers": [
            "US Aggregates (Indianapolis, IN)",
            {"name": "Michigan Limestone (Rogers City, MI)", "entry": "POHC"},
            "Martin Marietta (Clairton, PA)",
        ],
        "customers": [],
    },
    ("Ferrel Gas", "LPG Unload"): {
        "inbound_load": "LPG",
        "outbound_load": EMPTY,
        "suppliers": [
            {"name": "Ferrellgas Co (Taneytown, MD)", "entry": "POHC"},
            "Ferrellgas pipeline terminal",
        ],
        "customers": [],
    },
    ("Aristech Plastics", "Pellet Unload"): {
        "inbound_load": "Plastic Pellets",
        "outbound_load": EMPTY,
        "suppliers": [
            {"name": "Dow Chemical (Midland, MI)", "entry": "CSX"},
            "BASF (Wyandotte, MI)",
            {"name": "Novacor (Indian Orchard, MA)", "entry": "POHC"},
        ],
        "customers": [],
    },
    ("Aristech Plastics", "Chemical Unload"): {
        "inbound_load": "Process Chemicals",
        "outbound_load": EMPTY,
        "suppliers": [
            {
                "name": "Dow Chemical (Midland, MI)",
                "entry": "CSX",
                "commodity": "Styrene Monomer",
            },
            {
                "name": "Exxon Chemical (Bayonne, NJ)",
                "entry": "POHC",
                "commodity": "Methyl Methacrylate",
            },
            {
                "name": "Dow Chemical (Midland, MI)",
                "entry": "CSX",
                "commodity": "Ethyl Acrylate",
            },
        ],
        "customers": [],
    },
    ("Aristech Plastics", "Shipping Door"): {
        "inbound_load": EMPTY,
        "outbound_load": "Plastic Resins",
        "suppliers": [],
        "customers": [
            {"name": "Owens-Illinois (Toledo, OH)", "via": "NS"},
            {"name": "Bemis Company (Flemington, NJ)", "via": "NS"},
            {"name": "Owens-Illinois (Ottawa, IL)", "via": "CSX"},
        ],
    },
    ("A Stucki Co", "Crane Track"): {
        "inbound_load": "Steel",
        "outbound_load": EMPTY,
        "suppliers": [
            {"name": "Allegheny Ludlum (Brackenridge, PA)", "entry": "POHC"},
            {"name": "Republic Steel (Cleveland, OH)", "entry": "POHC"},
            "Metal Service Co. (Apollo, PA)",
        ],
        "customers": [],
    },
    ("A Stucki Co", "Team Track"): {
        "inbound_load": "General Freight",
        "outbound_load": "General Freight",
        "suppliers": [
            {"name": "Ryerson Steel Service", "commodity": "Steel Coils"},
            {
                "name": "McConway & Torley (Pittsburgh, PA)",
                "entry": "POHC",
                "commodity": "Steel Billets",
            },
            {
                "name": "Washington Steel (Washington, PA)",
                "commodity": "Steel Plate",
            },
        ],
        "customers": [
            {"name": "Ryerson Steel Service", "via": "CSX", "commodity": "Steel Coils"},
            {
                "name": "Metal Service Co. (Apollo, PA)",
                "via": "CSX",
                "commodity": "Machined Parts",
            },
            {
                "name": "McConway & Torley (Pittsburgh, PA)",
                "via": "NS",
                "commodity": "Forged Components",
            },
            {
                "name": "Pittsburgh Forge (McKees Rocks, PA)",
                "via": "NS",
                "commodity": "Railway Springs",
            },
        ],
    },
}

# CSX ↔ POHC interchange: through traffic only. Layout spot industries (see
# INDUSTRY_ORDER) must not appear as RouteFrom or RouteTo — those moves use
# spot waybills instead.
INTERCHANGE_HEADER = "INTERCHANGE"

# Names tied to on-layout industries (exact or operational alias).
_LAYOUT_PARTY_NAMES = frozenset(
    {
        *INDUSTRY_ORDER.keys(),
        "Ferrellgas Co (Taneytown, MD)",
        "Ferrellgas pipeline terminal",
    }
)


def _is_layout_party(name: str) -> bool:
    n = _norm(name)
    if not n:
        return False
    if n in _LAYOUT_PARTY_NAMES:
        return True
    if n.lower().startswith("ferrellgas"):
        return True
    return False


def _ix_card(**fields) -> dict:
    return {
        "Industry": INTERCHANGE_HEADER,
        "CardKind": "interchange",
        "Spots": "—",
        "RouteFrom": "",
        "RouteTo": "",
        "RouteChain": "",
        **fields,
    }


# Off-layout POHC-side industries (through interchange only — not spot cards).
STANDARD_FORGED = "Standard Forged Products (McKees Rocks, PA)"
UNIVERSAL_STAINLESS = "Universal Stainless & Alloy (Bridgeville, PA)"
GE_BRIDGEVILLE = "GE (Bridgeville, PA)"

# Through + POHC-industry interchange (RouteChain = CSX or POHC for Via … Interchange).
# Car types: coils → Coil Car; slabs/billets/plate/bar/forgings → Flat Car; scrap → Gondola.
_INTERCHANGE_IN_VIA_CSX: list[dict] = [
    _ix_card(Commodity="Steel Billets", CarType="Flat Car",
             RouteFrom="Republic Steel (Cleveland, OH)",
             RouteTo=STANDARD_FORGED,
             RouteChain="CSX"),
    _ix_card(Commodity="Stainless Slab", CarType="Flat Car",
             RouteFrom="Allegheny Ludlum (Brackenridge, PA)",
             RouteTo=UNIVERSAL_STAINLESS,
             RouteChain="CSX"),
    _ix_card(Commodity="Phosphor Compounds", CarType="Covered Hopper",
             RouteFrom="General Chemical (Parsippany, NJ)",
             RouteTo=GE_BRIDGEVILLE,
             RouteChain="CSX"),
    _ix_card(Commodity="Steel Billets", CarType="Flat Car",
             RouteFrom="Republic Steel (Cleveland, OH)",
             RouteTo="McConway & Torley (Pittsburgh, PA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Industrial Gases", CarType="Tank Car",
             RouteFrom="Dow Chemical (Midland, MI)",
             RouteTo="Knouse Foods (Orrtanna, PA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Steel Plate", CarType="Flat Car",
             RouteFrom="Bethlehem Steel (Bethlehem, PA)",
             RouteTo="Ryerson Steel Service (Pittsburgh, PA)",
             RouteChain="CSX"),
]

_INTERCHANGE_IN_VIA_POHC: list[dict] = [
    _ix_card(Commodity="Stainless Slab", CarType="Flat Car",
             RouteFrom="Weirton Steel (Weirton, WV)",
             RouteTo="Armco Steel (Middletown, OH)",
             RouteChain="POHC"),
    _ix_card(Commodity="Plastic Pellets", CarType="Covered Hopper",
             RouteFrom="BASF (Wyandotte, MI)",
             RouteTo="Owens-Illinois (Toledo, OH)",
             RouteChain="POHC"),
    _ix_card(Commodity="Phosphor Compounds", CarType="Covered Hopper",
             RouteFrom="General Chemical (Parsippany, NJ)",
             RouteTo="Heinz (Pittsburgh, PA)",
             RouteChain="POHC"),
    _ix_card(Commodity="Argon", CarType="Tank Car",
             RouteFrom="Air Products (Allentown, PA)",
             RouteTo=GE_BRIDGEVILLE,
             RouteChain="POHC"),
    _ix_card(Commodity="Methyl Methacrylate", CarType="Tank Car",
             RouteFrom="Exxon Chemical (Bayonne, NJ)",
             RouteTo="DuPont (Wilmington, DE)",
             RouteChain="POHC"),
    _ix_card(Commodity="Cement", CarType="Covered Hopper",
             RouteFrom="Lehigh Cement (Mitchell, IN)",
             RouteTo="Holcim (Buffalo, NY)",
             RouteChain="POHC"),
    _ix_card(Commodity="Steel Coils", CarType="Coil Car",
             RouteFrom="Republic Steel (Cleveland, OH)",
             RouteTo="John Deere (Moline, IL)",
             RouteChain="POHC"),
]

_INTERCHANGE_OUT_VIA_POHC: list[dict] = [
    _ix_card(Commodity="Forged Components", CarType="Flat Car",
             RouteFrom=STANDARD_FORGED,
             RouteTo="Caterpillar (Peoria, IL)",
             RouteChain="POHC"),
    _ix_card(Commodity="Stainless Bar", CarType="Flat Car",
             RouteFrom=UNIVERSAL_STAINLESS,
             RouteTo="Ryerson Steel (Chicago, IL)",
             RouteChain="POHC"),
    _ix_card(Commodity="Fluorescent Lamps", CarType="Boxcar",
             RouteFrom=GE_BRIDGEVILLE,
             RouteTo="Penelec (Erie, PA)",
             RouteChain="POHC"),
    _ix_card(Commodity="Fluorescent Tubes", CarType="Boxcar",
             RouteFrom=GE_BRIDGEVILLE,
             RouteTo="Graybar Electric (St. Louis, MO)",
             RouteChain="POHC"),
    _ix_card(Commodity="Frozen Foods", CarType="Reefer",
             RouteFrom="Heinz (Pittsburgh, PA)",
             RouteTo="Sysco Foods (Harrisburg, PA)",
             RouteChain="POHC"),
]

_INTERCHANGE_OUT_VIA_CSX: list[dict] = [
    _ix_card(Commodity="Coal", CarType="Hopper",
             RouteFrom="Consol Energy (Pittsburgh, PA)",
             RouteTo="American Electric Power (Columbus, OH)",
             RouteChain="CSX"),
    _ix_card(Commodity="Activated Carbon", CarType="Covered Hopper",
             RouteFrom="Calgon Corp (Columbus, OH)",
             RouteTo="Houghton Chemical (Allston, MA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Packaged Meats", CarType="Reefer",
             RouteFrom="Dubuque Packing Co (Dubuque, IA)",
             RouteTo="Giant Eagle (Pittsburgh, PA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Plastic Resins", CarType="Boxcar",
             RouteFrom="Dow Chemical (Midland, MI)",
             RouteTo="Owens-Illinois (Ottawa, IL)",
             RouteChain="CSX"),
    _ix_card(Commodity="LPG", CarType="Tank Car",
             RouteFrom="Mapco LP (Memphis, TN)",
             RouteTo="Suburban Propane (Buffalo, NY)",
             RouteChain="POHC"),
    _ix_card(Commodity="Stainless Bar", CarType="Flat Car",
             RouteFrom=UNIVERSAL_STAINLESS,
             RouteTo="Carpenter Steel (Reading, PA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Forged Components", CarType="Flat Car",
             RouteFrom=STANDARD_FORGED,
             RouteTo="Sharon Steel (Farrell, PA)",
             RouteChain="CSX"),
]

_INTERCHANGE_CSX_TO_NS: list[dict] = [
    _ix_card(Commodity="Tin Plate", LoadSummary=GENERAL_FREIGHT, CarType="Coil Car",
             RouteFrom="Wheeling-Pittsburgh Steel (Wheeling, WV)",
             RouteTo="Heinz (Pittsburgh, PA)",
             RouteChain="POHC"),
    _ix_card(Commodity="Cement", CarType="Covered Hopper",
             RouteFrom="Medusa Cement (Charlevoix, MI)",
             RouteTo="Knouse Foods (Orrtanna, PA)",
             RouteChain="POHC"),
    _ix_card(Commodity="Scrap Steel", CarType="Gondola",
             RouteFrom="Allegheny Ludlum (Brackenridge, PA)",
             RouteTo="McConway & Torley (Pittsburgh, PA)",
             RouteChain="POHC"),
]

_INTERCHANGE_NS_TO_CSX: list[dict] = [
    _ix_card(Commodity="Steel Coils", LoadSummary=GENERAL_FREIGHT, CarType="Coil Car",
             RouteFrom="Weirton Steel (Weirton, WV)",
             RouteTo="Ryerson Steel Service (Pittsburgh, PA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Plastic Pellets", CarType="Covered Hopper",
             RouteFrom="BASF (Wyandotte, MI)",
             RouteTo="Owens-Illinois (Toledo, OH)",
             RouteChain="CSX"),
]


def build_interchange_deck() -> list[dict]:
    """CSX ↔ POHC interchange and through-traffic cards."""
    raw = (
        _INTERCHANGE_IN_VIA_CSX
        + _INTERCHANGE_IN_VIA_POHC
        + _INTERCHANGE_OUT_VIA_POHC
        + _INTERCHANGE_OUT_VIA_CSX
        + _INTERCHANGE_CSX_TO_NS
        + _INTERCHANGE_NS_TO_CSX
    )
    deck: list[dict] = []
    for card in raw:
        if _is_layout_party(card.get("RouteFrom", "")) or _is_layout_party(
            card.get("RouteTo", "")
        ):
            continue
        _apply_load_summary(card)
        deck.append(card)
    return deck


def _norm(s: str) -> str:
    return (s or "").strip()


def _parse_spot_num(raw: str) -> int:
    return int(re.sub(r"\D", "", raw) or "0")


def normalize_car_type(raw: str) -> str:
    name = _norm(raw)
    lower = name.lower()
    if lower in {"loaded hopper", "empty hopper", "coal hopper"}:
        return "Hopper"
    if "hopper" in lower and any(k in lower for k in ("loaded", "empty", "coal")):
        return "Hopper"
    return name


def _parse_car_types(raw: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(";"):
        normalized = normalize_car_type(part)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return tuple(out)


def _format_spots(nums: list[int]) -> str:
    nums = sorted(set(n for n in nums if n))
    if not nums:
        return ""
    if len(nums) == 1:
        return str(nums[0])

    ranges: list[tuple[int, int]] = []
    start = end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append((start, end))
            start = end = n
    ranges.append((start, end))

    parts: list[str] = []
    for lo, hi in ranges:
        parts.append(str(lo) if lo == hi else f"{lo}-{hi}")
    return ", ".join(parts)


def _commodity_from_usage(usage: str) -> str:
    u = usage.lower()
    if "coal" in u:
        return "Coal"
    if "cement" in u:
        return "Cement"
    if "aggregate" in u:
        return "Aggregate"
    if "lpg" in u:
        return "LPG"
    if "pellet" in u:
        return "Plastic Pellets"
    if "chemical" in u:
        return "Chemicals"
    if "carbon" in u:
        return "Activated Carbon"
    if "steel" in u or "crane" in u:
        return "Steel"
    if "shipping" in u:
        return "Plastic Resins"
    return usage


def _waybill_spec(industry: str, usage: str) -> dict:
    spec = SPOT_WAYBILL.get((industry, usage))
    if spec:
        return spec

    u = usage.lower()
    commodity = _commodity_from_usage(usage)
    if "unload" in u:
        return {
            "inbound_load": commodity,
            "outbound_load": EMPTY,
            "suppliers": ["Various suppliers"],
            "customers": [],
        }
    if "load" in u or "shipping" in u:
        return {
            "inbound_load": EMPTY,
            "outbound_load": commodity,
            "suppliers": [],
            "customers": [{"name": "Various customers", "via": "CSX"}],
        }
    return {
        "inbound_load": "General Freight",
        "outbound_load": "General Freight",
        "suppliers": ["Various local shippers"],
        "customers": [
            {"name": "Various local receivers", "via": "CSX"},
        ],
    }


def _normalize_party(entry) -> dict[str, str]:
    if isinstance(entry, dict):
        return {
            "name": _norm(entry.get("name", "")),
            "via": _norm(entry.get("via", "")),
            "entry": _norm(entry.get("entry", "")),
            "commodity": _norm(entry.get("commodity", "")),
        }
    return {"name": _norm(str(entry)), "via": "", "entry": "", "commodity": ""}


def inbound_commodity_label(spec: dict) -> str:
    """Summary label for operator reference (uses inbound_load, not per-card names)."""
    load = spec.get("inbound_load", "")
    if load == EMPTY:
        return "Empty cars"
    return load


def _apply_load_summary(card: dict, summary_load: str = "") -> None:
    """Set LoadSummary when center commodity differs from the documented load label."""
    if card.get("LoadSummary"):
        return
    commodity = card.get("Commodity", "")
    if not commodity or commodity == EMPTY:
        return
    summary = summary_load or (
        PROCESS_CHEMICALS if commodity in _PROCESS_CHEMICAL_DETAILS else ""
    )
    if summary and summary != EMPTY and commodity != summary:
        card["LoadSummary"] = summary


def _party_pool(flow: str, load: str, spec: dict) -> list[dict[str, str]]:
    if load == EMPTY and flow == "IN":
        return [_normalize_party(c) for c in spec.get("customers") or []]
    if load == EMPTY:
        return []
    if flow == "IN":
        return [_normalize_party(name) for name in spec.get("suppliers") or []]
    return [_normalize_party(c) for c in spec.get("customers") or []]


def _spread_parties(pool: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    """Assign one party per card, shuffled and spread when pool is smaller."""
    blank = {"name": "", "via": "", "entry": "", "commodity": ""}
    if not pool or count <= 0:
        return [blank] * max(count, 0)
    if len(pool) >= count:
        picked = pool.copy()
        random.shuffle(picked)
        return picked[:count]
    shuffled = pool.copy()
    random.shuffle(shuffled)
    out: list[dict[str, str]] = []
    while len(out) < count:
        if out and len(out) % len(shuffled) == 0:
            random.shuffle(shuffled)
        out.append(shuffled[len(out) % len(shuffled)])
    return out


def _apply_route(
    card: dict, flow: str, load: str, party: dict[str, str], industry: str = ""
) -> None:
    if card.get("CardKind") == "interchange":
        return

    name = party.get("name", "")
    via = party.get("via", "")

    if load == EMPTY:
        if flow == "IN" and card.get("Spots"):
            card["RouteFrom"] = ""
            card["RouteTo"] = ""
            via = party.get("via", "")
            entry = party.get("entry", "")
            if via in ("NS", "POHC") or entry == "POHC":
                card["RouteChain"] = "POHC"
            elif via == "CSX" or entry == "CSX":
                card["RouteChain"] = "CSX"
            else:
                card["RouteChain"] = ""
        elif card.get("CardKind") != "outbound_empty":
            card["RouteFrom"] = ""
            card["RouteTo"] = ""
            card["RouteChain"] = ""
    elif flow == "IN":
        card["RouteFrom"] = name
        card["RouteTo"] = ""
        entry = party.get("entry", "")
        card["RouteChain"] = "POHC" if entry == "POHC" else "CSX"
    else:
        card["RouteFrom"] = ""
        card["RouteTo"] = name
        card["RouteChain"] = "POHC" if via in ("NS", "POHC") else "CSX"


def load_spot_groups() -> list[dict]:
    """Load CSV rows and merge spots with identical industry/usage/car lists."""
    if not SPOT_CSV.exists():
        raise FileNotFoundError(SPOT_CSV)

    groups: dict[tuple, dict] = {}
    with SPOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            industry = _norm(row.get("Industry"))
            usage = _norm(row.get("Usage"))
            if not industry or not usage:
                continue
            if usage.lower() in SKIP_USAGES:
                continue

            spot = _parse_spot_num(row.get("Spot #", ""))
            car_types = _parse_car_types(row.get("Cars Applicable", ""))
            if not spot or not car_types:
                continue

            key = (industry, usage, car_types)
            if key not in groups:
                groups[key] = {
                    "Industry": industry,
                    "Usage": usage,
                    "CarTypes": car_types,
                    "Spots": [],
                }
            groups[key]["Spots"].append(spot)

    merged: list[dict] = []
    for entry in groups.values():
        entry["Spots"] = _format_spots(entry["Spots"])
        merged.append(entry)
    return merged


def _spots_from_label(label: str) -> set[int]:
    nums: set[int] = set()
    label = _norm(label)
    if not label:
        return nums
    for part in label.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            nums.update(range(int(lo.strip()), int(hi.strip()) + 1))
        else:
            nums.add(int(part))
    return nums


def _industry_spot_counts(groups: list[dict]) -> dict[str, int]:
    """Unique active car spots per industry (groups already omit off spot / storage)."""
    by_industry: dict[str, set[int]] = defaultdict(set)
    for group in groups:
        by_industry[group["Industry"]].update(_spots_from_label(group["Spots"]))
    return {
        industry: len(spots)
        for industry, spots in by_industry.items()
        if spots
    }


def _industry_inbound_empty_spots(groups: list[dict]) -> dict[str, set[int]]:
    """Spots that receive dedicated inbound EMPTY cards (load tracks)."""
    by_industry: dict[str, set[int]] = defaultdict(set)
    for group in groups:
        spec = _waybill_spec(group["Industry"], group["Usage"])
        if spec.get("inbound_load") == EMPTY:
            by_industry[group["Industry"]].update(_spots_from_label(group["Spots"]))
    return dict(by_industry)


def _industry_outbound_empty_counts(groups: list[dict]) -> dict[str, int]:
    """Outbound empties = total spots minus load spots that use inbound empties."""
    all_spots: dict[str, set[int]] = defaultdict(set)
    for group in groups:
        all_spots[group["Industry"]].update(_spots_from_label(group["Spots"]))
    inbound = _industry_inbound_empty_spots(groups)
    return {
        industry: max(0, len(spots) - len(inbound.get(industry, set())))
        for industry, spots in all_spots.items()
        if spots
    }


def _spot_count(spots: str) -> int:
    """Return the number of physical spots in a formatted spot label."""
    return len(_spots_from_label(spots)) or 1


def build_industry_empty_cards(groups: list[dict]) -> list[dict]:
    """One generic outbound EMPTY per spot not covered by an inbound-empty load track."""
    counts = _industry_outbound_empty_counts(groups)
    cards: list[dict] = []
    for industry in sorted(counts, key=lambda name: INDUSTRY_ORDER.get(name, 99)):
        routing = OUTBOUND_EMPTY_RETURN.get(industry, {})
        for _ in range(counts[industry]):
            cards.append(
                {
                    "Industry": industry,
                    "CardKind": "outbound_empty",
                    "Usage": "",
                    "Spots": "",
                    "CarType": "",
                    "Flow": "OUT",
                    "Commodity": EMPTY,
                    "RouteFrom": "",
                    "RouteTo": routing.get("RouteTo", ""),
                    "RouteChain": routing.get("RouteChain", ""),
                }
            )
    return cards


def _pad_designs(designs: list[dict], count: int = CARDS_PER_DIRECTION) -> list[dict]:
    n = len(designs)
    if n == 1:
        return [deepcopy(designs[0]) for _ in range(count)]
    if n >= count:
        return [deepcopy(d) for d in designs[:count]]
    return [deepcopy(designs[i % n]) for i in range(count)]


def build_waybill_records(groups: list[dict]) -> tuple[list[dict], list[tuple]]:
    """IN + OUT waybill per car type for each spot group."""
    records: list[dict] = []
    group_order: list[tuple] = []

    for group in groups:
        spec = _waybill_spec(group["Industry"], group["Usage"])
        group_key = (group["Industry"], group["Spots"], group["Usage"])
        if group_key not in group_order:
            group_order.append(group_key)

        directions = (
            ("IN", spec["inbound_load"]),
            ("OUT", spec["outbound_load"]),
        )

        for flow, load in directions:
            if load == EMPTY and flow != "IN":
                continue
            pool = _party_pool(flow, load, spec)
            for car_type in group["CarTypes"]:
                records.append(
                    {
                        "GroupKey": group_key,
                        "DirectionKey": (group_key, flow),
                        "Industry": group["Industry"],
                        "Usage": group["Usage"],
                        "Spots": group["Spots"],
                        "Flow": flow,
                        "CarType": car_type,
                        "Commodity": load,
                        "PartyPool": pool,
                    }
                )

    records.sort(
        key=lambda r: (
            INDUSTRY_ORDER.get(r["Industry"], 99),
            r["Industry"],
            int(re.split(r"[-,\s]", r["Spots"])[0]),
            0 if r["Flow"] == "IN" else 1,
            r["Commodity"],
            r["CarType"],
        )
    )
    group_order.sort(
        key=lambda k: (
            INDUSTRY_ORDER.get(k[0], 99),
            k[0],
            int(re.split(r"[-,\s]", k[1])[0]),
        )
    )
    return records, group_order


def expand_copies(waybills: list[dict], group_order: list[tuple]) -> list[dict]:
    """Loaded and inbound empty: three per direction."""
    by_direction: dict[tuple, list[dict]] = defaultdict(list)
    for record in waybills:
        by_direction[record["DirectionKey"]].append(record)

    deck: list[dict] = []
    for group_key in group_order:
        for flow in ("IN", "OUT"):
            direction_key = (group_key, flow)
            designs = [
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("GroupKey", "DirectionKey", "PartyPool")
                }
                for r in by_direction[direction_key]
            ]
            if not designs:
                continue

            load = designs[0]["Commodity"]
            if load == EMPTY:
                copy_count = CARDS_PER_DIRECTION
                spec = _waybill_spec(group_key[0], group_key[2])
                pool = _party_pool("IN", EMPTY, spec)
            else:
                pool = by_direction[direction_key][0].get("PartyPool", [])
                # One shipment per supplier/customer — do not duplicate routes when
                # CARDS_PER_DIRECTION exceeds the party pool (e.g. Ferrel Gas LPG).
                copy_count = CARDS_PER_DIRECTION
                if pool:
                    copy_count = min(CARDS_PER_DIRECTION, max(len(pool), len(designs)))
            padded = _pad_designs(designs, copy_count)
            parties = _spread_parties(pool, len(padded))
            spec = _waybill_spec(group_key[0], group_key[2])
            summary_load = (
                spec["inbound_load"] if flow == "IN" else spec["outbound_load"]
            )

            for card, party in zip(padded, parties):
                card["Usage"] = group_key[2]
                if load == EMPTY:
                    card["CardKind"] = "inbound_empty"
                elif party.get("commodity"):
                    card["Commodity"] = party["commodity"]
                _apply_load_summary(card, summary_load)
                _apply_route(card, flow, load, party, group_key[0])
                deck.append(card)
    return deck


def _card_kind(card: dict) -> str:
    kind = card.get("CardKind")
    if kind in ("interchange", "outbound_empty", "inbound_empty"):
        return kind
    if card.get("Commodity") == EMPTY:
        if card.get("Spots"):
            return "inbound_empty"
        return "outbound_empty"
    return "loaded"


def _deck_sort_key(card: dict) -> tuple:
    industry = card.get("Industry", "")
    kind = _card_kind(card)
    if kind == "outbound_empty":
        section = 2
    elif kind == "interchange":
        section = 1
    else:
        section = 0
    kind_order = {"loaded": 0, "inbound_empty": 1}.get(kind, 0)
    flow = card.get("Flow", "")
    flow_order = 0 if flow == "IN" else 1 if flow == "OUT" else 2
    spots = card.get("Spots", "")
    spot_num = 0
    if spots:
        m = re.search(r"\d+", spots)
        if m:
            spot_num = int(m.group())
    return (
        section,
        INDUSTRY_ORDER.get(industry, 99),
        industry,
        kind_order,
        spot_num,
        flow_order,
        card.get("Usage", ""),
        card.get("CarType", ""),
        card.get("Commodity", ""),
    )


def sort_deck_by_industry(deck: list[dict]) -> list[dict]:
    """Order cards by industry, then kind, spot, flow, usage."""
    return sorted(deck, key=_deck_sort_key)


def _card_to_csv_row(card: dict, card_id: int) -> dict[str, str]:
    return {
        "card_id": str(card_id),
        "industry": card.get("Industry", ""),
        "card_kind": _card_kind(card),
        "usage": card.get("Usage", ""),
        "spots": card.get("Spots", ""),
        "flow": card.get("Flow", ""),
        "commodity": card.get("Commodity", ""),
        "load_summary": card.get("LoadSummary", ""),
        "car_type": card.get("CarType", ""),
        "route_from": card.get("RouteFrom", ""),
        "route_to": card.get("RouteTo", ""),
        "via": card.get("RouteChain", ""),
    }


def export_waybill_csv(deck: list[dict], path: Path) -> None:
    """Write one row per card for editing outside the Word file."""
    fieldnames = [
        "card_id",
        "industry",
        "card_kind",
        "usage",
        "spots",
        "flow",
        "commodity",
        "load_summary",
        "car_type",
        "route_from",
        "route_to",
        "via",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, card in enumerate(deck, start=1):
            writer.writerow(_card_to_csv_row(card, i))


def _summarize_deck(deck: list[dict]) -> list[dict]:
    """Aggregate card attributes per industry for reporting."""
    by_industry: dict[str, list[dict]] = defaultdict(list)
    for card in deck:
        by_industry[card.get("Industry", "")].append(card)

    rows: list[dict] = []
    industries = sorted(
        by_industry,
        key=lambda name: (INDUSTRY_ORDER.get(name, 99), name),
    )
    for industry in industries:
        cards = by_industry[industry]
        kinds = sorted({_card_kind(c) for c in cards})
        flows = sorted({c.get("Flow", "") for c in cards if c.get("Flow")})
        commodities = sorted(
            {c.get("Commodity", "") for c in cards if c.get("Commodity") != EMPTY}
        )
        car_types = sorted({c.get("CarType", "") for c in cards if c.get("CarType")})
        vias = sorted(
            {c.get("RouteChain", "") for c in cards if c.get("RouteChain")}
        )
        usages = sorted({c.get("Usage", "") for c in cards if c.get("Usage")})
        spots = sorted({c.get("Spots", "") for c in cards if c.get("Spots")})
        rows.append(
            {
                "industry": industry,
                "cards": len(cards),
                "kinds": ", ".join(kinds),
                "flows": ", ".join(flows) or "—",
                "usages": "; ".join(usages) or "—",
                "spots": "; ".join(spots) or "—",
                "commodities": "; ".join(commodities) or "EMPTY",
                "car_types": ", ".join(car_types) or "—",
                "vias": ", ".join(vias) or "—",
            }
        )
    return rows


def _fill_deck_to_page(deck: list[dict]) -> list[dict]:
    """Pad the deck so the last sticker page is full."""
    need = (CARDS_PER_PAGE - len(deck) % CARDS_PER_PAGE) % CARDS_PER_PAGE
    if not need:
        return deck

    candidates = [c for c in deck if c.get("Commodity") != EMPTY]
    if not candidates:
        candidates = deck[:]
    random.shuffle(candidates)

    for i in range(need):
        card = deepcopy(candidates[i % len(candidates)])
        if card.get("CardKind") != "interchange":
            spec = _waybill_spec(card["Industry"], card.get("Usage", ""))
            pool = _party_pool(card["Flow"], card["Commodity"], spec)
            _apply_route(
                card,
                card["Flow"],
                card["Commodity"],
                _spread_parties(pool, 1)[0] if pool else {},
                card["Industry"],
            )
        deck.append(card)
    return deck


def _set_page_break_before_table(tbl) -> None:
    first_row = tbl.findall(qn("w:tr"))[0]
    first_cell = first_row.findall(qn("w:tc"))[0]
    p = first_cell.find(qn("w:p"))
    if p is None:
        p = OxmlElement("w:p")
        first_cell.insert(0, p)
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.insert(0, OxmlElement("w:pageBreakBefore"))


def _append_grid(doc: Document, grid_xml) -> Table:
    body = doc.element.body
    tbl = deepcopy(grid_xml)
    _set_page_break_before_table(tbl)
    g._insert_before_sect(body, tbl)
    g._ensure_sect_pr_last(body)
    table = Table(body.findall(qn("w:tbl"))[-1], doc)
    g.strip_grid_guides(table)
    return table


def _blank_sticker_grid():
    scratch_path = BASE / ".scratch_waybill.docx"
    shutil.copy2(g.STICKER_SHEET, scratch_path)
    scratch = Document(scratch_path)
    g.keep_sticker_grid(scratch)
    grid = deepcopy(scratch.tables[0]._tbl)
    scratch_path.unlink(missing_ok=True)
    return grid


def _fill_page(sheet: Table, batch: list[dict], page_idx: int) -> None:
    for i, record in enumerate(batch):
        r, c = g.CARD_SLOTS[i]
        g.build_waybill_card(
            sheet.rows[r].cells[c],
            idx=page_idx * CARDS_PER_PAGE + i,
            record=record,
        )


def generate(deck: list[dict]) -> None:
    g.require_sticker_sheet()

    blank_grid = _blank_sticker_grid()
    temp_path = OUTPUT.with_suffix(".tmp.docx")
    shutil.copy2(g.STICKER_SHEET, temp_path)
    doc = Document(temp_path)
    g.keep_sticker_grid(doc)

    pages = [deck[i : i + CARDS_PER_PAGE] for i in range(0, len(deck), CARDS_PER_PAGE)]

    sheet = doc.tables[0]
    _fill_page(sheet, pages[0], 0)

    for page_idx, batch in enumerate(pages[1:], start=1):
        sheet = _append_grid(doc, blank_grid)
        _fill_page(sheet, batch, page_idx)

    g._add_document_tail(doc.element.body)
    doc.save(temp_path)
    os.replace(temp_path, OUTPUT)


def main() -> None:
    groups = load_spot_groups()
    waybills, group_order = build_waybill_records(groups)
    deck = expand_copies(waybills, group_order)
    inbound_empty_count = sum(
        1 for c in deck if _card_kind(c) == "inbound_empty"
    )
    outbound_empties = build_industry_empty_cards(groups)
    deck = sort_deck_by_industry(deck)
    interchange = build_interchange_deck()
    deck_with_ix = sort_deck_by_industry(deck + interchange + outbound_empties)

    export_waybill_csv(deck_with_ix, WAYBILL_CSV)
    summary = _summarize_deck(deck_with_ix)

    deck = _fill_deck_to_page(deck_with_ix.copy())
    filler_count = len(deck) - len(deck_with_ix)

    by_direction: dict[tuple, list[dict]] = defaultdict(list)
    for record in waybills:
        by_direction[record["DirectionKey"]].append(record)

    pages = (len(deck) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    loaded_card_count = sum(1 for c in deck_with_ix if _card_kind(c) == "loaded")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {WAYBILL_CSV}")
    print(
        f"  {len(waybills)} loaded designs → {loaded_card_count} loaded cards · "
        f"{inbound_empty_count} inbound empties · {len(outbound_empties)} outbound empties · "
        f"{len(interchange)} interchange · {filler_count} page fillers · "
        f"{len(deck)} total · {pages} pages"
    )
    print(f"  source: {SPOT_CSV.name}")
    outbound_empty_counts = _industry_outbound_empty_counts(groups)
    if outbound_empty_counts:
        empty_summary = ", ".join(
            f"{ind} ({outbound_empty_counts[ind]})"
            for ind in sorted(outbound_empty_counts, key=lambda n: INDUSTRY_ORDER.get(n, 99))
        )
        print(f"  outbound empties (industry): {empty_summary}")
    for group_key in group_order:
        industry, spots, usage = group_key
        parts: list[str] = []
        for flow in ("IN", "OUT"):
            designs = by_direction[(group_key, flow)]
            if not designs:
                continue
            load = designs[0]["Commodity"]
            types = ", ".join(d["CarType"] for d in designs)
            pool = designs[0].get("PartyPool", [])
            route_txt = ""
            if pool:
                if load == EMPTY and flow == "IN":
                    label = "via routing"
                    names = [
                        f"{p['name']} ({p['via']})" if p.get("via") else p["name"]
                        for p in pool
                    ]
                elif flow == "OUT":
                    label = "customers"
                    names = [
                        f"{p['name']} ({p['via']})" if p.get("via") else p["name"]
                        for p in pool
                    ]
                else:
                    label = "suppliers"
                    names = [
                        f"{p['name']} ({p['entry']})" if p.get("entry") else p["name"]
                        for p in pool
                    ]
                route_txt = f"{label}: {', '.join(names)}"
            n = len(designs)
            if load == EMPTY:
                card_note = f"{CARDS_PER_DIRECTION}×"
            elif n == 1:
                card_note = f"{CARDS_PER_DIRECTION}×"
            elif n >= CARDS_PER_DIRECTION:
                card_note = "1 each"
            else:
                card_note = f"1 each + {CARDS_PER_DIRECTION - n} extra"
            line = f"{flow} {load} ({types}) {card_note}"
            if route_txt:
                line += f" · {route_txt}"
            parts.append(line)
        if parts:
            print(f"    {industry} spot {spots}: {' | '.join(parts)}")

    via_csx = sum(1 for c in interchange if c.get("RouteChain") == "CSX")
    via_pohc = sum(1 for c in interchange if c.get("RouteChain") == "POHC")
    ix_pages = (len(interchange) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    print(
        f"  interchange: {via_csx} Via CSX · {via_pohc} Via POHC "
        f"({ix_pages} pages)"
    )

    loaded = [
        c for c in deck_with_ix
        if c.get("Commodity") != EMPTY and c.get("RouteChain") in ("CSX", "POHC")
    ]
    in_csx = sum(
        1 for c in loaded
        if c.get("Flow") == "IN" and c["RouteChain"] == "CSX"
    )
    in_pohc = sum(
        1 for c in loaded
        if c.get("Flow") == "IN" and c["RouteChain"] == "POHC"
    )
    out_csx = sum(
        1 for c in loaded
        if c.get("Flow") == "OUT" and c["RouteChain"] == "CSX"
    )
    out_pohc = sum(
        1 for c in loaded
        if c.get("Flow") == "OUT" and c["RouteChain"] == "POHC"
    )
    tot_in_csx = in_csx + len(_INTERCHANGE_IN_VIA_CSX) + len(_INTERCHANGE_NS_TO_CSX)
    tot_in_pohc = in_pohc + len(_INTERCHANGE_IN_VIA_POHC)
    tot_out_csx = out_csx + len(_INTERCHANGE_OUT_VIA_CSX)
    tot_out_pohc = (
        out_pohc + len(_INTERCHANGE_OUT_VIA_POHC) + len(_INTERCHANGE_CSX_TO_NS)
    )
    print(
        f"  loaded routing balance — IN: CSX {tot_in_csx} · POHC {tot_in_pohc} | "
        f"OUT: CSX {tot_out_csx} · POHC {tot_out_pohc}"
    )
    print(
        f"    (spot only — IN: CSX {in_csx} · POHC {in_pohc} | "
        f"OUT: CSX {out_csx} · POHC {out_pohc})"
    )

    print("\n  Industry summary:")
    for row in summary:
        print(
            f"    {row['industry']}: {row['cards']} cards · "
            f"{row['kinds']} · flows {row['flows']} · "
            f"vias {row['vias']}"
        )

    generate(deck)


if __name__ == "__main__":
    main()
