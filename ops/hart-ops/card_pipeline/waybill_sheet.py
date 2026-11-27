"""Page filling for generate_waybill_cards.py: the cards that make the last sticker page full.

The sheet itself is written by card_template_sheet.write_sticker_deck from generate_waybill_cards.py, which reads
the patched OUTPUT path.
"""

from __future__ import annotations

import random
from copy import deepcopy

# generate_waybill_cards loads card_template_sheet, waybill_data and waybill_deck by path
# before this module, so these names resolve to the sibling files in this checkout.
from card_errors import CardPipelineError
from card_template_sheet import CARDS_PER_PAGE
from waybill_data import EMPTY, DeckCard
from waybill_deck import apply_route, party_pool, spread_parties, waybill_spec


class EmptyPartyPoolError(CardPipelineError):
    """A page filler copies a loaded or inbound-empty card whose waybill spec gives it no party to route through."""


def fill_deck_to_page(deck: list[DeckCard]) -> list[DeckCard]:
    """Pad the deck so the last sticker page is full, with copies of its cards routed to a fresh party.

    An outbound empty has no party by design (party_pool gives none), so its copy takes spread_parties' blank
    party. Any other copy whose pool is empty raises EmptyPartyPoolError, naming the card and the pool.
    """
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
            flow, load = card["Flow"], card["Commodity"]
            spec = waybill_spec(card["Industry"], card.get("Usage", ""))
            pool = party_pool(flow, load, spec)
            if not pool and not (load == EMPTY and flow != "IN"):
                which = "suppliers" if flow == "IN" and load != EMPTY else "customers"
                raise EmptyPartyPoolError(
                    f"page filler for {card['Industry']} {card.get('Usage', '')!r} ({flow} {load}): "
                    f"its waybill spec has no {which}"
                )
            apply_route(card, flow, load, spread_parties(pool, 1)[0], card["Industry"])
        deck.append(card)
    return deck
