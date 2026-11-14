# Schematic maps: hand-off after the proof

- **Written:** 2026-11-13, at the end of the stage 0 session.
- **Read with:** [`schematic-maps.md`](schematic-maps.md) (plan, references, as-built notes) and the spike's `README.md`.
- **Where the work is:** branch `agent/claude/schematic-spike`, draft PR #423, folder `tools/schematic/spike/`. The owner approved the look of `system_sample.svg` there.

## The one thing to get right

The spike mixes three kinds of input in two options files (`staging_opts.json`, `main_asbuilt_opts.json`). They must be separated, because only the first two are the product:

1. **Plan overrides.** Facts about the railroad that AnyRail's plan does not hold or holds wrongly. They override the plan and every output uses them (schematic, CATS, station pages, Layout Editor).
2. **Generation.** Rules that turn plan plus overrides into a clean, stretched-out main line and track plan with no hand input.
3. **Preferences.** The owner's choices about how one sheet looks. Optional, applied last, never needed for a correct drawing.

**Test of the separation:** with layer 3 switched off, layers 1 and 2 alone must draw all three levels with no crossings or overlaps, the main line straight through every switch, and yard ladders stepping diagonally with their tracks level. Today that only happens with hints, so several hints below have to become rules.

## Layer 1: plan overrides (feed these over the AnyRail plan)

Source of track: AnyRail's JMRI export of plan 5.3b (`export_reader.py`; the owner keeps the file in `~/Documents/Layout/`). Heights come from the `.any` file, matched to the export by position (export scale is 120 px per inch of plan).

