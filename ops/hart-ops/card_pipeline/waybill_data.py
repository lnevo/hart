"""Waybill data for generate_waybill_cards.py: the card types, and the rules and through cards read from the data files.

The rules are kept in ops/hart-ops/data/ and read through hartlib.waybills: waybill_loads.csv and waybill_parties.csv
(each spot usage's loads, suppliers and customers), waybill_empty_returns.csv (where each industry's outbound empties
go) and the interchange rows of the card master HART_Spot_Waybills.csv (see wiki/pipelines/waybills.md). The deck
logic is in waybill_deck.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import TypedDict, cast

from card_errors import CardPipelineError
from card_template_records import WaybillCardRecord
import hartlib_path  # noqa: E402

hartlib_path.ensure_on_path()
from hartlib import operations, waybills  # noqa: E402
from hartlib.waybills import EmptyReturn, InterchangeCard  # noqa: E402

CARDS_PER_DIRECTION = 3
INTERCHANGE_PAGES = 2
EMPTY = "EMPTY"
PROCESS_CHEMICALS = "Process Chemicals"
GENERAL_FREIGHT = "General Freight"


class WaybillDataError(ValueError):
    """A waybill table entry or spot usage the deck cannot be built from."""


class WaybillRulesFileError(CardPipelineError, ValueError):
    """A waybill rule file or the card master cannot be read or names an industry the waybill decks do not have."""


class Party(TypedDict):
    """A supplier or customer on a waybill. Blank fields are unset."""

    name: str
    via: str  # the road a customer is reached by (CSX, NS, POHC)
    entry: str  # the road a supplier's load enters by (CSX, POHC)
    commodity: str  # the per-card load, when it differs from the spot's load


SpotGroupKey = tuple[str, str, str]  # (industry, spots, usage)
FlowKey = tuple[SpotGroupKey, str]  # (group, "IN" or "OUT")


class DeckCard(WaybillCardRecord, total=False):
    """A card of the waybill deck: the printed fields, plus the build keys build_waybill_records adds to a design.

    GroupKey, DirectionKey and PartyPool group the designs and carry their parties; expand_copies drops them before
    a card reaches the deck.
    """

    GroupKey: SpotGroupKey
    DirectionKey: FlowKey
    PartyPool: list[Party]


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
    inbound, outbound = raw["inbound_load"], raw["outbound_load"]
    if not (isinstance(inbound, str) and inbound and isinstance(outbound, str) and outbound):
        raise WaybillDataError(f"{where}: inbound_load and outbound_load must be non-blank text")
    suppliers, customers = raw["suppliers"], raw["customers"]
    if not (isinstance(suppliers, list | tuple) and isinstance(customers, list | tuple)):
        raise WaybillDataError(f"{where}: suppliers and customers must be lists")
    return {
        "inbound_load": inbound,
        "outbound_load": outbound,
        "suppliers": [normalize_party(p) for p in suppliers],
        "customers": [normalize_party(p) for p in customers],
    }


SKIP_USAGES = frozenset({"off spot", "storage"})

_INDUSTRY_SHEET = operations.read_industry_sheet()

# The waybill decks' industries in their order: industry_sheet.csv's waybill_order (hartlib.operations).
INDUSTRY_ORDER: dict[str, int] = dict(sorted(
    ((r.sheet_name, r.waybill_order) for r in _INDUSTRY_SHEET if r.waybill_order is not None),
    key=lambda pair: pair[1]))

# industry_id -> the name the decks key an industry by (spot_assignments.csv's Industry spelling)
_DECK_NAME: dict[str, str] = {r.industry_id: r.sheet_name for r in _INDUSTRY_SHEET if r.waybill_order is not None}


def _deck_name(industry_id: str, where: str) -> str:
    name = _DECK_NAME.get(industry_id)
    if name is None:
        raise WaybillRulesFileError(f"{where}: industry {industry_id!r} has no waybill_order in industry_sheet.csv")
    return name


def _party(p: waybills.RuleParty) -> Party:
    return {"name": p.name, "via": p.via, "entry": p.entry, "commodity": p.commodity}


@cache
def spot_waybill() -> dict[tuple[str, str], WaybillSpec]:
    """Per (industry, usage): the loads and the named suppliers and customers of waybill_loads.csv and
    waybill_parties.csv. Unload spots: loaded in, empty out. Load and shipping spots: empty in, loaded out."""
    try:
        rules = waybills.read_spot_rules()
    except waybills.WaybillRulesError as exc:
        raise WaybillRulesFileError(str(exc)) from exc
    return {
        (_deck_name(rule.industry_id, waybills.WAYBILL_LOADS.name), rule.usage): {
            "inbound_load": rule.inbound_load,
            "outbound_load": rule.outbound_load,
            "suppliers": [_party(p) for p in rule.suppliers],
            "customers": [_party(p) for p in rule.customers],
        }
        for rule in rules.values()
    }


@cache
def outbound_empty_return() -> dict[str, EmptyReturn]:
    """Per industry (its deck name): the yard and road its outbound empties return by (waybill_empty_returns.csv)."""
    try:
        returns = waybills.read_empty_returns()
    except waybills.WaybillRulesError as exc:
        raise WaybillRulesFileError(str(exc)) from exc
    return {_deck_name(i, waybills.WAYBILL_EMPTY_RETURNS.name): r for i, r in returns.items()}


def interchange_rows(master: Path = waybills.SPOT_WAYBILLS) -> list[InterchangeCard]:
    """The through cards of the card master HART_Spot_Waybills.csv (traffic interchange), in card_id order."""
    try:
        return waybills.read_interchange(master)
    except waybills.WaybillRulesError as exc:
        raise WaybillRulesFileError(str(exc)) from exc


INTERCHANGE_HEADER = "INTERCHANGE"

# Names tied to on-layout industries (exact or operational alias). Interchange cards carry through traffic only:
# a card that names one of these as RouteFrom or RouteTo is a spot waybill's move, not an interchange card.
_LAYOUT_PARTY_NAMES = frozenset(
    {
        *INDUSTRY_ORDER.keys(),
        "Ferrellgas Co (Taneytown, MD)",
        "Ferrellgas pipeline terminal",
    }
)


def interchange_card(row: InterchangeCard) -> DeckCard:
    """The deck card of a master interchange row. LoadSummary is set only where the row has one."""
    card = {
        "Industry": INTERCHANGE_HEADER,
        "CardKind": "interchange",
        "Spots": "—",
        "Commodity": row.commodity,
        "CarType": row.car_type,
        "RouteFrom": row.route_from,
        "RouteTo": row.route_to,
        "RouteChain": row.via,
    }
    if row.load_summary:
        card["LoadSummary"] = row.load_summary
    return cast(DeckCard, card)
