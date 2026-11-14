#!/usr/bin/env python3
"""PAIRS only: the historical CATS-pairs oracle. This module no longer writes anything.

SML is native: the Layout Editor panel defects that blocked Discover were fixed (see
jmri/layouts/hart/scripts/validate_le_signalling.py and docs/ctc/SIGNAL_FACING.md), Discover
generates the pairs with useLayoutEditor=yes, and they are stored in
jmri/layouts/hart/output/tables.xml. The old hand-pair injector (a text-slicing tables.xml
writer behind --force-legacy, and the startup Jython it generated) is deleted; git history
has it.

PAIRS below is the CATS-derived list that workaround used to apply. It is imported by
validate_le_signalling.py as a historical comparison oracle.
Known defects in PAIRS (why it is only historical):
- opposing-face pairs (Plane East Ext <-> Track Barn D, the OS Switch 7 plant pairs) that
  SML never models; replaced by true next-mast-down-the-line pairs
- Mast 38LB / Track McKeesport -> 111a rows are geometrically impossible
  (LH crossover 113 cannot route bottom-east to top-west)
- balloon A48 rows had source/dest direction swapped
"""

from __future__ import annotations

# source, dest, blocks (must be unoccupied), turnouts [(userName, closed|thrown)]
# Turnout polarity: TURNOUT_STATE_SOURCES.md / SIGNAL_FACING.md.
PAIRS: list[tuple[str, str, list[str], list[tuple[str, str]]]] = [
    # South line: Plane East Ext ↔ Track Barn D across Track East Ext (not East End Track Main West).
    (
        "Mast 6LB",
        "Mast 8RB",
        ["Track East Ext"],
        [],
    ),
    (
        "Mast 8RB",
        "Mast 6LB",
        ["Track East Ext"],
        [],
    ),
    (
        "Mast 8RB",
        "Mast 34R",
        ["OS Switch 7b", "Track Main East"],
        [("Switch 7", "closed")],
    ),
    (
        "Mast 8RB",
        "Mast 8RA",
        ["OS Switch 7"],
        [("Switch 7", "thrown")],
    ),
    (
        "Mast 8LA",
        "Mast 6LB",
        ["Track East Ext"],
        [("Switch 7", "closed")],
    ),
    (
        "Mast 6LA",
        "Mast 8RA",
        ["Track Scale"],
        [("Switch 5", "thrown")],
    ),
    (
        "Mast 8RA",
        "Mast 8LB",
        ["OS Switch 7", "Track Barn"],
        [("Switch 7", "closed")],
    ),
    (
        "Mast 2L",
        "Mast 8RB",
        ["OS Switch 5", "Track East Ext"],
        [("Switch 1", "thrown"), ("Switch 5", "closed")],
    ),
    (
        "Mast 2L",
        "Mast 8RA",
        ["OS Switch 5", "Track Scale"],
        [("Switch 1", "thrown"), ("Switch 5", "thrown")],
    ),
    (
        "Mast 24L",
        "Mast 2L",
        ["Track Main West"],
        [("Switch 23", "closed")],
    ),
    (
        "Mast 34L",
        "Mast 8LA",
        ["OS Switch 33", "Track Main East"],
        [("Switch 33", "thrown")],
    ),
    (
        "Mast 34R",
        "Mast 36RB",
        ["Track East Lead"],
        [("Switch 33", "thrown")],
    ),
    (
        "Mast 32R",
        "Mast 36RB",
        ["OS Switch 31", "Track East Lead"],
        [("Switch 31", "thrown"), ("Switch 33", "closed")],
    ),
    (
        "Mast 24RA",
        "Mast 36RA",
        ["Track West Ext"],
        [("Switch 23", "closed")],
    ),
    (
        "Mast 24RB",
        "Mast 36RB",
        ["Track S-R", "Track East Lead"],
        [("Switch 23", "closed"), ("Switch 33", "closed")],
    ),
    (
        "Mast 8LB",
        "Mast 8RA",
        ["Track Barn", "OS Switch 7"],
        [("Switch 7", "closed")],
    ),
    (
        "Mast 8LB",
        "Mast 6LA",
        ["Track Barn", "Track Scale"],
        [("Switch 7", "thrown")],
    ),
    # 114/115 C homes face west. Dest 111a (113 closed) or Track East Lead (113 thrown).
    (
        "Mast 40LB",
        "Mast 24L",
        ["OS Switch 39", "Track West Ext"],
        [("Switch 39", "thrown"), ("Switch 35", "closed")],
    ),
    (
        "Mast 40LB",
        "Mast 34L",
        ["OS Switch 39", "Track East Lead"],
        [("Switch 39", "thrown"), ("Switch 35", "thrown")],
    ),
    (
        "Mast 38LB",
        "Mast 24L",
        ["OS Switch 37", "Track West Ext"],
        [("Switch 37", "thrown"), ("Switch 35", "closed")],
    ),
    (
        "Mast 38LB",
        "Mast 34L",
        ["OS Switch 37", "Track East Lead"],
        [("Switch 37", "thrown"), ("Switch 35", "thrown")],
    ),
    (
        "Mast 40LA",
        "Mast 24L",
        ["OS Switch 39", "Track West Ext"],
        [("Switch 39", "closed"), ("Switch 35", "closed")],
    ),
    (
        "Mast 40LA",
        "Mast 34L",
        ["OS Switch 39", "Track East Lead"],
        [("Switch 39", "closed"), ("Switch 35", "thrown")],
    ),
    (
        "Mast 38LA",
        "Mast 24L",
        ["OS Switch 37", "Track West Ext"],
        [("Switch 37", "closed"), ("Switch 35", "closed")],
    ),
    (
        "Mast 38LA",
        "Mast 34L",
        ["OS Switch 37", "Track East Lead"],
        [("Switch 37", "closed"), ("Switch 35", "thrown")],
    ),
    (
        "Mast 36RA",
        "Mast 2035",
        ["OS Switch 35b", "OS Switch 39"],
        [("Switch 35", "closed"), ("Switch 39", "thrown")],
    ),
    (
        "Mast 36RA",
        "Mast 40LA",
        ["OS Switch 35b", "OS Switch 39"],
        [("Switch 35", "closed"), ("Switch 39", "closed")],
    ),
    (
        "Mast 36RB",
        "Mast 2036",
        ["OS Switch 35a", "OS Switch 37"],
        [("Switch 35", "closed"), ("Switch 37", "thrown")],
    ),
    (
        "Mast 36RB",
        "Mast 38LA",
        ["OS Switch 35a", "OS Switch 37"],
        [("Switch 35", "closed"), ("Switch 37", "closed")],
    ),
    # Balloon: dest each other across A48. Adjacent CPs — no intermediate
    # occupancy. (Old shared 1-1/1-2 circuit stuffed Track K-1 onto
    # Mast 2035→Mast 2036 so either track occupied Stopped both; sensors are independent now.)
    (
        "Mast 2036",
        "Mast 2035",
        [],
        [],
    ),
    (
        "Mast 2035",
        "Mast 2036",
        [],
        [],
    ),
    (
        "Mast 4RA",
        "Mast 24RA",
        ["Track W-1", "OS Switch 3", "Track Main West"],
        [("Switch 3", "closed")],
    ),
    (
        "Mast 4RB",
        "Mast 24RA",
        ["Track W-2", "OS Switch 3", "Track Main West"],
        [("Switch 3", "thrown")],
    ),
]
