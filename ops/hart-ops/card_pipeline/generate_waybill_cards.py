#!/usr/bin/env python3
"""Generate HART spot waybill cards from spot_assignments.csv.

CSV columns: industry_id, Industry, Spot #, Usage, Cars Applicable (industry_id names a row of
industries.csv; Industry is the name printed on the card)

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
import importlib.util
import os
import shutil
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from docx import Document

_HERE = Path(__file__).resolve().parent


def _load_sibling(name: str):
    """Import card_pipeline/<name>.py from this checkout, never a same-named module elsewhere."""
    path = _HERE / f"{name}.py"
    loaded = sys.modules.get(name)
    if loaded is not None:
        if Path(loaded.__file__).resolve() != path:
            raise ImportError(f"{name} is already imported from {loaded.__file__}, expected {path}")
        return loaded
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


# Order matters: each sibling imports the ones before it by name.
g = _load_sibling("generate_card_template")
_load_sibling("waybill_data")
_load_sibling("waybill_deck")
_load_sibling("waybill_sheet")

BASE = g.BASE
DATA = g.DATA
OUTPUT_DIR = g.OUTPUT_DIR
SPOT_CSV = DATA / "spot_assignments.csv"
OUTPUT = OUTPUT_DIR / "HART_Spot_Waybills.docx"
WAYBILL_CSV = DATA / "HART_Spot_Waybills.csv"

# Re-exported so generate_operator_sheet.py, the tests and older callers keep reading them
# here. The moved functions read these from their own module (waybill_data, waybill_deck,
# waybill_sheet), so patching one of these names on this module does not reach them; only
# BASE, OUTPUT_DIR, OUTPUT, WAYBILL_CSV and SPOT_CSV above are read from this module.
from waybill_data import (  # noqa: E402, F401
    _INTERCHANGE_CSX_TO_NS,
    _INTERCHANGE_IN_VIA_CSX,
    _INTERCHANGE_IN_VIA_POHC,
    _INTERCHANGE_NS_TO_CSX,
    _INTERCHANGE_OUT_VIA_CSX,
    _INTERCHANGE_OUT_VIA_POHC,
    _LAYOUT_PARTY_NAMES,
    _PROCESS_CHEMICAL_DETAILS,
    _ix_card,
    CARDS_PER_DIRECTION,
    EMPTY,
    GE_BRIDGEVILLE,
    GENERAL_FREIGHT,
    INDUSTRY_ORDER,
    INTERCHANGE_HEADER,
    INTERCHANGE_PAGES,
    OUTBOUND_EMPTY_RETURN,
    PROCESS_CHEMICALS,
    SKIP_USAGES,
    SPOT_WAYBILL,
    STANDARD_FORGED,
    UNIVERSAL_STAINLESS,
)
from waybill_deck import (  # noqa: E402, F401
    _apply_load_summary,
    _apply_route,
    _card_kind,
    _card_to_csv_row,
    _commodity_from_usage,
    _deck_sort_key,
    _format_spots,
    _industry_inbound_empty_spots,
    _industry_outbound_empty_counts,
    _industry_spot_counts,
    _is_layout_party,
    _norm,
    _normalize_party,
    _pad_designs,
    _parse_car_types,
    _parse_spot_num,
    _party_pool,
    _spot_count,
    _spots_from_label,
    _spread_parties,
    _summarize_deck,
    _waybill_spec,
    build_industry_empty_cards,
    build_interchange_deck,
    build_waybill_records,
    expand_copies,
    export_waybill_csv,
    inbound_commodity_label,
    normalize_car_type,
    sort_deck_by_industry,
)
from waybill_sheet import (  # noqa: E402, F401
    CARDS_PER_PAGE,
    _append_grid,
    _fill_deck_to_page,
    _fill_page,
    _set_page_break_before_table,
)


def load_spot_groups() -> list[dict]:
    """Load CSV rows and merge spots with identical industry/usage/car lists."""
    if not SPOT_CSV.exists():
        raise FileNotFoundError(SPOT_CSV)

    groups: dict[tuple, dict] = {}
    with SPOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            industry_id = _norm(row.get("industry_id"))
            industry = _norm(row.get("Industry"))
            usage = _norm(row.get("Usage"))
            if not industry_id or not industry or not usage:
                continue
            if usage.lower() in SKIP_USAGES:
                continue

            spot = _parse_spot_num(row.get("Spot #", ""))
            car_types = _parse_car_types(row.get("Cars Applicable", ""))
            if not spot or not car_types:
                continue

            key = (industry_id, industry, usage, car_types)
            if key not in groups:
                groups[key] = {
                    "IndustryId": industry_id,
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



def _blank_sticker_grid():
    scratch_path = BASE / ".scratch_waybill.docx"
    shutil.copy2(g.STICKER_SHEET, scratch_path)
    scratch = Document(scratch_path)
    g.keep_sticker_grid(scratch)
    grid = deepcopy(scratch.tables[0]._tbl)
    scratch_path.unlink(missing_ok=True)
    return grid



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
