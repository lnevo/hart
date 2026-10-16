# ADR-006 — Signal rulebook for Digicon SHSM

- **Status:** Accepted (amended 2026-09-28 — basic-enhanced trial)
- **Date:** 2026-09-03
- **Deciders:** lnevo

## Context

HART’s field hardware is 13 two-head searchlights (two independent G/Y/R discs) and 10 dwarfs (one disc). There are no three-head masts and no lunar. The leftover plant language is Chessie / early CSX, not AAR-1946 ABS.

Custom `hart-aar` `SL-2-digicon` was a 3-aspect collapse so stock AAR-1946 `SL-2-high-abs` would not pin SML at Stop (that pack’s dest-Approach mapping only offered undisplayable Advance Approach / Approach Medium). It had no Restricting; diverge R/Y was named Medium Approach.

Stock C&O-1980 was loaded briefly (homes `CO-33-hi`, dwarfs `CO-3-dwarf`) so the layout could be seen on Chessie rules before a Basic-family trial.

## Decision

1. Use stock **basic-enhanced** for every JMRI mast: homes `two-searchlight-high`, dwarfs and dispatcher virtuals `one-searchlight-low`.
2. Keep mast **user names** and IH head bindings. SML pairs stay keyed by user name; do not re-Discover unless facing changes.
3. Disable flashing aspects on the mast (not on the signal head): `Advanced Approach` on every mast, and `Diverging Advanced Approach` on two-head masts. JMRI then has no valid aspect when the next signal is Approach, and that mast shows Stop until the Approach clears.
4. Panel icons use the `discriminated` image set (AAR-1946 searchlights, the same drawings Basic uses). Layout Editor scale is 1.0. USS two-head icons are the same set at scale 0.5 so they fit a 21 px cell. Do not point icons at `noflash` (that set has no image for the steady aspects). Do not restore the hart-aar Clear collapse.
5. CATS `aar_aspect_bridge.py` remaps Digicon R-codes onto the enabled basic-enhanced names only. Live panels stay `HOLD_ONLY`.

## Consequences

- Two-head lamps while the flash aspects stay disabled: Clear G/R, Approach Y/R, Diverging Clear R/G, Diverging Approach R/Y, Stop R/R. Dwarfs: Clear, Approach, Stop.
- A mast two blocks from a real Stop shows Stop, not Clear and not flashing yellow. The chain goes green only after that Stop clears.
- Diverging Clear speed in this system is Limited.
- The C&O-1980 user-files overlay remains in the repo and is unused. Custom `hart-aar` remains unused.
- Changing mast **type** again still requires rewriting SHSM system names in tables.

## Alternatives considered

- Stock C&O-1980 — Chessie drawings and Y/G, R/G, Y/Y, R/Y without a two-block Stop. Seen on the layout, then left for this trial.
- Basic — same steady lamps as this disabled-flash setup except the two-blocks-out mast is Clear, and Diverging Clear speed is Medium.
- Expand `hart-aar` — would avoid a type change, but stays a private rulebook.
- `noflash` icons — static GIFs for the flashing aspects only. The head is still commanded FLASHYELLOW, and steady aspects have no image in that set.
