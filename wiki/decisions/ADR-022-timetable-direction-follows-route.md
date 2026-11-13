# ADR-022 — Timetable direction follows the route

- **Status:** Accepted
- **Date:** 2026-11-13
- **Deciders:** lnevo

## Context

The staging level already uses west and east: W-1 and W-2 are the west end, Princess and the helix the east end. The helix carries trains up to the main levels, where they run the opposite way along the same walls. No direction had been set for the main levels, and the schematic maps ([`projects/schematic-maps.md`](../projects/schematic-maps.md)) need one.

## Decision

Timetable direction is a property of the route, not of the room. A train that leaves staging eastward, toward Princess and the helix, is eastward all the way up and across the main levels; the return trip is westward throughout.

## Consequences

- Every band of the system schematic and every station map has east on the right.
- Crews, train orders, signal names (L and R, eastward and westward masts) and Dispatcher directions keep one meaning on every level.
- On a deck track map, which keeps the room's shape, east points a different way on each level, so each deck carries its own direction arrow.
- Track and switch names for the main levels are chosen with this direction in mind.
