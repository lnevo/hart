# Schematic maps: specification (stream B1)

- **Status:** draft for the owner's review, 2026-11-13.
- **Read with:** [`wiki/projects/schematic-maps-handoff.md`](../../wiki/projects/schematic-maps-handoff.md) (the contract) and [`wiki/projects/schematic-maps.md`](../../wiki/projects/schematic-maps.md) (plan).
- **Used by:** B2 (tested modules in `model-railroad-skills`), A1 (file split), C1 (CATS panel from the same grid).

This page fixes three things: the file format of each input layer, each generation rule with how it is tested, and the golden drawings the modules must reproduce.

## What goes in, what comes out

| Step | Input | Output |
|------|-------|--------|
| Read | AnyRail JMRI export (track and switches), `.any` file (heights only) | Track graph JSON |
| Override | Track graph + **layer 1** file | Railroad graph: the layout as built, with names |
| Generate | Railroad graph + **layer 2** rules (code, with a few numbers in a settings block) | Grid: every switch and track in whole cells, per band |
| Prefer | Grid + **layer 3** file (optional) | Adjusted grid |
| Draw | Grid + style | SVG, then PDF |

Every step writes a file the next one reads. Layers 1 and 3 are data files; layer 2 is code. The generic code and the made-up example go in `model-railroad-skills`. The HART files live in `jmri/layouts/hart/data/schematic/`.

**The separation test.** With layer 3 off, layers 1 and 2 must draw every level with no crossings or overlaps, the main straight through every switch on it, and yard ladders stepping diagonally with their tracks level. A hint file is not allowed in the finished tool.

## Layer 1: plan overrides

Facts about the railroad. They override the plan, and every output uses them (schematic, CATS, station pages, Layout Editor). One file per plan group: `staging.plan_overrides.json`, `main.plan_overrides.json`.

```json
{
  "schema": "schematic.plan_overrides/1",
  "plan": "5.3b",
  "levels": {
    "heights": [{"from_cm": 1.5, "to_cm": 5, "set_cm": 10.8, "why": "peninsula top is 4.25 in"}],
    "bands": [{"key": "Main", "below_cm": 5}, {"key": "Upper", "below_cm": 99}]
  },
  "edits": [ ... ],
  "main_route": [ ... ],
  "helix": {"T175": "McKees Rocks", "T251": "McKeesport"},
  "stations": {"Brick": ["1", "3"]},
  "west_end": "W-1"
}
```

**Edits** keep the spike's operations and run in file order:

| `op` | Meaning | Required fields |
|------|---------|-----------------|
| `relabel` | Plan part number to the railroad's switch number; two parts may share a number (a crossover) | `map` |
| `remove` | Not built; the straight route stays as track | `switches` |
| `switch` | Built but not in the plan, with what hangs off its diverging leg | `label`, `hand`, `on`, `cm_from_first`, `points_toward`, `source` |
| `crossover` | Two new switches joined by their diverging legs | `label`, `hand`, `sides`, `source` |
| `move` | Lift a switch out of one run and set it into another | `switch`, `through`, `onto`, `cm_from_first`, `hand`, `source` |
| `name` | Track names, and which runs are main | `tracks` |
| `end` | What a track end is: bumper, helix, open | `ends` |

`source` is new and required on every switch the edits create or move: `le_panel` (the Layout Editor panel in `tables.xml`), `owner` (with a date), or `plan`. A switch with no `hand` is an error, never a trial. Positions along a run come from `block_lengths.csv`; say in `why` when a length is an estimate.

**Main route** is a list of hops, each `[from, to]` or `[from, to, "direct"]`, spelled switch by switch, because the shortest path between two points can cut across a crossover. A helix name is a valid end.

**Levels.** `heights` corrects heights the plan holds wrongly. `bands` names which heights make which level; it is a fact about the railroad, so it sits here and not in the code.

**Signals** are layer 1, generated from the Layout Editor panel, never typed by hand: `staging.signals.json`, one entry per mast.

```json
{"mast": "24RA", "at": {"switch": "23", "leg": "A"}, "dir": "east", "kind": "field", "heads": 2, "source": "le_panel"}
{"mast": "2035", "at": {"run": ["37", "end:K-1"], "cm_from_first": 120}, "dir": "west", "kind": "field", "heads": 1, "source": "le_panel"}
```

`kind` is `field` (a signal on the railroad), `planned` (placeholder masts with no hardware, such as Princess) or `virtual` (masts that exist only for Dispatcher; not drawn). Direction comes from the binding (anchor slot, or the leg a turnout mast stands on), checked against the name's L or R.

Not in layer 1: `flip`, `assign`, band order, widths, nudges, lengths for looks. Those are layer 3.

## Layer 2: generation rules

Each rule has an id used in code, tests and fault messages. "Replaces" names the spike hint the rule makes unnecessary. A rule's test is passed when its choice equals the hint it replaces on the HART golden data, and it draws the made-up example without faults.

