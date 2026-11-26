"""The card pipeline's one error type, in a module that imports nothing: a module that needs only the error does not
read car_paths' environment (HART_CAR_CARDS_ROOT) at import."""
from __future__ import annotations


class CardPipelineError(Exception):
    """A card pipeline step cannot go on; the message says what to fix. The command's main() exits with it."""