| Override | Staging | Main and upper |
|----------|---------|----------------|
| Switch numbers for plan parts | T46=3, T116=1, T106=5, T52=15, T133=17, T73=19, T123=21, T68=25, T95=27, T94=29, T59=31, T77=33, T58+T118=23, T55+T98=35, T56=39, T129=37 | None yet (owner's names pending) |
| Not built | Crossover T41/T43 between Main West and S-R | — |
| Built but not in the plan | Switch 7 crossover (Scale / East Ext), Switch 13, Switches 11 and 9 with EH-1 to EH-3 | Closet junction: T300 moved onto the 4.25 in track |
| Moved | — | T300: out of the height-0 main, into the run between the double crossover and T237, about 292 cm from the crossover, right-hand (owner confirmed right-hand; the distance is the plan's old run length) |
| Heights | — | Peninsula top 1 in → 4.25 in |
| Track names | Main West, West Ext, East Ext, Main East, East Lead, Brick-Plane, Scale, Barn, S-R, S-1 to S-4, K-1, K-2, W-1, W-2, EH-1 to EH-3 | None yet |
| Track ends | W-1, W-2 bumpers | — |
| Helix tracks | From Switch 39: McKees Rocks (H1). From Switch 37: McKeesport (H2) | From T175: McKees Rocks (H1). From T251: McKeesport (H2). Owner confirmed |
| Main route | Main West, West Ext, Brick-Plane, East Ext, Main East, East Lead, the two throats from 35 to 37 and 39, both helix tracks | H2, T251, T285, the rise to T262, diverge to T275, round the west loop by T273, T256, T233 to T274 and T237, T300, both tracks to the double crossover, round the peninsula loop by T241 and T253. H1, T175, T199, T184, diverge at T187 on the long track to T153, T165, T160, T155, round the loop at T196. The T237–T262 crossover is not main |
| Stations | Brick (1, 3), Plane (5), Barn (7), South Yard (15–21), East End (23–33), Princess (35–39), as `control_points.csv` | None yet |
| West end | W-1 | — |

Also a reader rule, not an override: two track ends on the same spot in the export are one track and are joined (two pairs in 5.3b, one of them the main level's loop at T196).

Hands and legs of the added staging switches are taken from the Layout Editor panel in `tables.xml`, which is the source for them (owner, 2026-11-13):

| Switch | Hand | Straight leg | Diverging leg |
|--------|------|--------------|---------------|
| 7 | Left-hand crossover | Scale to Barn; East Ext to Main East | The crossover |
| 13 | Right | Barn | Switch 11 |
| 11 | Left | EH-1 | Switch 9 |
| 9 | Right | EH-3 | EH-2 (its normal route: the panel's continuing sense is thrown) |

Where they sit along their runs comes from `block_lengths.csv`, since the panel is not to scale: East Ext is measured (140.8 in, from the timed loop); Scale, Barn and EH-1 to EH-3 are 24 in estimates.

## Layer 2: generation rules

Already rules in the spike:

- One band per level; a run that joins two levels is cut and shown as lettered connectors. Level by height (below 5 cm: main; above: upper).
- Each switch faces left or right; runs that must double back are folded, choosing the folds that are U-turns on the layout, and keeping the choice that draws with the fewest faults.
- Tracks are ordered top to bottom from each switch's hand; a loop's two tracks are stacked by which way the loop bends.
- A double crossover's two tracks sit on neighbouring rows.
- Spare length along a band is shared in proportion to real track length; switches joined by short links move as blocks; track ends and folds travel with their switch; a long track always gets a level run; a connector gets one short cell.
- The drawing is checked for lines that cross or lie on top of each other, and the solver adds clearance until none do.

Must become rules (today they are hints):

| Hint used today | Rule to write |
|-----------------|---------------|
| `level_leg` on 18 switches of the main and upper bands and 4 of staging | The main route runs level through every switch on it |
| `level_leg` on Switches 13, 15, 17, 19 | In a ladder, the yard track runs level and the short link to the next switch slopes; a lead runs straight into the first ladder switch |
| `keep_close`, some `shorten` and `min_cells` | Rows should only be kept apart for tracks that really overlap along the band (the spike uses its working order, which is stricter) |
| Trial of T300's hand | Hands of added or moved switches come from layer 1, never from trial |

Known gaps: labels are not checked for collisions; a crossover's number prints on both halves; three junctions (12, 50, 51) match no plan part; no page folding; no capacity placeholder.

## Layer 3: the owner's preferences for this sheet

- Order from the top: main, upper, staging. Helix at the east end of every band (a 180-degree turn of the two upper bands was tried and undone; east and west on the looped mains are to be settled later by following the main line, perhaps on the CATS diagram; ADR-022 stands meanwhile).
- All bands the same width; main band 95% and nudged left; upper band nudged so H2 sits under H1.
- Helix marks: three-turn coil with H1 or H2 and "Helix to …". Connectors between main and upper: circled A and B.
- The helix-top switches T285 and T251 are drawn on the upper band (they are at height 0), T199 and T175 on the main band.
- Main level: the loop at T196 above the main, the three yard tracks below it (drawn sides flipped for T196, T155, T160, T162, T194, T183, 50, 51).
- Lengths: staging: Plane to the right of Brick, Switches 7 and 13 further east, a gap between 13 and 15, long yard tracks. Main: yard throat level with the loop's edge, a long run between T1 and 12, room between T160 and T165. Upper: T237 to T300 short, T262 to T285 five cells.
- NYAMR drafting style, Letter landscape, title block, station brackets under staging.

## Work to do, in parallel

The three layers above are the contract between the streams. Keep the spike's edit operations and hint names as the first file format, so every stream can start at once.

| Stream | Work | Who | Done when |
|--------|------|-----|-----------|
| A1 | Split the two options files into `plan_overrides` (layer 1) and `preferences` (layer 3) files per level under `jmri/layouts/hart/data/schematic/`; make the spike read them | Agent (Sonnet) | The spike draws the same sheet from the split files |
| A2 | Draw the **baseline**: layers 1 and 2 only. Record every fault and every place the main is not straight; that list is B's work list | Agent (Sonnet) | Baseline SVG and fault list committed beside the sample |
| A3 | Publish the approved sheet as PDF and SVG in `docs/ops/`, marked draft; run `evolution.py` after each committed drawing | Agent (Sonnet) | Files in `docs/ops/`, index rebuilt |
| B1 | Specification: file formats for the three layers, each rule, and golden drawings (baseline and approved sheet) | Main session | Reviewed by the owner |
| B2 | Tested modules in `model-railroad-skills`, with the hint-to-rule changes above and a made-up public example. Only track may be published from the owner's plan, never its custom objects or buildings | Agents (Sonnet); main session reviews the rules | Baseline is clean with no hints; the approved sheet reproduces with layer 3 |
| B3 | Skill text and style reference from `tools/schematic/spike/research/` | Agent (Sonnet) | Marketplace install works on the example |
| C1 | CATS panel for the main and upper levels from the same grid (CATS cell rules are in `research/survey_2.md`); settle east and west by following the main; carry facing and trailing per switch | Main session designs; agent builds | Owner approves the panel in CATS Designer |
| C2 | Station pages and deck track maps | Agents | After B2 |
| D1 | Signals: masts from the Layout Editor panel as layer 1 (`signal_reader.py`), drawn in the NYAMR Physical Characteristics Book style (stem, arm, one circle per head, right-hand side for the direction); labels placed by R12. Done on staging (PR #431, merged into the spike branch 2026-11-13): owner approved the look; label check 0 faults with East Lead 4 cells and South Yard 4 (owner's length change). Same placements to seed CATS signal icons in C1. Still open: labels claiming grid room in the layout (R12), so tight spots need no length preference | Main session | Done for staging; main levels when they have masts |
| C2a | One generated station page (South Yard) from the same grid, compared with the hand-drawn `www/crew/maps/south-yard/` page: what is missing (capacity, spots, west/east arrows) | Agent | Side-by-side for the owner |
| C3 | Layout Editor import of the main levels; switch facts for the new levels | Main session | After the owner's names |

## Other open items

- **B2, model-railroad-skills PR #18 (`plugins/schematic-maps`), merged 2026-11-13.** Reproduces the approved sheet byte for byte from layers 1 to 3 with no hints. R5 and R6 are weighted (`rule_weight` 2) at the owner's request (2026-11-13), so the approved loop entries and peninsula ladder come from the rules; the only `level_leg` pins left are T210 and T212, the owner's free choices. `ladder_link_max_cm` is 40 (60 would turn T143 and T226 into ladders). Layer files on main carry the keys it reads (`source`, `helix_side`, `helix_to`, `level_title`, mast name pattern). Since its review fixes, a mast on a fold stays on its toward end's half, so the planned Princess masts 2035 and 2036 draw near the K-1/K-2 turnback (they stand mid-run on the panel), not mid-half as on the published draft. The spike (PR #423) is closed; the plugin is the tool.
- **Rename East Ext / West Ext, PR #425.** Merged and deployed 2026-11-13; the run's logs in `~/speedmatch-logs/2026-11-13/` are converted (originals in `2026-11-13-before-rename/`).
- **Mast 32L renamed 16R, PR #441.** Hidden S-R east mast; merged and deployed 2026-11-13. `staging.signals.json` regenerated.
- **Spike, PR #423.** Draft; the layer split and baseline (#430) and signals and labels (#431) are merged into its branch after review. Keep as the reference; do not merge as the product. Review findings left for B2 (tested modules): label text measured with a macOS font file (needs a fallback), helix boxes and station brackets drawn after the label placer, the placer's speed, `schem.py`'s single-band entry no longer reads the layered files, run matching by end switches can tie on two stubs off one switch.
- **Owner's names** for the main and upper levels (stations, tracks, switch numbers, level names): pending by the owner's choice.
- **Evolution record.** `~/Documents/Layout/schematic-evolution/` holds every committed drawing and `evolution.gif`; refresh it after each drawing commit.
