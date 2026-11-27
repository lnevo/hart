"""The spot waybill rules and the interchange cards, read: the inputs of the waybill deck (ops/hart-ops/card_pipeline).

    from hartlib import waybills
    rules = waybills.read_spot_rules()          # {(industry_id, usage): SpotRule}: loads, suppliers, customers
    rules["calgon", "Coal Unload"].suppliers    # (RuleParty(name=..., via=..., entry=..., commodity=...), ...)
    waybills.read_empty_returns()["kosmos"]     # EmptyReturn: the yard and road an outbound empty goes home by
    waybills.read_interchange()                 # [InterchangeCard, ...]: the through cards, in card_id order

Four files in ops/hart-ops/data/, each with its column sidecar (docs/data/sidecars.md):

- waybill_loads.csv: one row per spot usage that has waybills, keyed by industry_id and usage (spot_assignments.csv's
  Usage). inbound_load and outbound_load are the loads the cards carry each way; EMPTY on the empty side.
- waybill_parties.csv: the suppliers and customers of each such usage, keyed by industry_id, usage, role (supplier or
  customer) and party (1, 2, ... within the usage and role). The party number is the order the deck draws from, so a
  deck with the random module seeded the same comes out the same. `via` is the road a customer is reached by (CSX, NS,
  POHC), `entry` the road a supplier's load enters by (CSX, POHC), `commodity` the per-card load where it differs from
  the usage's load.
- waybill_empty_returns.csv: per industry_id, the yard (`route_to`) and road (`via`) its outbound empty cards return
  by.
- HART_Spot_Waybills.csv, the waybill card master: its interchange rows (traffic interchange) are the through cards
  themselves, with `interchange_flow` the side (IN or OUT) of the deck's routing balance each counts on.

Each reader checks its file's shape and stops with WaybillRulesError, naming the file and line: a missing file or
column, an empty or malformed key, a key given twice, a value outside its list, a party whose usage has no load row,
and party numbers that are not 1 to n.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal, NamedTuple, cast

from . import paths
from .errors import HartlibError, FactsError

HART_OPS_DATA = paths.REPO_ROOT / "ops" / "hart-ops" / "data"
SPOT_WAYBILLS = HART_OPS_DATA / "HART_Spot_Waybills.csv"
WAYBILL_LOADS = HART_OPS_DATA / "waybill_loads.csv"
WAYBILL_PARTIES = HART_OPS_DATA / "waybill_parties.csv"
WAYBILL_EMPTY_RETURNS = HART_OPS_DATA / "waybill_empty_returns.csv"

Role = Literal["supplier", "customer"]
Flow = Literal["IN", "OUT"]
ROLES: tuple[Role, ...] = ("supplier", "customer")
FLOWS: tuple[Flow, ...] = ("IN", "OUT")
CUSTOMER_ROADS = ("CSX", "NS", "POHC")   # a customer's via
ENTRY_ROADS = ("CSX", "POHC")            # a supplier's entry, an empty's return road, an interchange card's via

LOAD_COLUMNS = ["industry_id", "usage", "inbound_load", "outbound_load"]
PARTY_COLUMNS = ["industry_id", "usage", "role", "party", "name", "via", "entry", "commodity"]
RETURN_COLUMNS = ["industry_id", "route_to", "via"]
INTERCHANGE_COLUMNS = ["card_id", "traffic", "card_kind", "interchange_flow", "commodity", "load_summary",
                       "car_type", "route_from", "route_to", "via"]

SpotKey = tuple[str, str]   # (industry_id, usage)


class WaybillRulesError(HartlibError, ValueError):
    """A waybill rule file or the card master cannot be read or is not in its shape; the message names the file and
    the line."""


class RuleParty(NamedTuple):
    """A supplier or customer of a spot usage. Blank fields are unset."""
    name: str
    via: str
    entry: str
    commodity: str


class SpotRule(NamedTuple):
    """The waybill rule of one industry's spot usage: its loads, and its parties in party order."""
    industry_id: str
    usage: str
    inbound_load: str
    outbound_load: str
    suppliers: tuple[RuleParty, ...]
    customers: tuple[RuleParty, ...]


class EmptyReturn(NamedTuple):
    """Where an industry's outbound empty cards send the car: the yard and the road."""
    industry_id: str
    route_to: str
    via: str


class InterchangeCard(NamedTuple):
    """One through card of the card master (traffic interchange)."""
    card_id: int
    flow: Flow           # the side of the routing balance it counts on
    commodity: str
    load_summary: str    # the group the card's lower table prints, or ""
    car_type: str
    route_from: str
    route_to: str
    via: str


def _rows(path: Path, required: list[str]) -> list[tuple[int, dict[str, str]]]:
    from .railroad_facts import read_rows   # here, so importing this module loads no layout modules
    try:
        return read_rows(path, required)
    except FactsError as exc:
        raise WaybillRulesError(str(exc)) from exc


def _need(path: Path, line: int, row: dict[str, str], cols: list[str]) -> None:
    empty = [c for c in cols if not row[c]]
    if empty:
        raise WaybillRulesError(f"{path}:{line}: {', '.join(empty)} must not be empty")


def _one_of(path: Path, line: int, col: str, value: str, allowed: tuple[str, ...], blank_ok: bool = False) -> None:
    if (blank_ok and not value) or value in allowed:
        return
    raise WaybillRulesError(f"{path}:{line}: {col} {value!r} is not one of {', '.join(allowed)}")


