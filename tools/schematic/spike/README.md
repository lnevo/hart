# Schematic spike (stage 0)

Proof of the construction in [`wiki/projects/schematic-maps.md`](../../../wiki/projects/schematic-maps.md).
Not tested, not wired into `check.sh`; the tested version goes in `model-railroad-skills`.

    python3 le_reader.py ../../../jmri/layouts/hart/output/tables.xml \
        ../../../jmri/layouts/hart/data/switches.csv ../../../jmri/layouts/hart/data/block_lengths.csv built.json
    python3 schem.py built.json built.svg built_opts.json

`built_sample.svg` is that output for the built staging level, with no hand placement.
`any_reader.py` builds the same logical graph from the AnyRail prototype reader's `parts.json` and `graph.json`.

How `schem.py` works:

1. **Orient.** Each switch faces left or right. Runs that must double back are turnbacks; the choice with the fewest, most U-shaped turnbacks wins.
2. **Sweep.** Walk left to right keeping the tracks in top-to-bottom order, using each switch's hand.
3. **Rows.** Each switch keeps one leg level. Rows are chosen to make the sloped legs as short as possible.
4. **Columns.** Every track gets room for its name; long tracks take up the slack.
5. **Draw.** SVG on a Letter landscape sheet.

`export_reader.py` reads AnyRail's "export to JMRI" XML, which is the better input: it holds the double
crossover and every turnout, and only track. It has no heights; those still come from the `.any` reader.

Staging is now drawn from the AnyRail export too, not from the Layout Editor panel (owner's choice,
2026-11-13): `export_reader.py plan.xml staging.json +Staging parts.json`, then the as-built edits in
`staging.plan_overrides.json` (relabel plan parts to switch numbers, drop the unbuilt crossover T41/T43, add the
Switch 7 crossover, Switch 13 and the engine terminal, name the tracks). Sample: `staging_sample.svg`.
`le_reader.py` and `built_opts.json` remain as a cross-check against the panel.

