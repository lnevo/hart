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
  - The interchange cards are the interchange rows of HART_Spot_Waybills.csv
    (through traffic). Header reads INTERCHANGE — not individual industry names.

The loads, parties and empty returns come from waybill_loads.csv, waybill_parties.csv
and waybill_empty_returns.csv (waybill_data.py, through hartlib.waybills).
"""


from __future__ import annotations

import csv
import importlib.util
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Literal, NamedTuple

from docx.table import _Cell

from card_errors import CardPipelineError

if TYPE_CHECKING:
    from waybill_data import DeckCard, FlowKey, InterchangeCard, Party, SpotGroupKey as GroupKey
    from waybill_deck import SpotGroup

_HERE = Path(__file__).resolve().parent


def _load_sibling(name: str) -> ModuleType:
    """Import card_pipeline/<name>.py from this checkout, never a same-named module elsewhere."""
    path = _HERE / f"{name}.py"
    loaded = sys.modules.get(name)
    if loaded is not None:
        if loaded.__file__ is None or Path(loaded.__file__).resolve() != path:
            raise ImportError(f"{name} is already imported from {loaded.__file__}, expected {path}")
        return loaded
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


# Order matters: each sibling imports the ones before it by name.
car_paths = _load_sibling("car_paths")
card_template_layout = _load_sibling("card_template_layout")
card_template_sheet = _load_sibling("card_template_sheet")
g = _load_sibling("generate_card_template")
wdata = _load_sibling("waybill_data")
wdeck = _load_sibling("waybill_deck")
wsheet = _load_sibling("waybill_sheet")

BASE = car_paths.ROOT
DATA = car_paths.DATA
OUTPUT_DIR = car_paths.OUTPUT_DIR
SPOT_CSV = DATA / "spot_assignments.csv"
OUTPUT = OUTPUT_DIR / "HART_Spot_Waybills.docx"
# the printed deck, one row per card; never the master HART_Spot_Waybills.csv, which the deck is read from:
# a run renumbers card_id from 1 and draws the parties, so writing the master would rewrite it
WAYBILL_CSV = OUTPUT_DIR / "HART_Spot_Waybills_deck.csv"


class SpotCsvMissingError(CardPipelineError, FileNotFoundError):
    """spot_assignments.csv is not where SPOT_CSV says."""



class WaybillDeck(NamedTuple):
    """The deck main() prints and writes, and the parts its report counts."""

    groups: list[SpotGroup]
    waybills: list[DeckCard]  # one design per car type and direction
    group_order: list[GroupKey]
    inbound_empty_count: int
    outbound_empties: list[DeckCard]
    interchange: list[DeckCard]
    interchange_rows: list[InterchangeCard]  # the master rows the interchange cards come from
    cards: list[DeckCard]  # every card in print order, before the page fillers


def load_spot_groups() -> list[SpotGroup]:
    """Load CSV rows and merge spots with identical industry/usage/car lists."""
    if not SPOT_CSV.exists():
        raise SpotCsvMissingError(f"Missing the spot list {SPOT_CSV}")

    spots_by_key: dict[tuple[str, str, tuple[str, ...]], list[int]] = {}
    with SPOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            industry = wdata.norm(row.get("Industry"))
            usage = wdata.norm(row.get("Usage"))
            if not industry or not usage:
                continue
            if usage.lower() in wdata.SKIP_USAGES:
                continue

            spot = wdeck.parse_spot_num(row.get("Spot #", ""))
            car_types = wdeck.parse_car_types(row.get("Cars Applicable", ""))
            if not spot or not car_types:
                continue
            spots_by_key.setdefault((industry, usage, car_types), []).append(spot)

    return [
        {"Industry": industry, "Usage": usage, "CarTypes": car_types, "Spots": wdeck.format_spots(spots)}
        for (industry, usage, car_types), spots in spots_by_key.items()
    ]


def build_deck(groups: list[SpotGroup]) -> WaybillDeck:
    """Every card for the spot groups, plus the interchange pages, in print order.

    The order of the steps fixes which random party each card gets, so it is kept.
    """
    waybills, group_order = wdeck.build_waybill_records(groups)
    copies = wdeck.expand_copies(waybills, group_order)
    inbound_empty_count = sum(1 for c in copies if wdeck.card_kind(c) == "inbound_empty")
    outbound_empties = wdeck.build_industry_empty_cards(groups)
    copies = wdeck.sort_deck_by_industry(copies)
    interchange_rows = wdata.interchange_rows()
    interchange = wdeck.build_interchange_deck(interchange_rows)
    cards = wdeck.sort_deck_by_industry(copies + interchange + outbound_empties)
    return WaybillDeck(groups, waybills, group_order, inbound_empty_count, outbound_empties, interchange,
                       interchange_rows, cards)


def _fill_slot(cell: _Cell, idx: int, record: DeckCard) -> None:
    g.build_waybill_card(cell, idx=idx, record=record)


def generate(deck: Sequence[DeckCard]) -> None:
    """Write the deck to OUTPUT, nine cards to a sticker page."""
    sticker_sheet = car_paths.require_sticker_sheet()
    card_template_sheet.write_sticker_deck(deck, _fill_slot, sticker_sheet=sticker_sheet, output=OUTPUT)


def route_text(flow: str, load: str, pool: Sequence[Party]) -> str:
    """The parties a direction's cards are spread over, as the report names them; blank with no pool."""
    if not pool:
        return ""
    key: Literal["via", "entry"]
    if load == wdata.EMPTY and flow == "IN":
        label, key = "via routing", "via"
    elif flow == "OUT":
        label, key = "customers", "via"
    else:
        label, key = "suppliers", "entry"
    names = [f"{p['name']} ({p[key]})" if p.get(key) else p["name"] for p in pool]
    return f"{label}: {', '.join(names)}"


