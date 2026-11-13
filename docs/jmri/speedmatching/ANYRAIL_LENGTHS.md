# Block lengths from the AnyRail plan (Part A, first pass)

Written 2026-11-13 for [`RERUN_PLAN.md`](RERUN_PLAN.md) Part A. Covers the 17 blocks of the
test loop. The yard, spurs and engine terminal keep their old values for now.

## What the plan file holds

Plan **5.3b** (`~/Documents/Layout`, not in the repo) was decoded with the prototype reader in
[`tools/anyrail/prototype/`](../../../tools/anyrail/prototype/). It is a Boost binary archive.
Coordinates are doubles in centimetres. Each track part has its part number, then tagged
endpoints (id, x, y, height, angle, track system). Flex track is a chain of cubic Bezier
segments, so its length is the arc length. A turnout has three endpoints; a route through it is
taken as the chord from the toe to the leg, which is within 1 mm for these Peco parts. Pieces
join where endpoints coincide (378 joins, no endpoint joined twice). This gives three
connected levels:

| Level | Height | Turnouts | Flex |
|---|---|---|---|
| Main level and helix | 0 to 10.8 cm | 37 | 92.7 m |
| **Staging level** | **-38.1 cm** | **20** | **87.8 m** |
| Reversing branch | 2.5 cm | 12 | 15.6 m |

**The built layout is the staging level.** It has the same yard (five tracks between two
ladders), the two spurs off Switch 3, the crossovers at 23 and 35 and the K return loop with 37
and 39. The lengths in the old `old_source` column (Yard Lead 108, East Bypass 195, East Loop
245, West Loop 72, Yard 3 178, Yard 4 212) are this level's turnout-to-turnout runs (107.9,
195.1, 245.8, 71.6, 178.1, 211.7 in), so they were read from this plan before. They had been
assigned to the wrong HART blocks in places.

## How the plan maps to HART

| Plan turnout | HART | Check |
|---|---|---|
| T46 (spurs 105.2 and 105.4 in) | Switch 3 | W-1, W-2 |
| T116 | Switch 1 | 71.6 in to T106 = Brick-Plane |
| T106 (Y, SL-8377) | Switch 5 | |
| T52, T133, T73, T123 | Switches 15, 17, 19, 21 | yard tracks 215.6, 211.7, 178.1, 144.6/141.2 in |
| T68, T95, T94, T59 | Switches 25, 27, 29, 31 | |
| T77 | Switch 33 | |
| T58 + T118 | Switch 23 crossover | |
| T55 + T98 | Switch 35 crossover | |
| T56, T129 | Switches 39, 37 | K loop 245.8 in |

Differences from the plan, as built:

1. The plan's crossover T41/T43 between Main West and Track S-R, about 27 in from Switch 1, is
   not on the panel. The loop length counts its straight route as track.
2. The Switch 7 crossover sits between the two long parallel runs from Switch 5 (to Switch 33,
   and to the yard ladder). It is not in the plan.
3. Switch 13 and the engine terminal (Switches 9 and 11, Barn, Scale, EH-1 to EH-3) are on the
   run from Switch 5 to the yard ladder. They are not in the plan.
4. The plan's two long dead ends past Switches 37 and 39 are the helix lines; on the layout they
   are the McKeesport and McKees Rocks stubs.

**Owner to confirm** the mapping and these four differences.

## The loop length and the speeds

Along the 2026-11-08 test route the plan gives **35,108 mm** (flex plus turnout routes). The
block table said 31,293 mm. So if the loop is built to plan, **every speed recorded on
2026-11-08 is about 12% low.** Comparisons between 2121 and 2738 are unaffected.

Independent check: place each turnout's OS block on the loop from the timings (block share of
lap time × 35,108 mm) and compare with where the plan puts the turnout. After a constant offset
of about 17 cm (where a block starts relative to the turnout), the eight turnouts on the loop
agree within -2 to +15 cm over 35 m.

## The lengths

[`infer_block_lengths.py`](../../../jmri/layouts/hart/scripts/infer_block_lengths.py): for each
block, the median over laps (steps 24 and up, both locos) of its share of the lap time, times
35,108 mm. Hidden throat stubs on the same detector (East Lead East, K-1 West, 400 mm each) are
taken off the track row. Spread across laps is 1 to 4 cm per block. The two locos ran opposite
ways (2121 west, 2738 east), and their lengths agree within 1% for the long blocks, so grades do
not bias the result much. Short OS blocks differ by up to 15% between directions; they are
within about 5 cm either way.

**Pinned to the plan turnouts.** The turnouts on the loop are on the plan too, so the timed
positions are then re-fitted piecewise: each OS section's centre is placed on its turnout's
centre on the plan (Switches 5, 33, 35a, 35b, 23a and 1), and the blocks between two of them
share out the plan distance between those turnouts by time. Each block then rests on the plan
lengths either side of it rather than on one scale for the whole loop. Switches 37 and 39 are
not pinned: they sit 0.4 m and 0.2 m from the Switch 35 crossover, and pinning such short
stretches turns a few cm of gap placement into large OS errors. Pinned and whole-loop lengths
agree within 3 cm for most blocks; East Lead (-10 cm) and West Main Ext (+9 cm) differ most,
which is about how far an OS section's centre can sit from its turnout's centre.

**The barn crossover.** The centre of the Switch 7b section comes out 4.15 m (163 in) from
Switch 5's points, 32.6% of the way along the plan run from Switch 5 to Switch 33. On the plan
that is the bottom straight, where the run to the yard ladder lies alongside at 6.4 cm (2.5 in)
track spacing from about 0.5 m to 5.7 m out of Switch 5, so a crossover fits there.

The basis is `inferred` in `block_lengths.csv`. The biggest changes: Main East 185 → 315 in,
East Lead 172 → 88 in (track row; the detector also covers the 400 mm East Lead East stub),
East Main Ext 88 → 141 in, Brick-Plane 72 → 58 in, and each OS block on the loop 10 → 9 to
25 in.

## Not done yet

- The yard tracks, spurs, Scale, Barn and EH tracks: plan runs are known (above), but the gap
  positions are not; they need a timed pass through them, or the owner's tape.
- The generic reader for the public `model-railroad-skills` plugin, checked against AnyRail's
  own figures (owner).
- Piece-to-layer links in the file (the Power District Gaps layer) are not decoded.
