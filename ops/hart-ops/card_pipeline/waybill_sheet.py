"""Page filling for generate_waybill_cards.py: the cards that make the last sticker page full.

The sheet itself is written by card_template_sheet.write_sticker_deck from generate_waybill_cards.py, which reads
the patched OUTPUT path.
"""

from __future__ import annotations

import random
from copy import deepcopy

# generate_waybill_cards loads card_template_sheet, waybill_data and waybill_deck by path
# before this module, so these names resolve to the sibling files in this checkout.
from card_template_sheet import CARDS_PER_PAGE
from waybill_data import EMPTY
from waybill_deck import apply_route, party_pool, spread_parties, waybill_spec


def fill_deck_to_page(deck: list[dict]) -> list[dict]:
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
            spec = waybill_spec(card["Industry"], card.get("Usage", ""))
            pool = party_pool(card["Flow"], card["Commodity"], spec)
            apply_route(
                card,
                card["Flow"],
                card["Commodity"],
                spread_parties(pool, 1)[0] if pool else {},
                card["Industry"],
            )
        deck.append(card)
    return deck

