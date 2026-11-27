"""MapError, the one error of the schematic's band, track, block-override and mast rules (plan_bands, plan_tracks,
block_override_rows, mast_routes, mast_rule) and of the device map builders over them, which raise it or a subclass."""
from __future__ import annotations


class MapError(RuntimeError):
    """A plan, a hand list or a rule's input that the device map cannot be built from; the text names what and where."""
