"""Waybill deck logic for generate_waybill_cards.py: spot parsing, routing and deck order.

Pure functions over the rules waybill_data.py reads. The CSV reader (load_spot_groups) stays in
generate_waybill_cards.py because tests patch SPOT_CSV there. A deck card is a waybill_data.DeckCard: the
fields of card_template_records.WaybillCardRecord, plus the build keys GroupKey, DirectionKey and PartyPool.
"""

from __future__ import annotations

import csv
import random
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import TypedDict

# generate_waybill_cards loads waybill_data by path before this module, so this name
# resolves to the sibling file in this checkout.
from waybill_data import (
    _LAYOUT_PARTY_NAMES,
    CARDS_PER_DIRECTION,
    EMPTY,
    DeckCard,
    FlowKey,
    INDUSTRY_ORDER,
    InterchangeCard,
    Party,
    SpotGroupKey,
    WaybillDataError,
    WaybillSpec,
    interchange_card,
    norm,
    normalize_spec,
    outbound_empty_return,
    spot_waybill,
)

class SpotGroup(TypedDict):
    """Spots of one industry that share a usage and a car-type list, as load_spot_groups merges them."""

    Industry: str
    Usage: str
    CarTypes: tuple[str, ...]
    Spots: str  # the spot numbers as format_spots writes them


class DeckSummaryRow(TypedDict):
    """One industry's line of the deck report: its card count and the values its cards use, joined."""

    industry: str
    cards: int
    kinds: str
    flows: str
    usages: str
    spots: str
    commodities: str
    car_types: str
    vias: str


def _is_layout_party(name: str) -> bool:
    n = norm(name)
    if not n:
        return False
    if n in _LAYOUT_PARTY_NAMES:
        return True
    if n.lower().startswith("ferrellgas"):
        return True
    return False



def build_interchange_deck(rows: Sequence[InterchangeCard]) -> list[DeckCard]:
    """The through cards, one per master interchange row, in row order. A row that names an island industry as
    its shipper or receiver is a spot waybill's move, not interchange, and stops the build."""
    deck: list[DeckCard] = []
    for row in rows:
        for end in (row.route_from, row.route_to):
            if _is_layout_party(end):
                raise WaybillDataError(f"interchange card {row.card_id} names the island industry {end!r}: "
                                       "its move belongs on a spot waybill")
        deck.append(interchange_card(row))
    return deck


def parse_spot_num(raw: str) -> int:
    return int(re.sub(r"\D", "", raw) or "0")


def normalize_car_type(raw: str) -> str:
    name = norm(raw)
    lower = name.lower()
    if lower in {"loaded hopper", "empty hopper", "coal hopper"}:
        return "Hopper"
    if "hopper" in lower and any(k in lower for k in ("loaded", "empty", "coal")):
        return "Hopper"
    return name


