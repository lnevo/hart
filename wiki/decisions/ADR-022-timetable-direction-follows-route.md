# ADR-022 — Timetable direction follows the route

- **Status:** Accepted
- **Date:** 2026-11-13
- **Deciders:** lnevo

## Context

The staging level already uses west and east: W-1 and W-2 are the west end, Princess and the helix the east end. The helix carries trains up to the main levels, where they run the opposite way along the same walls. No direction had been set for the main levels, and the schematic maps ([`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md)) need one.

## Decision

Timetable direction is a property of the route, not of the room. A train that leaves staging eastward, toward Princess and the helix, is eastward all the way up and across the main levels; the return trip is westward throughout.

## Consequences

- Every band of the system schematic and every station map has east on the right.
- Crews, train orders, signal names (L and R, eastward and westward masts) and Dispatcher directions keep one meaning on every level.
- On a deck track map, which keeps the room's shape, east points a different way on each level, so each deck carries its own direction arrow.
- Track and switch names for the main levels are chosen with this direction in mind.

## Amendment 2026-11-14 (owner): east on the main levels

- On the main and upper levels, east runs away from the helix along the main line. The helix is the west end of both levels. On the main level, the balloon at T196 and the three yard tracks are the east end. Trains from there cross onto Neville Island heading west, and a train toward the helix is westbound, toward West Yard.
- The system schematic keeps the helix at the right of every band, as the owner prefers. So on the main and upper bands, east is drawn to the left, and on the upper band's top row (after the west loop) to the right. Instead of one page legend, those bands carry a small EAST arrow on each main run, and every switch number carried its facing letter (R when its points meet an eastward train first) until REV 5, which turned the letters off (amendment below). Staging keeps east to the right.
- Amendment 2026-11-14 (REV 5): the facing letters are off (`facing_letters: false` in both preferences files). The owner is not yet confident in the switch assignments, and an L or R after a switch number reads as its hand, which differs on 8 of the 17 staging switches. Switch numbers print bare; signal names keep L and R (westward and eastward masts), and the EAST arrows stay. Turning the letters back on is the same setting.
