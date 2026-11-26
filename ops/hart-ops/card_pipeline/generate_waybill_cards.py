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
import importlib.util
import os
import shutil
import sys
from collections import defaultdict
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
WAYBILL_CSV = DATA / "HART_Spot_Waybills.csv"

def load_spot_groups() -> list[dict]:
    """Load CSV rows and merge spots with identical industry/usage/car lists."""
    if not SPOT_CSV.exists():
        raise FileNotFoundError(SPOT_CSV)

    groups: dict[tuple, dict] = {}
    with SPOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            industry = wdata._norm(row.get("Industry"))
            usage = wdata._norm(row.get("Usage"))
            if not industry or not usage:
                continue
            if usage.lower() in wdata.SKIP_USAGES:
                continue

            spot = wdeck._parse_spot_num(row.get("Spot #", ""))
            car_types = wdeck._parse_car_types(row.get("Cars Applicable", ""))
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
        entry["Spots"] = wdeck._format_spots(entry["Spots"])
        merged.append(entry)
    return merged


def generate(deck: list[dict]) -> None:
    car_paths.require_sticker_sheet()

    blank_grid = card_template_sheet.blank_sticker_grid(car_paths.STICKER_SHEET)
    temp_path = OUTPUT.with_suffix(".tmp.docx")
    shutil.copy2(car_paths.STICKER_SHEET, temp_path)
    doc = Document(temp_path)
    card_template_sheet.keep_sticker_grid(doc)

    pages = [deck[i : i + wsheet.CARDS_PER_PAGE] for i in range(0, len(deck), wsheet.CARDS_PER_PAGE)]

    sheet = doc.tables[0]
    wsheet._fill_page(sheet, pages[0], 0)

    for page_idx, batch in enumerate(pages[1:], start=1):
        sheet = card_template_sheet.append_grid(doc, blank_grid)
        wsheet._fill_page(sheet, batch, page_idx)

    card_template_sheet.add_document_tail(doc.element.body)
    doc.save(temp_path)
    os.replace(temp_path, OUTPUT)


def main() -> None:
    groups = load_spot_groups()
    waybills, group_order = wdeck.build_waybill_records(groups)
    deck = wdeck.expand_copies(waybills, group_order)
    inbound_empty_count = sum(
        1 for c in deck if wdeck._card_kind(c) == "inbound_empty"
    )
    outbound_empties = wdeck.build_industry_empty_cards(groups)
    deck = wdeck.sort_deck_by_industry(deck)
    interchange = wdeck.build_interchange_deck()
    deck_with_ix = wdeck.sort_deck_by_industry(deck + interchange + outbound_empties)

    wdeck.export_waybill_csv(deck_with_ix, WAYBILL_CSV)
    summary = wdeck._summarize_deck(deck_with_ix)

    deck = wsheet._fill_deck_to_page(deck_with_ix.copy())
    filler_count = len(deck) - len(deck_with_ix)

    by_direction: dict[tuple, list[dict]] = defaultdict(list)
    for record in waybills:
        by_direction[record["DirectionKey"]].append(record)

    pages = (len(deck) + wsheet.CARDS_PER_PAGE - 1) // wsheet.CARDS_PER_PAGE
    loaded_card_count = sum(1 for c in deck_with_ix if wdeck._card_kind(c) == "loaded")
    print(f"Wrote {OUTPUT}")
    print(f"Wrote {WAYBILL_CSV}")
    print(
        f"  {len(waybills)} loaded designs → {loaded_card_count} loaded cards · "
        f"{inbound_empty_count} inbound empties · {len(outbound_empties)} outbound empties · "
        f"{len(interchange)} interchange · {filler_count} page fillers · "
        f"{len(deck)} total · {pages} pages"
    )
    print(f"  source: {SPOT_CSV.name}")
    outbound_empty_counts = wdeck._industry_outbound_empty_counts(groups)
    if outbound_empty_counts:
        empty_summary = ", ".join(
            f"{ind} ({outbound_empty_counts[ind]})"
            for ind in sorted(outbound_empty_counts, key=lambda n: wdata.INDUSTRY_ORDER.get(n, 99))
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
                if load == wdata.EMPTY and flow == "IN":
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
            if load == wdata.EMPTY:
                card_note = f"{wdata.CARDS_PER_DIRECTION}×"
            elif n == 1:
                card_note = f"{wdata.CARDS_PER_DIRECTION}×"
            elif n >= wdata.CARDS_PER_DIRECTION:
                card_note = "1 each"
            else:
                card_note = f"1 each + {wdata.CARDS_PER_DIRECTION - n} extra"
            line = f"{flow} {load} ({types}) {card_note}"
            if route_txt:
                line += f" · {route_txt}"
            parts.append(line)
        if parts:
            print(f"    {industry} spot {spots}: {' | '.join(parts)}")

    via_csx = sum(1 for c in interchange if c.get("RouteChain") == "CSX")
    via_pohc = sum(1 for c in interchange if c.get("RouteChain") == "POHC")
    ix_pages = (len(interchange) + wsheet.CARDS_PER_PAGE - 1) // wsheet.CARDS_PER_PAGE
    print(
        f"  interchange: {via_csx} Via CSX · {via_pohc} Via POHC "
        f"({ix_pages} pages)"
    )

    loaded = [
        c for c in deck_with_ix
        if c.get("Commodity") != wdata.EMPTY and c.get("RouteChain") in ("CSX", "POHC")
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
    tot_in_csx = in_csx + len(wdata.INTERCHANGE_IN_VIA_CSX) + len(wdata.INTERCHANGE_NS_TO_CSX)
    tot_in_pohc = in_pohc + len(wdata.INTERCHANGE_IN_VIA_POHC)
    tot_out_csx = out_csx + len(wdata.INTERCHANGE_OUT_VIA_CSX)
    tot_out_pohc = (
        out_pohc + len(wdata.INTERCHANGE_OUT_VIA_POHC) + len(wdata.INTERCHANGE_CSX_TO_NS)
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
    try:
        main()
    except car_paths.CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
