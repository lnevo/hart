"""The share-card recipes of make_share_cards.py, one module per kind of card. Each public function is the whole
recipe for one card and returns its image; make_share_cards.CARDS names them in the order they run."""


class CardError(Exception):
    """A card cannot be made from its sources; the message names the card and what to change. make_share_cards.main()
    prints it and exits 1. Defined before the import below, which loads the recipes that raise it."""


# The recipes import make_share_cards (its helpers and constants), and it imports them after its helpers are defined.
# Loading it here first keeps that order when a recipe module is the first thing imported.
import make_share_cards  # noqa: E402,F401
