# Baseline faults: layer 1 and the generation rules only

Work list for stream B2. Drawn by

    python3 system.py staging.json main.json baseline_sample.svg --no-preferences --no-hints
    python3 baseline_report.py staging.json main.json --no-preferences --no-hints

`baseline_sample.svg` is the drawing. Layer 1 (`plan_overrides`, including T300 right-hand and Switch 9 hand R,
straight EH-3, diverging EH-2) is on; `hints` and `preferences` are off. Inputs: the 5.3b export, graphs made by
`export_reader.py` as in the README. The report script is `baseline_report.py`; its tests are the self-check
(`schem.check`) plus two more written for this list: main route not level, and ladder yard track not level.
Definitions are at the end.

## Totals

| Check | Upper | Main | Staging | All |
|-------|-------|------|---------|-----|
| Crossings or overlaps (self-check) | 0 | 0 | 0 | 0 |
| Layout warnings (ordering rules dropped, clearance not met) | none | none | none | none |
| Main route not level through a switch | 6 | 4 | 2 | 12 |
| Ladder where the yard track is not level | 2 | 0 | 1 | 3 |

The self-check prints nothing in the baseline: the solver adds clearance until no two lines cross or lie on top of
each other, so the work list is slope and layout quality, not crossings. (With the hints on, the same three checks
give 0 crossings; main not level 7 and ladder 2, listed under "With the hints on".)

## Crossings and overlaps

None on any band. Labels are not part of the self-check; see "Seen on the baseline sheet, not checked by a test".

## Main route not level through a switch

Each row is one switch. "Sloped leg" is the main leg that is drawn on a diagonal; "level leg" is what the solver kept
level instead. Switches either side are given as the common end (A), the sloped main leg and the level leg.

| # | Band | Switch | Common end A | Sloped main leg | Level leg (not main) | Hint that covered it |
|---|------|--------|--------------|-----------------|----------------------|----------------------|
| 1 | Main | T155 | T160 (24 cm, main) | B to T196, the loop (100 cm) | C to T162 (22 cm) | `level_leg` T155 = B |
| 2 | Main | T165 | T153 (11 cm, main) | B to T160 (11 cm) | C to T143 (24 cm) | `level_leg` T165 = B |
| 3 | Main | T187 | T184 (10 cm, main) | B to T153 (230 cm) | C to T1 (25 cm) | `level_leg` T187 = B |
| 4 | Main | T196 | T155 (100 cm) | C, loop track (777 cm) | B, loop track (777 cm), also main | none (main on all three legs: the balloon loop; still true with hints) |
| 5 | Upper | T256 | T233 (12 cm, main) | B to T273 (283 cm) | C to T231 (145 cm) | `level_leg` T256 = B |
| 6 | Upper | T274 | T237 (12 cm, main) | B to the west loop's turnback (23 cm, to T233) | C to T268 (163 cm) | `level_leg` T274 = B |
| 7 | Upper | T239 | 23, the double crossover (18 cm, main) | C to T241 (78 cm) | B to T210 (48 cm) | none (peninsula loop entry; still true with hints) |
| 8 | Upper | T241 | T239 (78 cm, main) | B, peninsula loop (519 cm, to T253) | C, spur end (97 cm) | none (peninsula loop; still true with hints) |
| 9 | Upper | T253 | 23, the double crossover (18 cm, main) | C, peninsula loop (519 cm, to T241) | B to T217 (21 cm) | none (peninsula loop; still true with hints) |
| 10 | Upper | T300* | T237 (660 cm, main) | B to 23, one of the two tracks to the double crossover (292 cm) | C to 23, the other track (292 cm), also main | `level_leg` T300* = B, which does not remove it: main is on all three legs |
| 11 | Staging | 1 (T116) | Main West to 23 (570 cm, main) | C, Brick-Plane round the loop (196 cm) | B to 3 (37 cm) | none (loop return into Main West; still true with hints) |
| 12 | Staging | 33 (T77) | East Lead to 35 (263 cm, main) | C, Main East round the loop (811 cm) | B to 31 (25 cm) | none (loop return into East Lead; still true with hints) |