def parse_car_types(raw: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(";"):
        normalized = normalize_car_type(part)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return tuple(out)


def format_spots(nums: list[int]) -> str:
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


# (industry, usage) pairs already warned about, so a spot is named once per run.
_WARNED_USAGES: set[tuple[str, str]] = set()


def _commodity_from_usage(usage: str, industry: str = "") -> str:
    """The load a spot usage names, from a keyword in it.

    With no keyword the usage text itself is the load, and a warning names the spot: give such
    a spot its own rows in waybill_loads.csv and waybill_parties.csv to set a real load.
    """
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
    if (industry, usage) in _WARNED_USAGES:
        return usage
    _WARNED_USAGES.add((industry, usage))
    print(
        f"waybill: spot usage {usage!r} at {industry or 'an industry'} names no known load; "
        "the cards show the usage as the load (add it to waybill_loads.csv)",
        file=sys.stderr,
    )
    return usage


def waybill_spec(industry: str, usage: str) -> WaybillSpec:
    """The table entry for a spot, else a generic one built from the usage text."""
    spec = spot_waybill().get((industry, usage))
    if spec:
        return spec
    where = f"default spec for ({industry!r}, {usage!r})"
    u = usage.lower()
    if "unload" in u:
        return normalize_spec({
            "inbound_load": _commodity_from_usage(usage, industry),
            "outbound_load": EMPTY,
            "suppliers": ["Various suppliers"],
            "customers": [],
        }, where)
    if "load" in u or "shipping" in u:
        return normalize_spec({
            "inbound_load": EMPTY,
            "outbound_load": _commodity_from_usage(usage, industry),
            "suppliers": [],
            "customers": [{"name": "Various customers", "via": "CSX"}],
        }, where)
    return normalize_spec({
        "inbound_load": "General Freight",
        "outbound_load": "General Freight",
        "suppliers": ["Various local shippers"],
        "customers": [
            {"name": "Various local receivers", "via": "CSX"},
        ],
    }, where)


def inbound_commodity_label(spec: WaybillSpec) -> str:
    """Summary label for operator reference (uses inbound_load, not per-card names)."""
    load = spec["inbound_load"]
    if load == EMPTY:
        return "Empty cars"
    return load


def _apply_load_summary(card: DeckCard, summary_load: str) -> None:
    """Set LoadSummary to the spot's documented load when the card's own commodity differs from it."""
    if card.get("LoadSummary"):
        return
    commodity = card.get("Commodity", "")
    if not commodity or commodity == EMPTY:
        return
    if summary_load and summary_load != EMPTY and commodity != summary_load:
        card["LoadSummary"] = summary_load


def party_pool(flow: str, load: str, spec: WaybillSpec) -> list[Party]:
    """Copies of the parties a direction's cards are spread over: customers route an inbound empty."""
    if load == EMPTY and flow == "IN":
        return [Party(**p) for p in spec["customers"]]
    if load == EMPTY:
        return []
    if flow == "IN":
        return [Party(**p) for p in spec["suppliers"]]
    return [Party(**p) for p in spec["customers"]]


def spread_parties(pool: list[Party], count: int) -> list[Party]:
    """Assign one party per card, shuffled and spread when pool is smaller."""
    blank: Party = {"name": "", "via": "", "entry": "", "commodity": ""}
    if not pool or count <= 0:
        return [blank] * max(count, 0)
    if len(pool) >= count:
        picked = pool.copy()
        random.shuffle(picked)
        return picked[:count]
    shuffled = pool.copy()
    random.shuffle(shuffled)
    out: list[Party] = []
    while len(out) < count:
        if out and len(out) % len(shuffled) == 0:
            random.shuffle(shuffled)
        out.append(shuffled[len(out) % len(shuffled)])
    return out


def apply_route(
    card: DeckCard, flow: str, load: str, party: Party, industry: str = ""
) -> None:
    if card.get("CardKind") == "interchange":
        return

    name = party["name"]
    via = party["via"]

    if load == EMPTY:
        if flow == "IN" and card.get("Spots"):
            card["RouteFrom"] = ""
            card["RouteTo"] = ""
            entry = party["entry"]
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
        card["RouteChain"] = "POHC" if party["entry"] == "POHC" else "CSX"
    else:
        card["RouteFrom"] = ""
        card["RouteTo"] = name
        card["RouteChain"] = "POHC" if via in ("NS", "POHC") else "CSX"



def _spots_from_label(label: str) -> set[int]:
    nums: set[int] = set()
    label = norm(label)
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


def _industry_spot_counts(groups: Sequence[SpotGroup]) -> dict[str, int]:
    """Unique active car spots per industry (groups already omit off spot / storage)."""
    by_industry: dict[str, set[int]] = defaultdict(set)
    for group in groups:
        by_industry[group["Industry"]].update(_spots_from_label(group["Spots"]))
    return {
        industry: len(spots)
        for industry, spots in by_industry.items()
        if spots
    }


def _industry_inbound_empty_spots(groups: Sequence[SpotGroup]) -> dict[str, set[int]]:
    """Spots that receive dedicated inbound EMPTY cards (load tracks)."""
    by_industry: dict[str, set[int]] = defaultdict(set)
    for group in groups:
        spec = waybill_spec(group["Industry"], group["Usage"])
        if spec["inbound_load"] == EMPTY:
            by_industry[group["Industry"]].update(_spots_from_label(group["Spots"]))
    return dict(by_industry)


def industry_outbound_empty_counts(groups: Sequence[SpotGroup]) -> dict[str, int]:
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


def build_industry_empty_cards(groups: Sequence[SpotGroup]) -> list[DeckCard]:
    """One generic outbound EMPTY per spot not covered by an inbound-empty load track."""
    counts = industry_outbound_empty_counts(groups)
    returns = outbound_empty_return()
    cards: list[DeckCard] = []
    for industry in sorted(counts, key=lambda name: INDUSTRY_ORDER.get(name, 99)):
        routing = returns.get(industry)
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
                    "RouteTo": routing.route_to if routing else "",
                    "RouteChain": routing.via if routing else "",
                }
            )
    return cards


def _pad_designs(designs: list[DeckCard], count: int = CARDS_PER_DIRECTION) -> list[DeckCard]:
    n = len(designs)
    if n == 1:
        return [deepcopy(designs[0]) for _ in range(count)]
    if n >= count:
        return [deepcopy(d) for d in designs[:count]]
    return [deepcopy(designs[i % n]) for i in range(count)]


