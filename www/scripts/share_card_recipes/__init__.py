"""The share-card recipes of make_share_cards.py, one module per kind of card. Each public function is the whole
recipe for one card and returns its image; make_share_cards.CARDS names them in the order they run."""

# The recipes import make_share_cards (its helpers and constants), and it imports them after its helpers are defined.
# Loading it here first keeps that order when a recipe module is the first thing imported.
import make_share_cards  # noqa: F401
