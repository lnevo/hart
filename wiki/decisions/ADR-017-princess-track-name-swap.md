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
7. Layout Editor drawing: unchanged. A same-day attempt to run the K tracks off the panel edge with a hidden wrap was reverted the same evening; the panel is the physical picture, so the K loop stays drawn as the balloon around the two mainline stubs, with Masts 2035 / 2036 at its apex.
8. CATS desks (2026-11-07, same day): the Designer source moves the K tracks to the outer rows too. Row 5 is Track K-1 and row 8 Track K-2, each running east to column 63 with Masts 2035 / 2036 and the SHARED wrap `(63,5)` ↔ `(63,8)`; rows 6 / 7 are the Track McKees Rocks / Track McKeesport stubs ending at column 59. Callouts read `K-1`, `McKees Rocks, PA`, `McKeesport, PA`, `K-2`. Because the straight leg is now the closed main, Switches 37 / 39 drop out of `INVERT_VS_JMRI` in `wire_digicon.py`.

## Consequences

- Dispatcher System sensors, sections, transits and the 500 traininfo files were renamed in place, so Stage 1 and Stage 2 did not have to be re-run.
- `public_name_map.csv` identity rows and aliases follow the new names.
- ADR-005's stub example (`Track K-1`) no longer holds; it now reads `Track W-1`.
- The Shenango station map was redrawn as SM-05 rev B (`ops/station_maps/scripts/render_shenango_station_map.py`).
- The website schematic renderer (`render_le_layout.py`) skips hidden track segments (none are in use today).