| Id | Rule | Replaces | Test |
|----|------|----------|------|
| R1 Bands | One band per level from layer 1 `bands`. A run that joins two levels is cut and drawn as a pair of lettered connectors (A, B, … in the order met along the main route). | `levels.assign` (only for what layer 1 now says) | Every cut run has exactly two connector ends with the same letter |
| R2 Facing and folds | Each switch faces left or right. Runs that must double back are folded; prefer folds that are U-turns on the layout; among the cheapest few choices keep the one that draws with the fewest faults. | — | Staging and main draw with the spike's fold choices |
| R3 Order | Tracks are ordered top to bottom from each switch's hand. A loop's two tracks are stacked by which way the loop bends. Two track ends on the same spot in the export are one track. | — | T196 loop drawn as a loop |
| R4 Double crossover | Its two tracks sit on neighbouring rows. | — | Double crossover at 23 on adjacent rows |
| R5 Main level | Every switch on the main route keeps its main-route leg level. Where the route uses the diverging leg, that leg is level and the straight leg slopes. **Loop exception:** where the main uses both legs (a loop's entry switch, such as T196, T300 and the upper peninsula loop at T239, T241, T253), the leg the main enters the loop by is level and the return is drawn as a fold; the check does not count the return leg. | `level_leg` on the 18 main/upper switches and on staging's main | Chosen leg equals each removed `level_leg` entry; the seven loop-return cases in A2's `baseline_faults.md` (PR #430) pass under the exception |
| R6 Ladder | A ladder is a chain of two or more switches, each joined to the next by a short link (shorter than `ladder_link_max_cm`, default 60), whose other legs start tracks off the main. The yard track leg of each ladder switch is level; the link slopes. The lead into the first switch runs straight into it: that switch's lead-side leg is level. | `level_leg` on 13, 15, 17, 19 | Chosen leg equals the removed entries; S-1 to S-4 drawn level and stepped |
| R7 Rows | Two tracks need separate rows only if their column spans overlap along the band. Tracks that never run side by side may share a row. | `keep_close`; the `shorten` and `min_cells` entries that only fixed row spacing | Upper band: helix tracks sit under T300 with no `keep_close` |
| R8 Length | Spare columns along a band are shared in proportion to real track length. Switches joined by short links move as a block; ends and folds travel with their switch. A long track (over `long_track_cm`, default 100) always gets a level run. A connector gets one short cell. | — | Three parallel tracks west of T162 and T160 show as three |
| R9 Clearance | After placing, test every pair of drawn lines for crossing or lying on top of each other; add clearance and redraw until none do. | — | Zero faults on all golden drawings |
| R10 No trial | Hands and legs of added or moved switches come from layer 1. A missing hand stops the run with an error naming the switch. | Trial of T300's hand | A test file with a missing hand fails with that message |

| R12 Labels | Every label is laid out, not dropped on at drawing time. A label (switch number, track name, connector, helix text, station name, mast name, capacity) has a measured box from the style's font metrics, an anchor (the thing it names) and an ordered list of allowed positions. A switch number may sit above or below, before the points or past the frog, never over track; the open side (away from the diverging leg) comes first, then the position that lines up with neighbours (a ladder's numbers in one line). Labels with the fewest free positions are placed first. When none is free, the label claims grid room and R9 widens the gap, as it does for lines. A crossover or double crossover prints its number once, between its halves. | Hand nudges; the crossover number printed twice | Zero label faults (check 5) on both goldens |
| R13 Signals | Each mast is a layer 1 fact at a switch leg or on a run, with its direction. It is drawn on the leg or run it governs, before the points for a facing move and at the fouling end for a trailing one, on the right-hand side of the track for its direction of travel (east is to the right on every band, ADR-022). The symbol and its name are one label item under R12, so masts claim room and never sit on track or on a switch number. | — | Every field mast in the source is drawn once, on the correct leg and side; zero label faults |

Numbers the rules use (cell size, `ladder_link_max_cm`, `long_track_cm`, label widths) sit in a settings block with defaults. They are tuning, not hints: one value for the whole sheet, never per switch.

Rule gaps carried from the spike, in order of need: three junctions (12, 50, 51) match no plan part; no page folding; no capacity text.

## Layer 3: preferences

The owner's look for one sheet, applied last. With this file absent the sheet must still be correct. One file per sheet: `system.preferences.json`.

| Key | Meaning |
|-----|---------|
| `band_order` | Bands from the top |
| `equal_width`, `band_width`, `band_shift`, `band_align` | Band widths and nudges |
| `rotate_bands` | Bands turned 180 degrees (empty today) |
| `helix_style`, `helix_side` | Coil, box or letters; which end of each band |
| `assign` | Which band draws a switch that could sit on either (T285, T251 on the upper band) |
| `flip` | Draw these switches' diverging side the other way up |
| `min_cells`, `shorten` | Lengths chosen for looks, per run |
| `title`, `system_title`, `num_px`, `style` | Title block text, number size, drafting style |
| `station_brackets` | Draw station brackets under a band |

A preference may only move, stretch or mirror what layer 2 placed. If applying it makes a fault, the run reports the fault and the preference that caused it.

## Golden drawings

Two goldens per level, stored as **fingerprints**, not SVG bytes, so a style change does not break them:

| Golden | Inputs | Must have |
|--------|--------|-----------|
| Baseline | Layers 1 and 2 | Zero faults, R5 and R6 met (after B2; A2's baseline is the starting fault list) |
| Approved | Layers 1, 2 and 3 | Same grid as the owner-approved `system_sample.svg` (PR #423 at 59fb4c6d) |

A fingerprint is JSON: for each switch its band, column, row, facing and level leg; for each track its row and column span; for each connector its letter and both ends. Tests compare fingerprints; a difference prints switch by switch. The SVG goes alongside for the eye.

The made-up example railroad in the plugin has its own baseline golden and must cover: a ladder, a double crossover, a loop, a helix between two levels, a switch added in layer 1, and a not-built switch.

## Checks run every time

1. Every switch, leg and run of the railroad graph appears once in the grid.
2. No two drawn lines cross or overlap unless they cross on the layout.
3. R5: the main is level through every switch on it. R6: yard tracks level in every ladder.
4. Every added or moved switch has a `source`.
5. No label overlaps a drawn line, a symbol or another label; each fault names both items.
6. For HART staging, the railroad graph agrees with `switch_legs.csv` (hands and legs).

## For the owner to decide

- Connector letters: assigned by the rule (order along the main) or kept as a preference (today A at T175, B at T199)?
- Station brackets: shown on staging only, or on every band once the main levels have names?