Inputs are split by kind (stream A1, 2026-11-13) into `jmri/layouts/hart/data/schematic/`:
`<level>.plan_overrides.json` (layer 1, facts about the railroad), `<level>.hints.json` (layer 2, temporary hand
hints that stand in for generation rules not written yet: `level_leg`, `keep_close`) and `<level>.preferences.json`
(layer 3, the owner's look), for `staging` and `main_upper`. `layers.py` merges them; `system.py` reads all three by
default, with `--no-preferences` and `--no-hints`:

    python3 export_reader.py plan53b.xml main.json -Staging parts.json
    python3 export_reader.py plan53b.xml staging.json +Staging parts.json
    python3 system.py staging.json main.json out.svg [--no-preferences] [--no-hints]

(`parts.json` comes from the AnyRail prototype reader over the plan's `.any` file; neither the `.any` file nor its
custom objects are in the repo.) `system_sample.svg` redraws byte-identical from the split files.

`system.py` puts staging, the main level and the upper level on one sheet in route order from the bottom up
(sample in `system_sample.svg`). Each band's helix tracks end in a HELIX box and carry the same track names on
both levels: the main level's helix track from T175 is McKees Rocks and the one from T251 is McKeesport
(owner confirmed, 2026-11-13).

`evolution.py` keeps a folder of every committed version of the sample drawings and an animated GIF of them
(owner's request, 2026-11-13). Run it after each commit that changes a sample:
`.venv/bin/python tools/schematic/spike/evolution.py`. It writes to `~/Documents/Layout/schematic-evolution/`,
outside the repo.

The spike checks its own drawing: every pair of drawn lines is tested for crossing or lying on top of
each other, and each fault is printed with the switches either side.

Main levels (2026-11-13), from the 5.3b export with the owner's as-built change (`main_upper.plan_overrides.json`,
sample in `main_asbuilt_sample.svg`):

| Drawing | Faults |
|---------|--------|
| One flat band | 52 crossings or overlaps, 2 switches whose leg must cross other track, 36 ordering rules dropped |
| Two bands, cut at the rise | 3 crossings on the upper level |
| Two bands, coincident track ends joined, loops ordered by their bend | 0 on both bands |

What fixed it: level bands with lettered connectors; choosing each switch's level leg so no above/below rule
is broken; keeping other track clear of the columns a sloped leg passes through; a double crossover's two
tracks on neighbouring rows; joining track ends the export leaves on the same spot (two pairs in 5.3b, one
of them the main level's balloon loop at T196); stacking a loop's two tracks by which way the loop bends on
the layout; trying the cheapest few fold-back choices and keeping the one that draws with the fewest faults. Two
tracks that never run side by side are kept apart along the row, not stacked on separate rows (this is what
had pushed T155 to the bottom). A long track always gets a level run, so the three parallel tracks west of
T162 and T160 show as three.

Known gaps (end of the 2026-11-13 session):

- **Helix-top switches (owner's layout of the bands, 2026-11-13).** T285 and T251 are drawn on the upper band
  with H2 McKeesport; T199 and T175 on the main level with H1 McKees Rocks. The two crossovers between the
  pairs are the links between the bands: connector B from T199 and connector A from T175. The owner said
  drawing T175 on the main level is optional; it is drawn. The moved T300 is right-hand, found by trial.
- The main level's main route diverges at T187 onto the long track to T153 (not the track through T1 and 12),
  then runs through T160 and T155 round the balloon loop at T196.
- **Spare length (2026-11-13).** Spare length along a band is shared between tracks in proportion to their real
  length (squared stretch), not given whole to the longest. Switches joined by short links move as a block,
  each part of such a group either side of one link can move on its own, and track ends and fold-backs
  travel with the switch they hang off. Hints: `min_cells` (a run at least so long), `shorten`,
  `equal_width`, `band_width`, `band_align`.
- **Rows are stricter than they need to be.** Two tracks are kept on separate rows whenever the working
  order had them open together, even if they end up nowhere near each other along the band. On the upper
  band this stops the helix tracks sitting directly under T300: the peninsula's lower spurs claim those rows
  although they lie further east. The fix is to take the above/below rules only from tracks that really
  overlap along the band. Hints `keep_close`, `level_leg` and `band_cell` (stretch) exist meanwhile.
- **Band direction (owner, 2026-11-13).** The sheet reads main, upper, staging from the top (`band_order`).
  The owner tried the main and upper bands turned 180 degrees (`rotate_bands`, which rotates the finished
  drawing and keeps the lettering upright) and then asked for it undone, so the helix is at the east end of
  all three bands. The owner's note: each level's main is a loop, so the direction flips along it; east and
  west will be worked out later by following the main line, perhaps better on the CATS diagram. ADR-022
  stands until then.
- **Helix marks (owner, 2026-11-13).** A three-turn coil on the track with its letter: H1 McKees Rocks,
  H2 McKeesport, the same on every band (`helix_style` coil; box, letters and arrow remain available).
- A band has no rule for which end is which except `left_end` (staging) and `side` on helix ends (upper).
- Main weight on the upper band follows `main_route`, as the owner gave it (2026-11-13): H2 McKeesport up
  the rise to T262, diverging there onto the outer track round the west balloon loop (T275, T273, T256, T233)
  back to T274 and T237, then T300, the double crossover, round the peninsula loop past T241 and back; and
  H1 McKees Rocks through T175 and T199 to connector A. The T237 to T262 crossover is not main. Routes are
  spelled hop by hop, because the shortest way between two points can cut across a crossover.
- `shorten` draws a named run short (T237 to T300).
- AnyRail's section names (Mainline, Branchline) are layer placeholders (owner, 2026-11-13); band titles are
  the spike's own.
- Labels are not checked for collisions (the connector text can overlap a track); switch numbers collide in
  places; a crossover's number is printed on both halves; no page folding; no capacity.
- Switch labels on the main and upper bands are plan part numbers, three junctions unmatched; no names there.

Signals and labels (2026-11-13, rules R12 and R13 in `docs/ops/SCHEMATIC_SPEC.md`):

    python3 signal_reader.py ../../../jmri/layouts/hart/output/tables.xml ../../../jmri/layouts/hart/data/switches.csv \
        ../../../jmri/layouts/hart/data/block_lengths.csv staging.json \
        ../../../jmri/layouts/hart/data/schematic/staging.plan_overrides.json \
        ../../../jmri/layouts/hart/data/schematic/staging.signals.json
    python3 label_check.py out.svg --list

- `signal_reader.py` writes the masts as layer 1 (`staging.signals.json`), never by hand: each mast bound on the
  Layout Editor panel (turnout leg, anchor or bumper), the run it stands on, the switch or end its move is heading
  for, its direction and head count. Anchor east/west follows JMRI's own rule (`isAtWestEndOfAnchor`). Virtual
  masts are kept in the file and not drawn; `signals_planned` in the overrides marks the Princess placeholders
  (drawn dashed).
- Masts are drawn in the NYAMR Physical Characteristics Book style: stem, short arm, one open circle per head
  pointing the way the mast governs, on the right-hand side of the track for that direction, name beside the stem.
- `labels.py` places switch numbers, track names and mast names: each has a list of allowed positions, and the
  ones with the fewest free positions are placed first, clear of every line, symbol and label. A crossover's
  number prints once. `label_check.py` is the independent check on the finished SVG.
- A mast on a run with no level stretch (32R on the 29-31 ladder link) is drawn along the slope on the right-hand
  side of its move, its name level, in line behind the stem or centred in the gap beside it; the other side of
  the track only when the right-hand side has no room at all.
- `signals_sample.svg`: approved look plus signals. Label faults: approved sheet 17 before the placer; 0 with
  signals, the placer and the owner's length change (East Lead 4 cells, South Yard tracks 6 to 4). The grid-room
  half of R12 (labels claiming room during layout, so no preference is needed) is still to do.
- 32L is named westward but bound eastward on the panel (virtual, so not drawn); reported by the reader.
