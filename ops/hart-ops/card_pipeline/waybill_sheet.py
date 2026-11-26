"""Sticker-sheet layout for generate_waybill_cards.py: page filling and grid copies.

The parts that read the entry module's patched paths (BASE for the scratch grid, OUTPUT for
the saved file) stay in generate_waybill_cards.py.
"""

from __future__ import annotations

import random
from copy import deepcopy

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table

# generate_waybill_cards loads generate_card_template, waybill_data and waybill_deck by path
# before this module, so these names resolve to the sibling files in this checkout.
import card_template_layout
import card_template_sheet
import generate_card_template as g
from waybill_data import EMPTY
from waybill_deck import _apply_route, _party_pool, _spread_parties, _waybill_spec

CARDS_PER_PAGE = len(card_template_layout.CARD_SLOTS)



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
    card_template_sheet.insert_before_sect(body, tbl)
    card_template_sheet.ensure_sect_pr_last(body)
    table = Table(body.findall(qn("w:tbl"))[-1], doc)
    card_template_sheet.strip_grid_guides(table)
    return table



def _fill_page(sheet: Table, batch: list[dict], page_idx: int) -> None:
    for i, record in enumerate(batch):
        r, c = card_template_layout.CARD_SLOTS[i]
        g.build_waybill_card(
            sheet.rows[r].cells[c],
            idx=page_idx * CARDS_PER_PAGE + i,
            record=record,
        )
