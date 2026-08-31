# Audit — 17 proposed masts vs 23 live signalmast beans

**Date:** 2026-08-31  
**Question:** Why does the validator report 17 map masts not on beans? Where are the rest?

## Short answer

Nothing is missing from the live Digicon layout. The **17** are **Dispatcher Stage 1 virtual stub masts** — names in `public_name_map.csv` as **proposed** (with historical alias rows) but **not yet applied** as `signalmast` beans in `tables.xml`. The **23** masts on beans are the live roster; they all match the map.

## Counts

| Set | Count | Meaning |
|-----|-------|---------|
| `signalmast` userNames in deploy `tables.xml` | **23** | Live JMRI masts (Digicon + Princess 2035/2036) |
| SML `destinationMast` entries | **93** | Signal Mast Logic routes (not the same as mast count) |
| Map rows (total) | 676 | Identity + historical aliases + equipment |
| Map rows `current != proposed` | 430 | Mostly **historical aliases** (old name → proposed) |
| Mast-related proposed-diff rows | 74 | Aliases pointing at ~17 virtual + Princess renames |
| Unique **Mast\*** names on map not on any bean | **17** | Virtual stubs (see list below) |
| Masts on beans **not** in map | **0** | Full alignment for live masts |

## The 17 (map-only virtual stubs)

These appear in Dispatcher traininfo/transits and in the map as proposed names; they are **END_BUMPER / hidden throat** endpoints for CreateTransits:

| Mast | Role (from map notes) |
|------|------------------------|
| Mast 10LA, Mast 10LB | EH-2 / EH-3 bumpers |
| Mast 12L | EH-1 bumper |
| Mast 16L | S-R west / 103 ladder |
| Mast 18L, Mast 18R | S-1 throats |
| Mast 20L, Mast 20R | S-2 throats |
| Mast 22L, Mast 22R | S-3 throats |
| Mast 26L, Mast 26R | S-4 throats |
| Mast 32L, Mast 38RA, Mast 40RA | Additional stub endpoints |
| Mast 4LA, Mast 4LB | West yard stub ends |

Historical alias examples: `119LA` → `Mast 10LA`, `Engine House 2 buffer` → `Mast 10LA`, `South Yard 2 west` → `Mast 18L`.

## The 23 live masts (on beans)

```
Mast 2035, Mast 2036, Mast 24L, Mast 24RA, Mast 24RB, Mast 2L,
Mast 32R, Mast 34L, Mast 34R, Mast 36RA, Mast 36RB, Mast 38LA,
Mast 38LB, Mast 40LA, Mast 40LB, Mast 4RA, Mast 4RB, Mast 6LA,
Mast 6LB, Mast 8LA, Mast 8LB, Mast 8RA, Mast 8RB
```

Princess **2035/2036** are on beans; map still has alias rows from old Princess names.

## What to do (consolidation — not promotion yet)

| Option | When |
|--------|------|
| **A — Document only** | Treat 17 as intentional map/proposed; validator warns but does not fail (current) |
| **B — Apply stub masts** | Run `apply_public_names` / LE stub mast pipeline so beans exist (promotion + PanelPro) |
| **C — Virtual mast beans** | Create SHSM stub masts per `STUB_MASTS` / `apply_le_cleanup.py` pattern |

See live [`wiki/DISPATCHER_LAYOUT_HOOPS.md`](../../wiki/DISPATCHER_LAYOUT_HOOPS.md) and [`NEXT_ROUND.md`](../NEXT_ROUND.md).

## Validator behavior (2026-08-31)

`check_names_diff.py` **excludes** the 17 virtual stub masts (`hardware` contains `virtual` on canonical mast rows). Any other equipment-like gap **fails** Tier A.

See `scripts/virtual_stub_masts.py`.