def build_waybill_records(groups: Sequence[SpotGroup]) -> tuple[list[DeckCard], list[SpotGroupKey]]:
    """IN + OUT waybill per car type for each spot group."""
    records: list[DeckCard] = []
    group_order: list[SpotGroupKey] = []

    for group in groups:
        spec = waybill_spec(group["Industry"], group["Usage"])
        group_key: SpotGroupKey = (group["Industry"], group["Spots"], group["Usage"])
        if group_key not in group_order:
            group_order.append(group_key)

        directions = (
            ("IN", spec["inbound_load"]),
            ("OUT", spec["outbound_load"]),
        )

        for flow, load in directions:
            if load == EMPTY and flow != "IN":
                continue
            pool = party_pool(flow, load, spec)
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


def _design(record: DeckCard) -> DeckCard:
    """A copy of a design without the build keys, its other keys in the same order."""
    design = DeckCard(**record)
    design.pop("GroupKey", None)
    design.pop("DirectionKey", None)
    design.pop("PartyPool", None)
    return design


def expand_copies(waybills: list[DeckCard], group_order: list[SpotGroupKey]) -> list[DeckCard]:
    """Loaded and inbound empty: three per direction."""
    by_direction: dict[FlowKey, list[DeckCard]] = defaultdict(list)
    for record in waybills:
        by_direction[record["DirectionKey"]].append(record)

    deck: list[DeckCard] = []
    for group_key in group_order:
        for flow in ("IN", "OUT"):
            direction_key: FlowKey = (group_key, flow)
            designs = [_design(r) for r in by_direction[direction_key]]
            if not designs:
                continue

            load = designs[0]["Commodity"]
            if load == EMPTY:
                copy_count = CARDS_PER_DIRECTION
                spec = waybill_spec(group_key[0], group_key[2])
                pool = party_pool("IN", EMPTY, spec)
            else:
                pool = by_direction[direction_key][0].get("PartyPool", [])
                # One shipment per supplier/customer — do not duplicate routes when
                # CARDS_PER_DIRECTION exceeds the party pool (e.g. Ferrel Gas LPG).
                copy_count = CARDS_PER_DIRECTION
                if pool:
                    copy_count = min(CARDS_PER_DIRECTION, max(len(pool), len(designs)))
            padded = _pad_designs(designs, copy_count)
            parties = spread_parties(pool, len(padded))
            spec = waybill_spec(group_key[0], group_key[2])
            summary_load = (
                spec["inbound_load"] if flow == "IN" else spec["outbound_load"]
            )

            for card, party in zip(padded, parties):
                card["Usage"] = group_key[2]
                if load == EMPTY:
                    card["CardKind"] = "inbound_empty"
                elif party["commodity"]:
                    card["Commodity"] = party["commodity"]
                _apply_load_summary(card, summary_load)
                apply_route(card, flow, load, party, group_key[0])
                deck.append(card)
    return deck


def card_kind(card: DeckCard) -> str:
    kind = card.get("CardKind")
    if kind in ("interchange", "outbound_empty", "inbound_empty"):
        return kind
    if card.get("Commodity") == EMPTY:
        if card.get("Spots"):
            return "inbound_empty"
        return "outbound_empty"
    return "loaded"


def _deck_sort_key(card: DeckCard) -> tuple[int, int, str, int, int, int, str, str, str]:
    industry = card.get("Industry", "")
    kind = card_kind(card)
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


def sort_deck_by_industry(deck: list[DeckCard]) -> list[DeckCard]:
    """Order cards by industry, then kind, spot, flow, usage."""
    return sorted(deck, key=_deck_sort_key)


def _card_to_csv_row(card: DeckCard, card_id: int) -> dict[str, str]:
    return {
        "card_id": str(card_id),
        "industry": card.get("Industry", ""),
        "card_kind": card_kind(card),
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


def export_waybill_csv(deck: list[DeckCard], path: Path) -> None:
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


def summarize_deck(deck: list[DeckCard]) -> list[DeckSummaryRow]:
    """Aggregate card attributes per industry for reporting."""
    by_industry: dict[str, list[DeckCard]] = defaultdict(list)
    for card in deck:
        by_industry[card.get("Industry", "")].append(card)

    rows: list[DeckSummaryRow] = []
    industries = sorted(
        by_industry,
        key=lambda name: (INDUSTRY_ORDER.get(name, 99), name),
    )
    for industry in industries:
        cards = by_industry[industry]
        kinds = sorted({card_kind(c) for c in cards})
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
