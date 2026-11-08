# ADR-017 — Princess track names swapped

- **Status:** Accepted. Supersedes the stub example in ADR-005.
- **Date:** 2026-11-07
- **Deciders:** lnevo

## Context

The helix is installed at the Princess (east) end. The former stubs east of Switches 39 and 37 now carry the mainline toward the McKees Rocks and McKeesport interchanges. The former loop legs are the K-1 and K-2 tracks.

## Decision

1. Names swap within each switch. Hardware, system names, sensors, geometry, lengths, block ids and roles stay with the physical track; only names moved.
2. The four blocks:

| Old name | New name | Block id | Occupancy | Sensor |
|----------|----------|----------|-----------|--------|
| Track K-1 (stub, Switch 39) | Track McKees Rocks | IB23 | Block 1-4 | M2S103 |
| Track McKees Rocks (loop leg) | Track K-1 | IB:AUTO:0010 | Block 1-1 | M2S100 |
| Track K-2 (stub, Switch 37) | Track McKeesport | IB24 | Block 1-3 | M2S102 |
| Track McKeesport (loop leg) | Track K-2 | IB:AUTO:0048 | Block 1-2 | M2S101 |

3. Sensor user names follow: `BS McKees Rocks` to `BS K-1`, `BS McKeesport` to `BS K-2`, `BS Switch 39 / BS K-1` to `BS Switch 39 / BS McKees Rocks`, `BS Switch 37 / BS K-2` to `BS Switch 37 / BS McKeesport`. Station and OS short forms swap the same way (`OS K-1` and `OS McKees Rocks`, `OS K-2` and `OS McKeesport`).
4. The mainline flag moved to Track McKees Rocks and Track McKeesport.
5. Unchanged: mast numbers, switch numbers, bumpers EB71/EB72, the panel arrow labels `McKees Rocks, PA` and `McKeesport, PA`, Operations Pro and STS names, and the real interchange and town names.
6. Role wording in the docs stays as it was. The old stubs are still stubs for now (the helix goes nowhere yet; they are only longer) and the K tracks are still a loop.
7. Panel drawing (2026-11-07, second pass): the turnout hands stay as built, so K-1 leaves Switch 39 on the top row and K-2 leaves Switch 37 on the bottom row. Both run east to the panel edge (anchors `A82` / `A83` at x=1950) and wrap around each other **virtually**: segments `F56-S-0` and `F55-S-0` meet at `A48` (x=1950, y=276) and are `hidden="yes"`, so no loop is drawn. Masts 2035 / 2036 and their NX sensors still sit on `A48` and are drawn at the east ends of the two rows. The mainline stubs stay in the centre rows and end at masts 40RA / 38RA as before.

## Consequences

- Dispatcher System sensors, sections, transits and the 500 traininfo files were renamed in place, so Stage 1 and Stage 2 did not have to be re-run.
- `public_name_map.csv` identity rows and aliases follow the new names.
- ADR-005's stub example (`Track K-1`) no longer holds; it now reads `Track W-1`.
- The Shenango station map was redrawn as SM-05 rev B (`ops/station_maps/scripts/render_shenango_station_map.py`).
- The website schematic renderer (`render_le_layout.py`) skips hidden track, so the virtual wrap does not show on hartrailroad.com either.
