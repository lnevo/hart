"""Frozen Entry/Exit (NX) identity for HART Layout Editor.

ISNX:* systemNames stay on the CTC numbers from first Discover (ADR-005).
Live userNames are ``NX Mast …``. Do not generate ``ISNX:Mast 2L``.
"""

from __future__ import annotations

# Live mast userName → frozen internal sensor systemName.
ISNX_SYSTEM: dict[str, str] = {
    "Mast 2L": "ISNX:100L",
    "Mast 4RA": "ISNX:101RA",
    "Mast 4RB": "ISNX:101RB",
    "Mast 6LA": "ISNX:102LA",
    "Mast 6LB": "ISNX:102LB",
    "Mast 8RA": "ISNX:117RA",
    "Mast 8RB": "ISNX:117RB",
    "Mast 8LA": "ISNX:117LA",
    "Mast 8LB": "ISNX:117LB",
    "Mast 24RA": "ISNX:111RA",
    "Mast 24RB": "ISNX:111RB",
    "Mast 24L": "ISNX:111L",
    "Mast 32R": "ISNX:110R",
    "Mast 34R": "ISNX:112R",
    "Mast 34L": "ISNX:112L",
    "Mast 36RA": "ISNX:113RA",
    "Mast 36RB": "ISNX:113RB",
    "Mast 2036": "ISNX:120R",
    "Mast 38LA": "ISNX:114LA",
    "Mast 38LB": "ISNX:114LB",
    "Mast 2035": "ISNX:120L",
    "Mast 40LA": "ISNX:115LA",
    "Mast 40LB": "ISNX:115LB",
}

NX_USER = {mast: f"NX {mast}" for mast in ISNX_SYSTEM}
EXPECTED_NX_PAIRS = 39
NXTYPE_SML = "signalmastlogic"
LAYOUT_PANEL = "HART Railroad"


def nx_user_name(mast: str) -> str:
    return NX_USER[mast]


def nx_system_name(mast: str) -> str:
    return ISNX_SYSTEM[mast]
