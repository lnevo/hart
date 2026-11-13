# Schematic maps from a track plan

- **Owner:** lnevo
- **Status:** Stage 0 in progress (2026-11-13). The spike in [`tools/schematic/spike/`](../../tools/schematic/spike/README.md) draws the built staging level from the Layout Editor panel with no hand placement; the AnyRail groups do not draw cleanly yet.
- **Goal:** turn an AnyRail plan into a logical (not physical) view of the railroad and draw professional maps from it. First output: the one-page system schematic. The same logical view later feeds station map pages, deck track maps, the CATS panel and the Layout Editor import for the main levels.

The generic tool and its skill go in the public `model-railroad-skills` plugin. HART's names, numbers and finished maps stay in this repo.

## Owner decisions (2026-11-13)

| Question | Decision |
|----------|----------|
| First output | System schematic. The other outputs follow once the construction is proved. |
| Home | Generic reader, layout engine, style and skill in `model-railroad-skills`; HART data and pages here. |
| Names | The tool proposes stations, tracks and roles in a draft file; the owner edits it; maps are drawn from it. |
| Look | NYAMR drafting style: black line work, heavy main and light secondary track, capitals, little colour. |

## References

Looked at, and what each one is the model for:

| Reference | Model for |
|-----------|-----------|
| North Western Vermont schematic, NER Coupler 303 pp. 22–23 | System schematic folded into rows across a page, large direction arrow, yard tracks with numbers and capacity, "To X" stubs, yard limit marks |
| NYAMR [orthogonal schematic](https://davebarraza.wordpress.com/wp-content/uploads/2021/02/nyamr-orthagonal-schematic-210210-1.pdf) | One band per level, helix letters joining the bands, station bars and interlocking brackets under the track, rule limits in red, title block |
| NYAMR [Physical Characteristics Book](https://davebarraza.wordpress.com/wp-content/uploads/2026/04/nyamr-physical-characteristics-book-260415.pdf) | Later station pages: one location per page, "West to / East to" arrows, capacity in 50-foot cars on each track, boxed industries with spots, roads, signals |
| NYAMR [track maps of each deck](https://davebarraza.wordpress.com/wp-content/uploads/2022/05/nyamr-overhead-view-2022.pdf) | Later deck maps: room shape kept, main in a second weight, aisles named |
| [St Charles Branch crew track chart](https://appalachianrailroadmodeling.com/stcharlesbranch/?p=796) | Multi-deck with a helix on one straightened line; dashed hidden track; lettered hidden segments |
| [Santa Rosalia town map](https://modelingthesp.blogspot.com/2025/10/an-op-session-briefing.html) | Track names written on the line, industries as boxes |
| [PRR Walbridge interlocking sheet](https://www.redoveryellow.com/position-light/PRR_Diagrams/walbridge.gif) | Switch and signal numbering, revision block |
| Luteberget and Johansen, "Drawing with SAT" and [railplot](https://github.com/luteberget/railplot) | Prior art for automatic railway schematics: what to minimise (width, height, bends, diagonal length). Read for ideas; licence not confirmed, so no code reuse |

Rules the references agree on: the main is one horizontal line per level; other tracks leave at 45 degrees and run parallel; main heavier than sidings and yard tracks; hidden track dashed; direction legend on every sheet; "To X" at open ends; title block with date and revision; black on white first, colour only as a second cue.

The first survey could not open several sources. Stage 3 fills that in.

## What exists

- `tools/anyrail/prototype/`: a reverse-engineered `.any` reader (280 lines, no tests). It reads plan 5.3b into three connected groups: 37 turnouts on the level at height 0 to 10.8, 20 turnouts at −38.1 (the built staging level) and 12 turnouts at 2.5.
- `jmri/layouts/hart/anyrail/hart.xml`: AnyRail's own XML export of the built level, already public.
- `switches.csv`, `switch_legs.csv`, `control_points.csv` and `hartlib` (ADR-021): the built level's plants and connectivity.
- `ops/hart-ops/publications/assets/station_map_full.png`: the hand-built map of the built level. It is the answer sheet for stage 0.
- The owner's `.any` files stay out of every repo.

## Design

Five steps, each writing a file the next one reads, so any step can be re-run or replaced:

1. **Read.** AnyRail plan to a *track graph*: parts, joints, lengths, heights, text labels. Plain JSON, not tied to AnyRail, so another reader (a Layout Editor panel, XTrackCAD) can feed the same steps.
2. **Reduce.** Track graph to a *logical graph*: switches with their three legs, crossings, track ends, level changes, and the runs between them with lengths. Crossover pairs, ladders, passing sidings, loops and spurs are recognised here.
3. **Name.** A draft set of CSV files per level (locations, tracks, switches) with proposed main route, track roles, station groups and capacity from length. The owner edits them. For HART these extend the ADR-021 files; they do not replace them.
4. **Lay out.** Logical graph plus names to grid positions. Deterministic rules, no solver:
   - the main route is row 0, left to right in timetable direction;
   - order along the row follows distance along the main, spaced by what the labels need, not by scale;
   - a parallel track takes the next free row on the side it is on in the room, so the aisle side stays the aisle side;
   - every diverging leg is one 45-degree step;
   - one band per level, a helix or ramp drawn as a lettered connector between bands;
   - a long band folds into rows across the page as the NWV schematic does;
   - a small hints file can pin a side, an order or a fold where the rules pick badly.
   
   Positions are whole grid cells. CATS Designer works on a cell grid too, so the same layout can seed a CATS panel later.
5. **Draw.** Grid positions to SVG and PDF through a style file. The NYAMR drafting style is the first style.

**Checks**, run after steps 2 and 4: every switch, leg and run of the track graph appears once in the drawing; no two tracks cross that do not cross on the layout; no label overlaps a track or another label. For HART, the built level's logical graph must agree with `switch_legs.csv`.

## Stages

| # | Work | Who | Done when |
|---|------|-----|-----------|
| 0 | Proof of the construction: the logical-graph and names file formats, and a first layout engine, run on the built staging level from plan 5.3b | Main session | The generated schematic of the built level shows the same plants and connections as `station_map_full.png`, and the owner agrees it reads better or as well |
| 1 | Reader: move the prototype into the plugin as a tested module; check whether text labels and track names can be read from `.any`; add a reader for AnyRail's XML export | Agent (Sonnet), plugin worktree | Tests pass on a public fixture; both readers give the same track graph for the built level |
| 2 | Reduce and name: pattern recognition and the draft CSV files | Main session designs the rules; agent (Sonnet) writes tests and the CSV plumbing | Draft files for the built level match the ADR-021 files without hand edits to switch legs |
| 3 | Reference library: second research pass (list below), written up as the skill's style reference with links, no copied images | Agent (Sonnet for reading, Haiku for link checks) | Each style rule names the examples it comes from |
| 4 | Drawing and style: SVG and PDF output, title block, direction arrows, station bars, limits, switch numbers; two or three sample sheets of one location | Agent (Sonnet); owner picks from an HTML preview | Owner approves the style on the built level |
| 5 | HART main levels: run steps 1 to 3 on the main-level plan, owner edits the names files, system schematic drawn for all levels | Main session with the owner | Schematic in `docs/ops/`, checks pass |
| 6 | Skill and release: skill text, a made-up example railroad, plugin tests and version | Agent (Sonnet); main session reviews | Marketplace install works on the example |
| Later | Station pages, deck maps, CATS panel seed, Layout Editor import of the main levels | Planned after stage 5 | — |

Stages 1 and 3 can start at once and run beside stage 0. Stages 2 and 4 wait for stage 0's file formats. Every agent that edits files works in its own worktree.

**Where the main session is needed:** stage 0, the layout rules in stages 2 and 4, reading each stage's drawings against the plan before the owner sees them, and stage 5. The rest is porting, tests, research and packaging.

## Research still worth doing (stage 3)

- Prototype track charts and timetable schematic pages for the railroads this layout draws on (Conrail, P&LE and PRR around Pittsburgh), for line weights, track numbering and limit marks.
- LIRR physical characteristics pages, which the NYAMR book imitates.
- The sources the first pass could not open: Maumee Route, Virginian & Ohio, Nickel Plate St. Louis Division, Gorre & Daphetid, N&W, Metro-North track charts.
- Operations SIG and Layout Design SIG articles on crew schematics and station diagrams.
- How helixes, hidden staging and reversing loops are drawn on other multi-deck layouts.
- CATS Designer's grid limits, so step 4's output can seed a panel.
- The "Drawing with SAT" paper in full, for its list of what makes a schematic readable.

## Answers from the owner (2026-11-13)

- Plan 5.3b is the full plan. The staging level and the helix are built; the helix is done to its top turn, and the McKees Rocks and McKeesport stubs are its two tracks today.
- Exports of the owner's track plan may be public. The custom objects and buildings in the plan may not: their author holds the copyright.
- Capacity: not yet. The drawing leaves a place for it.
- Page: Letter landscape.

## As built, compared with plan 5.3b (owner, 2026-11-13)

Part numbers (T…) are the plan's, as drawn in the spike's overlay picture.

- **Helix.** One turn more than planned. Its two tracks still leave the height-0 main (at T175 and T300), now run level to the peninsula near T226 and enter the helix there, and come out on the staging level as the McKees Rocks and McKeesport stubs. The plan file does not join every helix turn; the helix details are held separately.
- **Peninsula top.** Raised from 1 in to 4.25 in, level with the branch line, so the 0.9% grades either side of the double crossover are gone.
- **Beyond the double crossover.** In the plan the lower track climbed to the branch line (T237) and the upper one dropped to the height-0 main (T300). As built both stay at 4.25 in and join inside the closet on the north side, making a passing siding on that leg.
- **Rise.** The 2.1% grade from T285 (height 0, north side) to T262 (4.25 in, west wall), 521 cm, is as planned. It is now the only track between the height-0 main and the 4.25 in level.
- **Main levels.** Not final; plan 5.3b is a draft. As-built changes go in an overrides file applied on top of the export.

For the schematic this gives three bands: staging, the height-0 main, and the 4.25 in level (branch line, peninsula, double crossover), joined by the helix (two tracks) and the rise.

## Open questions for the owner

1. **Direction.** Which way is timetable east on each main level?
2. **T300.** With the upper neck track no longer reaching it, does T300 stay (as what) or go?
3. **Closet switch.** Where along the leg do the two tracks join?