def _whole(path: Path, line: int, col: str, value: str) -> int:
    if not value.isdigit() or not value.isascii() or int(value) < 1:
        raise WaybillRulesError(f"{path}:{line}: {col} {value!r} is not a whole number from 1")
    return int(value)


def read_loads(path: Path = WAYBILL_LOADS) -> dict[SpotKey, tuple[str, str]]:
    """{(industry_id, usage): (inbound_load, outbound_load)} of waybill_loads.csv, in file order."""
    out: dict[SpotKey, tuple[str, str]] = {}
    for line, row in _rows(path, LOAD_COLUMNS):
        _need(path, line, row, LOAD_COLUMNS)
        key = (row["industry_id"], row["usage"])
        if key in out:
            raise WaybillRulesError(f"{path}:{line}: {key[0]} {key[1]!r} is listed twice")
        out[key] = (row["inbound_load"], row["outbound_load"])
    return out


def read_spot_rules(loads: Path = WAYBILL_LOADS, parties: Path = WAYBILL_PARTIES) -> dict[SpotKey, SpotRule]:
    """{(industry_id, usage): SpotRule} of waybill_loads.csv, in its order, with the parties of waybill_parties.csv
    in party order."""
    load_rows = read_loads(loads)
    numbered: dict[tuple[str, str, Role], dict[int, RuleParty]] = defaultdict(dict)
    for line, row in _rows(parties, PARTY_COLUMNS):
        _need(parties, line, row, ["industry_id", "usage", "role", "party", "name"])
        spot: SpotKey = (row["industry_id"], row["usage"])
        if spot not in load_rows:
            raise WaybillRulesError(f"{parties}:{line}: {spot[0]} {spot[1]!r} has no row in {loads.name}")
        _one_of(parties, line, "role", row["role"], ROLES)
        role = cast(Role, row["role"])
        number = _whole(parties, line, "party", row["party"])
        _one_of(parties, line, "via", row["via"], CUSTOMER_ROADS, blank_ok=True)
        _one_of(parties, line, "entry", row["entry"], ENTRY_ROADS, blank_ok=True)
        group = numbered[(spot[0], spot[1], role)]
        if number in group:
            raise WaybillRulesError(f"{parties}:{line}: {spot[0]} {spot[1]!r} {role} {number} is listed twice")
        group[number] = RuleParty(row["name"], row["via"], row["entry"], row["commodity"])
    for (industry_id, usage, role), group in numbered.items():
        if sorted(group) != list(range(1, len(group) + 1)):
            raise WaybillRulesError(f"{parties}: {industry_id} {usage!r} {role} parties are numbered "
                                    f"{sorted(group)}, not 1 to {len(group)}")

    def ordered(spot: SpotKey, role: Role) -> tuple[RuleParty, ...]:
        group = numbered.get((spot[0], spot[1], role), {})
        return tuple(group[n] for n in sorted(group))

    return {spot: SpotRule(spot[0], spot[1], inbound, outbound, ordered(spot, "supplier"), ordered(spot, "customer"))
            for spot, (inbound, outbound) in load_rows.items()}


def read_empty_returns(path: Path = WAYBILL_EMPTY_RETURNS) -> dict[str, EmptyReturn]:
    """{industry_id: EmptyReturn} of waybill_empty_returns.csv, in file order."""
    out: dict[str, EmptyReturn] = {}
    for line, row in _rows(path, RETURN_COLUMNS):
        _need(path, line, row, RETURN_COLUMNS)
        _one_of(path, line, "via", row["via"], ENTRY_ROADS)
        if row["industry_id"] in out:
            raise WaybillRulesError(f"{path}:{line}: {row['industry_id']} is listed twice")
        out[row["industry_id"]] = EmptyReturn(row["industry_id"], row["route_to"], row["via"])
    return out


def read_interchange(path: Path = SPOT_WAYBILLS) -> list[InterchangeCard]:
    """The interchange rows of the card master as InterchangeCards, in card_id order. Every row's card_id is checked
    (a whole number, given once); an interchange row must be card_kind interchange and have every field but
    load_summary."""
    seen: set[int] = set()
    out: list[InterchangeCard] = []
    for line, row in _rows(path, INTERCHANGE_COLUMNS):
        card_id = _whole(path, line, "card_id", row["card_id"])
        if card_id in seen:
            raise WaybillRulesError(f"{path}:{line}: card_id {card_id} is listed twice")
        seen.add(card_id)
        if row["traffic"] != "interchange":
            if row["interchange_flow"]:
                raise WaybillRulesError(f"{path}:{line}: interchange_flow is for interchange traffic only")
            continue
        if row["card_kind"] != "interchange":
            raise WaybillRulesError(f"{path}:{line}: interchange traffic with card_kind {row['card_kind']!r}")
        _need(path, line, row, ["interchange_flow", "commodity", "car_type", "route_from", "route_to", "via"])
        _one_of(path, line, "interchange_flow", row["interchange_flow"], FLOWS)
        _one_of(path, line, "via", row["via"], ENTRY_ROADS)
        out.append(InterchangeCard(card_id, cast(Flow, row["interchange_flow"]), row["commodity"],
                                   row["load_summary"], row["car_type"], row["route_from"], row["route_to"],
                                   row["via"]))
    return sorted(out, key=lambda card: card.card_id)