Items 4, 7 to 12 are places where the main goes through the diverging leg because the main is a loop (balloon at
T196, the west and peninsula loops on the upper band, the staging loop). They are not covered by any hint and stay
with every hint on. B2 decides the rule: a loop's return track runs level through a switch only if the common end
slopes instead, or these switches are exempt. Items 1, 2, 3, 5, 6 are the hint cases: the baseline slopes the main
and keeps the short link level; the hint reverses that.

Hint entries that were on the main route but changed nothing in the baseline comparison (removing one at a time
from the hints-on, preferences-off drawing leaves the drawing as it was, and the baseline is level there already):
T262, T160, T153, T184, T199, T175, T251, T285, T275, T273, T233, T237 on the main and upper bands. B2 can drop them.
(`level_leg` T262 is needed on its own: removing only that entry makes T262 slope, but the baseline without any
hint has it level; the interaction is with the other hints.)

Also: removing `keep_close` (T237 to T262, T300* to T262) from the hints-on drawing changes no check. `shorten`
T237 to T300* and every `min_cells` entry sit in the preferences and are off in the baseline; no crossing or
slope fault appears without them, so they change only how long runs are drawn, which is a look. If B2 wants T262's helix track kept near T300 it needs its own rule; the baseline puts
T237 to T262 on the long diagonal seen in `baseline_sample.svg`.

## Ladder where the yard track is not level

A ladder switch whose level leg is a short link (40 cm or less, not main) to the next switch while the sloped leg is
a long track (more than twice the link plus 20 cm, not main). Staging Switches 17, 19, 21 and 25 to 31, the EH
ladder (13, 11, 9) and the main band's T160 throat draw correctly in the baseline; T160's level leg is main.

| # | Band | Switch | Level leg | Sloped leg | Hint that covered it |
|---|------|--------|-----------|------------|----------------------|
| 1 | Staging | 15 (T52) | C, link to 17 (27 cm) | B, S-R (570 cm) | `level_leg` T52 = B |
| 2 | Upper | T220 | B, link to T227 (10 cm) | C, spur to a track end (88 cm) | none (peninsula ladder; still true with hints) |
| 3 | Upper | T345 | B, link to T329 (14 cm) | C, spur to a track end (139 cm) | none (west ladder; still true with hints) |

The hints `level_leg` 13 = C, T133 = C, T73 = C (staging) were written for these ladders and for the lead into the
first ladder switch; the baseline draws that part correctly, so they changed nothing.

## Seen on the baseline sheet, not checked by a test

These come mostly from the preferences being off; the self-check does not test them.

- Main band: T285 and T251 (height 0) are drawn on the main band, not the upper band, because the preference that
  assigns them is off. Connector A is then the only connector (the link between the helix tops).
- Labels collide: the HELIX box covers the MCKEES ROCKS and MCKEESPORT names; "T251" and "T285" overlap; T196 and
  T162 labels sit on track. Labels are not checked for collisions (known gap).
- The loop at T196 is drawn dashed at the top of the main band (non-main track in a loop, `flip` preference off).

## With the hints on (preferences off)

For comparison, from `baseline_report.py staging.json main.json --no-preferences`: crossings 0; main not level 7
(upper T239, T241, T253, T300*; main T196; staging 1 and 33); ladder 2 (upper T220, T345). So the hints cover six
baseline items: main-not-level items 1, 2, 3, 5, 6 and the staging ladder at Switch 15. Everything that remains with
the hints on is uncovered by any hint and is B2's real work.

## Definitions

- Main not level: a switch whose common end (A) and exactly one other leg are main track, where that other leg is
  drawn on a diagonal. A switch with main on all three legs is listed once as such. A main strand drawn only as a
  diagonal between two switches would also be listed; there are none.
- Ladder: see above.
- The level leg of a switch is the leg whose drawn row equals the row of its common end.
