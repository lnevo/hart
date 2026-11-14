# Schematic maps from a track plan

- **Owner:** lnevo
- **Status:** Stage 0 done (2026-11-13). The spike in `tools/schematic/spike/` (draft PR #423) draws staging, the main level and the upper level on one sheet from the AnyRail export plus as-built edits and owner hints, with no crossings or overlaps; the owner approved the look. Next: the phases under "After the proof" below.
- **Hand-off:** [`schematic-maps-handoff.md`](schematic-maps-handoff.md) separates plan overrides, generation rules and the owner's preferences, and lists the parallel work.
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

- `archive/anyrail-prototype/`: a reverse-engineered `.any` reader (280 lines, no tests). It reads plan 5.3b into three connected groups: 37 turnouts on the level at height 0 to 10.8, 20 turnouts at −38.1 (the built staging level) and 12 turnouts at 2.5.
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
- **Helix track names.** Each helix track keeps its name on both levels. On the main level the track from T175 is McKees Rocks and the one from T251 is McKeesport (owner confirmed).
- **Peninsula top.** Raised from 1 in to 4.25 in, level with the branch line, so the 0.9% grades either side of the double crossover are gone.
- **Beyond the double crossover.** In the plan the lower track climbed to the branch line (T237) and the upper one dropped to the height-0 main (T300). As built both stay at 4.25 in and join inside the closet on the north side, making a passing siding on that leg.
- **T300.** The turnout moves from where it is up to the 4.25 in track (drawn blue in the overlay), adjusted for smooth transitions. There it joins the upper neck track to that track: the closet end of the passing siding.
- **T300's old place.** No turnout is left there. From T251 the track stays at height 0, alongside the other track going to the helix.
- **Rise.** The 2.1% grade from T285 (height 0, north side) to T262 (4.25 in, west wall), 521 cm, is as planned. It is now the only track between the height-0 main and the 4.25 in level.
- **Main levels.** Not final; plan 5.3b is a draft. As-built changes go in an overrides file applied on top of the export.

- **Timetable direction** follows the route, not the room ([ADR-022](../decisions/ADR-022-timetable-direction-follows-route.md)): eastward from staging stays eastward on every level, so every band has east on the right.

For the schematic this gives three bands: staging, the height-0 main, and the 4.25 in level (branch line, peninsula, double crossover), joined by the helix (two tracks) and the rise.

## After the proof (proposed 2026-11-13)

What stage 0 settled, beyond the design above:

- **Input.** AnyRail's JMRI export is the track source (it has every turnout and the double crossover, and only track); the `.any` file supplies heights. Staging is drawn from the export too, not from the Layout Editor panel.
- **As-built edits** sit on top of the plan as a list: relabel, remove, move, add a switch or crossover, name tracks and ends, flip a diverging side.
- **Owner hints** steer the drawing without touching the model: which leg of a switch runs level, a run at least so long or drawn short, two switches on neighbouring rows, band order, width, alignment and stretch, the main routes, helix marks (coil with H1/H2).
- **Rules that had to be found:** level bands with lettered connectors; fold-backs chosen by how the track bends on the layout; a loop's tracks stacked by the loop's bend; spare length shared in proportion to real length; ladders moving as blocks; the drawing checked for crossings and overlaps after every change.

Phases:

| # | Work | Who | Depends on |
|---|------|-----|------------|
| A1 | Move the spike's inputs into data files: as-built edits and hints per level under `jmri/layouts/hart/data/`, in the plan's CSV or JSON form | Agent (Sonnet) | — |
| A2 | Publish the sheet: Letter landscape PDF and SVG in `docs/ops/`, marked draft until the main and upper levels have names | Agent (Sonnet) | A1 |
| B1 | Write the specification from the spike: file formats, every rule above, and the three bands as golden drawings for regression tests | Main session | — |
| B2 | Rebuild as tested modules in `model-railroad-skills` (reader, edits, orient, order, rows, columns, draw, checker) with a made-up public example | Agents (Sonnet), main session reviews the layout rules | B1 |
| B3 | Skill text and the style reference from the two research surveys (kept in `tools/schematic/spike/research/`) | Agent (Sonnet) | B2 |
| C1 | CATS panel for the main and upper levels from the same grid; settle east and west there by following the main line, and carry facing and trailing for each switch | Main session designs, agent builds | B1 |
| C2 | Station pages and deck track maps from the same model | Agents | B2 |
| C3 | Layout Editor import of the main levels (physical picture) and the switch facts for the new levels | Main session | names |

Known weak spots to fix in B2 are listed in the spike's README: rows stricter than needed, labels not checked for collisions, a crossover's number printed twice, three unmatched junctions, no page folding, no capacity placeholder.

## Open questions for the owner

1. **Names** for the main and upper levels: stations, tracks, switch numbers, and what the two levels are called. Pending by the owner's choice.
2. **Order of work:** the tool first (B), or the CATS panel first (C1)?
3. **The spike:** keep as a draft reference, or review and merge it under `tools/schematic/spike/`?
