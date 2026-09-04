# ADR-006 — C&O-1980 signal rulebook for Digicon SHSM

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** lnevo

## Context

HART’s field hardware is 13 two-head searchlights (two independent G/Y/R discs) and 10 dwarfs (one disc). There are no three-head masts and no lunar. The leftover plant language is Chessie / early CSX, not AAR-1946 ABS.

Custom `hart-aar` `SL-2-digicon` was a 3-aspect collapse so stock AAR-1946 `SL-2-high-abs` would not pin SML at Stop (that pack’s dest-Approach mapping only offered undisplayable Advance Approach / Approach Medium). It had no Restricting; diverge R/Y was named Medium Approach.

## Decision

1. Use stock **C&O-1980** for every JMRI mast: homes `CO-33-hi`, dwarfs and dispatcher virtuals `CO-3-dwarf`.
2. Keep mast **user names** and IH head bindings. SML pairs stay keyed by user name; do not re-Discover unless facing changes.
3. Deploy a user-files overlay of C&O-1980 that adds USS CTC imagelinks (`ctc` / `ctc-w`). Aspect mappings stay the JMRI 1980 Chessie rulebook.
4. CATS `aar_aspect_bridge.py` remaps Digicon R-codes onto C&O-1980 names (Restricting is legal on 2-head). Live panels stay `HOLD_ONLY`.

## Consequences

- Two-head lamps: Clear G/R, Approach Medium Y/G, Medium Clear R/G, Approach Slow Y/Y, Approach Y/R, Restricting R/Y, Stop R/R.
- Thrown on this layout is Restricted speed, so an empty diverge is Restricting (R/Y), not Medium Clear.
- Custom `hart-aar` remains in the repo unused; profiles no longer install it.
- Changing mast **type** again still requires rewriting SHSM system names in tables.

## Alternatives considered

- Expand `hart-aar` — would avoid a type change, but stays a private rulebook.
- CSX-2014-Chessie — same Chessie lamps plus Limited flashers this layout never lines.
- CSX-1998 — era date match, but 3-3 Restricting needs lunar / 2R heads we do not have.