def copies_note(load: str, designs: int) -> str:
    """How many cards a direction with ``designs`` designs prints, as the report says it."""
    if load == wdata.EMPTY or designs == 1:
        return f"{wdata.CARDS_PER_DIRECTION}×"
    if designs >= wdata.CARDS_PER_DIRECTION:
        return "1 each"
    return f"1 each + {wdata.CARDS_PER_DIRECTION - designs} extra"


def group_line(group_key: GroupKey, by_direction: Mapping[FlowKey, list[DeckCard]]) -> str:
    """One spot group's IN and OUT designs for the report; blank when it has none."""
    parts: list[str] = []
    for flow in ("IN", "OUT"):
        designs = by_direction.get((group_key, flow), [])
        if not designs:
            continue
        load = designs[0]["Commodity"]
        types = ", ".join(d["CarType"] for d in designs)
        line = f"{flow} {load} ({types}) {copies_note(load, len(designs))}"
        route_txt = route_text(flow, load, designs[0].get("PartyPool", []))
        if route_txt:
            line += f" · {route_txt}"
        parts.append(line)
    return " | ".join(parts)


def print_spot_groups(deck: WaybillDeck) -> None:
    """The outbound empties per industry and one line per spot group."""
    outbound_empty_counts = wdeck.industry_outbound_empty_counts(deck.groups)
    if outbound_empty_counts:
        empty_summary = ", ".join(
            f"{ind} ({outbound_empty_counts[ind]})"
            for ind in sorted(outbound_empty_counts, key=lambda n: wdata.INDUSTRY_ORDER.get(n, 99))
        )
        print(f"  outbound empties (industry): {empty_summary}")
    by_direction: dict[FlowKey, list[DeckCard]] = defaultdict(list)
    for record in deck.waybills:
        by_direction[record["DirectionKey"]].append(record)
    for group_key in deck.group_order:
        industry, spots, _usage = group_key
        line = group_line(group_key, by_direction)
        if line:
            print(f"    {industry} spot {spots}: {line}")


def print_routing(deck: WaybillDeck) -> None:
    """The interchange cards by road, and the loaded cards' IN and OUT balance between CSX and POHC."""
    via_csx = sum(1 for c in deck.interchange if c.get("RouteChain") == "CSX")
    via_pohc = sum(1 for c in deck.interchange if c.get("RouteChain") == "POHC")
    ix_pages = card_template_sheet.page_count(len(deck.interchange))
    print(f"  interchange: {via_csx} Via CSX · {via_pohc} Via POHC ({ix_pages} pages)")

    loaded = [c for c in deck.cards
              if c.get("Commodity") != wdata.EMPTY and c.get("RouteChain") in ("CSX", "POHC")]

    def spot_count(flow: str, road: str) -> int:
        return sum(1 for c in loaded if c.get("Flow") == flow and c["RouteChain"] == road)

    def interchange_count(flow: str, road: str) -> int:
        return sum(1 for r in deck.interchange_rows if r.flow == flow and r.via == road)

    in_csx, in_pohc = spot_count("IN", "CSX"), spot_count("IN", "POHC")
    out_csx, out_pohc = spot_count("OUT", "CSX"), spot_count("OUT", "POHC")
    tot_in_csx = in_csx + interchange_count("IN", "CSX")
    tot_in_pohc = in_pohc + interchange_count("IN", "POHC")
    tot_out_csx = out_csx + interchange_count("OUT", "CSX")
    tot_out_pohc = out_pohc + interchange_count("OUT", "POHC")
    print(
        f"  loaded routing balance — IN: CSX {tot_in_csx} · POHC {tot_in_pohc} | "
        f"OUT: CSX {tot_out_csx} · POHC {tot_out_pohc}"
    )
    print(f"    (spot only — IN: CSX {in_csx} · POHC {in_pohc} | OUT: CSX {out_csx} · POHC {out_pohc})")


def print_report(deck: WaybillDeck, printed: int) -> None:
    """What main() wrote: the counts, the spot groups, the routing and one line per industry."""
    filler_count = printed - len(deck.cards)
    loaded_card_count = sum(1 for c in deck.cards if wdeck.card_kind(c) == "loaded")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {WAYBILL_CSV}")
    print(
        f"  {len(deck.waybills)} loaded designs → {loaded_card_count} loaded cards · "
        f"{deck.inbound_empty_count} inbound empties · {len(deck.outbound_empties)} outbound empties · "
        f"{len(deck.interchange)} interchange · {filler_count} page fillers · "
        f"{printed} total · {card_template_sheet.page_count(printed)} pages"
    )
    print(f"  source: {SPOT_CSV.name}")
    print_spot_groups(deck)
    print_routing(deck)
    print("\n  Industry summary:")
    for row in wdeck.summarize_deck(deck.cards):
        print(f"    {row['industry']}: {row['cards']} cards · {row['kinds']} · flows {row['flows']} · vias {row['vias']}")


def main() -> None:
    deck = build_deck(load_spot_groups())
    wdeck.export_waybill_csv(deck.cards, WAYBILL_CSV)
    printed = wsheet.fill_deck_to_page(deck.cards.copy())
    print_report(deck, len(printed))
    generate(printed)


if __name__ == "__main__":
    try:
        main()
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
