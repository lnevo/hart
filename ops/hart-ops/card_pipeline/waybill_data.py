"""Waybill tables for generate_waybill_cards.py: loads, routing and interchange decks.

Data only. These tables are the paper system of record for spot waybills (see
wiki/pipelines/waybills.md); the deck logic is in waybill_deck.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

CARDS_PER_DIRECTION = 3
INTERCHANGE_PAGES = 2
EMPTY = "EMPTY"
PROCESS_CHEMICALS = "Process Chemicals"
GENERAL_FREIGHT = "General Freight"


class WaybillDataError(ValueError):
    """A waybill table entry or spot usage the deck cannot be built from."""


class Party(TypedDict):
    """A supplier or customer on a waybill. Blank fields are unset."""

    name: str
    via: str  # the road a customer is reached by (CSX, NS, POHC)
    entry: str  # the road a supplier's load enters by (CSX, POHC)
    commodity: str  # the per-card load, when it differs from the spot's load


class WaybillSpec(TypedDict):
    """Loads and parties for one (industry, usage) spot."""

    inbound_load: str
    outbound_load: str
    suppliers: list[Party]
    customers: list[Party]


# A table entry names a party by its name alone, or by a mapping of Party fields.
RawParty = str | Mapping[str, str]
_PARTY_FIELDS = frozenset(Party.__annotations__)
_SPEC_FIELDS = frozenset(WaybillSpec.__annotations__)


def norm(s: str | None) -> str:
    return (s or "").strip()


def normalize_party(entry: RawParty) -> Party:
    """One Party from a table entry; a mapping may hold only Party fields."""
    if isinstance(entry, str):
        return {"name": norm(entry), "via": "", "entry": "", "commodity": ""}
    unknown = set(entry) - _PARTY_FIELDS
    if unknown:
        raise WaybillDataError(f"party {entry!r} has unknown fields {sorted(unknown)}")
    return {
        "name": norm(entry.get("name", "")),
        "via": norm(entry.get("via", "")),
        "entry": norm(entry.get("entry", "")),
        "commodity": norm(entry.get("commodity", "")),
    }


def normalize_spec(raw: Mapping[str, object], where: str) -> WaybillSpec:
    """A WaybillSpec from a table entry, with every party normalized; ``where`` names it in errors."""
    if set(raw) != _SPEC_FIELDS:
        raise WaybillDataError(f"{where}: fields {sorted(raw)}, expected {sorted(_SPEC_FIELDS)}")
    loads = raw["inbound_load"], raw["outbound_load"]
    if not all(isinstance(load, str) and load for load in loads):
        raise WaybillDataError(f"{where}: inbound_load and outbound_load must be non-blank text")
    return {
        "inbound_load": raw["inbound_load"],
        "outbound_load": raw["outbound_load"],
        "suppliers": [normalize_party(p) for p in raw["suppliers"]],  # type: ignore[union-attr]
        "customers": [normalize_party(p) for p in raw["customers"]],  # type: ignore[union-attr]
    }



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
_SPOT_WAYBILL_RAW: dict[tuple[str, str], dict[str, str | list[RawParty]]] = {
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
SPOT_WAYBILL: dict[tuple[str, str], WaybillSpec] = {
    key: normalize_spec(raw, f"SPOT_WAYBILL{key}") for key, raw in _SPOT_WAYBILL_RAW.items()
}

INTERCHANGE_HEADER = "INTERCHANGE"

# Names tied to on-layout industries (exact or operational alias).
_LAYOUT_PARTY_NAMES = frozenset(
    {
        *INDUSTRY_ORDER.keys(),
        "Ferrellgas Co (Taneytown, MD)",
        "Ferrellgas pipeline terminal",
    }
)



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
INTERCHANGE_IN_VIA_CSX: list[dict] = [
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

INTERCHANGE_IN_VIA_POHC: list[dict] = [
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

INTERCHANGE_OUT_VIA_POHC: list[dict] = [
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

INTERCHANGE_OUT_VIA_CSX: list[dict] = [
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

INTERCHANGE_CSX_TO_NS: list[dict] = [
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

INTERCHANGE_NS_TO_CSX: list[dict] = [
    _ix_card(Commodity="Steel Coils", LoadSummary=GENERAL_FREIGHT, CarType="Coil Car",
             RouteFrom="Weirton Steel (Weirton, WV)",
             RouteTo="Ryerson Steel Service (Pittsburgh, PA)",
             RouteChain="CSX"),
    _ix_card(Commodity="Plastic Pellets", CarType="Covered Hopper",
             RouteFrom="BASF (Wyandotte, MI)",
             RouteTo="Owens-Illinois (Toledo, OH)",
             RouteChain="CSX"),
]
