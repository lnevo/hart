# ADR-031 — Signals by rule, with prototype mileposts

- **Status:** Superseded by [ADR-024](ADR-024-signals-by-rule.md) (2026-11-23)
- **Date:** 2026-11-19
- **Deciders:** lnevo

> Superseded on 2026-11-23 (repo review): ADR-024 records the same signal rule, with every later change. Kept as written on 2026-11-21; its names are out of date. The loop turnback pairs are A83/A84 and B92/B93 now (ADR-024, "Intermediate (APB) signals"), `interlockings_staging.csv` is the level 1 rows of `interlockings.csv`, 239 Spur is 241 Spur, and the helix home signals are at 127 and 131.

## Context

Staging masts were placed by hand; main and upper came from a rule in `build_device_map.py`. The owner wanted one rule for every level, named the way a prototype railroad would name them. Only one staging mast (6LB, Switch 5, head IH432) is physically installed, so the rest were free to change. These decisions were kept in chat memory until 2026-11-21 and are recorded here so every agent sees them.

## Decision

The signal rule (`tools/schematic/mast_rule.py`) places every mast, and these choices drive it:

1. **Control points** hold main-route switches only. Staging interlockings: Brick (1, 3, 5), East End (23, 31, 33; 32R is the ladder entrance), Princess (35, 37, 39), read from `interlockings_staging.csv`. The control-point drawings (brackets, gantries) stay as they were.
2. **Mast types** (stock Basic, ADR-011): two heads when a route meets facing points inside the interlocking before the next signal (`facing_on_route`); high from running track, dwarf from a yard or lead; a bumper track that holds a train gets a dwarf (4RA, 4RB). A track longer than `LONG_CM` (150 cm) gets home masts at both ends and an intermediate pair at its block boundary (K-1/K-2 inside the Princess loop).
3. **Mileposts:** staging Switch 1 is MP 5.7, where the P&OV met the P&LE at Neville interlocking. The count runs through the helix (about 690 in per track) onto main and upper, both about MP 7.53 at the helix top. Duplicate mileposts on main and upper are deliberate.
4. **Line codes:** A is main, B is upper (after Furnace A and B); staging has none.
5. **Intermediate names** are milepost tenths, odd west and even east, from the plugin's own milepost count as printed on the sheets: K-1/K-2 is Mast 67/68; the pair at a loop's turnback sits at the loop's start milepost plus half its length (A84/A85 on 107 Loop, B91/B92 on 227-239), drawn back to back.
6. **Main and upper** (approved 2026-11-19 in PanelPro and CATS): CP 107 merged (107-119); CP 125 and CP 129 separate; the passing sidings are running track; 240L is the exit dwarf on 239 Spur. No helix intermediates: the home signals at 129 and 135 govern the helix.
7. Generated staging heads get internal names (`IH:HART:C1:…`). The Digicon boot-disable applies only to masts on wired IH-digit heads (6LB).

## Consequences

- Signal Mast Logic comes from stock discovery in a sandbox, not a local model.
- Helix-top intermediates (A75/B75) were tried and dropped by the owner; they are listed in [`not-pending.md`](../not-pending.md).
- The wiring plan for the staging heads and the unplaced main/upper heads is re-planned later, when the owner raises it.
